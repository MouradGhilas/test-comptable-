#!/usr/bin/env python3
"""Mise à jour de Cabinet Immo, sans perte de données.

Principe : le code et les données vivent dans deux mondes séparés. Une mise à
jour remplace le code, jamais le dossier `donnees/`.

Déroulé :
  1. sauvegarde complète (base + pièces justificatives) ;
  2. copie de sécurité du code actuel, pour pouvoir revenir en arrière ;
  3. remplacement des fichiers de programme par ceux de la nouvelle version ;
  4. migration de la base vers le nouveau schéma ;
  5. vérification ; en cas d'échec, retour automatique à la version précédente.

Utilisation :
    python3 outils/mise_a_jour.py version.zip          depuis une archive
    python3 outils/mise_a_jour.py ancienne.zip \\
            --restaurer donnees/sauvegardes/xxx.zip        retour en arrière
    python3 outils/mise_a_jour.py https://.../maj.zip  depuis un lien
    python3 outils/mise_a_jour.py                      cherche une archive
                                                       dans donnees/maj/
    python3 outils/mise_a_jour.py --annuler            revient en arrière
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

def _racine_cible() -> Path:
    """Dossier de l'installation à mettre à jour.

    Par défaut celui qui contient ce script ; `--vers` permet de viser une
    autre installation, ce qui rend l'outil utilisable depuis l'archive de la
    nouvelle version même si l'ancienne ne l'embarquait pas.
    """
    for index, argument in enumerate(sys.argv):
        if argument == "--vers" and index + 1 < len(sys.argv):
            return Path(sys.argv[index + 1]).expanduser().resolve()
        if argument.startswith("--vers="):
            return Path(argument.split("=", 1)[1]).expanduser().resolve()
    return Path(__file__).resolve().parent.parent


RACINE = _racine_cible()
sys.path.insert(0, str(RACINE))

#: Ce qui appartient à l'utilisateur et ne doit jamais être écrasé.
INTOUCHABLES = {"donnees", "configuration.json", "runtime", ".git"}

#: Ce que contient une version : tout le reste est ignoré.
ELEMENTS_PROGRAMME = ["app.py", "noyau", "modules", "reference", "web", "outils",
                      "README.md", "GUIDE.md", "CHANGELOG.md",
                      "LANCER.bat", "lancer.sh", "INSTALLER.bat"]


# --------------------------------------------------------------- Journal --
#
# Une mise à jour lancée depuis l'interface se déroule sans personne devant
# un terminal : l'application est fermée, il n'y a plus d'écran où écrire.
# Chaque étape est donc consignée dans un fichier que l'application relira
# à sa réouverture, pour dire ce qui s'est passé — succès comme échec.
# Sans cela, un échec est parfaitement silencieux : c'est ce qui donnait
# l'impression que « le bouton ne fait pas grand-chose ».

def _fichier_etat() -> Path:
    from noyau.config import config
    dossier = config.dossier_donnees / "maj"
    dossier.mkdir(parents=True, exist_ok=True)
    return dossier / "etat-maj.json"


#: Les étapes annoncées à l'utilisateur, dans l'ordre où il les verra.
ETAPES_MAJ = [
    ("fermeture", "Fermeture de l'application"),
    ("sauvegarde", "Sauvegarde des données"),
    ("installation", "Installation de la nouvelle version"),
    ("migration", "Mise à niveau de la base"),
    ("verification", "Vérification de la comptabilité"),
    ("relance", "Réouverture de l'application"),
]

_etat_maj = {}


def note_etat(etape_cle="", message="", **complements):
    """Consigne où en est la mise à jour, sans jamais faire échouer celle-ci."""
    import json
    import time
    if etape_cle:
        _etat_maj["etape"] = etape_cle
    if message:
        _etat_maj["message"] = message
    _etat_maj.update(complements)
    _etat_maj["horodatage"] = time.time()
    try:
        _fichier_etat().write_text(
            json.dumps(_etat_maj, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:                                        # noqa: BLE001
        pass    # un journal illisible ne doit pas empêcher la mise à jour


def processus_vivant(pid: int) -> bool:
    """Le processus tourne-t-il encore ? Vrai en cas de doute."""
    import os
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        # 0x400 = PROCESS_QUERY_INFORMATION ; un handle nul signifie que le
        # processus a disparu (ou qu'il est inaccessible, cas où l'on
        # préfère patienter plutôt que d'écrire sous ses pieds).
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.windll.kernel32.GetLastError() != 87   # 87 = pid inconnu
        sortie = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(sortie))
        ctypes.windll.kernel32.CloseHandle(handle)
        return sortie.value == 259                               # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # Un processus terminé mais pas encore récupéré par son parent (zombie)
    # existe toujours pour os.kill : sans ce contrôle, l'attente durerait
    # jusqu'à sa limite. Sous Linux, l'état 'Z' de /proc tranche.
    try:
        with open(f"/proc/{pid}/stat", encoding="ascii", errors="replace") as f:
            etat = f.read().rsplit(")", 1)[1].split()[0]
        if etat == "Z":
            return False
    except (OSError, IndexError):
        pass    # pas de /proc (autre système) : os.kill fait foi
    return True


def port_repond(port: int) -> bool:
    """L'application écoute-t-elle encore ?

    Contrôle bien plus sûr que l'existence du processus : un identifiant peut
    être réattribué, et sous Windows l'interrogation peut échouer pour
    d'autres raisons qu'une fermeture. Tant que le port répond, quelqu'un
    sert l'application — et remplacer ses fichiers sous ses pieds la laisse
    dans un état mixte : interface neuve, moteur ancien.
    """
    if not port:
        return False
    import socket
    with socket.socket() as s:
        s.settimeout(0.6)
        try:
            return s.connect_ex(("127.0.0.1", int(port))) == 0
        except OSError:
            return False


def attend_fermeture(pid: int, limite: float = 180.0, port: int = 0) -> bool:
    """Patiente jusqu'à ce que l'application ait vraiment rendu ses fichiers.

    Un simple délai fixe ne suffit pas : à la fermeture, l'application écrit
    une sauvegarde dont la durée dépend du volume de pièces justificatives.
    Commencer à remplacer les fichiers pendant ce temps, c'est courir après
    un « fichier en cours d'utilisation » sous Windows — et un échec de mise
    à jour parfaitement silencieux.
    """
    import time
    if pid <= 0:
        time.sleep(3.0)
        return True
    debut = time.monotonic()
    while time.monotonic() - debut < limite:
        if not processus_vivant(pid) and not port_repond(port):
            time.sleep(0.7)     # laisser le système libérer les descripteurs
            return True
        note_etat("fermeture",
                  "L'application termine sa fermeture "
                  f"({int(time.monotonic() - debut)} s).")
        time.sleep(0.5)
    return False


def titre(texte):
    print(f"\n\033[1m{texte}\033[0m")


def etape(texte):
    print(f"  → {texte}")


def succes(texte):
    print(f"  \033[32m✓\033[0m {texte}")


def echec(texte):
    print(f"  \033[31m✗\033[0m {texte}")


def dossier_sauvegarde_code() -> Path:
    return RACINE / "donnees" / "version_precedente"


def trouve_archive(argument: str | None) -> Path:
    """Localise l'archive de mise à jour : chemin, lien, ou dossier maj/."""
    if argument and argument.startswith(("http://", "https://")):
        etape(f"Téléchargement depuis {argument}")
        cible = Path(tempfile.gettempdir()) / "cabinet_immo_maj.zip"
        with urllib.request.urlopen(argument, timeout=120) as source, \
                open(cible, "wb") as destination:
            shutil.copyfileobj(source, destination)
        succes(f"Archive téléchargée ({cible.stat().st_size // 1024} Ko)")
        return cible

    if argument:
        chemin = Path(argument).expanduser().resolve()
        if not chemin.is_file():
            raise SystemExit(f"Archive introuvable : {chemin}")
        return chemin

    dossier = RACINE / "donnees" / "maj"
    dossier.mkdir(parents=True, exist_ok=True)
    archives = sorted(dossier.glob("*.zip"), key=lambda p: p.stat().st_mtime,
                      reverse=True)
    if not archives:
        raise SystemExit(
            f"Aucune archive trouvée.\n"
            f"Déposez le fichier .zip de la nouvelle version dans :\n  {dossier}\n"
            "puis relancez la mise à jour."
        )
    etape(f"Archive trouvée : {archives[0].name}")
    return archives[0]


