"""Mise à jour depuis l'application.

Jusqu'ici, mettre à jour demandait cinq gestes techniques : recevoir un zip,
le retrouver, créer `donnees\\maj\\`, l'y déposer, lancer un `.bat`. Dans les
faits, l'utilisateur ne les faisait pas — trois versions de corrections ne lui
sont jamais parvenues.

Ici, il dépose le fichier dans l'application. Le paquet est **contrôlé avant
d'être appliqué** : c'est bien une version de Cabinet Immo, elle est plus
récente que celle installée, et l'archive est complète.

L'application elle-même ne remplace jamais son propre code : elle confie le
travail à `outils/mise_a_jour.py`, lancé à part, qui sauvegarde, applique,
migre, vérifie et **revient en arrière seul en cas d'échec**. L'application se
ferme le temps de l'opération, puis est rouverte par l'outil.
"""

from __future__ import annotations

import base64
import json
import io
import os
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

from noyau import base as db
from noyau import serveur as mod_serveur
from noyau import util
from noyau.config import config, APPLICATION, VERSION, RACINE
from noyau.serveur import ErreurApplicative, route
from noyau.util import options_detachement

TAILLE_MAX = 64 * 1024 * 1024

#: Ce qu'une archive doit contenir pour être une version de Cabinet Immo.
FICHIERS_ATTENDUS = ("app.py", "noyau/config.py", "noyau/base.py",
                     "noyau/schema.sql", "modules/comptabilite.py")

#: Délai annoncé à l'interface. L'outil, lui, attend la fermeture réelle de
#: l'application : un délai fixe se fait rattraper par la sauvegarde d'arrêt
#: dès que le dossier de pièces justificatives grossit.
DELAI_FERMETURE = 3.0

#: Les étapes annoncées pendant l'attente, dans l'ordre. Elles doivent rester
#: identiques à ETAPES_MAJ de outils/mise_a_jour.py.
ETAPES_MAJ = [
    ("fermeture", "Fermeture de l'application"),
    ("sauvegarde", "Sauvegarde des données"),
    ("installation", "Installation de la nouvelle version"),
    ("migration", "Mise à niveau de la base"),
    ("verification", "Vérification de la comptabilité"),
    ("relance", "Réouverture de l'application"),
]


def _fichier_etat() -> Path:
    return config.dossier_donnees / "maj" / "etat-maj.json"


