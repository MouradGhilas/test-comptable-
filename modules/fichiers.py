"""Pièces justificatives et sauvegardes du dossier local.

Les fichiers scannés sont rangés dans
`donnees/pieces_justificatives/<societe>/<annee>/` et référencés en base par
un chemin relatif — le dossier de données reste donc déplaçable d'un poste à
l'autre sans casser les liens.
"""

from __future__ import annotations

import base64
import binascii
import gc
import io
import json
import re
import shutil
import sqlite3
import zipfile
from pathlib import Path

from noyau import base as db
from noyau import util
from noyau.config import config, APPLICATION, VERSION, RACINE as RACINE_APPLICATION
from noyau.serveur import ErreurApplicative, route, Reponse

EXTENSIONS_AUTORISEES = {
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".tif", ".tiff",
    ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt", ".odt", ".ods",
}

TAILLE_MAX = 20 * 1024 * 1024   # 20 Mio par pièce


def nom_sur(nom: str) -> str:
    nom = Path(nom or "piece").name
    nom = re.sub(r"[^\w.\- ]+", "_", util.sans_accents(nom))
    return nom[:120] or "piece"


@route("POST", "/api/pieces")
def api_depose(ctx):
    """Dépôt d'une pièce justificative (contenu encodé en base64)."""
    ctx.interdit_lecture_seule()
    societe_id = ctx.entier("societe_id")
    entite = ctx.champ_requis("entite")
    entite_id = ctx.entier("entite_id")
    if entite not in ("ecriture", "facture", "contrat_vsp", "bail", "lot", "programme",
                      "quittance", "tiers", "immobilisation", "situation_travaux"):
        raise ErreurApplicative("Type d'entité non reconnu.")

    contenu_b64 = ctx.champ_requis("contenu")
    if "," in contenu_b64[:100] and contenu_b64.startswith("data:"):
        contenu_b64 = contenu_b64.split(",", 1)[1]
    try:
        contenu = base64.b64decode(contenu_b64, validate=True)
    except (binascii.Error, ValueError) as err:
        raise ErreurApplicative("Fichier illisible (encodage invalide).") from err
    if len(contenu) > TAILLE_MAX:
        raise ErreurApplicative(
            f"Fichier trop volumineux ({len(contenu) // 1024 // 1024} Mio). "
            "Maximum : 20 Mio. Scannez en qualité réduite."
        )

    nom_fichier = nom_sur(ctx.champ_requis("nom_fichier"))
    extension = Path(nom_fichier).suffix.lower()
    if extension not in EXTENSIONS_AUTORISEES:
        raise ErreurApplicative(
            f"Extension « {extension} » non autorisée. "
            "Formats acceptés : PDF, images, documents bureautiques."
        )

    annee = util.aujourdhui()[:4]
    dossier = config.dossier_pieces / f"societe_{societe_id}" / annee / entite
    dossier.mkdir(parents=True, exist_ok=True)
    horodatage = util.maintenant().replace(":", "").replace("-", "").replace(" ", "_")
    cible = dossier / f"{entite_id or 0}_{horodatage}_{nom_fichier}"
    cible.write_bytes(contenu)

    relatif = str(cible.relative_to(config.dossier_donnees)).replace("\\", "/")
    with db.transaction():
        identifiant = db.insere("pieces_jointes", {
            "societe_id": societe_id, "entite": entite, "entite_id": entite_id or 0,
            "nom_fichier": nom_fichier, "chemin": relatif, "taille": len(contenu),
            "type_mime": ctx.champ("type_mime"),
            "description": util.nettoie(ctx.champ("description")),
            "cree_le": util.maintenant(),
        })
        db.trace("depot", "piece_jointe", identifiant, nom_fichier, ctx.nom_utilisateur)
    return {"id": identifiant, "url": "/fichiers/" + relatif, "taille": len(contenu)}


@route("GET", "/api/pieces")
def api_liste(ctx):
    return {"pieces": db.lignes(
        "SELECT * FROM pieces_jointes WHERE entite = ? AND entite_id = ? ORDER BY id DESC",
        (ctx.arg("entite"), ctx.arg_int("entite_id", 0)),
    )}


