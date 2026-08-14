"""Fiscalité algérienne : déclaration mensuelle G n° 50, livres de TVA,
IBS et acomptes provisionnels, calendrier des obligations.

⚠️ Les taux et barèmes proviennent de la table `parametres_fiscaux`,
modifiable par exercice depuis l'écran « Paramètres > Fiscalité ». La loi de
finances change chaque année : l'application calcule, le comptable valide.
Aucun taux n'est codé en dur dans ce module.
"""

from __future__ import annotations

import json

from noyau import base as db
from noyau import util
from noyau import tableur
from noyau.serveur import ErreurApplicative, route, Reponse
from modules import comptabilite as compta

COMPTE_TVA_COLLECTEE = "4457"
COMPTE_TVA_DEDUCTIBLE_BS = "44566"
COMPTE_TVA_DEDUCTIBLE_IMMO = "44562"
COMPTE_PRECOMPTE = "44567"
COMPTE_TVA_A_PAYER = "4451"
COMPTE_TAP_DETTE = "4471"
COMPTE_TAP_CHARGE = "6421"
COMPTE_IRG_SALAIRES = "4421"
COMPTE_TIMBRE = "4472"
COMPTE_IBS_ACOMPTE = "4441"


# ---------------------------------------------------------------------------
# Paramètres fiscaux
# ---------------------------------------------------------------------------

@route("GET", "/api/parametres-fiscaux")
def api_parametres(ctx):
    annee = ctx.arg_int("annee") or int(util.aujourdhui()[:4])
    parametres = db.lignes(
        "SELECT * FROM parametres_fiscaux WHERE annee = ? ORDER BY cle", (annee,)
    )
    if not parametres:
        # Recopie l'année disponible la plus proche pour permettre l'édition
        source = db.valeur(
            "SELECT annee FROM parametres_fiscaux WHERE annee <= ? "
            "ORDER BY annee DESC LIMIT 1", (annee,)
        ) or db.valeur("SELECT MIN(annee) FROM parametres_fiscaux")
        if source:
            with db.transaction():
                for p in db.lignes("SELECT * FROM parametres_fiscaux WHERE annee = ?",
                                   (source,)):
                    db.execute(
                        "INSERT OR IGNORE INTO parametres_fiscaux "
                        "(annee, cle, valeur, libelle, unite, source) VALUES (?,?,?,?,?,?)",
                        (annee, p["cle"], p["valeur"], p["libelle"], p["unite"],
                         (p["source"] or "") + f" (repris de {source} — à vérifier)"),
                    )
            parametres = db.lignes(
                "SELECT * FROM parametres_fiscaux WHERE annee = ? ORDER BY cle", (annee,))
    return {"annee": annee, "parametres": parametres,
            "annees": [r["annee"] for r in db.lignes(
                "SELECT DISTINCT annee FROM parametres_fiscaux ORDER BY annee DESC")]}


@route("PUT", "/api/parametres-fiscaux")
def api_modifie_parametres(ctx):
    ctx.exige_role("admin", "comptable")
    annee = ctx.entier("annee") or int(util.aujourdhui()[:4])
    with db.transaction():
        for p in ctx.champ("parametres") or []:
            valeur = p.get("valeur")
            if isinstance(valeur, (list, dict)):
                valeur = json.dumps(valeur, ensure_ascii=False)
            db.execute(
                "INSERT INTO parametres_fiscaux (annee, cle, valeur, libelle, unite, source) "
                "VALUES (?,?,?,?,?,?) ON CONFLICT(annee, cle) DO UPDATE SET "
                "valeur = excluded.valeur, libelle = excluded.libelle, "
                "source = excluded.source",
                (annee, p["cle"], str(valeur), p.get("libelle"), p.get("unite", "texte"),
                 p.get("source")),
            )
        db.trace("modification", "parametres_fiscaux", None, {"annee": annee},
                 ctx.nom_utilisateur)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Calcul de la G50
# ---------------------------------------------------------------------------

def _mouvement(societe_id: int, prefixe: str, du: str, au: str) -> dict:
    return compta.solde_compte(societe_id, prefixe, du, au)