def racine_dans_archive(zf: zipfile.ZipFile) -> str:
    """Une archive peut contenir un dossier racine (cabinet-immo/…) ou non."""
    noms = [n for n in zf.namelist() if not n.startswith("__MACOSX")]
    if any(n in ("app.py", "./app.py") for n in noms):
        return ""
    premiers = {n.split("/")[0] for n in noms if "/" in n}
    for candidat in premiers:
        if f"{candidat}/app.py" in noms:
            return candidat + "/"
    raise SystemExit(
        "Cette archive ne ressemble pas à une version de Cabinet Immo "
        "(app.py est introuvable)."
    )


def dossier_donnees() -> Path:
    try:
        from noyau.config import config
        return Path(config.dossier_donnees)
    except Exception:                                        # noqa: BLE001
        return RACINE / "donnees"


def archive_version(version: str) -> Path | None:
    """Range le programme en place dans la bibliothèque des versions.

    Un paquet reçu par messagerie n'existe qu'une fois. S'il n'est pas
    conservé, la version qu'il installe devient la seule possible : revenir
    en arrière supposerait de le redemander à quelqu'un. On garde donc une
    copie de ce qui était là avant de le remplacer.
    """
    dossier = dossier_donnees() / "versions"
    propre = "".join(c for c in str(version) if c.isalnum() or c in "._-") or "inconnue"
    cible = dossier / f"cabinet-immo-{propre}.zip"
    if cible.exists() and cible.stat().st_size > 0:
        return cible
    try:
        dossier.mkdir(parents=True, exist_ok=True)
        temporaire = cible.with_suffix(".zip.partiel")
        with zipfile.ZipFile(temporaire, "w", zipfile.ZIP_DEFLATED) as archive:
            for nom in ELEMENTS_PROGRAMME:
                source = RACINE / nom
                if not source.exists():
                    continue
                if source.is_file():
                    archive.write(source, nom)
                    continue
                for fichier in source.rglob("*"):
                    if not fichier.is_file() or "__pycache__" in fichier.parts:
                        continue
                    archive.write(fichier,
                                  str(fichier.relative_to(RACINE)).replace("\\", "/"))
        temporaire.replace(cible)
        return cible
    except OSError:
        return None