@route("DELETE", "/api/pieces/<id>")
def api_supprime(ctx):
    ctx.interdit_lecture_seule()
    identifiant = int(ctx.params["id"])
    piece = db.ligne("SELECT * FROM pieces_jointes WHERE id = ?", (identifiant,))
    if not piece:
        raise ErreurApplicative("Pièce introuvable.", 404)
    chemin = (config.dossier_donnees / piece["chemin"]).resolve()
    try:
        chemin.relative_to(config.dossier_donnees.resolve())
        if chemin.is_file():
            chemin.unlink()
    except (ValueError, OSError):
        pass
    with db.transaction():
        db.supprime("pieces_jointes", identifiant)
        db.trace("suppression", "piece_jointe", identifiant, piece["nom_fichier"],
                 ctx.nom_utilisateur)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Sauvegarde / restauration
# ---------------------------------------------------------------------------

@route("GET", "/api/sauvegardes")
def api_liste_sauvegardes(ctx):
    config.prepare_dossiers()
    fichiers = []
    for chemin in sorted(config.dossier_sauvegardes.glob("*.zip"), reverse=True):
        infos = chemin.stat()
        fichiers.append({
            "nom": chemin.name, "taille": infos.st_size,
            "date": util.maintenant() if not infos.st_mtime else
                    __import__("datetime").datetime.fromtimestamp(
                        infos.st_mtime).replace(microsecond=0).isoformat(sep=" "),
        })
    return {
        "sauvegardes": fichiers,
        "dossier": str(config.dossier_sauvegardes),
        "dossier_donnees": str(config.dossier_donnees),
        "taille_base": config.base_de_donnees.stat().st_size
                       if config.base_de_donnees.exists() else 0,
        # Ces archives sont sur le même disque que la comptabilité : l'écran
        # doit pouvoir dire depuis quand il en existe une copie ailleurs.
        "copie_externe": etat_copie_externe(),
    }


