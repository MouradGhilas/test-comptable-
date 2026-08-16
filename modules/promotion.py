"""Promotion immobilière — loi n° 11-04 du 17 février 2011.

Chaîne métier couverte :
  programme → tranches → lots → contrat de vente sur plan (VSP) →
  échéancier adossé à l'avancement des travaux → appels de fonds →
  encaissements → livraison → constatation du produit.

Points comptables structurants :

* Les sommes encaissées avant livraison **ne sont pas un chiffre d'affaires** :
  ce sont des avances (compte 419x « Clients créditeurs »). Le produit
  (compte 701x) n'est constaté qu'à la livraison du lot — ou à l'avancement
  si le programme est configuré ainsi.
* Les dépenses du programme sont enregistrées par nature en classe 6 avec un
  axe analytique « programme », puis stockées en travaux en cours
  (332 / 723) à chaque arrêté, et transférées en produits finis (355 / 724)
  à l'achèvement. C'est le traitement SCF de la construction-vente.
* Le coût de revient est réparti sur les lots au prorata de la surface ou du
  prix, ce qui donne la marge réelle par logement.
"""

from __future__ import annotations

import json

from noyau import base as db
from noyau import util
from noyau import tableur
from noyau.serveur import ErreurApplicative, route, Reponse
from modules import comptabilite as compta

COMPTE_AVANCE_VSP = "4191"
COMPTE_ARRHES = "4192"
COMPTE_TVA_COLLECTEE = "4457"
COMPTE_TVA_A_REGULARISER = "4458"
COMPTE_ENCOURS = "332"
COMPTE_VARIATION_ENCOURS = "723"
COMPTE_PRODUITS_FINIS = "355"
COMPTE_VARIATION_PRODUITS_FINIS = "724"
COMPTE_FGCMPI = "6225"

COMPTES_VENTE = {
    "logement": "7011",
    "local_commercial": "7012",
    "bureau": "7012",
    "parking": "7013",
    "cave": "7013",
    "terrain": "701",
}


def programme_ou_erreur(programme_id: int) -> dict:
    p = db.ligne("SELECT * FROM programmes WHERE id = ?", (programme_id,))
    if not p:
        raise ErreurApplicative("Programme introuvable.", 404)
    return p


def contrat_ou_erreur(contrat_id: int) -> dict:
    c = db.ligne("SELECT * FROM contrats_vsp WHERE id = ?", (contrat_id,))
    if not c:
        raise ErreurApplicative("Contrat introuvable.", 404)
    return c


# ===========================================================================
# PROGRAMMES
# ===========================================================================

@route("GET", "/api/programmes")
def api_programmes(ctx):
    societe_id = ctx.arg_int("societe")
    conditions = ["p.societe_id = ?"]
    params: list = [societe_id]
    if ctx.arg("statut"):
        conditions.append("p.statut = ?")
        params.append(ctx.arg("statut"))
    programmes = db.lignes(
        "SELECT p.*, "
        "  (SELECT COUNT(*) FROM lots WHERE programme_id = p.id) AS nb_lots_saisis, "
        "  (SELECT COUNT(*) FROM lots WHERE programme_id = p.id AND statut IN ('vendu','livre')) AS nb_vendus, "
        "  (SELECT COUNT(*) FROM lots WHERE programme_id = p.id AND statut = 'reserve') AS nb_reserves, "
        "  (SELECT COALESCE(SUM(montant_encaisse),0) FROM contrats_vsp WHERE programme_id = p.id) AS encaisse, "
        "  (SELECT COALESCE(SUM(prix_total),0) FROM contrats_vsp WHERE programme_id = p.id AND statut <> 'resilie') AS vendu "
        "FROM programmes p "
        f"WHERE {' AND '.join(conditions)} ORDER BY p.statut, p.intitule", params
    )
    for p in programmes:
        p["budget_total"] = (p["budget_terrain"] + p["budget_etudes"] + p["budget_travaux"]
                             + p["budget_vrd"] + p["budget_frais_divers"]
                             + p["budget_frais_financiers"])
        p["cout_engage"] = _cout_engage(societe_id, p["id"])
    return {"programmes": programmes}


@route("GET", "/api/programmes/<id>")
def api_programme(ctx):
    identifiant = int(ctx.params["id"])
    p = programme_ou_erreur(identifiant)
    p["tranches"] = db.lignes(
        "SELECT * FROM tranches WHERE programme_id = ? ORDER BY code", (identifiant,))
    p["lots"] = db.lignes(
        "SELECT l.*, t.code AS tranche_code, c.numero AS contrat_numero, "
        "       c.id AS contrat_id, ti.raison_sociale AS acquereur "
        "FROM lots l LEFT JOIN tranches t ON t.id = l.tranche_id "
        "LEFT JOIN contrats_vsp c ON c.lot_id = l.id AND c.statut <> 'resilie' "
        "LEFT JOIN tiers ti ON ti.id = c.acquereur_id "
        "WHERE l.programme_id = ? ORDER BY l.numero", (identifiant,))
    p["budget_lignes"] = db.lignes(
        "SELECT * FROM budget_lignes WHERE programme_id = ? ORDER BY ordre", (identifiant,))
    p["budget_total"] = (p["budget_terrain"] + p["budget_etudes"] + p["budget_travaux"]
                         + p["budget_vrd"] + p["budget_frais_divers"]
                         + p["budget_frais_financiers"])
    p["cout_engage"] = _cout_engage(p["societe_id"], identifiant)
    p["contrats"] = db.lignes(
        "SELECT c.*, l.numero AS lot_numero, t.raison_sociale AS acquereur "
        "FROM contrats_vsp c JOIN lots l ON l.id = c.lot_id "
        "JOIN tiers t ON t.id = c.acquereur_id WHERE c.programme_id = ? "
        "ORDER BY c.numero", (identifiant,))
    p["synthese"] = _synthese_programme(p)
    return p


def _solde_avances(societe_id: int, lot_id: int, tiers_id: int) -> int:
    """Solde créditeur réel du compte 419x pour un lot donné, en centimes."""
    return int(db.valeur(
        "SELECT COALESCE(SUM(l.credit - l.debit),0) FROM lignes l "
        "JOIN ecritures e ON e.id = l.ecriture_id "
        "WHERE e.societe_id = ? AND l.compte LIKE '419%' AND l.lot_id = ? "
        "AND l.tiers_id = ?",
        (societe_id, lot_id, tiers_id), 0
    ))


def _cout_engage(societe_id: int, programme_id: int) -> int:
    """Total des charges (classe 6) imputées analytiquement au programme."""
    return int(db.valeur(
        "SELECT COALESCE(SUM(l.debit - l.credit),0) FROM lignes l "
        "JOIN ecritures e ON e.id = l.ecriture_id "
        "WHERE e.societe_id = ? AND l.programme_id = ? AND l.compte LIKE '6%'",
        (societe_id, programme_id), 0
    ))


def _synthese_programme(p: dict) -> dict:
    programme_id = p["id"]
    societe_id = p["societe_id"]
    lots = db.lignes("SELECT * FROM lots WHERE programme_id = ?", (programme_id,))
    contrats = db.lignes(
        "SELECT * FROM contrats_vsp WHERE programme_id = ? AND statut <> 'resilie'",
        (programme_id,))
    budget_total = (p["budget_terrain"] + p["budget_etudes"] + p["budget_travaux"]
                    + p["budget_vrd"] + p["budget_frais_divers"]
                    + p["budget_frais_financiers"])
    cout_engage = _cout_engage(societe_id, programme_id)
    ca_prevu = p["chiffre_affaires_prevu"] or sum(l["prix_vente"] for l in lots)
    ca_contractualise = sum(c["prix_total"] for c in contrats)
    encaisse = sum(c["montant_encaisse"] for c in contrats)
    surface_totale = sum(l["surface_habitable"] for l in lots)

    return {
        "nb_lots": len(lots),
        "nb_disponibles": sum(1 for l in lots if l["statut"] == "disponible"),
        "nb_reserves": sum(1 for l in lots if l["statut"] == "reserve"),
        "nb_vendus": sum(1 for l in lots if l["statut"] in ("vendu", "livre")),
        "surface_totale": surface_totale,
        "budget_total": budget_total,
        "cout_engage": cout_engage,
        "reste_a_engager": budget_total - cout_engage,
        "taux_consommation_budget": (util.part_proportionnelle(util.BASE_TAUX, cout_engage,
                                                              budget_total)
                                     if budget_total else 0),
        "ca_prevu": ca_prevu,
        "ca_contractualise": ca_contractualise,
        "taux_commercialisation": (util.part_proportionnelle(util.BASE_TAUX, ca_contractualise,
                                                            ca_prevu) if ca_prevu else 0),
        "encaisse": encaisse,
        "reste_a_encaisser": ca_contractualise - encaisse,
        "marge_prevue": ca_prevu - budget_total,
        "marge_taux": (util.part_proportionnelle(util.BASE_TAUX, ca_prevu - budget_total, ca_prevu)
                       if ca_prevu else 0),
        "prix_revient_m2": (util.part_proportionnelle(budget_total, 100, surface_totale)
                            if surface_totale else 0),
        "avancement": p["avancement"],
    }


