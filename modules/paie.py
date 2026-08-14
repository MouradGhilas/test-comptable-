"""Paie : salariés, bulletins, cotisations CNAS et IRG sur salaires.

Le calcul suit la mécanique algérienne usuelle :

    Salaire brut          = salaire de base + primes
    Base cotisable        = éléments soumis à cotisation sociale
    Retenue CNAS salarié  = base cotisable × taux salarial
    Base imposable IRG    = salaire brut − retenue CNAS − éléments non imposables
    IRG brut              = barème progressif mensuel
    IRG net               = IRG brut − abattement (plafonné)
    Net à payer           = salaire brut − CNAS salarié − IRG − autres retenues

Tous les taux, le barème et l'abattement sont lus dans les paramètres
fiscaux de l'année : ils se règlent sans toucher au code.
"""

from __future__ import annotations

import json

from noyau import base as db
from noyau import util
from noyau import tableur
from noyau.serveur import ErreurApplicative, route, Reponse
from modules import comptabilite as compta

COMPTE_SALAIRES_BRUTS = "631"
COMPTE_CHARGES_SOCIALES = "635"
COMPTE_PERSONNEL_DU = "421"
COMPTE_CNAS = "431"
COMPTE_IRG = "4421"


def impot_progressif(base: int, tranches: list[dict]) -> int:
    """Applique un barème progressif. `plafond` en centimes, `taux` en millièmes de %."""
    if base <= 0 or not tranches:
        return 0
    impot = 0
    plancher = 0
    for tranche in tranches:
        plafond = tranche.get("plafond")
        taux = int(tranche.get("taux") or 0)
        if plafond is None:
            impot += util.applique_taux(max(base - plancher, 0), taux)
            break
        portion = min(base, int(plafond)) - plancher
        if portion > 0:
            impot += util.applique_taux(portion, taux)
        plancher = int(plafond)
        if base <= plancher:
            break
    return impot


def calcule_bulletin(societe_id: int, salarie: dict, periode: str,
                     saisie: dict | None = None) -> dict:
    """Calcule un bulletin sans l'enregistrer."""
    saisie = saisie or {}
    annee = int(periode[:4])

    jours = int(round(float(saisie.get("jours_travailles", 30)) * 1000))
    salaire_base = util.centimes(saisie.get("salaire_base")) or salarie["salaire_base"]
    if jours != 30000:
        salaire_base = util.part_proportionnelle(salaire_base, jours, 30000)

    primes_saisies = saisie.get("primes")
    if primes_saisies is None:
        primes_saisies = json.loads(salarie["primes"]) if salarie["primes"] else []

    primes_soumises = primes_non_soumises = 0
    detail_primes = []
    for prime in primes_saisies:
        montant = util.centimes(prime.get("montant"))
        if not montant:
            continue
        soumis_cnas = bool(prime.get("soumis_cnas", True))
        soumis_irg = bool(prime.get("soumis_irg", True))
        if soumis_cnas:
            primes_soumises += montant
        else:
            primes_non_soumises += montant
        detail_primes.append({
            "libelle": prime.get("libelle", "Prime"), "montant": montant,
            "soumis_cnas": soumis_cnas, "soumis_irg": soumis_irg,
        })

    salaire_brut = salaire_base + primes_soumises + primes_non_soumises
    base_cnas = salaire_base + primes_soumises

    taux_salarial = db.parametre_fiscal_int(annee, "cnas_part_salariale", 900)
    taux_patronal = db.parametre_fiscal_int(annee, "cnas_part_patronale", 2600)
    cnas_salarie = util.applique_taux(base_cnas, taux_salarial)
    cnas_patronale = util.applique_taux(base_cnas, taux_patronal)

    non_imposable = sum(p["montant"] for p in detail_primes if not p["soumis_irg"])
    base_irg = max(salaire_brut - cnas_salarie - non_imposable, 0)

    seuil = db.parametre_fiscal_int(annee, "irg_seuil_exoneration", 0)
    if seuil and salaire_brut <= seuil:
        irg_brut = abattement = irg = 0
    else:
        irg_brut = impot_progressif(base_irg, db.bareme_irg(annee))
        taux_abattement = db.parametre_fiscal_int(annee, "irg_abattement_taux", 0)
        abattement = util.applique_taux(irg_brut, taux_abattement)
        minimum = db.parametre_fiscal_int(annee, "irg_abattement_min_mois", 0)
        maximum = db.parametre_fiscal_int(annee, "irg_abattement_max_mois", 0)
        if taux_abattement:
            if minimum:
                abattement = max(abattement, min(minimum, irg_brut))
            if maximum:
                abattement = min(abattement, maximum)
        irg = max(irg_brut - abattement, 0)

    autres_retenues = util.centimes(saisie.get("autres_retenues", 0))
    net = salaire_brut - cnas_salarie - irg - autres_retenues
    cout_employeur = salaire_brut + cnas_patronale

    return {
        "salarie_id": salarie["id"], "periode": periode,
        "jours_travailles": jours, "salaire_base": salaire_base,
        "primes": detail_primes,
        "primes_soumises": primes_soumises,
        "primes_non_soumises": primes_non_soumises,
        "salaire_brut": salaire_brut, "base_cnas": base_cnas,
        "taux_cnas_salarie": taux_salarial, "cnas_salarie": cnas_salarie,
        "taux_cnas_patronale": taux_patronal, "cnas_patronale": cnas_patronale,
        "base_irg": base_irg, "irg_brut": irg_brut, "abattement_irg": abattement,
        "irg": irg, "autres_retenues": autres_retenues,
        "net_a_payer": net, "cout_employeur": cout_employeur,
    }