def calcule_g50(societe_id: int, periode: str) -> dict:
    """Calcule la déclaration mensuelle à partir de la comptabilité."""
    soc = compta.societe(societe_id)
    du = periode + "-01"
    au = util.fin_de_mois(periode)
    annee = int(periode[:4])

    tva_collectee_mvt = _mouvement(societe_id, COMPTE_TVA_COLLECTEE, du, au)
    tva_collectee = tva_collectee_mvt["credit"] - tva_collectee_mvt["debit"]
    deduct_bs_mvt = _mouvement(societe_id, COMPTE_TVA_DEDUCTIBLE_BS, du, au)
    tva_deductible_bs = deduct_bs_mvt["debit"] - deduct_bs_mvt["credit"]
    deduct_immo_mvt = _mouvement(societe_id, COMPTE_TVA_DEDUCTIBLE_IMMO, du, au)
    tva_deductible_immo = deduct_immo_mvt["debit"] - deduct_immo_mvt["credit"]

    # Précompte reporté de la déclaration précédente
    precedente = db.ligne(
        "SELECT precompte_reporte FROM declarations_g50 WHERE societe_id = ? AND periode = ?",
        (societe_id, util.mois_precedent(periode)),
    )
    precompte_anterieur = precedente["precompte_reporte"] if precedente else 0
    if not precedente:
        solde_precompte = compta.solde_compte(societe_id, COMPTE_PRECOMPTE, None,
                                              util.fin_de_mois(util.mois_precedent(periode)))
        precompte_anterieur = max(solde_precompte["solde"], 0)

    solde_tva = tva_collectee - tva_deductible_bs - tva_deductible_immo - precompte_anterieur
    tva_a_payer = max(solde_tva, 0)
    precompte_reporte = max(-solde_tva, 0)

    # Chiffre d'affaires de la période
    ca_mvt = _mouvement(societe_id, "70", du, au)
    ca_total = ca_mvt["credit"] - ca_mvt["debit"]
    base_tva = (util.part_proportionnelle(tva_collectee, util.BASE_TAUX,
                                          db.parametre_fiscal_int(annee, "tva_taux_normal", 1900))
                if tva_collectee else 0)
    ca_exonere = max(ca_total - base_tva, 0)

    # TAP — applicable seulement si la loi de finances de l'année le prévoit
    tap_applicable = db.parametre_fiscal_int(annee, "tap_applicable", 0)
    taux_tap = db.parametre_fiscal_int(annee, "tap_taux", 0)
    refaction = db.parametre_fiscal_int(annee, "tap_refaction", 0)
    base_tap = ca_total - util.applique_taux(ca_total, refaction) if tap_applicable else 0
    tap = util.applique_taux(base_tap, taux_tap) if tap_applicable else 0

    # Retenues à la source
    irg_mvt = _mouvement(societe_id, COMPTE_IRG_SALAIRES, du, au)
    irg_salaires = irg_mvt["credit"] - irg_mvt["debit"]
    irg_autres_mvt = _mouvement(societe_id, "4422", du, au)
    irg_ras_autres = irg_autres_mvt["credit"] - irg_autres_mvt["debit"]

    timbre_mvt = _mouvement(societe_id, COMPTE_TIMBRE, du, au)
    droit_timbre = timbre_mvt["credit"] - timbre_mvt["debit"]

    total = tva_a_payer + tap + irg_salaires + irg_ras_autres + droit_timbre

    jour_limite = db.parametre_fiscal_int(annee, "g50_jour_limite", 20)
    periode_depot = util.mois_suivant(periode)

    return {
        "societe_id": societe_id, "periode": periode,
        "societe": {"raison_sociale": soc["raison_sociale"], "nif": soc["nif"],
                    "rc": soc["rc"], "article_imposition": soc["article_imposition"],
                    "adresse": soc["adresse"], "commune": soc["commune"],
                    "wilaya": soc["wilaya"], "activite": soc["activite"]},
        "date_limite": util.jour_du_mois(periode_depot, jour_limite),
        "ca_taxable": base_tva, "ca_exonere": ca_exonere, "ca_total": ca_total,
        "tva_collectee": tva_collectee,
        "tva_deductible_bs": tva_deductible_bs,
        "tva_deductible_immo": tva_deductible_immo,
        "precompte_anterieur": precompte_anterieur,
        "tva_a_payer": tva_a_payer, "precompte_reporte": precompte_reporte,
        "tap_applicable": bool(tap_applicable), "base_tap": base_tap,
        "taux_tap": taux_tap, "tap": tap,
        "irg_salaires": irg_salaires, "irg_ras_autres": irg_ras_autres,
        "acompte_ibs": 0, "droit_timbre": droit_timbre,
        "total_a_payer": total,
        "avertissements": _avertissements_g50(annee, tap_applicable),
    }