@route("POST", "/api/programmes")
def api_cree_programme(ctx):
    ctx.interdit_lecture_seule()
    societe_id = ctx.entier("societe_id")
    code = str(ctx.champ_requis("code")).upper()[:20]
    if db.ligne("SELECT id FROM programmes WHERE societe_id = ? AND code = ?",
                (societe_id, code)):
        raise ErreurApplicative(f"Le programme « {code} » existe déjà.")
    with db.transaction():
        identifiant = db.insere("programmes", {
            "societe_id": societe_id, "code": code,
            "intitule": ctx.champ_requis("intitule"),
            "adresse": util.nettoie(ctx.champ("adresse")),
            "commune": util.nettoie(ctx.champ("commune")),
            "wilaya": util.nettoie(ctx.champ("wilaya")),
            "surface_terrain": int(round(float(ctx.champ("surface_terrain") or 0) * 100)),
            "surface_batie": int(round(float(ctx.champ("surface_batie") or 0) * 100)),
            "nb_logements": ctx.entier("nb_logements", 0) or 0,
            "nb_locaux": ctx.entier("nb_locaux", 0) or 0,
            "num_permis_construire": util.nettoie(ctx.champ("num_permis_construire")),
            "date_permis": ctx.date("date_permis"),
            "num_acte_terrain": util.nettoie(ctx.champ("num_acte_terrain")),
            "date_acte_terrain": ctx.date("date_acte_terrain"),
            "date_debut_travaux": ctx.date("date_debut_travaux"),
            "date_fin_prevue": ctx.date("date_fin_prevue"),
            "budget_terrain": ctx.montant("budget_terrain"),
            "budget_etudes": ctx.montant("budget_etudes"),
            "budget_travaux": ctx.montant("budget_travaux"),
            "budget_vrd": ctx.montant("budget_vrd"),
            "budget_frais_divers": ctx.montant("budget_frais_divers"),
            "budget_frais_financiers": ctx.montant("budget_frais_financiers"),
            "chiffre_affaires_prevu": ctx.montant("chiffre_affaires_prevu"),
            "methode_produit": ctx.champ("methode_produit", "achevement"),
            "fait_generateur_tva": ctx.champ("fait_generateur_tva", "livraison"),
            "taux_tva": ctx.taux("taux_tva", 1900),
            "avancement": 0,
            "statut": ctx.champ("statut", "etude"),
            "fgcmpi_police": util.nettoie(ctx.champ("fgcmpi_police")),
            "fgcmpi_taux": ctx.taux("fgcmpi_taux"),
            "notes": util.nettoie(ctx.champ("notes")),
            "cree_le": util.maintenant(),
        })
        # Postes budgétaires types (suivi budget / réalisé par nature de dépense)
        for poste in _postes_budget_type():
            db.insere("budget_lignes", {
                "programme_id": identifiant, "poste": poste["poste"],
                "libelle": poste["libelle"], "montant_prevu": 0,
                "comptes": poste["comptes"], "ordre": poste["ordre"],
            })
        db.trace("creation", "programme", identifiant, code, ctx.nom_utilisateur)
    return {"id": identifiant}


def _postes_budget_type() -> list[dict]:
    from noyau.config import config
    donnees = json.loads(
        (config.dossier_reference / "plan_comptable_scf.json").read_text("utf-8")
    )
    return donnees.get("budget_type_promotion", [])


@route("PUT", "/api/programmes/<id>")
def api_modifie_programme(ctx):
    ctx.interdit_lecture_seule()
    identifiant = int(ctx.params["id"])
    with db.transaction():
        db.modifie("programmes", identifiant, {
            "intitule": ctx.champ_requis("intitule"),
            "adresse": util.nettoie(ctx.champ("adresse")),
            "commune": util.nettoie(ctx.champ("commune")),
            "wilaya": util.nettoie(ctx.champ("wilaya")),
            "surface_terrain": int(round(float(ctx.champ("surface_terrain") or 0) * 100)),
            "surface_batie": int(round(float(ctx.champ("surface_batie") or 0) * 100)),
            "nb_logements": ctx.entier("nb_logements", 0) or 0,
            "nb_locaux": ctx.entier("nb_locaux", 0) or 0,
            "num_permis_construire": util.nettoie(ctx.champ("num_permis_construire")),
            "date_permis": ctx.date("date_permis"),
            "num_acte_terrain": util.nettoie(ctx.champ("num_acte_terrain")),
            "date_acte_terrain": ctx.date("date_acte_terrain"),
            "num_certificat_conformite": util.nettoie(ctx.champ("num_certificat_conformite")),
            "date_conformite": ctx.date("date_conformite"),
            "date_debut_travaux": ctx.date("date_debut_travaux"),
            "date_fin_prevue": ctx.date("date_fin_prevue"),
            "date_livraison": ctx.date("date_livraison"),
            "budget_terrain": ctx.montant("budget_terrain"),
            "budget_etudes": ctx.montant("budget_etudes"),
            "budget_travaux": ctx.montant("budget_travaux"),
            "budget_vrd": ctx.montant("budget_vrd"),
            "budget_frais_divers": ctx.montant("budget_frais_divers"),
            "budget_frais_financiers": ctx.montant("budget_frais_financiers"),
            "chiffre_affaires_prevu": ctx.montant("chiffre_affaires_prevu"),
            "methode_produit": ctx.champ("methode_produit", "achevement"),
            "fait_generateur_tva": ctx.champ("fait_generateur_tva", "livraison"),
            "taux_tva": ctx.taux("taux_tva", 1900),
            "statut": ctx.champ("statut", "etude"),
            "fgcmpi_police": util.nettoie(ctx.champ("fgcmpi_police")),
            "fgcmpi_taux": ctx.taux("fgcmpi_taux"),
            "notes": util.nettoie(ctx.champ("notes")),
        })
    return {"ok": True}


@route("POST", "/api/programmes/<id>/avancement")
def api_avancement(ctx):
    """Met à jour l'avancement des travaux et rend exigibles les échéances liées."""
    ctx.interdit_lecture_seule()
    identifiant = int(ctx.params["id"])
    p = programme_ou_erreur(identifiant)
    avancement = ctx.taux("avancement")
    if avancement < 0 or avancement > util.BASE_TAUX:
        raise ErreurApplicative("L'avancement doit être compris entre 0 et 100 %.")

    with db.transaction():
        db.modifie("programmes", identifiant, {"avancement": avancement})
        devenues_exigibles = db.lignes(
            "SELECT ev.id FROM echeances_vsp ev JOIN contrats_vsp c ON c.id = ev.contrat_id "
            "WHERE c.programme_id = ? AND c.statut = 'en_cours' "
            "AND ev.declencheur = 'avancement' AND ev.seuil_avancement <= ? "
            "AND ev.statut = 'a_venir'", (identifiant, avancement)
        )
        for e in devenues_exigibles:
            db.modifie("echeances_vsp", e["id"], {"statut": "exigible"})
        db.trace("avancement", "programme", identifiant,
                 {"avancement": avancement, "echeances": len(devenues_exigibles)},
                 ctx.nom_utilisateur)
    return {"avancement": avancement, "echeances_exigibles": len(devenues_exigibles),
            "message": f"Avancement porté à {util.taux_pourcent(avancement)} %. "
                       f"{len(devenues_exigibles)} échéance(s) deviennent exigibles."}


# ===========================================================================
# TRANCHES & LOTS
# ===========================================================================

@route("POST", "/api/tranches")
def api_cree_tranche(ctx):
    ctx.interdit_lecture_seule()
    with db.transaction():
        identifiant = db.insere("tranches", {
            "programme_id": ctx.entier("programme_id"),
            "code": str(ctx.champ_requis("code")).upper()[:16],
            "intitule": ctx.champ_requis("intitule"),
            "nb_lots": ctx.entier("nb_lots", 0) or 0,
            "date_debut": ctx.date("date_debut"),
            "date_livraison_prevue": ctx.date("date_livraison_prevue"),
            "avancement": ctx.taux("avancement"),
            "statut": ctx.champ("statut", "en_cours"),
        })
    return {"id": identifiant}