def cree_sauvegarde(motif: str = "manuelle") -> Path:
    """Copie cohérente de la base + des pièces justificatives dans une archive."""
    config.prepare_dossiers()
    horodatage = util.maintenant().replace(":", "").replace("-", "").replace(" ", "_")
    cible = config.dossier_sauvegardes / f"sauvegarde_{horodatage}_{motif}.zip"

    # Sauvegarde SQLite à chaud, sans interrompre l'application
    temporaire = config.dossier_sauvegardes / "_copie_temporaire.db"
    source = db.connexion()
    destination = sqlite3.connect(str(temporaire))
    try:
        source.backup(destination)
    finally:
        destination.close()

    with zipfile.ZipFile(cible, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(temporaire, "comptabilite.db")
        archive.writestr("manifeste.json", json.dumps({
            "application": APPLICATION, "version": VERSION,
            "date": util.maintenant(), "motif": motif,
            "societes": [dict(s) for s in db.lignes(
                "SELECT id, code, raison_sociale FROM societes")],
        }, ensure_ascii=False, indent=2))
        if config.dossier_pieces.exists():
            for fichier in config.dossier_pieces.rglob("*"):
                if fichier.is_file():
                    archive.write(
                        fichier,
                        "pieces_justificatives/"
                        + str(fichier.relative_to(config.dossier_pieces)).replace("\\", "/"),
                    )
    temporaire.unlink(missing_ok=True)

    # Rotation : on ne conserve que les N dernières
    a_conserver = int(config.get("sauvegardes_a_conserver", 30))
    archives = sorted(config.dossier_sauvegardes.glob("*.zip"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
    for vieille in archives[a_conserver:]:
        vieille.unlink(missing_ok=True)

    return cible


@route("POST", "/api/sauvegardes")
def api_cree_sauvegarde(ctx):
    ctx.exige_role("admin", "comptable")
    chemin = cree_sauvegarde(ctx.champ("motif", "manuelle"))
    db.trace("sauvegarde", "systeme", None, chemin.name, ctx.nom_utilisateur)
    return {"nom": chemin.name, "taille": chemin.stat().st_size,
            "chemin": str(chemin),
            "message": f"Sauvegarde créée : {chemin.name}"}


@route("GET", "/api/sauvegardes/telecharger")
def api_telecharge(ctx):
    nom = Path(ctx.arg("nom") or "").name
    chemin = (config.dossier_sauvegardes / nom).resolve()
    try:
        chemin.relative_to(config.dossier_sauvegardes.resolve())
    except ValueError:
        raise ErreurApplicative("Chemin invalide.", 403) from None
    if not chemin.is_file():
        raise ErreurApplicative("Sauvegarde introuvable.", 404)
    return Reponse(chemin.read_bytes(), "application/zip", nom)


@route("POST", "/api/sauvegardes/deposer")
def api_depose_sauvegarde(ctx):
    """Ranger ici une sauvegarde venue d'un autre poste.

    La restauration ne savait choisir que parmi les sauvegardes déjà
    présentes sur la machine : il fallait donc trouver soi-même le dossier
    `donnees/sauvegardes/` et y glisser le fichier. On le dépose désormais
    depuis l'écran, et il rejoint la liste comme les autres.
    """
    ctx.interdit_lecture_seule()
    ctx.exige_role("admin")
    contenu = ctx.champ_requis("contenu")
    if contenu.startswith("data:") and "," in contenu[:120]:
        contenu = contenu.split(",", 1)[1]
    try:
        octets = base64.b64decode(contenu, validate=True)
    except (binascii.Error, ValueError) as err:
        raise ErreurApplicative(f"Fichier illisible : {err}") from err

    try:
        archive = zipfile.ZipFile(io.BytesIO(octets))
    except zipfile.BadZipFile as err:
        raise ErreurApplicative(
            "Ce fichier n'est pas une sauvegarde de " + APPLICATION + ". "
            "Cherchez un fichier nommé « sauvegarde_… .zip ». "
            f"Détail : {err}") from err
    noms = archive.namelist()
    if "comptabilite.db" not in noms:
        raise ErreurApplicative(
            "Ce fichier ne contient pas de comptabilité : ce n'est pas une "
            "sauvegarde de " + APPLICATION + ".")
    manifeste = {}
    if "manifeste.json" in noms:
        try:
            manifeste = json.loads(archive.read("manifeste.json").decode("utf-8"))
        except ValueError:
            manifeste = {}

    config.prepare_dossiers()
    nom = nom_sur(ctx.champ("nom") or "sauvegarde_recue.zip")
    if not nom.lower().endswith(".zip"):
        nom += ".zip"
    cible = config.dossier_sauvegardes / nom
    rang = 1
    while cible.exists():
        cible = config.dossier_sauvegardes / f"{nom[:-4]}_{rang}.zip"
        rang += 1
    cible.write_bytes(octets)
    db.trace("depot_sauvegarde", "systeme", None, cible.name, ctx.nom_utilisateur)
    return {
        "nom": cible.name, "taille": cible.stat().st_size,
        "faite_le": manifeste.get("date"), "version": manifeste.get("version"),
        "societes": [s.get("raison_sociale") for s in manifeste.get("societes", [])],
        "message": f"{cible.name} est maintenant sur ce poste. "
                   "Utilisez « Restaurer » pour la mettre en place.",
    }


@route("POST", "/api/sauvegardes/restaurer")
def api_restaure(ctx):
    """Restauration d'une archive. Une sauvegarde de sécurité est prise avant."""
    ctx.exige_role("admin")
    nom = Path(ctx.champ_requis("nom")).name
    archive = (config.dossier_sauvegardes / nom).resolve()
    try:
        archive.relative_to(config.dossier_sauvegardes.resolve())
    except ValueError:
        raise ErreurApplicative("Chemin invalide.", 403) from None
    if not archive.is_file():
        raise ErreurApplicative("Sauvegarde introuvable.", 404)
    if ctx.champ("confirmation") != "RESTAURER":
        raise ErreurApplicative(
            "Cette opération remplace l'intégralité des données actuelles. "
            "Saisissez RESTAURER pour confirmer."
        )

    cree_sauvegarde("avant_restauration")
    _pose_la_base(archive.read_bytes())
    db.initialise()
    db.trace("restauration", "systeme", None, nom, ctx.nom_utilisateur)
    return {"ok": True,
            "message": "Restauration terminée. Reconnectez-vous pour recharger les données."}


def _pose_la_base(octets: bytes) -> dict:
    """Écrit la base et les pièces d'une archive de sauvegarde.

    Partagé par la restauration ordinaire et par celle d'un poste neuf : le
    geste est le même, seuls les garde-fous diffèrent.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(octets))
    except zipfile.BadZipFile as err:
        raise ErreurApplicative(
            "Ce fichier n'est pas une sauvegarde de " + APPLICATION + ". "
            "Cherchez un fichier nommé « sauvegarde_… .zip », pris sur "
            "l'autre poste dans Paramètres → Sauvegarde & données. "
            f"Détail : {err}") from err
    noms = archive.namelist()
    if "comptabilite.db" not in noms:
        raise ErreurApplicative(
            "Ce fichier n'est pas une sauvegarde de " + APPLICATION
            + " : la comptabilité n'y est pas. Cherchez un fichier nommé "
              "« sauvegarde_… .zip ».")
    manifeste = {}
    if "manifeste.json" in noms:
        try:
            manifeste = json.loads(archive.read("manifeste.json").decode("utf-8"))
        except ValueError:
            manifeste = {}

    config.prepare_dossiers()
    db.ferme()
    # Une connexion oubliée par un fil qui vient de finir garderait le
    # fichier — et son journal WAL — sous les pieds de celui qu'on pose.
    gc.collect()

    # L'ordre compte, et c'est ce qui manquait : le journal WAL de l'ancienne
    # base est retiré **avant** que la nouvelle ne prenne sa place. Écrire
    # par-dessus en laissant traîner un WAL qui décrit une autre base donnait
    # « disk I/O error » à la réouverture — la restauration d'une sauvegarde
    # n'a jamais abouti depuis l'écran.
    base = Path(config.base_de_donnees)
    for suffixe in ("-wal", "-shm"):
        Path(str(base) + suffixe).unlink(missing_ok=True)
    # Effacer plutôt qu'écraser : un descripteur encore ouvert sur l'ancien
    # fichier ne suit pas le nouveau, qui repart sur une entrée neuve.
    base.unlink(missing_ok=True)
    with archive.open("comptabilite.db") as source, open(base, "wb") as destination:
        shutil.copyfileobj(source, destination)
    for interne in noms:
        if interne.startswith("pieces_justificatives/") and not interne.endswith("/"):
            cible = config.dossier_donnees / interne
            cible.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(interne) as source, open(cible, "wb") as destination:
                shutil.copyfileobj(source, destination)
    return manifeste


@route("POST", "/api/installation/restaurer", public=True)
def api_installe_depuis_sauvegarde(ctx):
    """Reprendre un dossier existant sur un poste neuf.

    Le second poste demandait de créer un compte et une entreprise, alors
    que tout cela existait déjà sur le premier : il n'y avait aucun moyen de
    dire « j'ai déjà un dossier, le voici ». On restaurait donc un compte
    pour pouvoir en restaurer un autre.

    N'est ouvert que tant qu'aucun utilisateur n'existe : sur une
    installation en service, la restauration passe par l'écran Sauvegardes,
    avec confirmation.
    """
    if db.valeur("SELECT COUNT(*) FROM utilisateurs", (), 0):
        raise ErreurApplicative(
            "Ce poste a déjà un dossier. Pour le remplacer par une "
            "sauvegarde, connectez-vous puis passez par Paramètres → "
            "Sauvegarde & données.", 409)

    contenu = ctx.champ_requis("contenu")
    if contenu.startswith("data:") and "," in contenu[:120]:
        contenu = contenu.split(",", 1)[1]
    try:
        octets = base64.b64decode(contenu, validate=True)
    except (binascii.Error, ValueError) as err:
        raise ErreurApplicative(f"Fichier illisible : {err}") from err

    manifeste = _pose_la_base(octets)
    try:
        db.initialise()
    except Exception as err:                                  # noqa: BLE001
        # La base posée ne s'ouvre pas : on la retire, sans quoi le poste
        # resterait avec un dossier qu'il ne sait pas lire.
        db.ferme()
        Path(config.base_de_donnees).unlink(missing_ok=True)
        raise ErreurApplicative(
            "Cette sauvegarde n'a pas pu être ouverte sur ce poste. "
            f"Détail : {err}. Si elle vient d'une version plus récente, "
            "mettez d'abord ce poste à jour, puis recommencez.") from err

    comptes = [u["identifiant"] for u in db.lignes(
        "SELECT identifiant FROM utilisateurs WHERE actif = 1 ORDER BY id")]
    societes = [s["raison_sociale"] for s in db.lignes(
        "SELECT raison_sociale FROM societes ORDER BY id")]
    db.trace("restauration", "installation", None,
             {"depuis": manifeste.get("version"), "date": manifeste.get("date")})
    return {
        "ok": True,
        "faite_le": manifeste.get("date"),
        "version": manifeste.get("version"),
        "societes": societes,
        "comptes": comptes,
        "message": "Dossier repris sur ce poste. Connectez-vous avec vos "
                   "identifiants habituels — les mêmes que sur l'autre poste.",
    }


@route("GET", "/api/systeme/infos")
def api_infos(ctx):
    config.prepare_dossiers()
    taille_pieces = sum(f.stat().st_size for f in config.dossier_pieces.rglob("*")
                        if f.is_file()) if config.dossier_pieces.exists() else 0
    return {
        "application": APPLICATION, "version": VERSION,
        "dossier_donnees": str(config.dossier_donnees),
        "base_de_donnees": str(config.base_de_donnees),
        "taille_base": (config.base_de_donnees.stat().st_size
                        if config.base_de_donnees.exists() else 0),
        "nombre_pieces": db.valeur("SELECT COUNT(*) FROM pieces_jointes", (), 0),
        "taille_pieces": taille_pieces,
        "nombre_ecritures": db.valeur("SELECT COUNT(*) FROM ecritures", (), 0),
        "nombre_societes": db.valeur("SELECT COUNT(*) FROM societes", (), 0),
        "derniere_sauvegarde": max(
            (f.name for f in config.dossier_sauvegardes.glob("*.zip")), default=None),
        "sauvegardes": len(list(config.dossier_sauvegardes.glob("*.zip"))),
    }


@route("POST", "/api/systeme/verifier")
def api_verifie(ctx):
    """Contrôle d'intégrité de la base et cohérence des écritures."""
    ctx.exige_role("admin", "comptable")
    integrite = db.valeur("PRAGMA integrity_check", (), "inconnu")
    orphelines = db.valeur(
        "SELECT COUNT(*) FROM lignes l LEFT JOIN ecritures e ON e.id = l.ecriture_id "
        "WHERE e.id IS NULL", (), 0)
    desequilibrees = db.lignes(
        "SELECT e.id, e.numero, e.date, e.libelle, "
        "  COALESCE(SUM(l.debit),0) AS d, COALESCE(SUM(l.credit),0) AS c "
        "FROM ecritures e LEFT JOIN lignes l ON l.ecriture_id = e.id "
        "GROUP BY e.id HAVING d <> c LIMIT 100")
    comptes_inconnus = db.lignes(
        "SELECT DISTINCT l.compte FROM lignes l JOIN ecritures e ON e.id = l.ecriture_id "
        "WHERE NOT EXISTS (SELECT 1 FROM comptes c WHERE c.numero = l.compte "
        "AND (c.societe_id = e.societe_id OR c.societe_id IS NULL)) LIMIT 50")
    pieces_manquantes = [
        p["nom_fichier"] for p in db.lignes("SELECT chemin, nom_fichier FROM pieces_jointes")
        if not (config.dossier_donnees / p["chemin"]).is_file()
    ]
    return {
        "integrite_base": integrite,
        "lignes_orphelines": orphelines,
        "ecritures_desequilibrees": desequilibrees,
        "comptes_inconnus": [c["compte"] for c in comptes_inconnus],
        "pieces_manquantes": pieces_manquantes[:50],
        "conforme": (integrite == "ok" and not orphelines and not desequilibrees
                     and not comptes_inconnus),
    }


# ---------------------------------------------------------------------------
# Copie hors du poste
#
# Les sauvegardes sont rangées dans `donnees/sauvegardes/`, c'est-à-dire sur
# le même disque que la comptabilité elle-même. Une panne de disque, un vol
# ou un rançongiciel emporte donc les comptes ET toutes leurs copies d'un
# seul coup. Le guide conseillait une clé USB hebdomadaire ; rien ne le
# rappelait ni ne le vérifiait. Ces routes permettent de faire la copie
# depuis l'application, et surtout de voir quand elle date.
# ---------------------------------------------------------------------------

#: Au-delà, l'application le signale : une copie trop vieille ne protège
#: plus grand-chose.
JOURS_AVANT_RAPPEL = 7


def _lit_copie_externe() -> dict:
    brut = db.valeur("SELECT valeur FROM meta WHERE cle = 'copie_externe'")
    if not brut:
        return {}
    try:
        valeur = json.loads(brut)
    except ValueError:
        return {}
    return valeur if isinstance(valeur, dict) else {}


def _ecrit_copie_externe(destination: Path, nom: str) -> dict:
    etat = {"date": util.maintenant(), "destination": str(destination), "nom": nom}
    with db.transaction():
        db.execute("INSERT OR REPLACE INTO meta (cle, valeur) VALUES (?, ?)",
                   ("copie_externe", json.dumps(etat, ensure_ascii=False)))
    return etat


def etat_copie_externe() -> dict:
    """Où en est la dernière copie hors du poste, et depuis quand."""
    etat = dict(_lit_copie_externe())
    etat["seuil_jours"] = JOURS_AVANT_RAPPEL
    date = etat.get("date")
    if not date:
        etat["jours"] = None
        etat["a_rappeler"] = True
        return etat
    import datetime
    try:
        quand = datetime.datetime.fromisoformat(date)
    except ValueError:
        etat["jours"] = None
        etat["a_rappeler"] = True
        return etat
    jours = (datetime.datetime.now() - quand).days
    etat["jours"] = jours
    etat["a_rappeler"] = jours >= JOURS_AVANT_RAPPEL
    return etat


def _verifie_destination(brut: str) -> Path:
    """Un emplacement qui protège vraiment : ailleurs que le dossier de travail."""
    if not brut or not brut.strip():
        raise ErreurApplicative(
            "Indiquez où copier la sauvegarde : une clé USB (E:\\), un disque "
            "externe, ou un dossier d'un autre disque.")
    try:
        destination = Path(brut.strip()).expanduser().resolve()
    except (OSError, ValueError) as err:
        raise ErreurApplicative(f"Emplacement illisible : {err}") from err

    if not destination.exists():
        raise ErreurApplicative(
            f"« {destination} » est introuvable. Si c'est une clé USB, "
            "vérifiez qu'elle est bien branchée, puis réessayez.")
    if not destination.is_dir():
        raise ErreurApplicative(
            f"« {destination} » n'est pas un dossier. Indiquez un dossier, "
            "pas un fichier.")

    # Copier à côté de l'original ne protège de rien : c'est le disque entier
    # que l'on cherche à ne pas perdre.
    for interdit, motif in (
        (config.dossier_donnees, "dans votre dossier de données"),
        (RACINE_APPLICATION, "dans le dossier du programme"),
    ):
        try:
            destination.relative_to(Path(interdit).resolve())
        except ValueError:
            continue
        raise ErreurApplicative(
            f"Cet emplacement est {motif} : la copie serait perdue en même "
            "temps que l'original. Choisissez une clé USB ou un autre disque.")

    essai = destination / ".cabinet_immo_essai"
    try:
        essai.write_bytes(b"")
        essai.unlink()
    except OSError as err:
        raise ErreurApplicative(
            f"Impossible d'écrire dans « {destination} » ({err}). Vérifiez "
            "que le support n'est pas protégé en écriture.") from err
    return destination


@route("POST", "/api/sauvegardes/copier")
def api_copie_externe(ctx):
    """Copie une sauvegarde hors du poste, et retient où et quand."""
    ctx.interdit_lecture_seule()
    ctx.exige_role("admin", "comptable")
    destination = _verifie_destination(ctx.champ("destination", ""))

    nom = Path(ctx.champ("nom") or "").name
    if nom:
        source = (config.dossier_sauvegardes / nom).resolve()
        try:
            source.relative_to(config.dossier_sauvegardes.resolve())
        except ValueError:
            raise ErreurApplicative("Sauvegarde inconnue.")
        if not source.is_file():
            raise ErreurApplicative(f"La sauvegarde « {nom} » n'existe plus.")
    else:
        # Aucune précision : la plus récente, en la créant au besoin pour que
        # la copie reflète bien la comptabilité d'aujourd'hui.
        archives = sorted(config.dossier_sauvegardes.glob("*.zip"),
                          key=lambda p: p.stat().st_mtime, reverse=True)
        source = archives[0] if archives else cree_sauvegarde("copie_externe")

    cible = destination / source.name
    try:
        shutil.copy2(source, cible)
    except OSError as err:
        raise ErreurApplicative(
            f"Copie impossible ({err}). Si c'est une clé USB, vérifiez "
            "qu'il reste de la place et qu'elle n'a pas été retirée.") from err

    etat = _ecrit_copie_externe(destination, source.name)
    db.trace("copie_externe", "systeme", None,
             {"nom": source.name, "destination": str(destination)},
             ctx.nom_utilisateur)
    return {
        "nom": source.name,
        "destination": str(destination),
        "chemin": str(cible),
        "taille": cible.stat().st_size,
        "date": etat["date"],
        "message": f"Sauvegarde copiée dans {destination}.",
    }