def _avertissements_g50(annee: int, tap_applicable: int) -> list[str]:
    messages = []
    if not tap_applicable:
        messages.append(
            "La TAP est désactivée pour cet exercice dans les paramètres fiscaux. "
            "Si elle s'applique encore à votre activité, activez-la et renseignez le "
            "taux dans Paramètres > Fiscalité."
        )
    controle = db.ligne(
        "SELECT source FROM parametres_fiscaux WHERE annee = ? AND cle = 'tva_taux_normal'",
        (annee,))
    if controle and "repris de" in (controle["source"] or ""):
        messages.append(
            f"Les paramètres fiscaux {annee} ont été recopiés d'une année antérieure. "
            "Vérifiez-les avec la loi de finances en vigueur avant de déposer."
        )
    return messages


@route("GET", "/api/g50")
def api_g50(ctx):
    societe_id = ctx.arg_int("societe")
    periode = ctx.arg("periode") or util.mois_precedent(util.periode_de(util.aujourdhui()))
    enregistree = db.ligne(
        "SELECT * FROM declarations_g50 WHERE societe_id = ? AND periode = ?",
        (societe_id, periode),
    )
    calculee = calcule_g50(societe_id, periode)
    calculee["enregistree"] = enregistree
    if enregistree and enregistree["statut"] in ("deposee", "payee"):
        # Une déclaration déposée fait foi : on affiche les montants déclarés
        for cle in ("ca_taxable", "ca_exonere", "tva_collectee", "tva_deductible_bs",
                    "tva_deductible_immo", "precompte_anterieur", "tva_a_payer",
                    "precompte_reporte", "base_tap", "tap", "irg_salaires",
                    "irg_ras_autres", "acompte_ibs", "droit_timbre", "total_a_payer"):
            calculee[cle] = enregistree[cle]
    return calculee


@route("GET", "/api/g50/liste")
def api_g50_liste(ctx):
    return {"declarations": db.lignes(
        "SELECT * FROM declarations_g50 WHERE societe_id = ? ORDER BY periode DESC LIMIT 60",
        (ctx.arg_int("societe"),)
    )}