@route("GET", "/api/lots")
def api_lots(ctx):
    societe_id = ctx.arg_int("societe")
    conditions = ["l.societe_id = ?"]
    params: list = [societe_id]
    if ctx.arg("programme"):
        conditions.append("l.programme_id = ?")
        params.append(ctx.arg_int("programme"))
    if ctx.arg("statut"):
        conditions.append("l.statut = ?")
        params.append(ctx.arg("statut"))
    if ctx.arg("type"):
        conditions.append("l.type_lot = ?")
        params.append(ctx.arg("type"))
    return {"lots": db.lignes(
        "SELECT l.*, p.intitule AS programme, p.code AS programme_code, "
        "       c.numero AS contrat_numero, c.id AS contrat_id, "
        "       c.montant_encaisse, c.prix_total AS prix_contrat, "
        "       ti.raison_sociale AS acquereur "
        "FROM lots l JOIN programmes p ON p.id = l.programme_id "
        "LEFT JOIN contrats_vsp c ON c.lot_id = l.id AND c.statut <> 'resilie' "
        "LEFT JOIN tiers ti ON ti.id = c.acquereur_id "
        f"WHERE {' AND '.join(conditions)} ORDER BY p.code, l.numero LIMIT 2000", params
    )}


@route("POST", "/api/lots")
def api_cree_lot(ctx):
    ctx.interdit_lecture_seule()
    programme_id = ctx.entier("programme_id")
    p = programme_ou_erreur(programme_id)
    numero = str(ctx.champ_requis("numero")).strip()
    if db.ligne("SELECT id FROM lots WHERE programme_id = ? AND numero = ?",
                (programme_id, numero)):
        raise ErreurApplicative(f"Le lot n° {numero} existe déjà dans ce programme.")
    surface = int(round(float(ctx.champ("surface_habitable") or 0) * 100))
    prix_m2 = ctx.montant("prix_m2")
    prix_vente = ctx.montant("prix_vente") or util.part_proportionnelle(prix_m2, surface, 100)
    with db.transaction():
        identifiant = db.insere("lots", {
            "societe_id": p["societe_id"], "programme_id": programme_id,
            "tranche_id": ctx.entier("tranche_id"), "numero": numero,
            "type_lot": ctx.champ("type_lot", "logement"),
            "typologie": util.nettoie(ctx.champ("typologie")),
            "batiment": util.nettoie(ctx.champ("batiment")),
            "etage": util.nettoie(ctx.champ("etage")),
            "surface_habitable": surface,
            "surface_utile": int(round(float(ctx.champ("surface_utile") or 0) * 100)),
            "quote_part_terrain": ctx.entier("quote_part_terrain", 0) or 0,
            "prix_m2": prix_m2, "prix_vente": prix_vente, "cout_revient": 0,
            "statut": ctx.champ("statut", "disponible"),
            "notes": util.nettoie(ctx.champ("notes")),
        })
    return {"id": identifiant}


@route("POST", "/api/lots/generer")
def api_genere_lots(ctx):
    """Création en série des lots d'un bâtiment (gain de temps à la saisie)."""
    ctx.interdit_lecture_seule()
    programme_id = ctx.entier("programme_id")
    p = programme_ou_erreur(programme_id)
    modele = ctx.champ("lots") or []
    if not modele:
        raise ErreurApplicative("Aucun lot à générer.")
    crees = 0
    with db.transaction():
        for spec in modele:
            numero = str(spec.get("numero") or "").strip()
            if not numero:
                continue
            if db.ligne("SELECT id FROM lots WHERE programme_id = ? AND numero = ?",
                        (programme_id, numero)):
                continue
            surface = int(round(float(spec.get("surface_habitable") or 0) * 100))
            prix_m2 = util.centimes(spec.get("prix_m2"))
            prix = (util.centimes(spec.get("prix_vente"))
                    or util.part_proportionnelle(prix_m2, surface, 100))
            db.insere("lots", {
                "societe_id": p["societe_id"], "programme_id": programme_id,
                "tranche_id": spec.get("tranche_id") or ctx.entier("tranche_id"),
                "numero": numero,
                "type_lot": spec.get("type_lot", "logement"),
                "typologie": spec.get("typologie"),
                "batiment": spec.get("batiment"), "etage": spec.get("etage"),
                "surface_habitable": surface, "surface_utile": 0,
                "quote_part_terrain": 0, "prix_m2": prix_m2, "prix_vente": prix,
                "cout_revient": 0, "statut": "disponible",
            })
            crees += 1
    return {"crees": crees}


@route("PUT", "/api/lots/<id>")
def api_modifie_lot(ctx):
    ctx.interdit_lecture_seule()
    identifiant = int(ctx.params["id"])
    surface = int(round(float(ctx.champ("surface_habitable") or 0) * 100))
    prix_m2 = ctx.montant("prix_m2")
    with db.transaction():
        db.modifie("lots", identifiant, {
            "tranche_id": ctx.entier("tranche_id"),
            "numero": str(ctx.champ_requis("numero")).strip(),
            "type_lot": ctx.champ("type_lot", "logement"),
            "typologie": util.nettoie(ctx.champ("typologie")),
            "batiment": util.nettoie(ctx.champ("batiment")),
            "etage": util.nettoie(ctx.champ("etage")),
            "surface_habitable": surface,
            "surface_utile": int(round(float(ctx.champ("surface_utile") or 0) * 100)),
            "quote_part_terrain": ctx.entier("quote_part_terrain", 0) or 0,
            "prix_m2": prix_m2,
            "prix_vente": ctx.montant("prix_vente")
                          or util.part_proportionnelle(prix_m2, surface, 100),
            "statut": ctx.champ("statut", "disponible"),
            "notes": util.nettoie(ctx.champ("notes")),
        })
    return {"ok": True}


@route("DELETE", "/api/lots/<id>")
def api_supprime_lot(ctx):
    ctx.exige_role("admin", "comptable")
    identifiant = int(ctx.params["id"])
    if db.valeur("SELECT COUNT(*) FROM contrats_vsp WHERE lot_id = ?", (identifiant,), 0):
        raise ErreurApplicative("Ce lot fait l'objet d'un contrat : suppression impossible.")
    with db.transaction():
        db.supprime("lots", identifiant)
    return {"ok": True}


@route("POST", "/api/programmes/<id>/repartir-cout")
def api_repartit_cout(ctx):
    """Répartit le coût de revient du programme sur les lots.

    Clé de répartition : surface habitable (défaut) ou prix de vente.
    """
    ctx.interdit_lecture_seule()
    identifiant = int(ctx.params["id"])
    p = programme_ou_erreur(identifiant)
    lots = db.lignes("SELECT * FROM lots WHERE programme_id = ? ORDER BY numero",
                     (identifiant,))
    if not lots:
        raise ErreurApplicative("Ce programme ne comporte aucun lot.")

    base = ctx.champ("base", "reel")   # reel = coût engagé, budget = budget prévisionnel
    cle = ctx.champ("cle", "surface")
    if base == "budget":
        total = (p["budget_terrain"] + p["budget_etudes"] + p["budget_travaux"]
                 + p["budget_vrd"] + p["budget_frais_divers"] + p["budget_frais_financiers"])
    else:
        total = _cout_engage(p["societe_id"], identifiant)
    if total <= 0:
        raise ErreurApplicative(
            "Aucun coût à répartir : renseignez le budget ou imputez des charges "
            "au programme."
        )

    poids = [l["surface_habitable"] if cle == "surface" else l["prix_vente"] for l in lots]
    if sum(poids) == 0:
        raise ErreurApplicative(
            f"La clé de répartition « {cle} » est nulle sur tous les lots."
        )
    parts = util.repartir(total, poids)

    with db.transaction():
        for lot, part in zip(lots, parts):
            db.modifie("lots", lot["id"], {"cout_revient": part})
        db.trace("repartition_cout", "programme", identifiant,
                 {"total": total, "cle": cle, "base": base}, ctx.nom_utilisateur)
    return {"total_reparti": total, "lots": len(lots), "cle": cle}


# ===========================================================================
# CONTRATS DE VENTE SUR PLAN
# ===========================================================================

