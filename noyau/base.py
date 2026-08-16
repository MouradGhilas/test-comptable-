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

#: Version du schéma attendue par cette version du programme.
#: À incrémenter dès qu'une migration est ajoutée ci-dessous.
VERSION_SCHEMA = 3


def colonnes(table: str) -> set[str]:
    cur = connexion().execute(f"PRAGMA table_info({table})")
    try:
        return {r[1] for r in cur.fetchall()}
    finally:
        cur.close()


def table_existe(table: str) -> bool:
    return bool(valeur(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)))


def ajoute_colonne(table: str, colonne: str, definition: str) -> bool:
    """Ajoute une colonne si elle manque. Idempotent : ne fait rien sinon.

    C'est le cœur des mises à jour sans perte de données — une base existante
    reçoit les nouvelles colonnes, une base neuve les a déjà par le schéma.
    """
    if not table_existe(table) or colonne in colonnes(table):
        return False
    execute(f"ALTER TABLE {table} ADD COLUMN {colonne} {definition}")
    return True


def _migration_2() -> None:
    """Périmètre déclaratif : chaque opération est marquée « déclaré » ou
    « hors déclaration », afin de séparer nettement ce qui entre dans les
    déclarations fiscales de ce qui n'y entre pas.

    Les opérations déjà saisies sont réputées déclarées (valeur par défaut) :
    aucune donnée existante n'est modifiée ni perdue.
    """
    for table in ("ecritures", "factures", "reglements", "quittances"):
        ajoute_colonne(table, "perimetre", "TEXT NOT NULL DEFAULT 'declare'")
    ajoute_colonne("societes", "perimetre_defaut", "TEXT NOT NULL DEFAULT 'declare'")
    ajoute_colonne("societes", "suivi_hors_declaration", "INTEGER NOT NULL DEFAULT 1")


#: Index portant sur des colonnes introduites par migration. Créés une fois les
#: migrations appliquées, et seulement si la colonne existe réellement.
INDEX_COMPLEMENTAIRES = [
    ("idx_ecr_perimetre", "ecritures", "societe_id, perimetre", ["perimetre"]),
]


def _cree_index_complementaires() -> None:
    for nom, table, expression, requises in INDEX_COMPLEMENTAIRES:
        if not table_existe(table):
            continue
        if not set(requises) <= colonnes(table):
            continue
        execute(f"CREATE INDEX IF NOT EXISTS {nom} ON {table}({expression})")


def _migration_3() -> None:
    """Canaux de notification : la table est créée par le schéma ; cette
    migration ne sert qu'à marquer le palier de version."""
    return None


#: version -> fonction de migration. Exécutées dans l'ordre croissant.
MIGRATIONS = {
    2: _migration_2,
    3: _migration_3,
}


def version_schema() -> int:
    brut = valeur("SELECT valeur FROM meta WHERE cle = 'version_schema'")
    try:
        return int(brut) if brut is not None else 0
    except (TypeError, ValueError):
        return 0


def initialise(sauvegarde_avant_migration: bool = True) -> dict:
    """Crée ou met à niveau la base, sans jamais toucher aux données existantes.

    Retourne un rapport : version de départ, version d'arrivée, migrations
    appliquées, sauvegarde éventuellement créée.
    """
    config.prepare_dossiers()
    conn = connexion()

    base_neuve = not config.base_de_donnees.exists() or not table_existe("meta")
    depart = 0 if base_neuve else version_schema()

    # `CREATE TABLE IF NOT EXISTS` : ajoute les tables manquantes sans rien
    # écraser. Les colonnes ajoutées à des tables existantes relèvent des
    # migrations ci-dessous.
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))

    rapport = {"version_depart": depart, "version_arrivee": depart,
               "migrations": [], "sauvegarde": None, "base_neuve": base_neuve}

    if base_neuve:
        with transaction():
            execute("INSERT OR REPLACE INTO meta (cle, valeur) VALUES "
                    "('version_schema', ?)", (str(VERSION_SCHEMA),))
            execute("INSERT OR REPLACE INTO meta (cle, valeur) VALUES (?, ?)",
                    ("cree_le", util.maintenant()))
        rapport["version_arrivee"] = VERSION_SCHEMA
    elif depart < VERSION_SCHEMA:
        # Filet de sécurité : on archive la base avant toute transformation.
        if sauvegarde_avant_migration:
            try:
                rapport["sauvegarde"] = _archive_avant_migration(depart)
            except Exception as err:                      # noqa: BLE001
                print(f"[migration] Sauvegarde préalable impossible : {err}")

        for version in sorted(MIGRATIONS):
            if version <= depart:
                continue
            with transaction():
                MIGRATIONS[version]()
                execute("INSERT OR REPLACE INTO meta (cle, valeur) VALUES "
                        "('version_schema', ?)", (str(version),))
                trace("migration", "base", None, {"version": version})
            rapport["migrations"].append(version)
            print(f"[migration] Base mise à niveau en version {version}.")
        rapport["version_arrivee"] = version_schema()
    elif depart > VERSION_SCHEMA:
        raise RuntimeError(
            f"Cette base a été créée par une version plus récente du programme "
            f"(schéma {depart} > {VERSION_SCHEMA}). Mettez l'application à jour "
            "avant de l'ouvrir, sous peine de corrompre les données."
        )

    _cree_index_complementaires()
    charge_parametres_fiscaux_par_defaut()
    return rapport


def _archive_avant_migration(version: int) -> str:
    """Copie la base telle quelle avant migration, dans les sauvegardes."""
    horodatage = util.maintenant().replace(":", "").replace("-", "").replace(" ", "_")
    cible = (config.dossier_sauvegardes
             / f"avant_migration_v{version}_{horodatage}.db")
    destination = sqlite3.connect(str(cible))
    try:
        connexion().backup(destination)
    finally:
        destination.close()
    return cible.name


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