@route("POST", "/api/g50")
def api_enregistre_g50(ctx):
    """Enregistre (ou met à jour) la déclaration de la période."""
    ctx.interdit_lecture_seule()
    societe_id = ctx.entier("societe_id")
    periode = ctx.champ_requis("periode")
    calculee = calcule_g50(societe_id, periode)

    # Le comptable peut corriger les montants avant dépôt
    def valeur_finale(cle):
        saisi = ctx.champ(cle)
        return util.centimes(saisi) if saisi not in (None, "") else calculee[cle]

    acompte_ibs = util.centimes(ctx.champ("acompte_ibs", 0))
    autres = util.centimes(ctx.champ("autres", 0))
    donnees = {
        "societe_id": societe_id, "periode": periode,
        "date_limite": calculee["date_limite"],
        "ca_taxable": valeur_finale("ca_taxable"),
        "ca_exonere": valeur_finale("ca_exonere"),
        "tva_collectee": valeur_finale("tva_collectee"),
        "tva_deductible_bs": valeur_finale("tva_deductible_bs"),
        "tva_deductible_immo": valeur_finale("tva_deductible_immo"),
        "precompte_anterieur": valeur_finale("precompte_anterieur"),
        "tva_a_payer": valeur_finale("tva_a_payer"),
        "precompte_reporte": valeur_finale("precompte_reporte"),
        "base_tap": valeur_finale("base_tap"),
        "taux_tap": calculee["taux_tap"],
        "tap": valeur_finale("tap"),
        "irg_salaires": valeur_finale("irg_salaires"),
        "irg_ras_autres": valeur_finale("irg_ras_autres"),
        "acompte_ibs": acompte_ibs,
        "droit_timbre": valeur_finale("droit_timbre"),
        "autres": autres,
        "detail": json.dumps(calculee, ensure_ascii=False, default=str),
        "statut": ctx.champ("statut", "calculee"),
        "date_depot": ctx.date("date_depot"),
        "reference_depot": util.nettoie(ctx.champ("reference_depot")),
    }
    donnees["total_a_payer"] = (donnees["tva_a_payer"] + donnees["tap"]
                                + donnees["irg_salaires"] + donnees["irg_ras_autres"]
                                + donnees["acompte_ibs"] + donnees["droit_timbre"]
                                + donnees["autres"])

    with db.transaction():
        existante = db.ligne(
            "SELECT id, statut FROM declarations_g50 WHERE societe_id = ? AND periode = ?",
            (societe_id, periode),
        )
        if existante:
            if existante["statut"] == "payee" and not ctx.booleen("forcer"):
                raise ErreurApplicative(
                    "Cette déclaration est marquée payée : elle n'est plus modifiable."
                )
            db.modifie("declarations_g50", existante["id"], donnees)
            identifiant = existante["id"]
        else:
            donnees["cree_le"] = util.maintenant()
            identifiant = db.insere("declarations_g50", donnees)
        db.trace("enregistrement", "g50", identifiant, periode, ctx.nom_utilisateur)

        _marque_obligation(societe_id, "g50", periode,
                           "fait" if donnees["statut"] in ("deposee", "payee") else "a_faire")
    return {"id": identifiant, "total_a_payer": donnees["total_a_payer"]}


@route("POST", "/api/g50/comptabiliser")
def api_comptabilise_g50(ctx):
    """Génère l'écriture de liquidation de la TVA (et de la TAP le cas échéant).

        4457 TVA collectée        D  TVA collectée du mois
            44566 TVA déductible      C
            44562 TVA déd. immo       C
            44567 Précompte           C  (imputation du crédit antérieur)
            4451 TVA à décaisser      C  (solde à payer)
        ou 44567 Précompte        D  (nouveau crédit reporté)
    """
    ctx.interdit_lecture_seule()
    societe_id = ctx.entier("societe_id")
    periode = ctx.champ_requis("periode")
    declaration = db.ligne(
        "SELECT * FROM declarations_g50 WHERE societe_id = ? AND periode = ?",
        (societe_id, periode),
    )
    if not declaration:
        raise ErreurApplicative(
            "Enregistrez d'abord la déclaration avant de la comptabiliser."
        )
    if declaration["ecriture_id"]:
        raise ErreurApplicative("Cette déclaration est déjà comptabilisée.")

    date = ctx.date("date", util.fin_de_mois(periode))
    libelle = f"Liquidation TVA — {util.libelle_periode(periode)}"
    lignes = []
    if declaration["tva_collectee"]:
        lignes.append({"compte": COMPTE_TVA_COLLECTEE,
                       "debit": declaration["tva_collectee"], "credit": 0,
                       "libelle": libelle})
    if declaration["tva_deductible_bs"]:
        lignes.append({"compte": COMPTE_TVA_DEDUCTIBLE_BS, "debit": 0,
                       "credit": declaration["tva_deductible_bs"], "libelle": libelle})
    if declaration["tva_deductible_immo"]:
        lignes.append({"compte": COMPTE_TVA_DEDUCTIBLE_IMMO, "debit": 0,
                       "credit": declaration["tva_deductible_immo"], "libelle": libelle})
    if declaration["precompte_anterieur"]:
        lignes.append({"compte": COMPTE_PRECOMPTE, "debit": 0,
                       "credit": declaration["precompte_anterieur"],
                       "libelle": "Imputation du précompte antérieur"})
    if declaration["tva_a_payer"]:
        lignes.append({"compte": COMPTE_TVA_A_PAYER, "debit": 0,
                       "credit": declaration["tva_a_payer"],
                       "libelle": f"TVA à décaisser — {util.libelle_periode(periode)}"})
    if declaration["precompte_reporte"]:
        lignes.append({"compte": COMPTE_PRECOMPTE,
                       "debit": declaration["precompte_reporte"], "credit": 0,
                       "libelle": f"Précompte reporté — {util.libelle_periode(periode)}"})

    if len(lignes) < 2:
        raise ErreurApplicative("Aucun mouvement de TVA à comptabiliser sur cette période.")

    with db.transaction():
        ecriture_id = compta.enregistre_ecriture(
            societe_id, "OD", date, libelle, lignes, module="fiscalite",
            source_type="g50", source_id=declaration["id"],
            utilisateur=ctx.nom_utilisateur,
        )
        # TAP : charge de l'exercice et dette envers le Trésor
        ecriture_tap = None
        if declaration["tap"]:
            ecriture_tap = compta.enregistre_ecriture(
                societe_id, "OD", date, f"TAP — {util.libelle_periode(periode)}", [
                    {"compte": COMPTE_TAP_CHARGE, "debit": declaration["tap"], "credit": 0,
                     "libelle": f"TAP {util.libelle_periode(periode)}"},
                    {"compte": COMPTE_TAP_DETTE, "debit": 0, "credit": declaration["tap"],
                     "libelle": f"TAP à payer {util.libelle_periode(periode)}"},
                ],
                module="fiscalite", source_type="g50_tap", source_id=declaration["id"],
                utilisateur=ctx.nom_utilisateur,
            )
        db.modifie("declarations_g50", declaration["id"], {"ecriture_id": ecriture_id})
    return {"ecriture_id": ecriture_id, "ecriture_tap": ecriture_tap}