@route("GET", "/api/contrats-vsp")
def api_contrats(ctx):
    societe_id = ctx.arg_int("societe")
    conditions = ["c.societe_id = ?"]
    params: list = [societe_id]
    if ctx.arg("programme"):
        conditions.append("c.programme_id = ?")
        params.append(ctx.arg_int("programme"))
    if ctx.arg("statut"):
        conditions.append("c.statut = ?")
        params.append(ctx.arg("statut"))
    if ctx.arg("q"):
        conditions.append("(c.numero LIKE ? OR t.raison_sociale LIKE ? OR l.numero LIKE ?)")
        motif = "%" + ctx.arg("q") + "%"
        params += [motif, motif, motif]
    return {"contrats": db.lignes(
        "SELECT c.*, l.numero AS lot_numero, l.typologie, l.surface_habitable, "
        "       p.intitule AS programme, p.code AS programme_code, "
        "       t.raison_sociale AS acquereur, t.telephone AS acquereur_tel "
        "FROM contrats_vsp c JOIN lots l ON l.id = c.lot_id "
        "JOIN programmes p ON p.id = c.programme_id "
        "JOIN tiers t ON t.id = c.acquereur_id "
        f"WHERE {' AND '.join(conditions)} ORDER BY c.date_contrat DESC LIMIT 800", params
    )}


@route("GET", "/api/contrats-vsp/<id>")
def api_contrat(ctx):
    identifiant = int(ctx.params["id"])
    c = db.ligne(
        "SELECT c.*, l.numero AS lot_numero, l.typologie, l.surface_habitable, "
        "       l.etage, l.batiment, l.type_lot, "
        "       p.intitule AS programme, p.code AS programme_code, p.avancement, "
        "       p.fait_generateur_tva, p.adresse AS programme_adresse, "
        "       t.raison_sociale AS acquereur, t.telephone AS acquereur_tel, "
        "       t.adresse AS acquereur_adresse, t.piece_identite "
        "FROM contrats_vsp c JOIN lots l ON l.id = c.lot_id "
        "JOIN programmes p ON p.id = c.programme_id "
        "JOIN tiers t ON t.id = c.acquereur_id WHERE c.id = ?", (identifiant,)
    )
    if not c:
        raise ErreurApplicative("Contrat introuvable.", 404)
    c["echeances"] = db.lignes(
        "SELECT * FROM echeances_vsp WHERE contrat_id = ? ORDER BY ordre", (identifiant,))
    c["reste_a_encaisser"] = c["prix_total"] - c["montant_encaisse"]
    c["taux_encaissement"] = (util.part_proportionnelle(util.BASE_TAUX, c["montant_encaisse"],
                                                       c["prix_total"])
                              if c["prix_total"] else 0)
    return c


@route("GET", "/api/modeles-echeancier")
def api_modeles(ctx):
    modeles = db.lignes(
        "SELECT * FROM modeles_echeancier WHERE societe_id = ? OR societe_id IS NULL "
        "ORDER BY code", (ctx.arg_int("societe"),)
    )
    for m in modeles:
        m["lignes"] = json.loads(m["lignes"])
    return {"modeles": modeles}


@route("POST", "/api/contrats-vsp")
def api_cree_contrat(ctx):
    """Crée le contrat et son échéancier de paiement."""
    ctx.interdit_lecture_seule()
    societe_id = ctx.entier("societe_id")
    lot_id = ctx.entier("lot_id")
    lot = db.ligne("SELECT * FROM lots WHERE id = ?", (lot_id,))
    if not lot:
        raise ErreurApplicative("Sélectionnez le lot vendu.")
    existant = db.ligne(
        "SELECT numero FROM contrats_vsp WHERE lot_id = ? AND statut <> 'resilie'",
        (lot_id,))
    if existant:
        raise ErreurApplicative(
            f"Le lot n° {lot['numero']} fait déjà l'objet du contrat {existant['numero']}."
        )
    acquereur_id = ctx.entier("acquereur_id")
    if not acquereur_id:
        raise ErreurApplicative("Sélectionnez l'acquéreur.")
    p = programme_ou_erreur(lot["programme_id"])

    prix_total = ctx.montant("prix_total") or lot["prix_vente"]
    if prix_total <= 0:
        raise ErreurApplicative("Indiquez le prix de vente du lot.")
    taux_tva = ctx.taux("taux_tva", p["taux_tva"])
    prix_ht, tva = util.ht_depuis_ttc(prix_total, taux_tva)

    with db.transaction():
        numero = util.nettoie(ctx.champ("numero")) or db.numero_suivant(
            societe_id, "contrat_vsp")
        contrat_id = db.insere("contrats_vsp", {
            "societe_id": societe_id, "numero": numero,
            "programme_id": lot["programme_id"], "lot_id": lot_id,
            "acquereur_id": acquereur_id,
            "type_contrat": ctx.champ("type_contrat", "vsp"),
            "date_reservation": ctx.date("date_reservation"),
            "date_contrat": ctx.date("date_contrat", util.aujourdhui()),
            "notaire_id": ctx.entier("notaire_id"),
            "num_acte_notarie": util.nettoie(ctx.champ("num_acte_notarie")),
            "date_publication": ctx.date("date_publication"),
            "prix_total": prix_total, "prix_ht": prix_ht, "tva": tva,
            "taux_tva": taux_tva,
            "mode_financement": ctx.champ("mode_financement", "fonds_propres"),
            "banque": util.nettoie(ctx.champ("banque")),
            "montant_credit": ctx.montant("montant_credit"),
            "aide_etat": ctx.montant("aide_etat"),
            "fgcmpi_atteste": ctx.booleen("fgcmpi_atteste"),
            "fgcmpi_numero": util.nettoie(ctx.champ("fgcmpi_numero")),
            "fgcmpi_prime": ctx.montant("fgcmpi_prime"),
            "montant_encaisse": 0, "statut": "en_cours",
            "notes": util.nettoie(ctx.champ("notes")),
            "cree_le": util.maintenant(),
        })

        _construit_echeancier(ctx, contrat_id, prix_total, p)

        db.modifie("lots", lot_id, {"statut": "reserve"})
        db.trace("creation", "contrat_vsp", contrat_id, numero, ctx.nom_utilisateur)
    return {"id": contrat_id, "numero": numero}


def _construit_echeancier(ctx, contrat_id: int, prix_total: int, programme: dict) -> None:
    """Crée l'échéancier depuis un modèle ou depuis une saisie libre."""
    lignes_saisies = ctx.champ("echeances")
    if not lignes_saisies:
        code_modele = ctx.champ("modele_echeancier", "VSP_STANDARD")
        modele = db.ligne(
            "SELECT * FROM modeles_echeancier WHERE code = ? AND (societe_id = ? "
            "OR societe_id IS NULL) ORDER BY societe_id DESC LIMIT 1",
            (code_modele, ctx.entier("societe_id")),
        )
        if not modele:
            raise ErreurApplicative(
                f"Modèle d'échéancier « {code_modele} » introuvable."
            )
        lignes_saisies = json.loads(modele["lignes"])

    total_pourcentage = sum(int(l.get("pourcentage") or 0) for l in lignes_saisies)
    if total_pourcentage and abs(total_pourcentage - util.BASE_TAUX) > 10:
        raise ErreurApplicative(
            f"L'échéancier totalise {util.taux_pourcent(total_pourcentage)} % du prix "
            "au lieu de 100 %."
        )

    poids = [int(l.get("pourcentage") or 0) for l in lignes_saisies]
    montants = util.repartir(prix_total, poids) if sum(poids) else [
        util.centimes(l.get("montant")) for l in lignes_saisies
    ]

    date_base = ctx.date("date_contrat", util.aujourdhui())
    for index, (l, montant) in enumerate(zip(lignes_saisies, montants)):
        declencheur = l.get("declencheur", "date")
        seuil = int(l.get("seuil") or l.get("seuil_avancement") or 0)
        date_prevue = util.date_iso(l.get("date_prevue"))
        if declencheur == "date" and not date_prevue:
            date_prevue = util.ajoute_mois(date_base, index * int(
                ctx.entier("intervalle_mois", 3) or 3))
        statut = "exigible" if (
            (declencheur == "date" and date_prevue and date_prevue <= util.aujourdhui())
            or (declencheur == "avancement" and seuil <= programme["avancement"])
        ) else "a_venir"
        db.insere("echeances_vsp", {
            "contrat_id": contrat_id, "ordre": index,
            "libelle": l.get("libelle") or f"Échéance {index + 1}",
            "declencheur": declencheur, "seuil_avancement": seuil,
            "date_prevue": date_prevue,
            "pourcentage": int(l.get("pourcentage") or 0),
            "montant": montant, "montant_regle": 0, "statut": statut,
        })


