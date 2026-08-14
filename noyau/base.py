"""Couche d'accès à la base SQLite locale.

Une connexion par thread (le serveur est multi-thread), mode WAL pour la
robustesse, contraintes de clés étrangères activées.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from .config import config
from . import util

_local = threading.local()
_verrou_ecriture = threading.RLock()


def connexion() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        config.prepare_dossiers()
        conn = sqlite3.connect(
            str(config.base_de_donnees),
            timeout=30.0,
            isolation_level=None,          # autocommit : on gère les transactions à la main
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA synchronous = FULL")   # priorité à l'intégrité comptable
        conn.execute("PRAGMA busy_timeout = 30000")
        _local.conn = conn
    return conn


def ferme():
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None


# ---------------------------------------------------------------------------
# Helpers de requêtage
# ---------------------------------------------------------------------------

def lignes(sql: str, params=()) -> list[dict]:
    cur = connexion().execute(sql, params)
    try:
        return [dict(r) for r in cur.fetchall()]
    finally:
        cur.close()


def ligne(sql: str, params=()) -> dict | None:
    cur = connexion().execute(sql, params)
    try:
        r = cur.fetchone()
        return dict(r) if r else None
    finally:
        cur.close()


def valeur(sql: str, params=(), defaut=None):
    cur = connexion().execute(sql, params)
    try:
        r = cur.fetchone()
        if r is None or r[0] is None:
            return defaut
        return r[0]
    finally:
        cur.close()


def execute(sql: str, params=()) -> sqlite3.Cursor:
    return connexion().execute(sql, params)


def insere(table: str, donnees: dict) -> int:
    colonnes = list(donnees.keys())
    marques = ", ".join("?" for _ in colonnes)
    sql = f"INSERT INTO {table} ({', '.join(colonnes)}) VALUES ({marques})"
    cur = connexion().execute(sql, [donnees[c] for c in colonnes])
    try:
        return cur.lastrowid
    finally:
        cur.close()


def modifie(table: str, identifiant: int, donnees: dict) -> None:
    if not donnees:
        return
    colonnes = list(donnees.keys())
    affectations = ", ".join(f"{c} = ?" for c in colonnes)
    sql = f"UPDATE {table} SET {affectations} WHERE id = ?"
    connexion().execute(sql, [donnees[c] for c in colonnes] + [identifiant])


def supprime(table: str, identifiant: int) -> None:
    connexion().execute(f"DELETE FROM {table} WHERE id = ?", (identifiant,))


class transaction:
    """Gestionnaire de contexte : BEGIN IMMEDIATE / COMMIT / ROLLBACK.

    Sérialise les écritures entre threads pour éviter tout entrelacement au
    milieu d'une écriture comptable en partie double.
    """

    def __enter__(self):
        _verrou_ecriture.acquire()
        conn = connexion()
        if not conn.in_transaction:
            conn.execute("BEGIN IMMEDIATE")
            self._proprietaire = True
        else:
            self._proprietaire = False
        return conn

    def __exit__(self, type_exc, valeur_exc, trace):
        conn = connexion()
        try:
            if self._proprietaire and conn.in_transaction:
                if type_exc is None:
                    conn.execute("COMMIT")
                else:
                    conn.execute("ROLLBACK")
        finally:
            _verrou_ecriture.release()
        return False


# ---------------------------------------------------------------------------
# Initialisation du schéma
# ---------------------------------------------------------------------------

SCHEMA = Path(__file__).parent / "schema.sql"


def initialise() -> None:
    config.prepare_dossiers()
    conn = connexion()
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    version = valeur("SELECT valeur FROM meta WHERE cle = 'version_schema'")
    if version is None:
        execute("INSERT INTO meta (cle, valeur) VALUES ('version_schema', '1')")
        execute(
            "INSERT INTO meta (cle, valeur) VALUES ('cree_le', ?)",
            (util.maintenant(),),
        )
    charge_parametres_fiscaux_par_defaut()


def charge_parametres_fiscaux_par_defaut() -> None:
    """Insère les paramètres fiscaux de référence s'ils sont absents.

    Ne réécrit jamais une valeur déjà saisie par le comptable.
    """
    fichier = config.dossier_reference / "parametres_fiscaux.json"
    if not fichier.exists():
        return
    donnees = json.loads(fichier.read_text(encoding="utf-8"))
    with transaction():
        for annee_txt, params in donnees.get("annees", {}).items():
            annee = int(annee_txt)
            for cle, spec in params.items():
                if cle.startswith("_"):
                    continue
                if isinstance(spec, dict) and "tranches" in spec:
                    valeur_txt = json.dumps(spec["tranches"], ensure_ascii=False)
                    unite = "bareme"
                elif isinstance(spec, dict):
                    valeur_txt = str(spec.get("valeur", ""))
                    unite = spec.get("unite", "texte")
                else:
                    valeur_txt, unite = str(spec), "texte"
                libelle = spec.get("libelle") if isinstance(spec, dict) else None
                source = spec.get("source") if isinstance(spec, dict) else None
                execute(
                    "INSERT OR IGNORE INTO parametres_fiscaux "
                    "(annee, cle, valeur, libelle, unite, source) VALUES (?,?,?,?,?,?)",
                    (annee, cle, valeur_txt, libelle, unite, source),
                )


def parametre_fiscal(annee: int, cle: str, defaut=None):
    """Récupère un paramètre fiscal, avec repli sur l'année disponible la plus proche."""
    val = valeur(
        "SELECT valeur FROM parametres_fiscaux WHERE annee = ? AND cle = ?",
        (annee, cle),
    )
    if val is None:
        val = valeur(
            "SELECT valeur FROM parametres_fiscaux WHERE cle = ? AND annee <= ? "
            "ORDER BY annee DESC LIMIT 1",
            (cle, annee),
        )
    if val is None:
        val = valeur(
            "SELECT valeur FROM parametres_fiscaux WHERE cle = ? ORDER BY annee ASC LIMIT 1",
            (cle,),
        )
    return defaut if val is None else val