@route("POST", "/api/g50/payer")
def api_paye_g50(ctx):
    """Règlement de la G50 : solde les dettes fiscales par la trésorerie."""
    ctx.interdit_lecture_seule()
    societe_id = ctx.entier("societe_id")
    periode = ctx.champ_requis("periode")
    declaration = db.ligne(
        "SELECT * FROM declarations_g50 WHERE societe_id = ? AND periode = ?",
        (societe_id, periode))
    if not declaration:
        raise ErreurApplicative("Déclaration introuvable.", 404)
    tres = db.ligne("SELECT * FROM comptes_tresorerie WHERE id = ?",
                    (ctx.entier("tresorerie_id"),))
    if not tres:
        raise ErreurApplicative("Sélectionnez le compte de paiement.")
    date = ctx.date("date", util.aujourdhui())
    libelle = f"Paiement G50 — {util.libelle_periode(periode)}"

    lignes = []
    for compte, montant, texte in (
        (COMPTE_TVA_A_PAYER, declaration["tva_a_payer"], "TVA"),
        (COMPTE_TAP_DETTE, declaration["tap"], "TAP"),
        (COMPTE_IRG_SALAIRES, declaration["irg_salaires"], "IRG salaires"),
        ("4422", declaration["irg_ras_autres"], "IRG retenues diverses"),
        (COMPTE_IBS_ACOMPTE, declaration["acompte_ibs"], "Acompte IBS"),
        (COMPTE_TIMBRE, declaration["droit_timbre"], "Droit de timbre"),
    ):
        if montant:
            lignes.append({"compte": compte, "debit": montant, "credit": 0,
                           "libelle": f"{texte} — {util.libelle_periode(periode)}"})
    total = sum(l["debit"] for l in lignes)
    if total <= 0:
        raise ErreurApplicative("Aucun montant à payer sur cette déclaration.")
    lignes.append({"compte": tres["compte"], "debit": 0, "credit": total,
                   "libelle": libelle})

    with db.transaction():
        ecriture_id = compta.enregistre_ecriture(
            societe_id, "BQ" if tres["type"] in ("banque", "ccp") else "CA",
            date, libelle, lignes, piece=util.nettoie(ctx.champ("reference")),
            module="fiscalite", source_type="g50_paiement", source_id=declaration["id"],
            utilisateur=ctx.nom_utilisateur,
        )
        db.modifie("declarations_g50", declaration["id"], {
            "statut": "payee", "date_depot": declaration["date_depot"] or date,
            "reference_depot": (declaration["reference_depot"]
                                or util.nettoie(ctx.champ("reference"))),
        })
        _marque_obligation(societe_id, "g50", periode, "fait")
    return {"ecriture_id": ecriture_id, "montant": total}