@route("PUT", "/api/contrats-vsp/<id>")
def api_modifie_contrat(ctx):
    ctx.interdit_lecture_seule()
    identifiant = int(ctx.params["id"])
    c = contrat_ou_erreur(identifiant)
    prix_total = ctx.montant("prix_total") or c["prix_total"]
    taux_tva = ctx.taux("taux_tva", c["taux_tva"])
    prix_ht, tva = util.ht_depuis_ttc(prix_total, taux_tva)
    if prix_total != c["prix_total"] and c["montant_encaisse"] > prix_total:
        raise ErreurApplicative(
            "Le nouveau prix est inférieur au montant déjà encaissé."
        )
    with db.transaction():
        db.modifie("contrats_vsp", identifiant, {
            "type_contrat": ctx.champ("type_contrat", c["type_contrat"]),
            "date_reservation": ctx.date("date_reservation"),
            "date_contrat": ctx.date("date_contrat", c["date_contrat"]),
            "notaire_id": ctx.entier("notaire_id"),
            "num_acte_notarie": util.nettoie(ctx.champ("num_acte_notarie")),
            "date_publication": ctx.date("date_publication"),
            "prix_total": prix_total, "prix_ht": prix_ht, "tva": tva,
            "taux_tva": taux_tva,
            "mode_financement": ctx.champ("mode_financement"),
            "banque": util.nettoie(ctx.champ("banque")),
            "montant_credit": ctx.montant("montant_credit"),
            "aide_etat": ctx.montant("aide_etat"),
            "fgcmpi_atteste": ctx.booleen("fgcmpi_atteste"),
            "fgcmpi_numero": util.nettoie(ctx.champ("fgcmpi_numero")),
            "fgcmpi_prime": ctx.montant("fgcmpi_prime"),
            "notes": util.nettoie(ctx.champ("notes")),
        })
    return {"ok": True}


@route("GET", "/api/echeances-vsp")
def api_echeances(ctx):
    societe_id = ctx.arg_int("societe")
    conditions = ["c.societe_id = ?"]
    params: list = [societe_id]
    if ctx.arg("programme"):
        conditions.append("c.programme_id = ?")
        params.append(ctx.arg_int("programme"))
    if ctx.arg("statut") == "retard":
        conditions.append("ev.statut IN ('exigible','partielle') AND "
                          "(ev.date_prevue IS NULL OR ev.date_prevue < ?)")
        params.append(util.aujourdhui())
    elif ctx.arg("statut"):
        conditions.append("ev.statut = ?")
        params.append(ctx.arg("statut"))
    echeances = db.lignes(
        "SELECT ev.*, c.numero AS contrat_numero, c.prix_total, "
        "       l.numero AS lot_numero, p.intitule AS programme, p.code AS programme_code, "
        "       t.raison_sociale AS acquereur, t.telephone AS acquereur_tel "
        "FROM echeances_vsp ev JOIN contrats_vsp c ON c.id = ev.contrat_id "
        "JOIN lots l ON l.id = c.lot_id JOIN programmes p ON p.id = c.programme_id "
        "JOIN tiers t ON t.id = c.acquereur_id "
        f"WHERE {' AND '.join(conditions)} "
        "ORDER BY COALESCE(ev.date_prevue, '9999'), ev.ordre LIMIT 1000", params
    )
    aujourdhui = util.aujourdhui()
    for e in echeances:
        e["reste"] = e["montant"] - e["montant_regle"]
        e["en_retard"] = bool(e["date_prevue"] and e["date_prevue"] < aujourdhui
                              and e["statut"] not in ("reglee",))
    return {
        "echeances": echeances,
        "totaux": {
            "montant": sum(e["montant"] for e in echeances),
            "regle": sum(e["montant_regle"] for e in echeances),
            "reste": sum(e["reste"] for e in echeances),
            "en_retard": sum(e["reste"] for e in echeances if e["en_retard"]),
        },
    }


@route("POST", "/api/echeances-vsp/<id>/appel")
def api_appel_de_fonds(ctx):
    ctx.interdit_lecture_seule()
    identifiant = int(ctx.params["id"])
    with db.transaction():
        db.modifie("echeances_vsp", identifiant, {
            "appelee": 1, "date_appel": ctx.date("date", util.aujourdhui()),
            "statut": "exigible",
        })
    return {"ok": True}


@route("POST", "/api/echeances-vsp/<id>/encaisser")
def api_encaisse_echeance(ctx):
    """Encaissement d'une tranche VSP.

    Écriture (fait générateur TVA à l'encaissement) :
        Banque              D  montant TTC
            4191 Avances VSP    C  part HT
            4457 TVA collectée  C  part TVA

    Écriture (fait générateur TVA à la livraison) :
        Banque              D  montant
            4191 Avances VSP    C  montant
    """
    ctx.interdit_lecture_seule()
    identifiant = int(ctx.params["id"])
    echeance = db.ligne("SELECT * FROM echeances_vsp WHERE id = ?", (identifiant,))
    if not echeance:
        raise ErreurApplicative("Échéance introuvable.", 404)
    contrat = contrat_ou_erreur(echeance["contrat_id"])
    programme = programme_ou_erreur(contrat["programme_id"])

    montant = ctx.montant("montant") or (echeance["montant"] - echeance["montant_regle"])
    if montant <= 0:
        raise ErreurApplicative("Montant d'encaissement invalide.")
    reste = echeance["montant"] - echeance["montant_regle"]
    if montant > reste and not ctx.booleen("forcer"):
        raise ErreurApplicative(
            f"Montant supérieur au reste dû sur cette échéance "
            f"({util.formate_montant(reste)})."
        )

    tresorerie_id = ctx.entier("tresorerie_id")
    tres = db.ligne("SELECT * FROM comptes_tresorerie WHERE id = ?", (tresorerie_id,))
    if not tres:
        raise ErreurApplicative("Sélectionnez le compte d'encaissement.")

    date = ctx.date("date", util.aujourdhui())
    libelle = (f"Encaissement {echeance['libelle']} — contrat {contrat['numero']}")
    journal = "BQ" if tres["type"] in ("banque", "ccp") else "CA"

    lignes = [{"compte": tres["compte"], "debit": montant, "credit": 0,
               "libelle": libelle, "programme_id": programme["id"],
               "lot_id": contrat["lot_id"]}]
    if programme["fait_generateur_tva"] == "encaissement" and contrat["taux_tva"]:
        part_ht, part_tva = util.ht_depuis_ttc(montant, contrat["taux_tva"])
        lignes.append({"compte": COMPTE_AVANCE_VSP, "debit": 0, "credit": part_ht,
                       "tiers_id": contrat["acquereur_id"], "libelle": libelle,
                       "programme_id": programme["id"], "lot_id": contrat["lot_id"]})
        lignes.append({"compte": COMPTE_TVA_COLLECTEE, "debit": 0, "credit": part_tva,
                       "libelle": f"TVA sur encaissement — {contrat['numero']}",
                       "programme_id": programme["id"]})
    else:
        lignes.append({"compte": COMPTE_AVANCE_VSP, "debit": 0, "credit": montant,
                       "tiers_id": contrat["acquereur_id"], "libelle": libelle,
                       "programme_id": programme["id"], "lot_id": contrat["lot_id"]})

    with db.transaction():
        ecriture_id = compta.enregistre_ecriture(
            contrat["societe_id"], journal, date, libelle, lignes,
            piece=util.nettoie(ctx.champ("reference")), reference=contrat["numero"],
            module="promotion", source_type="echeance_vsp", source_id=identifiant,
            utilisateur=ctx.nom_utilisateur, perimetre=ctx.champ("perimetre"),
        )
        regle = echeance["montant_regle"] + montant
        db.modifie("echeances_vsp", identifiant, {
            "montant_regle": regle,
            "date_reglement": date,
            "statut": "reglee" if regle >= echeance["montant"] else "partielle",
        })
        nouveau_total = contrat["montant_encaisse"] + montant
        db.modifie("contrats_vsp", contrat["id"], {"montant_encaisse": nouveau_total})
        if nouveau_total >= contrat["prix_total"] and contrat["statut"] == "en_cours":
            db.modifie("contrats_vsp", contrat["id"], {"statut": "solde"})
        db.insere("reglements", {
            "societe_id": contrat["societe_id"],
            "exercice_id": compta.exercice_pour_date(contrat["societe_id"], date)["id"],
            "sens": "encaissement", "date": date,
            "tiers_id": contrat["acquereur_id"], "tresorerie_id": tresorerie_id,
            "montant": montant, "mode": ctx.champ("mode", "virement"),
            "reference": util.nettoie(ctx.champ("reference")), "libelle": libelle,
            "echeance_id": identifiant, "ecriture_id": ecriture_id,
            "cree_le": util.maintenant(),
        })
        db.trace("encaissement", "echeance_vsp", identifiant,
                 util.formate_montant(montant), ctx.nom_utilisateur)
    return {"ecriture_id": ecriture_id, "montant_encaisse": nouveau_total}


