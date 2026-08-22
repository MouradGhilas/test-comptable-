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

**Aller dans les deux sens.** Une mise à jour qui déplaît doit pouvoir être
défaite : sans cela on hésite à en installer une. Chaque version installée est
donc conservée sur le poste, et l'écran de mise à jour en dresse la liste — on
y revient d'un bouton. Deux situations à ne pas confondre :

* la version visée **comprend la base telle qu'elle est** : seul le programme
  recule, la comptabilité n'est pas touchée ;
* la version visée est **antérieure au schéma de la base** : le programme seul
  ne suffit pas, il faut aussi remettre les données dans l'état d'alors. Ce
  qui a été saisi depuis serait perdu — c'est dit, c'est chiffré, et l'état
  actuel est sauvegardé avant pour que le mouvement reste réversible.
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


# ---------------------------------------------------------------------------
# La bibliothèque des versions présentes sur le poste
# ---------------------------------------------------------------------------
#
# Sans hébergement, un paquet reçu par messagerie n'existe qu'une fois : une
# fois installé, il n'est plus nulle part. Revenir en arrière supposait alors
# de le redemander à quelqu'un. On le garde donc, et on archive aussi la
# version en place avant de la remplacer : ce que le poste a connu, il peut y
# retourner.

#: Ce qu'une version contient, à l'identique de `outils/mise_a_jour.py`.
ELEMENTS_PROGRAMME = ["app.py", "noyau", "modules", "reference", "web", "outils",
                      "README.md", "GUIDE.md", "CHANGELOG.md",
                      "LANCER.bat", "lancer.sh", "INSTALLER.bat"]


def dossier_versions() -> Path:
    dossier = config.dossier_donnees / "versions"
    dossier.mkdir(parents=True, exist_ok=True)
    return dossier


def _nom_de_paquet(version: str) -> str:
    propre = re.sub(r"[^0-9A-Za-z._-]", "", str(version)) or "inconnue"
    return f"cabinet-immo-{propre}.zip"


def archive_version_courante() -> Path | None:
    """Met le programme en place dans la bibliothèque, s'il n'y est pas déjà.

    Fait avant toute installation : c'est ce qui garantit qu'on pourra
    revenir sur ses pas, y compris après une mise à jour qu'on regrette.
    """
    cible = dossier_versions() / _nom_de_paquet(VERSION)
    if cible.exists() and cible.stat().st_size > 0:
        return cible
    temporaire = cible.with_suffix(".zip.partiel")
    try:
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
                    archive.write(fichier, str(fichier.relative_to(RACINE)
                                               ).replace("\\", "/"))
        temporaire.replace(cible)
    except OSError:
        temporaire.unlink(missing_ok=True)
        return None
    return cible


def _version_dans_paquet(chemin: Path) -> dict | None:
    """Numéro de version et schéma d'un paquet rangé dans la bibliothèque."""
    try:
        with zipfile.ZipFile(chemin) as archive:
            prefixe = racine_dans_archive(archive.namelist())
            if prefixe is None:
                return None
            source = archive.read(prefixe + "noyau/config.py").decode("utf-8")
            trouve = re.search(r'^VERSION\s*=\s*["\']([^"\']+)["\']', source, re.M)
            if not trouve:
                return None
            return {"version": trouve.group(1),
                    "schema": _schema_dans_archive(archive, prefixe)}
    except (zipfile.BadZipFile, KeyError, OSError, UnicodeDecodeError):
        return None


def bibliotheque() -> list[dict]:
    """Les versions disponibles sur ce poste, de la plus récente à la plus ancienne."""
    versions = []
    for chemin in dossier_versions().glob("*.zip"):
        details = _version_dans_paquet(chemin)
        if not details:
            continue
        schema_base = _schema_base()
        versions.append({
            "version": details["version"],
            "schema": details["schema"],
            "fichier": chemin.name,
            "taille": chemin.stat().st_size,
            "date": time.strftime("%d/%m/%Y %H:%M",
                                  time.localtime(chemin.stat().st_mtime)),
            "installee": version_en_tuple(details["version"]) == version_en_tuple(VERSION),
            "sens": _sens(details["version"]),
            # Une version dont le schéma est en retard sur la base ne peut pas
            # l'ouvrir : il faudra remettre les données d'alors.
            "donnees_compatibles": details["schema"] is None
                                   or schema_base is None
                                   or details["schema"] >= schema_base,
        })
    versions.sort(key=lambda v: version_en_tuple(v["version"]), reverse=True)
    return versions


def _sens(version: str) -> str:
    if version_en_tuple(version) > version_en_tuple(VERSION):
        return "avance"
    if version_en_tuple(version) < version_en_tuple(VERSION):
        return "retour"
    return "identique"


def _schema_base() -> int | None:
    try:
        return db.version_schema()
    except Exception:                                         # noqa: BLE001
        return None