# ---------------------------------------------------------------------------
# Salariés
# ---------------------------------------------------------------------------

@route("GET", "/api/salaries")
def api_salaries(ctx):
    salaries = db.lignes(
        "SELECT * FROM salaries WHERE societe_id = ? "
        + ("AND actif = 1 " if ctx.arg("actifs_seuls") == "1" else "")
        + "ORDER BY nom, prenom", (ctx.arg_int("societe"),)
    )
    for s in salaries:
        s["primes"] = json.loads(s["primes"]) if s["primes"] else []
    return {"salaries": salaries}


@route("POST", "/api/salaries")
def api_cree_salarie(ctx):
    ctx.interdit_lecture_seule()
    societe_id = ctx.entier("societe_id")
    with db.transaction():
        matricule = util.nettoie(ctx.champ("matricule")) or db.numero_suivant(
            societe_id, "tiers_salarie")
        if db.ligne("SELECT id FROM salaries WHERE societe_id = ? AND matricule = ?",
                    (societe_id, matricule)):
            raise ErreurApplicative(f"Le matricule « {matricule} » existe déjà.")
        identifiant = db.insere("salaries", {
            "societe_id": societe_id, "matricule": matricule,
            "nom": ctx.champ_requis("nom"), "prenom": ctx.champ_requis("prenom"),
            "date_naissance": ctx.date("date_naissance"),
            "num_secu": util.nettoie(ctx.champ("num_secu")),
            "poste": util.nettoie(ctx.champ("poste")),
            "categorie": util.nettoie(ctx.champ("categorie")),
            "date_embauche": ctx.date("date_embauche"),
            "type_contrat": ctx.champ("type_contrat", "CDI"),
            "salaire_base": ctx.montant("salaire_base"),
            "primes": json.dumps(ctx.champ("primes") or [], ensure_ascii=False),
            "situation_familiale": util.nettoie(ctx.champ("situation_familiale")),
            "nb_enfants": ctx.entier("nb_enfants", 0) or 0,
            "rib": util.nettoie(ctx.champ("rib")),
            "actif": 1,
        })
    return {"id": identifiant, "matricule": matricule}


@route("PUT", "/api/salaries/<id>")
def api_modifie_salarie(ctx):
    ctx.interdit_lecture_seule()
    with db.transaction():
        db.modifie("salaries", int(ctx.params["id"]), {
            "nom": ctx.champ_requis("nom"), "prenom": ctx.champ_requis("prenom"),
            "date_naissance": ctx.date("date_naissance"),
            "num_secu": util.nettoie(ctx.champ("num_secu")),
            "poste": util.nettoie(ctx.champ("poste")),
            "categorie": util.nettoie(ctx.champ("categorie")),
            "date_embauche": ctx.date("date_embauche"),
            "date_sortie": ctx.date("date_sortie"),
            "type_contrat": ctx.champ("type_contrat", "CDI"),
            "salaire_base": ctx.montant("salaire_base"),
            "primes": json.dumps(ctx.champ("primes") or [], ensure_ascii=False),
            "situation_familiale": util.nettoie(ctx.champ("situation_familiale")),
            "nb_enfants": ctx.entier("nb_enfants", 0) or 0,
            "rib": util.nettoie(ctx.champ("rib")),
            "actif": ctx.booleen("actif", True),
        })
    return {"ok": True}


# ---------------------------------------------------------------------------
# Bulletins
# ---------------------------------------------------------------------------