@route("POST", "/api/contrats-vsp/<id>/livrer")
def api_livre_lot(ctx):
    """Livraison du lot : constatation du chiffre d'affaires.

        4191 Avances VSP      D  montant encaissé
        411 Client            D  solde restant dû (le cas échéant)
            701x Ventes           C  prix HT
            4457 TVA collectée    C  TVA (si non déjà collectée à l'encaissement)

    Et, si le coût de revient du lot est connu, sortie de stock :
        724 Variation stocks  D  coût de revient
            355 Produits finis    C  coût de revient
    """
    ctx.interdit_lecture_seule()
    identifiant = int(ctx.params["id"])
    contrat = contrat_ou_erreur(identifiant)
    if contrat["statut"] == "livre":
        raise ErreurApplicative("Ce lot a déjà été livré et comptabilisé.")
    if contrat["statut"] == "resilie":
        raise ErreurApplicative("Contrat résilié.")
    programme = programme_ou_erreur(contrat["programme_id"])
    lot = db.ligne("SELECT * FROM lots WHERE id = ?", (contrat["lot_id"],))
    date = ctx.date("date", util.aujourdhui())

    prix_ht = contrat["prix_ht"]
    encaisse = contrat["montant_encaisse"]
    solde_du = contrat["prix_total"] - encaisse

    # On solde le compte d'avances sur son solde RÉEL et non sur un montant
    # recalculé : les encaissements successifs ont chacun subi leur propre
    # arrondi HT/TVA, et une reconstitution laisserait un résidu au 419.
    avance_a_solder = _solde_avances(contrat["societe_id"], lot["id"],
                                     contrat["acquereur_id"])
    tva_deja_collectee = encaisse - avance_a_solder
    tva_restante = contrat["tva"] - tva_deja_collectee

    libelle = (f"Livraison lot n° {lot['numero']} — {programme['intitule']} — "
               f"contrat {contrat['numero']}")
    compte_vente = COMPTES_VENTE.get(lot["type_lot"], "701")

    lignes = []
    if avance_a_solder:
        lignes.append({"compte": COMPTE_AVANCE_VSP, "debit": avance_a_solder, "credit": 0,
                       "tiers_id": contrat["acquereur_id"],
                       "libelle": "Solde des avances reçues",
                       "programme_id": programme["id"], "lot_id": lot["id"]})
    # Reste dû converti en créance client
    if solde_du > 0:
        lignes.append({"compte": "4111", "debit": solde_du, "credit": 0,
                       "tiers_id": contrat["acquereur_id"],
                       "libelle": "Solde à recevoir sur livraison",
                       "programme_id": programme["id"], "lot_id": lot["id"],
                       "echeance": date})
    lignes.append({"compte": compte_vente, "debit": 0, "credit": prix_ht,
                   "libelle": libelle, "programme_id": programme["id"],
                   "lot_id": lot["id"]})
    if tva_restante:
        lignes.append({"compte": COMPTE_TVA_COLLECTEE, "debit": 0, "credit": tva_restante,
                       "libelle": f"TVA sur vente — {contrat['numero']}",
                       "programme_id": programme["id"]})

    with db.transaction():
        ecriture_id = compta.enregistre_ecriture(
            contrat["societe_id"], "VE", date, libelle, lignes,
            piece=contrat["numero"], reference=contrat["num_acte_notarie"],
            module="promotion", source_type="livraison_vsp", source_id=identifiant,
            utilisateur=ctx.nom_utilisateur,
        )
        # Sortie de stock du produit fini
        ecriture_stock = None
        if lot["cout_revient"] and ctx.booleen("destocker", True):
            ecriture_stock = compta.enregistre_ecriture(
                contrat["societe_id"], "OD", date,
                f"Sortie de stock — lot n° {lot['numero']}", [
                    {"compte": COMPTE_VARIATION_PRODUITS_FINIS,
                     "debit": lot["cout_revient"], "credit": 0,
                     "libelle": f"Déstockage lot {lot['numero']}",
                     "programme_id": programme["id"], "lot_id": lot["id"]},
                    {"compte": COMPTE_PRODUITS_FINIS, "debit": 0,
                     "credit": lot["cout_revient"],
                     "libelle": f"Déstockage lot {lot['numero']}",
                     "programme_id": programme["id"], "lot_id": lot["id"]},
                ],
                module="promotion", source_type="destockage_lot", source_id=lot["id"],
                utilisateur=ctx.nom_utilisateur,
            )
        db.modifie("contrats_vsp", identifiant, {
            "statut": "livre", "date_livraison": date,
            "date_pv_reception": ctx.date("date_pv_reception", date),
        })
        db.modifie("lots", lot["id"], {"statut": "livre"})
        db.trace("livraison", "contrat_vsp", identifiant, libelle, ctx.nom_utilisateur)
    return {"ecriture_id": ecriture_id, "ecriture_stock": ecriture_stock,
            "chiffre_affaires": prix_ht, "solde_du": solde_du}


@route("POST", "/api/contrats-vsp/<id>/resilier")
def api_resilie(ctx):
    """Résiliation : restitution des sommes, éventuelle indemnité conservée."""
    ctx.interdit_lecture_seule()
    identifiant = int(ctx.params["id"])
    contrat = contrat_ou_erreur(identifiant)
    if contrat["statut"] == "livre":
        raise ErreurApplicative("Un lot livré ne peut pas être résilié ici.")
    indemnite = ctx.montant("indemnite")
    a_restituer = contrat["montant_encaisse"] - indemnite
    if a_restituer < 0:
        raise ErreurApplicative("L'indemnité dépasse les sommes encaissées.")
    date = ctx.date("date", util.aujourdhui())
    tres = db.ligne("SELECT * FROM comptes_tresorerie WHERE id = ?",
                    (ctx.entier("tresorerie_id"),))
    if a_restituer > 0 and not tres:
        raise ErreurApplicative("Indiquez le compte depuis lequel les fonds sont restitués.")

    programme = programme_ou_erreur(contrat["programme_id"])
    # Comme à la livraison, on repart du solde réel du compte d'avances.
    avance_ht = _solde_avances(contrat["societe_id"], contrat["lot_id"],
                              contrat["acquereur_id"])
    avance_tva = contrat["montant_encaisse"] - avance_ht

    libelle = f"Résiliation du contrat {contrat['numero']}"
    lignes = [{"compte": COMPTE_AVANCE_VSP, "debit": avance_ht, "credit": 0,
               "tiers_id": contrat["acquereur_id"], "libelle": libelle,
               "programme_id": programme["id"], "lot_id": contrat["lot_id"]}]
    if avance_tva:
        lignes.append({"compte": COMPTE_TVA_COLLECTEE, "debit": avance_tva, "credit": 0,
                       "libelle": "Régularisation TVA sur avances restituées",
                       "programme_id": programme["id"]})
    if indemnite:
        lignes.append({"compte": "7581", "debit": 0, "credit": indemnite,
                       "libelle": "Indemnité de résiliation conservée",
                       "programme_id": programme["id"]})
    if a_restituer:
        lignes.append({"compte": tres["compte"], "debit": 0, "credit": a_restituer,
                       "libelle": f"Restitution à {contrat['acquereur_id']}"})

    with db.transaction():
        ecriture_id = compta.enregistre_ecriture(
            contrat["societe_id"],
            "BQ" if (tres and tres["type"] in ("banque", "ccp")) else "OD",
            date, libelle, lignes, piece=contrat["numero"], module="promotion",
            source_type="resiliation_vsp", source_id=identifiant,
            utilisateur=ctx.nom_utilisateur,
        )
        db.modifie("contrats_vsp", identifiant, {"statut": "resilie"})
        db.modifie("lots", contrat["lot_id"], {"statut": "disponible"})
        db.trace("resiliation", "contrat_vsp", identifiant, libelle, ctx.nom_utilisateur)
    return {"ecriture_id": ecriture_id, "restitue": a_restituer, "indemnite": indemnite}


# ===========================================================================
# STOCKS : travaux en cours et produits finis
# ===========================================================================