def _schema_dans_archive(archive: zipfile.ZipFile, prefixe: str) -> int | None:
    """Le numéro de schéma que le paquet sait ouvrir."""
    try:
        source = archive.read(prefixe + "noyau/base.py").decode("utf-8")
    except (KeyError, UnicodeDecodeError):
        return None
    trouve = re.search(r"^VERSION_SCHEMA\s*=\s*(\d+)", source, re.M)
    return int(trouve.group(1)) if trouve else None


def sauvegardes_utilisables(version_visee: str) -> list[dict]:
    """Les sauvegardes qu'une version antérieure saura rouvrir.

    Une sauvegarde faite par une version au plus égale à celle visée porte
    forcément un schéma que celle-ci connaît : c'est le seul critère sûr,
    et il ne demande aucune table de correspondance à tenir à jour.
    """
    retenues = []
    for chemin in sorted(config.dossier_sauvegardes.glob("*.zip"), reverse=True):
        try:
            with zipfile.ZipFile(chemin) as archive:
                manifeste = json.loads(archive.read("manifeste.json").decode("utf-8"))
        except (zipfile.BadZipFile, KeyError, OSError, ValueError):
            continue
        faite_par = str(manifeste.get("version") or "")
        if not faite_par or version_en_tuple(faite_par) > version_en_tuple(version_visee):
            continue
        retenues.append({"nom": chemin.name, "version": faite_par,
                         "date": manifeste.get("date", ""),
                         "motif": manifeste.get("motif", ""),
                         "taille": chemin.stat().st_size})
    return retenues


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

    schema = _schema_dans_archive(archive, prefixe)
    schema_base = _schema_base()
    sens = _sens(version)
    # Une version ne peut ouvrir une base que si elle en connaît le schéma.
    # C'est le vrai obstacle au retour en arrière : le programme recule sans
    # peine, la base non — elle ne sait pas se défaire de ses migrations.
    compatible = schema is None or schema_base is None or schema >= schema_base

    return {
        "version": version,
        "version_installee": VERSION,
        "fichiers": sum(1 for n in noms if not n.endswith("/")),
        "changelog": extrait_changelog(changelog, version, VERSION),
        "plus_recente": version_en_tuple(version) > version_en_tuple(VERSION),
        "identique": version_en_tuple(version) == version_en_tuple(VERSION),
        "sens": sens,
        "schema": schema,
        "schema_base": schema_base,
        "donnees_compatibles": compatible,
        # Ce qu'il faudrait remettre en place pour que cette version rouvre
        # la comptabilité. Vide s'il n'y a rien à remettre.
        "sauvegardes": ([] if compatible or sens != "retour"
                        else sauvegardes_utilisables(version)),
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


def decrit_situation(resultat: dict) -> dict:
    """Ce que le paquet ferait, dit à celui qui va appuyer sur le bouton.

    Trois cas, trois discours : une version plus récente s'installe, la même
    se réinstalle — c'est la réponse à une mise à jour restée à mi-chemin —,
    une plus ancienne demande à être confirmée, et parfois à remettre aussi
    les données du jour où elle était en place.
    """
    version = resultat["version"]
    if resultat["plus_recente"]:
        return {
            "action": "installer",
            "bouton": f"Installer la version {version}",
            "titre": f"Version {version} prête à être installée",
            "detail": (f"Vous êtes en {VERSION}. {resultat['fichiers']} fichier(s) "
                       "seront remplacés. Votre comptabilité n'est pas touchée."),
            "ton": "succes",
            "confirmation": "",
        }
    if resultat["identique"]:
        return {
            "action": "reinstaller",
            "bouton": f"Réinstaller la version {version}",
            "titre": f"Vous avez déjà la version {version}",
            "detail": ("Il n'y a rien de nouveau à installer. La réinstaller "
                       "remet tous les fichiers du programme en place : c'est "
                       "ce qu'il faut faire si une mise à jour s'est arrêtée "
                       "en chemin et que l'application se comporte mal. Votre "
                       "comptabilité n'est pas touchée."),
            "ton": "info",
            "confirmation": "",
        }
    if resultat["donnees_compatibles"]:
        return {
            "action": "revenir",
            "bouton": f"Revenir à la version {version}",
            "titre": f"Retour à la version {version}",
            "detail": (f"Vous êtes en {VERSION}. Seul le programme recule : "
                       "cette version sait ouvrir votre comptabilité telle "
                       "qu'elle est, rien de ce que vous avez saisi ne sera "
                       "perdu. Une sauvegarde est prise avant, comme toujours."),
            "ton": "alerte",
            "confirmation": "REVENIR",
        }
    dispo = resultat.get("sauvegardes") or []
    return {
        "action": "revenir_avec_donnees",
        "bouton": f"Revenir à la version {version}",
        "titre": f"Retour à la version {version} : les données doivent suivre",
        "detail": (
            f"La version {version} ne connaît pas la base dans son état actuel "
            f"(elle s'arrête au schéma {resultat.get('schema')}, votre base est "
            f"au {resultat.get('schema_base')}). Le programme peut reculer, "
            "pas la base : il faut donc aussi remettre les données telles "
            "qu'elles étaient du temps de cette version. "
            + ("Choisissez la sauvegarde à remettre ci-dessous : tout ce qui a "
               "été saisi depuis sera perdu. L'état actuel est sauvegardé avant, "
               "vous pourrez y revenir." if dispo else
               "Aucune sauvegarde d'avant cette version n'est disponible sur ce "
               "poste : le retour n'est pas possible sans elle.")),
        "ton": "danger" if dispo else "alerte",
        "confirmation": "REVENIR",
        "possible": bool(dispo),
    }


@route("POST", "/api/maj/analyse")
def api_analyse(ctx):
    """Contrôle le fichier déposé et annonce ce qu'il contient."""
    ctx.interdit_lecture_seule()
    ctx.exige_role("admin", "comptable")
    # Le paquet vient d'un dépôt, ou de la bibliothèque du poste : on
    # l'examine de la même façon dans les deux cas.
    resultat = inspecte_paquet(_octets_demandes(ctx))
    resultat["situation"] = decrit_situation(resultat)
    return resultat


@route("GET", "/api/maj/versions")
def api_versions(ctx):
    """Les versions présentes sur ce poste, et celle qui tourne."""
    ctx.exige_role("admin", "comptable")
    # La version en cours est rangée à la première occasion : c'est elle
    # qu'on voudra retrouver après une mise à jour qui déçoit.
    archive_version_courante()
    return {"version": VERSION, "schema_base": _schema_base(),
            "versions": bibliotheque(), "dossier": str(dossier_versions())}


@route("DELETE", "/api/maj/versions")
def api_oublie_version(ctx):
    """Retire un paquet de la bibliothèque, pour faire de la place."""
    ctx.exige_role("admin")
    nom = Path(ctx.arg("fichier") or ctx.champ("fichier") or "").name
    chemin = (dossier_versions() / nom).resolve()
    try:
        chemin.relative_to(dossier_versions().resolve())
    except ValueError:
        raise ErreurApplicative("Chemin invalide.", 403) from None
    if not chemin.is_file():
        raise ErreurApplicative("Ce paquet n'est pas sur ce poste.", 404)
    details = _version_dans_paquet(chemin)
    if details and version_en_tuple(details["version"]) == version_en_tuple(VERSION):
        raise ErreurApplicative(
            "C'est la version en cours d'utilisation : la retirer vous "
            "priverait du seul moyen de la réinstaller.")
    chemin.unlink()
    return {"ok": True, "message": f"{nom} retiré de ce poste."}


def _octets_demandes(ctx) -> bytes:
    """Le paquet visé : celui qu'on dépose, ou celui déjà sur le poste."""
    fichier = Path(str(ctx.champ("fichier") or "")).name
    if not fichier:
        return _decode(ctx)
    chemin = (dossier_versions() / fichier).resolve()
    try:
        chemin.relative_to(dossier_versions().resolve())
    except ValueError:
        raise ErreurApplicative("Chemin invalide.", 403) from None
    if not chemin.is_file():
        raise ErreurApplicative(
            "Ce paquet n'est plus sur ce poste. Déposez le fichier .zip.", 404)
    return chemin.read_bytes()


def _sauvegarde_a_remettre(ctx, resultat: dict) -> Path | None:
    """Contrôle la sauvegarde choisie pour un retour que la base interdit."""
    nom = Path(str(ctx.champ("sauvegarde") or "")).name
    if not nom:
        raise ErreurApplicative(
            f"La version {resultat['version']} ne sait pas ouvrir votre base "
            f"dans son état actuel (schéma {resultat.get('schema')} contre "
            f"{resultat.get('schema_base')}). Pour y revenir, il faut remettre "
            "les données telles qu'elles étaient à cette époque : choisissez "
            "la sauvegarde à remettre.")
    autorisees = {s["nom"] for s in sauvegardes_utilisables(resultat["version"])}
    if nom not in autorisees:
        raise ErreurApplicative(
            f"La sauvegarde « {nom} » n'a pas été faite par une version que "
            f"la {resultat['version']} sait relire. Choisissez-en une autre.")
    chemin = (config.dossier_sauvegardes / nom).resolve()
    if not chemin.is_file():
        raise ErreurApplicative("Sauvegarde introuvable.", 404)
    return chemin


@route("POST", "/api/maj/appliquer")
def api_applique(ctx):
    """Range le paquet, lance l'outil de mise à jour, puis ferme l'application.

    Sert aussi bien à avancer qu'à reculer : ce sont les mêmes gestes, avec
    des garde-fous différents. Reculer se confirme, et si la base a pris de
    l'avance sur la version visée, elle recule avec — explicitement.
    """
    ctx.interdit_lecture_seule()
    ctx.exige_role("admin")
    octets = _octets_demandes(ctx)
    resultat = inspecte_paquet(octets)
    situation = decrit_situation(resultat)
    a_remettre = None

    if situation["confirmation"] and \
            str(ctx.champ("confirmation") or "").strip().upper() != situation["confirmation"]:
        raise ErreurApplicative(
            f"Revenir à la version {resultat['version']} change le programme "
            "en place. Saisissez REVENIR pour confirmer. Rien n'a été touché.")

    if situation["action"] == "revenir_avec_donnees":
        a_remettre = _sauvegarde_a_remettre(ctx, resultat)

    # Avant de toucher au programme : garder celui qui tourne. C'est ce qui
    # rend le mouvement réversible — sans quoi une version installée puis
    # remplacée n'existe plus nulle part.
    archive_version_courante()

    dossier = config.dossier_donnees / "maj"
    dossier.mkdir(parents=True, exist_ok=True)
    # Les archives d'un essai précédent fausseraient le choix de l'outil.
    for ancienne in dossier.glob("*.zip"):
        ancienne.unlink()
    archive = dossier / f"maj-{resultat['version']}.zip"
    archive.write_bytes(octets)
    # Le paquet rejoint la bibliothèque : reçu une fois, disponible toujours.
    try:
        (dossier_versions() / _nom_de_paquet(resultat["version"])).write_bytes(octets)
    except OSError:
        pass

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

    # Le fils écrit dans un fichier, dont il choisit l'encodage d'après la
    # page de codes du système : sur un Windows français, cp1252. Le moindre
    # caractère semi-graphique de son cadre d'accueil y levait alors une
    # UnicodeEncodeError, et la mise à jour mourait à sa première ligne. On
    # impose l'UTF-8 par l'environnement, en plus du garde-fou que l'outil
    # pose lui-même : celui-ci n'existe pas dans les versions déjà installées.
    environnement = dict(os.environ, PYTHONIOENCODING="utf-8:replace",
                         PYTHONUTF8="1",
                         # Ceinture et bretelles : les versions de l'outil
                         # antérieures à --donnees lisent au moins ceci.
                         CABINET_IMMO_DONNEES=str(config.dossier_donnees))

    try:
        subprocess.Popen(
            [sys.executable, str(outil), str(archive), "--auto", "--relancer",
             "--relancer-options", options,
             # Attendre la fermeture réelle plutôt qu'un délai fixe : la
             # sauvegarde d'arrêt dure ce que dure le dossier de pièces.
             "--attendre-pid", str(os.getpid()),
             # Le processus peut avoir disparu des listes sans que le port
             # soit rendu — et un identifiant se réattribue. Tant que le port
             # répond, l'application sert encore : remplacer ses fichiers la
             # laisserait avec une interface neuve sur un moteur ancien.
             "--attendre-port", str(mod_serveur.port_courant or 0),
             "--vers", str(RACINE),
             # Sans cela, l'outil travaillerait sur le dossier de données par
             # défaut : il sauvegarderait, migrerait et vérifierait une autre
             # comptabilité que celle qui est ouverte.
             "--donnees", str(config.dossier_donnees)]
            # Un retour en arrière que la base interdit : les données
            # reviennent avec le programme, sinon la version installée ne
            # pourrait même pas ouvrir le dossier.
            + (["--restaurer", str(a_remettre)] if a_remettre else []),
            cwd=str(RACINE), **options_detachement(), env=environnement,
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
             {"de": VERSION, "vers": resultat["version"],
              "sens": situation["action"],
              "donnees_remises": a_remettre.name if a_remettre else None},
             ctx.nom_utilisateur)

    # L'application doit libérer ses fichiers avant qu'ils ne soient remplacés.
    # L'outil vient de recevoir notre PID : il attend la fermeture réelle, pas
    # un délai. Inutile donc de retarder l'arrêt.
    mod_serveur.arret_pour_maj = True
    if mod_serveur.demande_arret:
        mod_serveur.demande_arret()

    verbe = {"revenir": "Retour à la version",
             "revenir_avec_donnees": "Retour à la version",
             "reinstaller": "Réinstallation de la version"}.get(
                 situation["action"], "Mise à jour vers la version")
    return {
        "version": resultat["version"],
        "ancienne_version": VERSION,
        "action": situation["action"],
        "donnees_remises": a_remettre.name if a_remettre else None,
        "delai": DELAI_FERMETURE,
        "message": (f"{verbe} {resultat['version']} en cours. L'application "
                    "se ferme et se rouvre toute seule."),
    }