def _prepare_etat(version_visee: str) -> None:
    """Pose un état de départ, pour qu'une mise à jour qui échoue avant même
    d'avoir démarré ne laisse pas l'écran précédent faire illusion."""
    try:
        _fichier_etat().write_text(json.dumps({
            "etape": "fermeture",
            "message": "L'application se ferme pour laisser la place.",
            "version_avant": VERSION,
            "version_visee": version_visee,
            "horodatage": time.time(),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def lit_etat_maj() -> dict | None:
    """Ce que la dernière mise à jour a fait, tel que l'outil l'a consigné."""
    fichier = _fichier_etat()
    try:
        etat = json.loads(fichier.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(etat, dict):
        return None
    etat["etapes"] = [{"cle": cle, "libelle": libelle} for cle, libelle in ETAPES_MAJ]
    etat["version_actuelle"] = VERSION
    # Une mise à jour réussie se reconnaît à la version qui a bougé, pas
    # seulement au drapeau : c'est la version installée qui fait foi.
    if etat.get("ok") is None and etat.get("version_visee"):
        etat["ok"] = VERSION == etat["version_visee"] or None
    journal = config.dossier_donnees / "maj" / "journal-maj.txt"
    if journal.is_file():
        try:
            etat["journal"] = journal.read_text(encoding="utf-8", errors="replace")[-8000:]
        except OSError:
            pass
    return etat


@route("GET", "/api/maj/resultat")
def api_resultat(ctx):
    """Ce qu'a donné la dernière mise à jour lancée depuis l'application.

    L'application est fermée pendant l'opération : il n'y a aucun moyen de
    suivre les étapes en direct. Elle relit donc, à sa réouverture, ce que
    l'outil a consigné — succès comme échec, avec la raison.
    """
    ctx.exige_role("admin")
    etat = lit_etat_maj()
    if not etat:
        return {"present": False}
    etat["present"] = True
    return etat


def version_en_tuple(texte: str) -> tuple:
    """« 1.4.10 » -> (1, 4, 10), pour comparer autrement qu'alphabétiquement."""
    morceaux = []
    for bout in str(texte or "").split("."):
        chiffres = "".join(c for c in bout if c.isdigit())
        morceaux.append(int(chiffres) if chiffres else 0)
    return tuple(morceaux)


def racine_dans_archive(noms: list[str]) -> str | None:
    """Une archive peut contenir un dossier racine (cabinet-immo/…) ou non."""
    utiles = [n for n in noms if not n.startswith("__MACOSX")]
    if any(n in ("app.py", "./app.py") for n in utiles):
        return ""
    for candidat in {n.split("/")[0] for n in utiles if "/" in n}:
        if f"{candidat}/app.py" in utiles:
            return candidat + "/"
    return None


def inspecte_paquet(octets: bytes) -> dict:
    """Dit ce que contient l'archive déposée, sans rien installer."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(octets))
    except zipfile.BadZipFile as err:
        raise ErreurApplicative(
            "Ce fichier n'est pas une archive lisible. Vérifiez qu'il n'a pas "
            f"été tronqué pendant l'envoi. Détail : {err}") from err

    noms = archive.namelist()
    prefixe = racine_dans_archive(noms)
    if prefixe is None:
        raise ErreurApplicative(
            f"Ce fichier n'est pas une version de {APPLICATION} : le programme "
            "y est introuvable. Vérifiez que c'est bien le fichier reçu pour "
            "la mise à jour.")

    manquants = [f for f in FICHIERS_ATTENDUS if prefixe + f not in noms]
    if manquants:
        raise ErreurApplicative(
            "Cette archive est incomplète : il y manque "
            f"{', '.join(manquants)}. Redemandez le fichier, il a sans doute "
            "été abîmé pendant l'envoi.")

    try:
        source = archive.read(prefixe + "noyau/config.py").decode("utf-8")
    except (KeyError, UnicodeDecodeError) as err:
        raise ErreurApplicative(f"Version illisible dans l'archive : {err}") from err
    trouve = re.search(r'^VERSION\s*=\s*["\']([^"\']+)["\']', source, re.M)
    if not trouve:
        raise ErreurApplicative(
            "Impossible de lire le numéro de version de cette archive.")
    version = trouve.group(1)

    changelog = ""
    for nom in (prefixe + "CHANGELOG.md", prefixe + "CHANGELOG.txt"):
        if nom in noms:
            changelog = archive.read(nom).decode("utf-8", errors="replace")
            break

    return {
        "version": version,
        "version_installee": VERSION,
        "fichiers": sum(1 for n in noms if not n.endswith("/")),
        "changelog": extrait_changelog(changelog, version, VERSION),
        "plus_recente": version_en_tuple(version) > version_en_tuple(VERSION),
        "identique": version_en_tuple(version) == version_en_tuple(VERSION),
    }


def extrait_changelog(texte: str, jusqua: str, depuis: str) -> str:
    """Ne garde que les versions comprises entre celle installée et la nouvelle.

    L'utilisateur veut savoir ce que la mise à jour lui apporte, pas relire
    l'historique complet du logiciel.
    """
    if not texte:
        return ""
    sections = re.split(r"^##\s+", texte, flags=re.M)
    retenues = []
    for section in sections[1:]:
        titre = section.splitlines()[0].strip()
        numero = re.search(r"(\d+(?:\.\d+)*)", titre)
        if not numero:
            continue
        valeur = version_en_tuple(numero.group(1))
        if version_en_tuple(depuis) < valeur <= version_en_tuple(jusqua):
            retenues.append("## " + section.rstrip())
    return "\n\n".join(retenues) or texte.strip()


def _decode(ctx) -> bytes:
    contenu = ctx.champ_requis("contenu")
    if contenu.startswith("data:") and "," in contenu[:120]:
        contenu = contenu.split(",", 1)[1]
    try:
        octets = base64.b64decode(contenu, validate=True)
    except Exception as err:                                  # noqa: BLE001
        raise ErreurApplicative(f"Fichier illisible : {err}") from err
    if len(octets) > TAILLE_MAX:
        raise ErreurApplicative("Fichier trop volumineux (64 Mio maximum).", 413)
    return octets


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@route("GET", "/api/maj/etat")
def api_etat(ctx):
    """De quoi afficher la carte « Mettre à jour » sans rien déposer."""
    ctx.exige_role("admin", "comptable")
    notes = RACINE / "CHANGELOG.md"
    return {
        "version": VERSION,
        "application": APPLICATION,
        "url_versions": config.get("url_versions", ""),
        "changelog": (notes.read_text(encoding="utf-8", errors="replace")
                      if notes.exists() else ""),
    }


@route("GET", "/api/maj/verifier")
def api_verifie(ctx):
    """Y a-t-il une version plus récente publiée ?

    Sans adresse configurée, aucun appel réseau n'est fait : l'application
    fonctionne hors ligne, et ne contacte rien à l'insu de l'utilisateur.
    """
    ctx.exige_role("admin", "comptable")
    adresse = (config.get("url_versions") or "").strip()
    if not adresse:
        return {"active": False, "version": VERSION}

    import json as _json
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(adresse, timeout=6) as reponse:
            publie = _json.loads(reponse.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as err:
        # Pas d'Internet, adresse fautive : ce n'est pas une erreur de
        # l'utilisateur, on le dit sans alarmer.
        return {"active": True, "version": VERSION, "joignable": False,
                "detail": str(err)}

    derniere = str(publie.get("version") or "")
    return {
        "active": True,
        "joignable": True,
        "version": VERSION,
        "derniere": derniere,
        "disponible": bool(derniere)
                      and version_en_tuple(derniere) > version_en_tuple(VERSION),
        "notes": publie.get("notes", ""),
        "lien": publie.get("lien", ""),
    }


@route("POST", "/api/maj/analyse")
def api_analyse(ctx):
    """Contrôle le fichier déposé et annonce ce qu'il contient."""
    ctx.interdit_lecture_seule()
    ctx.exige_role("admin", "comptable")
    resultat = inspecte_paquet(_decode(ctx))
    if resultat["identique"]:
        resultat["avertissement"] = (
            f"Vous avez déjà la version {resultat['version']}. "
            "Il n'y a rien à mettre à jour.")
    elif not resultat["plus_recente"]:
        resultat["avertissement"] = (
            f"Ce fichier contient la version {resultat['version']}, plus "
            f"ancienne que la vôtre ({VERSION}). Revenir en arrière depuis "
            "l'application n'est pas possible : demandez le bon fichier.")
    return resultat


@route("POST", "/api/maj/appliquer")
def api_applique(ctx):
    """Range le paquet, lance l'outil de mise à jour, puis ferme l'application."""
    ctx.interdit_lecture_seule()
    ctx.exige_role("admin")
    octets = _decode(ctx)
    resultat = inspecte_paquet(octets)
    if not resultat["plus_recente"]:
        raise ErreurApplicative(
            f"Version {resultat['version']} : elle n'est pas plus récente que "
            f"la vôtre ({VERSION}). Rien n'a été touché.")

    dossier = config.dossier_donnees / "maj"
    dossier.mkdir(parents=True, exist_ok=True)
    # Les archives d'un essai précédent fausseraient le choix de l'outil.
    for ancienne in dossier.glob("*.zip"):
        ancienne.unlink()
    archive = dossier / f"maj-{resultat['version']}.zip"
    archive.write_bytes(octets)

    outil = RACINE / "outils" / "mise_a_jour.py"
    if not outil.exists():
        raise ErreurApplicative(
            "L'outil de mise à jour est introuvable dans cette installation.")

    # Rejouer le lancement d'origine — port, dossier de données, etc. Sans
    # cela l'application rouvrirait sur les valeurs par défaut, donc
    # éventuellement sur une autre comptabilité que celle en cours.
    options = json.dumps(sys.argv[1:])

    # La sortie de l'outil allait jusqu'ici dans le néant : un échec ne
    # laissait aucune trace et l'utilisateur n'avait plus qu'une fenêtre
    # muette. Elle est désormais conservée à côté de l'archive.
    journal = dossier / "journal-maj.txt"
    _prepare_etat(resultat["version"])
    try:
        sortie = journal.open("w", encoding="utf-8", errors="replace")
    except OSError:
        sortie = None

    try:
        subprocess.Popen(
            [sys.executable, str(outil), str(archive), "--auto", "--relancer",
             "--relancer-options", options,
             # Attendre la fermeture réelle plutôt qu'un délai fixe : la
             # sauvegarde d'arrêt dure ce que dure le dossier de pièces.
             "--attendre-pid", str(os.getpid()),
             "--vers", str(RACINE)],
            cwd=str(RACINE), **options_detachement(),
            stdin=subprocess.DEVNULL,
            stdout=sortie or subprocess.DEVNULL,
            stderr=subprocess.STDOUT)
    except OSError as err:
        raise ErreurApplicative(
            f"Impossible de lancer la mise à jour : {err}") from err
    finally:
        if sortie:
            sortie.close()

    db.trace("mise_a_jour", "systeme", None,
             {"de": VERSION, "vers": resultat["version"]}, ctx.nom_utilisateur)

    # L'application doit libérer ses fichiers avant qu'ils ne soient remplacés.
    # L'outil vient de recevoir notre PID : il attend la fermeture réelle, pas
    # un délai. Inutile donc de retarder l'arrêt.
    mod_serveur.arret_pour_maj = True
    if mod_serveur.demande_arret:
        mod_serveur.demande_arret()

    return {
        "version": resultat["version"],
        "ancienne_version": VERSION,
        "delai": DELAI_FERMETURE,
        "message": (f"Mise à jour vers la version {resultat['version']} en "
                    "cours. L'application se ferme et se rouvre toute seule."),
    }