def restaure_donnees(archive: Path) -> None:
    """Remet la comptabilité telle qu'une sauvegarde l'a figée.

    Nécessaire pour revenir à une version antérieure au schéma de la base :
    le programme sait reculer, la base non — elle ne défait pas ses
    migrations. Écrit ici plutôt qu'appelé dans `modules/` : à cet instant
    précis, les fichiers du programme sont en train d'être remplacés.
    """
    from noyau.config import config
    config.prepare_dossiers()
    with zipfile.ZipFile(archive) as zf:
        noms = zf.namelist()
        if "comptabilite.db" not in noms:
            raise RuntimeError(
                "cette sauvegarde ne contient pas de base de données")
        with zf.open("comptabilite.db") as source, \
                open(config.base_de_donnees, "wb") as destination:
            shutil.copyfileobj(source, destination)
        for interne in noms:
            if interne.startswith("pieces_justificatives/") and not interne.endswith("/"):
                cible = config.dossier_donnees / interne
                cible.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(interne) as source, open(cible, "wb") as destination:
                    shutil.copyfileobj(source, destination)
    # Le journal d'écriture de l'ancienne base n'a plus rien à voir avec celle
    # qu'on vient de poser : le laisser reviendrait à mélanger les deux.
    for suffixe in ("-wal", "-shm"):
        Path(str(config.base_de_donnees) + suffixe).unlink(missing_ok=True)