def _marque_obligation(societe_id: int, code: str, periode: str, statut: str) -> None:
    obligation = db.ligne(
        "SELECT id FROM obligations WHERE societe_id = ? AND code = ? AND periode = ?",
        (societe_id, code, periode))
    if obligation:
        db.modifie("obligations", obligation["id"], {
            "statut": statut,
            "date_execution": util.aujourdhui() if statut == "fait" else None,
        })


# ---------------------------------------------------------------------------
# Livres de TVA (ventes / achats)
# ---------------------------------------------------------------------------

@route("GET", "/api/livre-tva")
def api_livre_tva(ctx):
    """Détail des opérations taxables — pièce justificative de la G50."""
    societe_id = ctx.arg_int("societe")
    periode = ctx.arg("periode") or util.periode_de(util.aujourdhui())
    sens = ctx.arg("sens", "ventes")
    du, au = periode + "-01", util.fin_de_mois(periode)
    compte_tva = COMPTE_TVA_COLLECTEE if sens == "ventes" else "4456"
    colonne = "credit" if sens == "ventes" else "debit"

    operations = db.lignes(
        f"SELECT e.id, e.date, e.numero, e.piece, e.libelle, j.code AS journal, "
        f"  l.{colonne} AS tva, t.raison_sociale AS tiers, t.nif, t.rc "
        "FROM lignes l JOIN ecritures e ON e.id = l.ecriture_id "
        "JOIN journaux j ON j.id = e.journal_id "
        "LEFT JOIN tiers t ON t.id = ("
        "  SELECT tiers_id FROM lignes WHERE ecriture_id = e.id AND tiers_id IS NOT NULL LIMIT 1) "
        "WHERE e.societe_id = ? AND l.compte LIKE ? AND e.date BETWEEN ? AND ? "
        f"AND l.{colonne} > 0 ORDER BY e.date, e.id",
        (societe_id, compte_tva + "%", du, au),
    )
    for op in operations:
        base = db.valeur(
            "SELECT COALESCE(SUM(" + ("credit" if sens == "ventes" else "debit") + "),0) "
            "FROM lignes WHERE ecriture_id = ? AND compte LIKE ?",
            (op["id"], "7%" if sens == "ventes" else "6%"), 0
        )
        op["base_ht"] = base
    return {
        "periode": periode, "sens": sens, "operations": operations,
        "total_tva": sum(o["tva"] for o in operations),
        "total_base": sum(o["base_ht"] for o in operations),
    }


@route("GET", "/api/export/livre-tva")
def api_export_livre_tva(ctx):
    societe_id = ctx.arg_int("societe")
    soc = compta.societe(societe_id)
    donnees = api_livre_tva(ctx)
    classeur = tableur.Classeur()
    f = classeur.feuille(f"TVA {donnees['sens']}")
    f.titre(f"{soc['raison_sociale']} — Livre des {donnees['sens']} "
            f"({util.libelle_periode(donnees['periode'])})")
    f.ajoute(tableur.texte(f"NIF : {soc['nif'] or '—'}    "
                           f"Article d'imposition : {soc['article_imposition'] or '—'}"))
    f.vide()
    f.entetes("Date", "Journal", "N° écriture", "Pièce", "Tiers", "NIF", "Libellé",
              "Base HT", "TVA")
    f.largeurs_auto(12, 8, 14, 16, 32, 20, 42, 16, 16)
    for op in donnees["operations"]:
        f.ajoute(
            tableur.date_cel(op["date"]), tableur.texte(op["journal"]),
            tableur.texte(op["numero"]), tableur.texte(op["piece"]),
            tableur.texte(op["tiers"]), tableur.texte(op["nif"]),
            tableur.texte(op["libelle"]), tableur.monnaie(op["base_ht"]),
            tableur.monnaie(op["tva"]),
        )
    f.ajoute(tableur.texte("TOTAUX", tableur.GRAS), *[tableur.texte("")] * 6,
             tableur.monnaie(donnees["total_base"], total=True),
             tableur.monnaie(donnees["total_tva"], total=True))
    return Reponse(classeur.octets(),
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   f"livre_tva_{donnees['sens']}_{donnees['periode']}.xlsx")