@route("GET", "/api/bulletins")
def api_bulletins(ctx):
    societe_id = ctx.arg_int("societe")
    conditions = ["b.societe_id = ?"]
    params: list = [societe_id]
    if ctx.arg("periode"):
        conditions.append("b.periode = ?")
        params.append(ctx.arg("periode"))
    if ctx.arg("salarie"):
        conditions.append("b.salarie_id = ?")
        params.append(ctx.arg_int("salarie"))
    bulletins = db.lignes(
        "SELECT b.*, s.nom, s.prenom, s.matricule, s.poste "
        "FROM bulletins b JOIN salaries s ON s.id = b.salarie_id "
        f"WHERE {' AND '.join(conditions)} ORDER BY b.periode DESC, s.nom LIMIT 500",
        params,
    )
    return {
        "bulletins": bulletins,
        "totaux": {
            "brut": sum(b["salaire_brut"] for b in bulletins),
            "cnas_salarie": sum(b["cnas_salarie"] for b in bulletins),
            "cnas_patronale": sum(b["cnas_patronale"] for b in bulletins),
            "irg": sum(b["irg"] for b in bulletins),
            "net": sum(b["net_a_payer"] for b in bulletins),
            "cout": sum(b["cout_employeur"] for b in bulletins),
        },
    }


@route("POST", "/api/bulletins/simuler")
def api_simule(ctx):
    """Calcule un bulletin sans l'enregistrer (aide à la négociation salariale)."""
    societe_id = ctx.entier("societe_id")
    salarie_id = ctx.entier("salarie_id")
    if salarie_id:
        salarie = db.ligne("SELECT * FROM salaries WHERE id = ?", (salarie_id,))
        if not salarie:
            raise ErreurApplicative("Salarié introuvable.", 404)
    else:
        salarie = {"id": None, "salaire_base": ctx.montant("salaire_base"), "primes": None}
    periode = ctx.champ("periode") or util.periode_de(util.aujourdhui())
    return calcule_bulletin(societe_id, salarie, periode, ctx.corps)


@route("POST", "/api/bulletins/generer")
def api_genere_bulletins(ctx):
    """Génère les bulletins du mois pour tous les salariés actifs."""
    ctx.interdit_lecture_seule()
    societe_id = ctx.entier("societe_id")
    periode = ctx.champ("periode") or util.periode_de(util.aujourdhui())
    salaries = db.lignes(
        "SELECT * FROM salaries WHERE societe_id = ? AND actif = 1 "
        "AND (date_sortie IS NULL OR date_sortie >= ?)",
        (societe_id, periode + "-01"),
    )
    crees, existants = 0, 0
    with db.transaction():
        for salarie in salaries:
            if db.ligne("SELECT id FROM bulletins WHERE societe_id = ? AND salarie_id = ? "
                        "AND periode = ?", (societe_id, salarie["id"], periode)):
                existants += 1
                continue
            calcul = calcule_bulletin(societe_id, salarie, periode)
            _enregistre_bulletin(societe_id, calcul)
            crees += 1
        db.trace("generation", "bulletins", None,
                 {"periode": periode, "crees": crees}, ctx.nom_utilisateur)
    return {"crees": crees, "existants": existants, "periode": periode}


def _enregistre_bulletin(societe_id: int, calcul: dict) -> int:
    return db.insere("bulletins", {
        "societe_id": societe_id, "salarie_id": calcul["salarie_id"],
        "periode": calcul["periode"], "jours_travailles": calcul["jours_travailles"],
        "salaire_base": calcul["salaire_base"],
        "primes_soumises": calcul["primes_soumises"],
        "primes_non_soumises": calcul["primes_non_soumises"],
        "salaire_brut": calcul["salaire_brut"], "base_cnas": calcul["base_cnas"],
        "cnas_salarie": calcul["cnas_salarie"], "cnas_patronale": calcul["cnas_patronale"],
        "base_irg": calcul["base_irg"], "irg": calcul["irg"],
        "abattement_irg": calcul["abattement_irg"],
        "autres_retenues": calcul["autres_retenues"],
        "net_a_payer": calcul["net_a_payer"], "cout_employeur": calcul["cout_employeur"],
        "detail": json.dumps(calcul, ensure_ascii=False),
        "statut": "brouillon", "cree_le": util.maintenant(),
    })