@route("POST", "/api/programmes/<id>/stock-encours")
def api_stock_encours(ctx):
    """Constate les travaux en cours à la date d'arrêté (332 / 723).

    Montant stocké = charges imputées au programme depuis l'origine, diminuées
    de ce qui est déjà en stock, et des lots déjà transférés en produits finis.
    """
    ctx.interdit_lecture_seule()
    identifiant = int(ctx.params["id"])
    p = programme_ou_erreur(identifiant)
    date = ctx.date("date", util.aujourdhui())

    charges = int(db.valeur(
        "SELECT COALESCE(SUM(l.debit - l.credit),0) FROM lignes l "
        "JOIN ecritures e ON e.id = l.ecriture_id "
        "WHERE e.societe_id = ? AND l.programme_id = ? AND l.compte LIKE '6%' "
        "AND e.date <= ?", (p["societe_id"], identifiant, date), 0
    ))
    deja_stocke = int(db.valeur(
        "SELECT COALESCE(SUM(l.debit - l.credit),0) FROM lignes l "
        "JOIN ecritures e ON e.id = l.ecriture_id "
        "WHERE e.societe_id = ? AND l.programme_id = ? AND l.compte LIKE '33%' "
        "AND e.date <= ?", (p["societe_id"], identifiant, date), 0
    ))
    montant = ctx.montant("montant") or (charges - deja_stocke)
    if montant == 0:
        return {"message": "Le stock d'en-cours est déjà à jour : aucune écriture générée.",
                "charges": charges, "deja_stocke": deja_stocke}

    libelle = f"Travaux en cours au {util.date_fr(date)} — {p['intitule']}"
    if montant > 0:
        lignes = [
            {"compte": COMPTE_ENCOURS, "debit": montant, "credit": 0, "libelle": libelle,
             "programme_id": identifiant},
            {"compte": COMPTE_VARIATION_ENCOURS, "debit": 0, "credit": montant,
             "libelle": libelle, "programme_id": identifiant},
        ]
    else:
        lignes = [
            {"compte": COMPTE_VARIATION_ENCOURS, "debit": -montant, "credit": 0,
             "libelle": libelle, "programme_id": identifiant},
            {"compte": COMPTE_ENCOURS, "debit": 0, "credit": -montant,
             "libelle": libelle, "programme_id": identifiant},
        ]
    with db.transaction():
        ecriture_id = compta.enregistre_ecriture(
            p["societe_id"], "OD", date, libelle, lignes, module="promotion",
            source_type="stock_encours", source_id=identifiant,
            utilisateur=ctx.nom_utilisateur,
        )
    return {"ecriture_id": ecriture_id, "montant": montant, "charges": charges,
            "deja_stocke": deja_stocke}


@route("POST", "/api/programmes/<id>/achever")
def api_acheve(ctx):
    """Achèvement : transfert des en-cours (33) vers les produits finis (355)."""
    ctx.interdit_lecture_seule()
    identifiant = int(ctx.params["id"])
    p = programme_ou_erreur(identifiant)
    date = ctx.date("date", util.aujourdhui())
    encours = int(db.valeur(
        "SELECT COALESCE(SUM(l.debit - l.credit),0) FROM lignes l "
        "JOIN ecritures e ON e.id = l.ecriture_id "
        "WHERE e.societe_id = ? AND l.programme_id = ? AND l.compte LIKE '33%' "
        "AND e.date <= ?", (p["societe_id"], identifiant, date), 0
    ))
    montant = ctx.montant("montant") or encours
    if montant <= 0:
        raise ErreurApplicative(
            "Aucun en-cours à transférer. Constatez d'abord les travaux en cours."
        )
    libelle = f"Achèvement du programme {p['intitule']} — transfert en produits finis"
    with db.transaction():
        ecriture_id = compta.enregistre_ecriture(
            p["societe_id"], "OD", date, libelle, [
                {"compte": COMPTE_PRODUITS_FINIS, "debit": montant, "credit": 0,
                 "libelle": libelle, "programme_id": identifiant},
                {"compte": COMPTE_VARIATION_PRODUITS_FINIS, "debit": 0, "credit": montant,
                 "libelle": libelle, "programme_id": identifiant},
                {"compte": COMPTE_VARIATION_ENCOURS, "debit": montant, "credit": 0,
                 "libelle": "Déstockage des travaux en cours",
                 "programme_id": identifiant},
                {"compte": COMPTE_ENCOURS, "debit": 0, "credit": montant,
                 "libelle": "Déstockage des travaux en cours",
                 "programme_id": identifiant},
            ],
            module="promotion", source_type="achevement", source_id=identifiant,
            utilisateur=ctx.nom_utilisateur,
        )
        db.modifie("programmes", identifiant,
                   {"statut": "acheve", "avancement": util.BASE_TAUX})
    return {"ecriture_id": ecriture_id, "montant": montant}


# ===========================================================================
# SITUATIONS DE TRAVAUX (entreprises sous-traitantes)
# ===========================================================================

@route("GET", "/api/situations-travaux")
def api_situations(ctx):
    conditions = ["s.societe_id = ?"]
    params: list = [ctx.arg_int("societe")]
    if ctx.arg("programme"):
        conditions.append("s.programme_id = ?")
        params.append(ctx.arg_int("programme"))
    return {"situations": db.lignes(
        "SELECT s.*, t.raison_sociale AS entreprise, p.intitule AS programme, "
        "       f.numero AS facture_numero "
        "FROM situations_travaux s LEFT JOIN tiers t ON t.id = s.entreprise_id "
        "JOIN programmes p ON p.id = s.programme_id "
        "LEFT JOIN factures f ON f.id = s.facture_id "
        f"WHERE {' AND '.join(conditions)} ORDER BY s.date DESC LIMIT 500", params
    )}


@route("POST", "/api/situations-travaux")
def api_cree_situation(ctx):
    """Situation de travaux d'une entreprise, avec retenue de garantie."""
    ctx.interdit_lecture_seule()
    societe_id = ctx.entier("societe_id")
    programme_id = ctx.entier("programme_id")
    programme_ou_erreur(programme_id)
    montant_ht = ctx.montant("montant_ht")
    if montant_ht <= 0:
        raise ErreurApplicative("Indiquez le montant HT de la situation.")
    taux_tva = ctx.taux("taux_tva", 1900)
    tva = util.applique_taux(montant_ht, taux_tva)
    ttc = montant_ht + tva
    taux_retenue = ctx.taux("taux_retenue")
    retenue = util.applique_taux(ttc, taux_retenue) if taux_retenue else ctx.montant("retenue_garantie")
    date = ctx.date("date", util.aujourdhui())

    with db.transaction():
        numero = util.nettoie(ctx.champ("numero")) or db.numero_suivant(
            societe_id, "situation", int(date[:4]))
        identifiant = db.insere("situations_travaux", {
            "societe_id": societe_id, "programme_id": programme_id,
            "entreprise_id": ctx.entier("entreprise_id"), "numero": numero,
            "date": date, "lot_travaux": util.nettoie(ctx.champ("lot_travaux")),
            "montant_marche": ctx.montant("montant_marche"),
            "avancement": ctx.taux("avancement"),
            "montant_ht": montant_ht, "taux_tva": taux_tva, "montant_ttc": ttc,
            "retenue_garantie": retenue, "net_a_payer": ttc - retenue,
            "statut": "brouillon", "cree_le": util.maintenant(),
        })
        if ctx.booleen("comptabiliser", True):
            _comptabilise_situation(ctx, identifiant)
    return {"id": identifiant, "numero": numero}


def _comptabilise_situation(ctx, situation_id: int) -> int:
    s = db.ligne("SELECT * FROM situations_travaux WHERE id = ?", (situation_id,))
    compte_charge = ctx.champ("compte", "6051")
    poste = ctx.champ("poste_budget", "gros_oeuvre")
    libelle = f"Situation de travaux n° {s['numero']}"
    lignes = [
        {"compte": compte_charge, "debit": s["montant_ht"], "credit": 0,
         "libelle": libelle, "programme_id": s["programme_id"], "poste_budget": poste},
    ]
    if s["montant_ttc"] - s["montant_ht"]:
        lignes.append({"compte": "44566", "debit": s["montant_ttc"] - s["montant_ht"],
                       "credit": 0, "libelle": f"TVA déductible — {s['numero']}"})
    if s["retenue_garantie"]:
        lignes.append({"compte": "1681", "debit": 0, "credit": s["retenue_garantie"],
                       "tiers_id": s["entreprise_id"],
                       "libelle": f"Retenue de garantie — {s['numero']}"})
    lignes.append({"compte": "4011", "debit": 0, "credit": s["net_a_payer"],
                   "tiers_id": s["entreprise_id"], "libelle": libelle})

    ecriture_id = compta.enregistre_ecriture(
        s["societe_id"], "AC", s["date"], libelle, lignes, piece=s["numero"],
        module="promotion", source_type="situation_travaux", source_id=situation_id,
        utilisateur=ctx.nom_utilisateur,
    )
    db.modifie("situations_travaux", situation_id, {"statut": "comptabilisee"})
    return ecriture_id


# ===========================================================================
# ANALYSES
# ===========================================================================