# ---------------------------------------------------------------------------
# IBS
# ---------------------------------------------------------------------------

@route("GET", "/api/ibs")
def api_ibs(ctx):
    """Calcul de l'IBS de l'exercice et des acomptes provisionnels."""
    societe_id = ctx.arg_int("societe")
    ex = compta.exercice(ctx.arg_int("exercice"))
    soc = compta.societe(societe_id)
    annee = int(ex["date_fin"][:4])

    produits = compta.solde_compte(societe_id, "7", ex["date_debut"], ex["date_fin"])
    charges = compta.solde_compte(societe_id, "6", ex["date_debut"], ex["date_fin"])
    # L'IBS lui-même (695) ne fait pas partie du résultat imposable
    ibs_deja = compta.solde_compte(societe_id, "695", ex["date_debut"], ex["date_fin"])
    resultat_comptable = ((produits["credit"] - produits["debit"])
                          - (charges["debit"] - charges["credit"]))
    resultat_avant_impot = resultat_comptable + (ibs_deja["debit"] - ibs_deja["credit"])

    reintegrations = util.centimes(ctx.arg("reintegrations", 0))
    deductions = util.centimes(ctx.arg("deductions", 0))
    deficits_anterieurs = util.centimes(ctx.arg("deficits", 0))
    resultat_fiscal = (resultat_avant_impot + reintegrations - deductions
                       - deficits_anterieurs)

    taux = soc["taux_ibs"] or db.parametre_fiscal_int(annee, "ibs_autres", 2600)
    ibs_brut = util.applique_taux(max(resultat_fiscal, 0), taux)
    minimum = db.parametre_fiscal_int(annee, "ibs_minimum", 0)
    ibs_du = max(ibs_brut, minimum) if minimum else ibs_brut

    acomptes_verses = compta.solde_compte(societe_id, COMPTE_IBS_ACOMPTE,
                                          ex["date_debut"], ex["date_fin"])["solde"]
    taux_acompte = db.parametre_fiscal_int(annee, "ibs_acompte_taux", 3000)

    return {
        "exercice": ex,
        "resultat_comptable": resultat_comptable,
        "resultat_avant_impot": resultat_avant_impot,
        "reintegrations": reintegrations, "deductions": deductions,
        "deficits_anterieurs": deficits_anterieurs,
        "resultat_fiscal": resultat_fiscal,
        "taux_ibs": taux, "ibs_brut": ibs_brut, "minimum_imposition": minimum,
        "ibs_du": ibs_du,
        "acomptes_verses": acomptes_verses,
        "solde_a_payer": ibs_du - acomptes_verses,
        "acompte_suivant": util.applique_taux(ibs_du, taux_acompte),
        "taux_acompte": taux_acompte,
        "note": "Le résultat fiscal doit être ajusté des réintégrations et déductions "
                "extra-comptables propres à votre situation (amortissements excédentaires, "
                "amendes, provisions non déductibles, déficits reportables…). "
                "Saisissez-les ci-dessus avant de retenir le montant.",
    }


@route("POST", "/api/ibs/comptabiliser")
def api_comptabilise_ibs(ctx):
    ctx.interdit_lecture_seule()
    societe_id = ctx.entier("societe_id")
    ex = compta.exercice(ctx.entier("exercice_id"))
    montant = ctx.montant("montant")
    if montant <= 0:
        raise ErreurApplicative("Montant d'IBS invalide.")
    date = ctx.date("date", ex["date_fin"])
    acomptes = ctx.montant("acomptes_imputes")
    libelle = f"Impôt sur les bénéfices — exercice {ex['libelle']}"
    lignes = [{"compte": "695", "debit": montant, "credit": 0, "libelle": libelle}]
    if acomptes:
        lignes.append({"compte": COMPTE_IBS_ACOMPTE, "debit": 0, "credit": acomptes,
                       "libelle": "Imputation des acomptes provisionnels versés"})
    solde = montant - acomptes
    if solde > 0:
        lignes.append({"compte": "4442", "debit": 0, "credit": solde,
                       "libelle": "Solde d'IBS à payer"})
    elif solde < 0:
        lignes.append({"compte": "4441", "debit": -solde, "credit": 0,
                       "libelle": "Excédent d'acomptes à reporter"})
    with db.transaction():
        ecriture_id = compta.enregistre_ecriture(
            societe_id, "OD", date, libelle, lignes, module="fiscalite",
            source_type="ibs", source_id=ex["id"], utilisateur=ctx.nom_utilisateur,
        )
    return {"ecriture_id": ecriture_id}