def version_de_archive(archive: Path) -> str:
    """Le numéro de version que porte le paquet, sans rien installer."""
    try:
        with zipfile.ZipFile(archive) as zf:
            prefixe = racine_dans_archive(zf)
            source = zf.read(prefixe + "noyau/config.py").decode("utf-8")
    except Exception:                                        # noqa: BLE001
        return ""
    trouve = re.search(r'^VERSION\s*=\s*["\']([^"\']+)["\']', source, re.M)
    return trouve.group(1) if trouve else ""


def en_tuple(texte: str) -> tuple:
    morceaux = []
    for bout in str(texte or "").split("."):
        chiffres = "".join(c for c in bout if c.isdigit())
        morceaux.append(int(chiffres) if chiffres else 0)
    return tuple(morceaux)


def sauvegarde_code() -> Path:
    """Met le code actuel de côté pour permettre un retour en arrière."""
    cible = dossier_sauvegarde_code()
    if cible.exists():
        shutil.rmtree(cible)
    cible.mkdir(parents=True)
    for nom in ELEMENTS_PROGRAMME:
        source = RACINE / nom
        if not source.exists():
            continue
        if source.is_dir():
            shutil.copytree(source, cible / nom)
        else:
            shutil.copy2(source, cible / nom)
    return cible


def restaure_code() -> bool:
    source = dossier_sauvegarde_code()
    if not source.exists():
        return False
    for element in source.iterdir():
        cible = RACINE / element.name
        if cible.is_dir():
            shutil.rmtree(cible)
        elif cible.exists():
            cible.unlink()
        if element.is_dir():
            shutil.copytree(element, cible)
        else:
            shutil.copy2(element, cible)
    return True


def purge_bytecode() -> int:
    """Supprime les dossiers __pycache__ de l'installation.

    Python valide son bytecode sur la taille du source et son horodatage
    **à la seconde près**. Deux versions dont le fichier fait la même taille,
    remplacées dans la même seconde, laissent le cache passer pour valide :
    l'application continuerait alors d'exécuter l'ancien code tout en
    affichant le nouveau numéro de version. Le cas s'est produit.
    """
    supprimes = 0
    for cache in RACINE.rglob("__pycache__"):
        if "donnees" in cache.parts:
            continue
        shutil.rmtree(cache, ignore_errors=True)
        supprimes += 1
    return supprimes


def applique_archive(archive: Path) -> int:
    fichiers = 0
    with zipfile.ZipFile(archive) as zf:
        prefixe = racine_dans_archive(zf)
        for interne in zf.namelist():
            if interne.endswith("/") or interne.startswith("__MACOSX"):
                continue
            if prefixe and not interne.startswith(prefixe):
                continue
            relatif = interne[len(prefixe):]
            if not relatif:
                continue
            premier = relatif.split("/")[0]
            if premier in INTOUCHABLES:
                continue
            cible = (RACINE / relatif).resolve()
            try:
                cible.relative_to(RACINE)
            except ValueError:
                continue                      # chemin sortant de l'application
            cible.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(interne) as source, open(cible, "wb") as destination:
                shutil.copyfileobj(source, destination)
            fichiers += 1
    return fichiers


def version_installee() -> str:
    try:
        from noyau.config import VERSION
        return VERSION
    except Exception:                                        # noqa: BLE001
        return "inconnue"