def parametre_fiscal_int(annee: int, cle: str, defaut: int = 0) -> int:
    val = parametre_fiscal(annee, cle)
    if val is None:
        return defaut
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return defaut


def bareme_irg(annee: int) -> list[dict]:
    brut = parametre_fiscal(annee, "irg_bareme_mensuel")
    if not brut:
        return []
    try:
        return json.loads(brut)
    except ValueError:
        return []


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

def trace(action: str, entite: str, entite_id=None, details=None, utilisateur=None) -> None:
    execute(
        "INSERT INTO audit (horodatage, utilisateur, action, entite, entite_id, details) "
        "VALUES (?,?,?,?,?,?)",
        (util.maintenant(), utilisateur, action, entite, entite_id,
         details if isinstance(details, str) or details is None
         else json.dumps(details, ensure_ascii=False)),
    )


# ---------------------------------------------------------------------------
# Compteurs de numérotation (séquences sans trou, par société / clé / année)
# ---------------------------------------------------------------------------

FORMATS_DEFAUT = {
    "facture_vente": "FV{annee}-{numero:04d}",
    "facture_achat": "FA{annee}-{numero:04d}",
    "avoir_vente": "AV{annee}-{numero:04d}",
    "avoir_achat": "AA{annee}-{numero:04d}",
    "proforma": "PF{annee}-{numero:04d}",
    "reglement": "REG{annee}-{numero:05d}",
    "quittance": "Q{annee}-{numero:05d}",
    "mandat": "MDT{annee}-{numero:04d}",
    "transaction": "TR{annee}-{numero:04d}",
    "bail": "BAIL{annee}-{numero:04d}",
    "contrat_vsp": "VSP{annee}-{numero:04d}",
    "bien": "B{numero:05d}",
    "situation": "ST{annee}-{numero:04d}",
    "tiers_client": "C{numero:05d}",
    "tiers_fournisseur": "F{numero:05d}",
    "tiers_mandant": "P{numero:05d}",
    "tiers_salarie": "S{numero:04d}",
    "tiers_autre": "T{numero:05d}",
}


def numero_suivant(societe_id: int, cle: str, annee: int | None = None) -> str:
    """Attribue le numéro suivant de façon atomique (à appeler dans une transaction)."""
    annee = annee or int(util.aujourdhui()[:4])
    execute(
        "INSERT OR IGNORE INTO compteurs (societe_id, cle, annee, valeur, format) "
        "VALUES (?,?,?,0,?)",
        (societe_id, cle, annee, FORMATS_DEFAUT.get(cle, "{annee}-{numero:05d}")),
    )
    execute(
        "UPDATE compteurs SET valeur = valeur + 1 WHERE societe_id = ? AND cle = ? AND annee = ?",
        (societe_id, cle, annee),
    )
    enregistrement = ligne(
        "SELECT valeur, format FROM compteurs WHERE societe_id = ? AND cle = ? AND annee = ?",
        (societe_id, cle, annee),
    )
    gabarit = enregistrement["format"] or "{annee}-{numero:05d}"
    try:
        return gabarit.format(annee=annee, numero=enregistrement["valeur"],
                              annee_courte=str(annee)[2:])
    except (KeyError, ValueError):
        return f"{annee}-{enregistrement['valeur']:05d}"