# ---------------------------------------------------------------------------
# Calendrier des obligations
# ---------------------------------------------------------------------------

@route("GET", "/api/obligations")
def api_obligations(ctx):
    societe_id = ctx.arg_int("societe")
    conditions = ["societe_id = ?"]
    params: list = [societe_id]
    if ctx.arg("statut"):
        conditions.append("statut = ?")
        params.append(ctx.arg("statut"))
    if ctx.arg("annee"):
        conditions.append("date_limite LIKE ?")
        params.append(ctx.arg("annee") + "%")
    obligations = db.lignes(
        f"SELECT * FROM obligations WHERE {' AND '.join(conditions)} "
        "ORDER BY date_limite", params
    )
    aujourdhui = util.aujourdhui()
    for o in obligations:
        if o["statut"] == "a_faire" and o["date_limite"] < aujourdhui:
            o["en_retard"] = True
            o["jours_retard"] = util.jours_ecart(o["date_limite"], aujourdhui)
        else:
            o["en_retard"] = False
            o["jours_restants"] = util.jours_ecart(aujourdhui, o["date_limite"])
    return {"obligations": obligations}


@route("POST", "/api/obligations/generer")
def api_genere_obligations(ctx):
    """Crée le calendrier fiscal et social de l'année."""
    ctx.interdit_lecture_seule()
    societe_id = ctx.entier("societe_id")
    annee = ctx.entier("annee") or int(util.aujourdhui()[:4])

    from noyau.config import config
    reference = json.loads(
        (config.dossier_reference / "parametres_fiscaux.json").read_text("utf-8")
    )
    modeles = reference.get("echeances_annuelles", [])

    creees = 0
    with db.transaction():
        for modele in modeles:
            if modele["periodicite"] == "mensuelle":
                for mois in range(1, 13):
                    periode_declaree = f"{annee}-{mois:02d}"
                    periode_depot = util.mois_suivant(periode_declaree)
                    date_limite = util.jour_du_mois(periode_depot, modele["jour"])
                    if _cree_obligation(societe_id, modele["code"],
                                        f"{modele['libelle']} — "
                                        f"{util.libelle_periode(periode_declaree)}",
                                        periode_declaree, date_limite):
                        creees += 1
            else:
                date_limite = f"{annee}-{modele['date']}"
                if _cree_obligation(societe_id, modele["code"], modele["libelle"],
                                    str(annee), date_limite):
                    creees += 1
    return {"creees": creees, "annee": annee}


def _cree_obligation(societe_id, code, libelle, periode, date_limite) -> bool:
    if db.ligne("SELECT id FROM obligations WHERE societe_id = ? AND code = ? "
                "AND periode = ?", (societe_id, code, periode)):
        return False
    db.insere("obligations", {
        "societe_id": societe_id, "code": code, "libelle": libelle,
        "periode": periode, "date_limite": date_limite, "statut": "a_faire",
    })
    return True


@route("PUT", "/api/obligations/<id>")
def api_modifie_obligation(ctx):
    ctx.interdit_lecture_seule()
    identifiant = int(ctx.params["id"])
    with db.transaction():
        db.modifie("obligations", identifiant, {
            "statut": ctx.champ("statut", "a_faire"),
            "date_execution": ctx.date("date_execution"),
            "reference": util.nettoie(ctx.champ("reference")),
            "notes": util.nettoie(ctx.champ("notes")),
        })
    return {"ok": True}