def abandonne(arguments, etape_cle: str, message: str) -> int:
    """Consigne un échec et rouvre la version restaurée si besoin.

    Après l'attente du PID, l'application est déjà fermée : un échec qui se
    contenterait de « return 1 » laisserait l'utilisateur devant une fenêtre
    close, sans rien réouvrir. On rouvre donc la version précédente — elle
    vient d'être remise en place — pour qu'il retrouve son écran et le compte
    rendu de ce qui s'est passé.
    """
    note_etat(etape_cle, ok=False, message=message)
    echec(message)
    if arguments.relancer:
        relance_application(arguments.relancer_options)
    return 1


def sortie_utf8() -> None:
    """Rend l'affichage insensible à la page de codes de Windows.

    Une console française hérite de cp1252, et un fichier ouvert par un
    processus fils aussi : le moindre « → » ou « ═ » y lève alors
    UnicodeEncodeError. Comme la toute première ligne affichée par cet outil
    contenait un cadre en caractères semi-graphiques, la mise à jour mourait
    avant même de commencer — sans rien installer, et sans rien dire quand la
    sortie partait au néant.

    On force donc l'UTF-8, avec `errors="replace"` en garde-fou : un
    caractère manquant doit dégrader l'affichage, jamais interrompre une
    mise à jour. Défini sur place, sans import : ce fichier doit tenir même
    quand le reste du programme vient d'être remplacé.
    """
    import sys
    for flux in (sys.stdout, sys.stderr):
        # pythonw.exe ne fournit aucun flux : il n'y a alors rien à régler.
        if flux is None:
            continue
        try:
            flux.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass    # flux exotique : on continue, quitte à perdre un accent