@route("GET", "/api/programmes/<id>/cout-revient")
def api_cout_revient(ctx):
    """Budget vs réalisé par poste, et coût de revient par lot."""
    identifiant = int(ctx.params["id"])
    p = programme_ou_erreur(identifiant)
    societe_id = p["societe_id"]

    postes = db.lignes(
        "SELECT * FROM budget_lignes WHERE programme_id = ? ORDER BY ordre", (identifiant,))
    realise_par_compte = {
        r["compte"]: r["montant"] for r in db.lignes(
            "SELECT l.compte, COALESCE(SUM(l.debit - l.credit),0) AS montant "
            "FROM lignes l JOIN ecritures e ON e.id = l.ecriture_id "
            "WHERE e.societe_id = ? AND l.programme_id = ? AND l.compte LIKE '6%' "
            "GROUP BY l.compte", (societe_id, identifiant)
        )
    }
    comptes_affectes = set()
    for poste in postes:
        comptes = [c.strip() for c in (poste["comptes"] or "").split(";") if c.strip()]
        realise = 0
        for compte in comptes:
            for numero, montant in realise_par_compte.items():
                if numero.startswith(compte):
                    realise += montant
                    comptes_affectes.add(numero)
        poste["realise"] = realise
        poste["ecart"] = poste["montant_prevu"] - realise
        poste["taux"] = (util.part_proportionnelle(100000, realise, poste["montant_prevu"])
                         if poste["montant_prevu"] else 0)

    non_affecte = sum(m for c, m in realise_par_compte.items() if c not in comptes_affectes)
    if non_affecte:
        postes.append({
            "poste": "autres", "libelle": "Autres charges imputées au programme",
            "montant_prevu": 0, "realise": non_affecte, "ecart": -non_affecte,
            "taux": 0, "comptes": "", "ordre": 99,
        })

    lots = db.lignes(
        "SELECT l.*, c.prix_total AS prix_contrat, c.statut AS statut_contrat "
        "FROM lots l LEFT JOIN contrats_vsp c ON c.lot_id = l.id AND c.statut <> 'resilie' "
        "WHERE l.programme_id = ? ORDER BY l.numero", (identifiant,))
    for l in lots:
        prix = l["prix_contrat"] or l["prix_vente"]
        l["prix_effectif"] = prix
        l["marge"] = prix - l["cout_revient"]
        l["taux_marge"] = (util.part_proportionnelle(util.BASE_TAUX, l["marge"], prix)
                           if prix else 0)

    return {
        "programme": p, "postes": postes, "lots": lots,
        "synthese": _synthese_programme(p),
        "total_prevu": sum(x["montant_prevu"] for x in postes),
        "total_realise": sum(x["realise"] for x in postes),
    }


@route("PUT", "/api/programmes/<id>/budget")
def api_modifie_budget(ctx):
    ctx.interdit_lecture_seule()
    identifiant = int(ctx.params["id"])
    programme_ou_erreur(identifiant)
    with db.transaction():
        for poste in ctx.champ("postes") or []:
            if poste.get("id"):
                db.modifie("budget_lignes", int(poste["id"]), {
                    "libelle": poste.get("libelle", ""),
                    "montant_prevu": util.centimes(poste.get("montant_prevu")),
                    "comptes": poste.get("comptes"),
                })
            else:
                db.insere("budget_lignes", {
                    "programme_id": identifiant, "poste": poste.get("poste", "autre"),
                    "libelle": poste.get("libelle", ""),
                    "montant_prevu": util.centimes(poste.get("montant_prevu")),
                    "comptes": poste.get("comptes"),
                    "ordre": int(poste.get("ordre") or 50),
                })
    return {"ok": True}


@route("GET", "/api/export/programme")
def api_export_programme(ctx):
    identifiant = ctx.arg_int("programme")
    p = programme_ou_erreur(identifiant)
    soc = compta.societe(p["societe_id"])
    donnees = api_cout_revient(_Faux(ctx, {"id": str(identifiant)}))
    synthese = donnees["synthese"]

    classeur = tableur.Classeur()

    f = classeur.feuille("Synthèse")
    f.titre(f"{p['intitule']} ({p['code']}) — synthèse")
    f.ajoute(tableur.texte(soc["raison_sociale"]))
    f.vide()
    for libelle, valeur, est_montant in [
        ("Nombre de lots", synthese["nb_lots"], False),
        ("Disponibles", synthese["nb_disponibles"], False),
        ("Réservés", synthese["nb_reserves"], False),
        ("Vendus / livrés", synthese["nb_vendus"], False),
        ("Avancement des travaux (%)", util.taux_pourcent(synthese["avancement"]), False),
        ("Budget total", synthese["budget_total"], True),
        ("Coût engagé", synthese["cout_engage"], True),
        ("Reste à engager", synthese["reste_a_engager"], True),
        ("Chiffre d'affaires prévu", synthese["ca_prevu"], True),
        ("Chiffre d'affaires contractualisé", synthese["ca_contractualise"], True),
        ("Encaissé", synthese["encaisse"], True),
        ("Reste à encaisser", synthese["reste_a_encaisser"], True),
        ("Marge prévisionnelle", synthese["marge_prevue"], True),
    ]:
        f.ajoute(tableur.texte(libelle, tableur.GRAS),
                 tableur.monnaie(valeur) if est_montant else tableur.nombre(valeur))
    f.largeurs_auto(40, 20)

    f2 = classeur.feuille("Budget vs réalisé")
    f2.entetes("Poste", "Comptes", "Budget", "Réalisé", "Écart", "Consommation %")
    f2.largeurs_auto(42, 24, 18, 18, 18, 16)
    for poste in donnees["postes"]:
        f2.ajoute(
            tableur.texte(poste["libelle"]), tableur.texte(poste.get("comptes")),
            tableur.monnaie(poste["montant_prevu"]), tableur.monnaie(poste["realise"]),
            tableur.monnaie(poste["ecart"]),
            tableur.nombre(util.taux_pourcent(poste["taux"])),
        )
    f2.ajoute(tableur.texte("TOTAL", tableur.GRAS), tableur.texte(""),
              tableur.monnaie(donnees["total_prevu"], total=True),
              tableur.monnaie(donnees["total_realise"], total=True),
              tableur.monnaie(donnees["total_prevu"] - donnees["total_realise"], total=True))

    f3 = classeur.feuille("Lots")
    f3.entetes("N° lot", "Type", "Typologie", "Bâtiment", "Étage", "Surface (m²)",
               "Prix vente", "Coût de revient", "Marge", "Marge %", "Statut", "Acquéreur")
    f3.largeurs_auto(10, 16, 10, 12, 8, 13, 18, 18, 18, 10, 13, 28)
    for l in donnees["lots"]:
        f3.ajoute(
            tableur.texte(l["numero"]), tableur.texte(l["type_lot"]),
            tableur.texte(l["typologie"]), tableur.texte(l["batiment"]),
            tableur.texte(l["etage"]),
            tableur.nombre(l["surface_habitable"] / 100.0, tableur.NORMAL),
            tableur.monnaie(l["prix_effectif"]), tableur.monnaie(l["cout_revient"]),
            tableur.monnaie(l["marge"]),
            tableur.nombre(util.taux_pourcent(l["taux_marge"])),
            tableur.texte(l["statut"]), tableur.texte(""),
        )

    f4 = classeur.feuille("Contrats & encaissements")
    f4.entetes("Contrat", "Lot", "Acquéreur", "Date", "Prix total", "Encaissé",
               "Reste", "Statut", "FGCMPI")
    f4.largeurs_auto(16, 10, 30, 12, 18, 18, 18, 13, 12)
    contrats = db.lignes(
        "SELECT c.*, l.numero AS lot_numero, t.raison_sociale AS acquereur "
        "FROM contrats_vsp c JOIN lots l ON l.id = c.lot_id "
        "JOIN tiers t ON t.id = c.acquereur_id WHERE c.programme_id = ? ORDER BY c.numero",
        (identifiant,))
    for c in contrats:
        f4.ajoute(
            tableur.texte(c["numero"]), tableur.texte(c["lot_numero"]),
            tableur.texte(c["acquereur"]), tableur.date_cel(c["date_contrat"]),
            tableur.monnaie(c["prix_total"]), tableur.monnaie(c["montant_encaisse"]),
            tableur.monnaie(c["prix_total"] - c["montant_encaisse"]),
            tableur.texte(c["statut"]),
            tableur.texte("Oui" if c["fgcmpi_atteste"] else "Non"),
        )

    return Reponse(classeur.octets(),
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   f"programme_{p['code']}.xlsx")


class _Faux:
    def __init__(self, ctx, params):
        self._ctx = ctx
        self.params = params

    def __getattr__(self, nom):
        return getattr(self._ctx, nom)