@route("PUT", "/api/bulletins/<id>")
def api_modifie_bulletin(ctx):
    ctx.interdit_lecture_seule()
    identifiant = int(ctx.params["id"])
    bulletin = db.ligne("SELECT * FROM bulletins WHERE id = ?", (identifiant,))
    if not bulletin:
        raise ErreurApplicative("Bulletin introuvable.", 404)
    if bulletin["statut"] != "brouillon":
        raise ErreurApplicative("Bulletin déjà comptabilisé : il n'est plus modifiable.")
    salarie = db.ligne("SELECT * FROM salaries WHERE id = ?", (bulletin["salarie_id"],))
    calcul = calcule_bulletin(bulletin["societe_id"], salarie, bulletin["periode"], ctx.corps)
    with db.transaction():
        db.modifie("bulletins", identifiant, {
            "jours_travailles": calcul["jours_travailles"],
            "salaire_base": calcul["salaire_base"],
            "primes_soumises": calcul["primes_soumises"],
            "primes_non_soumises": calcul["primes_non_soumises"],
            "salaire_brut": calcul["salaire_brut"], "base_cnas": calcul["base_cnas"],
            "cnas_salarie": calcul["cnas_salarie"],
            "cnas_patronale": calcul["cnas_patronale"],
            "base_irg": calcul["base_irg"], "irg": calcul["irg"],
            "abattement_irg": calcul["abattement_irg"],
            "autres_retenues": calcul["autres_retenues"],
            "net_a_payer": calcul["net_a_payer"],
            "cout_employeur": calcul["cout_employeur"],
            "detail": json.dumps(calcul, ensure_ascii=False),
        })
    return calcul


@route("POST", "/api/bulletins/comptabiliser")
def api_comptabilise_paie(ctx):
    """Écriture de paie du mois, tous salariés confondus.

        631 Rémunérations du personnel   D  brut total
        635 Cotisations sociales         D  part patronale
            421 Personnel — rému. dues       C  net à payer
            431 Sécurité sociale (CNAS)      C  part salariale + patronale
            4421 IRG / Salaires              C  retenue IRG
            427 Oppositions                  C  autres retenues
    """
    ctx.interdit_lecture_seule()
    societe_id = ctx.entier("societe_id")
    periode = ctx.champ_requis("periode")
    bulletins = db.lignes(
        "SELECT * FROM bulletins WHERE societe_id = ? AND periode = ? AND statut = 'brouillon'",
        (societe_id, periode),
    )
    if not bulletins:
        raise ErreurApplicative("Aucun bulletin en brouillon pour cette période.")

    brut = sum(b["salaire_brut"] for b in bulletins)
    patronale = sum(b["cnas_patronale"] for b in bulletins)
    salariale = sum(b["cnas_salarie"] for b in bulletins)
    irg = sum(b["irg"] for b in bulletins)
    autres = sum(b["autres_retenues"] for b in bulletins)
    net = sum(b["net_a_payer"] for b in bulletins)

    date = ctx.date("date", util.fin_de_mois(periode))
    libelle = f"Paie de {util.libelle_periode(periode)}"
    lignes = [
        {"compte": COMPTE_SALAIRES_BRUTS, "debit": brut, "credit": 0, "libelle": libelle},
        {"compte": COMPTE_CHARGES_SOCIALES, "debit": patronale, "credit": 0,
         "libelle": f"Cotisations patronales — {util.libelle_periode(periode)}"},
        {"compte": COMPTE_PERSONNEL_DU, "debit": 0, "credit": net,
         "libelle": f"Net à payer — {util.libelle_periode(periode)}"},
        {"compte": COMPTE_CNAS, "debit": 0, "credit": salariale + patronale,
         "libelle": f"CNAS — {util.libelle_periode(periode)}"},
    ]
    if irg:
        lignes.append({"compte": COMPTE_IRG, "debit": 0, "credit": irg,
                       "libelle": f"IRG/Salaires — {util.libelle_periode(periode)}"})
    if autres:
        lignes.append({"compte": "427", "debit": 0, "credit": autres,
                       "libelle": "Retenues diverses"})

    programme_id = ctx.entier("programme_id")
    if programme_id:
        for l in lignes:
            if l["compte"] in (COMPTE_SALAIRES_BRUTS, COMPTE_CHARGES_SOCIALES):
                l["programme_id"] = programme_id
                l["poste_budget"] = "frais_generaux"

    with db.transaction():
        ecriture_id = compta.enregistre_ecriture(
            societe_id, "PA", date, libelle, lignes, module="paie",
            source_type="paie_periode", source_id=None, utilisateur=ctx.nom_utilisateur,
        )
        for b in bulletins:
            db.modifie("bulletins", b["id"],
                       {"statut": "comptabilise", "ecriture_id": ecriture_id})
        db.trace("comptabilisation", "paie", ecriture_id, periode, ctx.nom_utilisateur)
    return {"ecriture_id": ecriture_id, "bulletins": len(bulletins),
            "brut": brut, "net": net}