def principal() -> int:
    sortie_utf8()
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("archive", nargs="?", help="fichier .zip ou lien")
    analyseur.add_argument("--annuler", action="store_true",
                           help="revenir à la version précédente")
    analyseur.add_argument("--sans-sauvegarde", action="store_true",
                           help="ne pas créer de sauvegarde préalable (déconseillé)")
    analyseur.add_argument("--restaurer", metavar="SAUVEGARDE",
                           help="remettre aussi les données de cette sauvegarde "
                                "(retour à une version antérieure au schéma "
                                "de la base)")
    analyseur.add_argument("--vers", metavar="DOSSIER",
                           help="installation à mettre à jour (défaut : celle-ci)")
    analyseur.add_argument("--donnees", metavar="DOSSIER",
                           help="dossier de données de cette installation "
                                "(défaut : celui de la configuration)")
    analyseur.add_argument("--auto", action="store_true",
                           help="ne rien demander : en cas de doute, renoncer")
    analyseur.add_argument("--attendre", type=float, default=0, metavar="SECONDES",
                           help="patienter avant de commencer (le temps que "
                                "l'application se ferme)")
    analyseur.add_argument("--attendre-port", type=int, default=0, metavar="PORT",
                           help="attendre aussi que ce port ne réponde plus")
    analyseur.add_argument("--attendre-pid", type=int, default=0, metavar="PID",
                           help="attendre la fermeture réelle de ce processus "
                                "plutôt qu'un délai fixe")
    analyseur.add_argument("--relancer", action="store_true",
                           help="rouvrir l'application une fois la mise à jour faite")
    analyseur.add_argument("--relancer-options", default="", metavar="JSON",
                           help="options de lancement à rejouer (port, dossier "
                                "de données…), au format JSON")
    arguments = analyseur.parse_args()

    # L'application peut tourner sur un dossier de données choisi à la main
    # (`--donnees`, une clé USB, un second dossier d'essai). L'outil, lancé à
    # part, ne le devinait pas : il sauvegardait, migrait et vérifiait le
    # dossier par défaut — c'est-à-dire pas celui de l'utilisateur. Posé ici,
    # avant tout accès à la configuration.
    if arguments.donnees:
        import os as _os
        _os.environ["CABINET_IMMO_DONNEES"] = str(
            Path(arguments.donnees).expanduser().resolve())

    if arguments.attendre_pid:
        note_etat("fermeture", "L'application se ferme.", ok=None,
                  demarre_a=__import__("time").time())
        if not attend_fermeture(arguments.attendre_pid,
                                port=arguments.attendre_port):
            note_etat("fermeture", ok=False, message=(
                "L'application ne s'est pas fermée. Rien n'a été touché : "
                "fermez-la puis relancez la mise à jour."))
            echec("L'application ne s'est pas fermée ; mise à jour abandonnée.")
            return 1
    elif arguments.attendre:
        import time
        time.sleep(arguments.attendre)

    print("\n\033[1m═══ MISE À JOUR DE CABINET IMMO ═══\033[0m")
    print(f"Dossier : {RACINE}")

    if arguments.annuler:
        titre("Retour à la version précédente")
        if restaure_code():
            succes("Code restauré. Relancez l'application.")
            return 0
        echec("Aucune version précédente enregistrée.")
        return 1

    ancienne_version = version_installee()
    note_etat(version_avant=ancienne_version)
    archive = trouve_archive(arguments.archive)
    version_visee = version_de_archive(archive)
    retour = bool(version_visee) and en_tuple(version_visee) < en_tuple(ancienne_version)
    if retour:
        print(f"  Retour en arrière : {ancienne_version} → {version_visee}")

    # 1. Sauvegarde des données -------------------------------------------
    filet = None
    if not arguments.sans_sauvegarde:
        titre("1. Sauvegarde des données")
        note_etat("sauvegarde", "Sauvegarde des données avant toute chose.")
        try:
            from modules.fichiers import cree_sauvegarde
            from noyau import base as db
            db.initialise()
            filet = cree_sauvegarde("avant_retour" if retour else "avant_mise_a_jour")
            db.ferme()
            succes(f"Sauvegarde créée : {filet.name}")
        except Exception as err:                             # noqa: BLE001
            echec(f"Sauvegarde impossible : {err}")
            if arguments.auto:
                # Sans personne devant l'écran, on renonce plutôt que de
                # toucher au programme sans filet.
                return abandonne(arguments, "sauvegarde",
                    f"Sauvegarde impossible ({err}). Rien n'a été touché.")
            reponse = input("  Continuer sans sauvegarde ? (o/N) ").strip().lower()
            if reponse not in ("o", "oui", "y"):
                return 1

    # 1 bis. Retour des données -------------------------------------------
    #
    # Une version antérieure au schéma de la base ne sait pas l'ouvrir : elle
    # refuse même de démarrer, et la mise à jour se solderait par un retour
    # automatique à celle qu'on voulait quitter. Les données reviennent donc
    # avec le programme — c'est demandé explicitement, jamais deviné.
    donnees_remises = False
    if arguments.restaurer:
        titre("1 bis. Retour des données à l'état de cette version")
        note_etat("sauvegarde", "Retour des données à l'état d'alors.")
        source = Path(arguments.restaurer).expanduser()
        try:
            if not source.is_file():
                raise RuntimeError(f"sauvegarde introuvable : {source}")
            restaure_donnees(source)
            donnees_remises = True
            succes(f"Données remises dans l'état de {source.name}")
        except Exception as err:                             # noqa: BLE001
            echec(f"Restauration impossible : {err}")
            return abandonne(arguments, "sauvegarde",
                f"Impossible de remettre les données ({err}). Rien n'a été "
                f"touché : vous êtes toujours en version {ancienne_version}.")

    # 2. Copie du code actuel ---------------------------------------------
    titre("2. Mise de côté de la version actuelle")
    note_etat("installation", "Mise de côté de la version actuelle.")
    sauvegarde_code()
    rangee = archive_version(ancienne_version)
    succes(f"Version {ancienne_version} conservée "
           f"(revenir en arrière : mise_a_jour.py --annuler)")
    if rangee:
        succes(f"Version {ancienne_version} rangée dans la bibliothèque "
               f"({rangee.name}) : on pourra y revenir depuis l'application")

    def remet_les_donnees() -> str:
        """Après un échec, la comptabilité doit repartir comme elle était.

        Sans cela, un retour raté laisserait le programme d'origine devant
        des données vieillies : le pire des deux mondes.
        """
        if not donnees_remises or not filet:
            return ""
        try:
            restaure_donnees(Path(filet))
            succes("Données remises telles qu'elles étaient avant l'opération.")
            return " Vos données ont été remises comme elles étaient."
        except Exception as err:                             # noqa: BLE001
            echec(f"Les données n'ont pas pu être remises : {err}")
            return (f" ATTENTION : les données sont restées dans l'état de "
                    f"{Path(arguments.restaurer).name} ; restaurez "
                    f"{Path(filet).name} depuis l'écran Sauvegardes.")

    # 3. Remplacement du code ---------------------------------------------
    titre("3. Installation de la nouvelle version")
    try:
        fichiers = applique_archive(archive)
        succes(f"{fichiers} fichier(s) de programme mis à jour")
        caches = purge_bytecode()
        if caches:
            succes(f"{caches} cache(s) de bytecode purgé(s)")
    except Exception as err:                                 # noqa: BLE001
        echec(f"Installation impossible : {err}")
        restaure_code()
        succes("Version précédente restaurée.")
        return abandonne(arguments, "installation",
            f"Installation impossible ({err}). La version {ancienne_version} "
            "a été remise en place et vos données sont intactes."
            + remet_les_donnees())

    # 4. Migration de la base ---------------------------------------------
    titre("4. Mise à niveau de la base de données")
    note_etat("migration", "Mise à niveau de la base de données.")
    for module in [m for m in list(sys.modules) if m.startswith(("noyau", "modules"))]:
        del sys.modules[module]
    try:
        from noyau import base as db
        rapport = db.initialise()
        if rapport["migrations"]:
            succes(f"Migrations appliquées : {rapport['migrations']} "
                   f"(schéma v{rapport['version_arrivee']})")
        else:
            succes(f"Schéma déjà à jour (v{rapport['version_arrivee']})")
        if rapport["sauvegarde"]:
            print(f"      copie préalable : {rapport['sauvegarde']}")
    except Exception as err:                                 # noqa: BLE001
        echec(f"Migration impossible : {err}")
        restaure_code()
        succes("Version précédente restaurée. Vos données sont intactes.")
        # Le cas courant, quand on recule : la base a été migrée par une
        # version plus récente et l'ancienne ne sait pas la lire. Le dire.
        explication = (
            f" La version {version_visee} est antérieure à la structure "
            "actuelle de votre base : pour y revenir, il faut aussi remettre "
            "les données de l'époque. L'écran « Mise à jour » le propose et "
            "vous laisse choisir la sauvegarde."
            if retour and not donnees_remises else "")
        return abandonne(arguments, "migration",
            f"Mise à niveau de la base impossible ({err}). La version "
            f"{ancienne_version} a été remise en place et vos données sont "
            "intactes." + explication + remet_les_donnees())

    # 5. Vérification ------------------------------------------------------
    titre("5. Vérification")
    note_etat("verification", "Vérification de la comptabilité.")
    try:
        integrite = db.valeur("PRAGMA integrity_check", (), "?")
        desequilibrees = db.lignes(
            "SELECT e.id FROM ecritures e LEFT JOIN lignes l ON l.ecriture_id = e.id "
            "GROUP BY e.id HAVING COALESCE(SUM(l.debit),0) <> COALESCE(SUM(l.credit),0)")
        ecritures = db.valeur("SELECT COUNT(*) FROM ecritures", (), 0)
        db.ferme()

        if integrite != "ok" or desequilibrees:
            echec(f"Contrôle négatif (intégrité : {integrite}, "
                  f"{len(desequilibrees)} écriture(s) déséquilibrée(s))")
            restaure_code()
            return abandonne(arguments, "verification",
                "Contrôle de la comptabilité négatif après mise à jour. La "
                f"version {ancienne_version} a été remise en place."
                + remet_les_donnees())
        succes(f"Base saine — {ecritures} écriture(s), comptabilité équilibrée")
    except Exception as err:                                 # noqa: BLE001
        echec(f"Vérification impossible : {err}")
        restaure_code()
        return abandonne(arguments, "verification",
            f"Vérification impossible ({err}). La version {ancienne_version} "
            "a été remise en place." + remet_les_donnees())

    nouvelle_version = version_installee()
    intitule = "Retour terminé" if retour else "Mise à jour terminée"
    sort_des_donnees = (
        f"Vos données ont été remises dans l'état de {Path(arguments.restaurer).name}."
        if donnees_remises else "Vos données n'ont pas été touchées.")
    print()
    print("=" * 68)
    print(f"  {intitule} : version {ancienne_version} → {nouvelle_version}")
    print(f"  {sort_des_donnees}")
    if donnees_remises and filet:
        print(f"  L'état d'avant reste disponible : {Path(filet).name}")
    if not arguments.relancer:
        print("  Relancez l'application (raccourci « Cabinet Immo »).")
    print("=" * 68)

    note_etat("relance", version_apres=nouvelle_version, ok=True, message=(
        f"{intitule} : version {ancienne_version} → {nouvelle_version}. "
        + sort_des_donnees
        + (f" L'état d'avant reste disponible : {Path(filet).name}."
           if donnees_remises and filet else "")))

    if arguments.relancer:
        relance_application(arguments.relancer_options)
    note_etat("termine")
    return 0


def _options_detachement() -> dict:
    """Arguments Popen pour un processus qui doit survivre à l'outil.

    Sous Windows, `start_new_session` est ignoré (subprocess le nomme
    `unused_start_new_session`) : sans détachement explicite, la nouvelle
    application reste rattachée à la console qui a lancé l'ancienne, et un
    Ctrl+C ou la fermeture de cette fenêtre la tuerait. Défini ici, en dur,
    pour ne dépendre d'aucun fichier que la mise à jour vient de remplacer.
    """
    import os
    import subprocess
    if os.name != "nt":
        return {"start_new_session": True}
    detache = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
    nouveau_groupe = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    return {"creationflags": detache | nouveau_groupe, "close_fds": True}


def relance_application(options_json: str = "") -> None:
    """Rouvre l'application après une mise à jour lancée depuis l'interface.

    Sans cela, l'utilisateur verrait sa fenêtre se fermer et devrait
    comprendre qu'il lui faut rouvrir le raccourci.

    Les options du lancement d'origine sont rejouées. Sans elles, une
    installation démarrée sur un autre port, ou sur un dossier de données
    déplacé — une clé USB, par exemple — rouvrirait sur les valeurs par
    défaut, donc sur la mauvaise comptabilité.
    """
    import json
    import subprocess
    options = []
    if options_json:
        try:
            options = [str(o) for o in json.loads(options_json)]
        except ValueError:
            echec("Options de relance illisibles : valeurs par défaut utilisées.")
    executable = sys.executable
    # pythonw.exe évite de rouvrir une fenêtre noire sous Windows.
    sans_console = Path(executable).with_name("pythonw.exe")
    if sans_console.exists():
        executable = str(sans_console)
    try:
        subprocess.Popen([executable, str(RACINE / "app.py"), *options],
                         cwd=str(RACINE), **_options_detachement())
        detail = f" ({' '.join(options)})" if options else ""
        print(f"  Application relancée{detail}.")
        note_etat(relance=True)
    except OSError as err:
        echec(f"Relance impossible ({err}). Rouvrez le raccourci « Cabinet Immo ».")
        note_etat(relance=False, message=(
            "La mise à jour est faite, mais l'application n'a pas pu être "
            "rouverte automatiquement. Ouvrez le raccourci « Cabinet Immo » : "
            "la nouvelle version est en place et vos données sont intactes."))


if __name__ == "__main__":
    raise SystemExit(principal())