@route("POST", "/api/bulletins/payer")
def api_paye_salaires(ctx):
    ctx.interdit_lecture_seule()
    societe_id = ctx.entier("societe_id")
    periode = ctx.champ_requis("periode")
    tres = db.ligne("SELECT * FROM comptes_tresorerie WHERE id = ?",
                    (ctx.entier("tresorerie_id"),))
    if not tres:
        raise ErreurApplicative("Sélectionnez le compte de paiement.")
    net = db.valeur(
        "SELECT COALESCE(SUM(net_a_payer),0) FROM bulletins WHERE societe_id = ? "
        "AND periode = ? AND statut = 'comptabilise'", (societe_id, periode), 0
    )
    if not net:
        raise ErreurApplicative(
            "Aucun salaire comptabilisé à payer pour cette période."
        )
    date = ctx.date("date", util.aujourdhui())
    libelle = f"Règlement des salaires — {util.libelle_periode(periode)}"
    with db.transaction():
        ecriture_id = compta.enregistre_ecriture(
            societe_id, "BQ" if tres["type"] in ("banque", "ccp") else "CA",
            date, libelle, [
                {"compte": COMPTE_PERSONNEL_DU, "debit": net, "credit": 0,
                 "libelle": libelle},
                {"compte": tres["compte"], "debit": 0, "credit": net, "libelle": libelle},
            ],
            module="paie", source_type="paiement_salaires",
            utilisateur=ctx.nom_utilisateur,
        )
        db.execute("UPDATE bulletins SET statut = 'paye' WHERE societe_id = ? "
                   "AND periode = ? AND statut = 'comptabilise'", (societe_id, periode))
    return {"ecriture_id": ecriture_id, "montant": net}


@route("GET", "/api/export/paie")
def api_export_paie(ctx):
    """Livre de paie de la période — support de la déclaration CNAS."""
    societe_id = ctx.arg_int("societe")
    soc = compta.societe(societe_id)
    periode = ctx.arg("periode") or util.periode_de(util.aujourdhui())
    donnees = api_bulletins(ctx)

    classeur = tableur.Classeur()
    f = classeur.feuille("Livre de paie")
    f.titre(f"{soc['raison_sociale']} — Livre de paie {util.libelle_periode(periode)}")
    f.vide()
    f.entetes("Matricule", "Nom", "Prénom", "N° sécurité sociale", "Poste",
              "Jours", "Salaire de base", "Primes soumises", "Primes non soumises",
              "Brut", "Base CNAS", "CNAS 9 %", "Base IRG", "IRG", "Autres retenues",
              "Net à payer", "CNAS patronale", "Coût employeur")
    f.largeurs_auto(11, 20, 18, 20, 20, 8, 16, 16, 17, 16, 16, 14, 16, 14, 15, 16, 16, 17)
    salaries = {s["id"]: s for s in db.lignes(
        "SELECT * FROM salaries WHERE societe_id = ?", (societe_id,))}
    for b in donnees["bulletins"]:
        s = salaries.get(b["salarie_id"], {})
        f.ajoute(
            tableur.texte(b["matricule"]), tableur.texte(b["nom"]),
            tableur.texte(b["prenom"]), tableur.texte(s.get("num_secu")),
            tableur.texte(b["poste"]),
            tableur.nombre(b["jours_travailles"] / 1000.0, tableur.NORMAL),
            tableur.monnaie(b["salaire_base"]), tableur.monnaie(b["primes_soumises"]),
            tableur.monnaie(b["primes_non_soumises"]), tableur.monnaie(b["salaire_brut"]),
            tableur.monnaie(b["base_cnas"]), tableur.monnaie(b["cnas_salarie"]),
            tableur.monnaie(b["base_irg"]), tableur.monnaie(b["irg"]),
            tableur.monnaie(b["autres_retenues"]), tableur.monnaie(b["net_a_payer"]),
            tableur.monnaie(b["cnas_patronale"]), tableur.monnaie(b["cout_employeur"]),
        )
    t = donnees["totaux"]
    f.ajoute(tableur.texte("TOTAUX", tableur.GRAS), *[tableur.texte("")] * 8,
             tableur.monnaie(t["brut"], total=True), tableur.texte(""),
             tableur.monnaie(t["cnas_salarie"], total=True), tableur.texte(""),
             tableur.monnaie(t["irg"], total=True), tableur.texte(""),
             tableur.monnaie(t["net"], total=True),
             tableur.monnaie(t["cnas_patronale"], total=True),
             tableur.monnaie(t["cout"], total=True))
    return Reponse(classeur.octets(),
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   f"livre_paie_{soc['code']}_{periode}.xlsx")
