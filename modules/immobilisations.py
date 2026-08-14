"""Immobilisations et amortissements.

Génère le plan d'amortissement (linéaire ou dégressif) et l'écriture de
dotation de l'exercice. Le prorata temporis est calculé au mois, à partir de
la date de mise en service.
"""

from __future__ import annotations

from noyau import base as db
from noyau import util
from noyau import tableur
from noyau.serveur import ErreurApplicative, route, Reponse
from modules import comptabilite as compta

# Correspondance usuelle compte d'immobilisation → compte d'amortissement
COMPTES_AMORTISSEMENT = {
    "204": "2804", "205": "2804", "208": "2804",
    "212": "2812", "213": "2813", "215": "2815",
    "218": "2818", "2182": "2818", "2183": "2818", "2184": "2818", "2185": "2818",
}

DUREES_INDICATIVES = {
    "213": 240,   # constructions : 20 ans
    "2182": 60,   # matériel de transport : 5 ans
    "2183": 36,   # matériel informatique : 3 ans
    "2184": 120,  # mobilier : 10 ans
    "215": 120,   # installations techniques : 10 ans
    "204": 36,    # logiciels : 3 ans
}


def compte_amortissement(compte: str) -> str:
    for prefixe in sorted(COMPTES_AMORTISSEMENT, key=len, reverse=True):
        if compte.startswith(prefixe):
            return COMPTES_AMORTISSEMENT[prefixe]
    return "281"


def plan_amortissement(immo: dict) -> list[dict]:
    """Calcule le plan année par année."""
    base = immo["valeur_acquisition"] - immo["valeur_residuelle"]
    duree = max(immo["duree_mois"], 1)
    debut = immo["date_mise_service"] or immo["date_acquisition"]
    annee_debut = int(debut[:4])
    mois_debut = int(debut[5:7])

    plan = []
    cumul = 0
    reste_mois = duree
    annee = annee_debut
    valeur_nette = immo["valeur_acquisition"]

    if immo["mode"] == "degressif":
        taux_lineaire = 12 * util.BASE_TAUX // duree
        # Le coefficient dégressif est stocké en millièmes (1,5 => 1500)
        taux = min(taux_lineaire * max(immo["coefficient"], 1000) // 1000, util.BASE_TAUX)
    else:
        taux = None

    while reste_mois > 0 and len(plan) < 60:
        mois_annee = 12 - mois_debut + 1 if annee == annee_debut else 12
        mois_annee = min(mois_annee, reste_mois)

        if immo["mode"] == "degressif":
            dotation_annuelle = util.applique_taux(valeur_nette - immo["valeur_residuelle"],
                                                   taux)
            lineaire_restant = util.part_proportionnelle(
                valeur_nette - immo["valeur_residuelle"], 12, max(reste_mois, 1))
            dotation_annuelle = max(dotation_annuelle, lineaire_restant)
            dotation = util.part_proportionnelle(dotation_annuelle, mois_annee, 12)
        else:
            dotation = util.part_proportionnelle(base, mois_annee, duree)

        if cumul + dotation > base:
            dotation = base - cumul
        cumul += dotation
        valeur_nette = immo["valeur_acquisition"] - cumul

        plan.append({
            "annee": annee, "mois": mois_annee, "base": base,
            "dotation": dotation, "cumul": cumul, "vnc": valeur_nette,
        })
        reste_mois -= mois_annee
        annee += 1
        if cumul >= base:
            break
    return plan


@route("GET", "/api/immobilisations")
def api_liste(ctx):
    societe_id = ctx.arg_int("societe")
    conditions = ["societe_id = ?"]
    params: list = [societe_id]
    if ctx.arg("statut"):
        conditions.append("statut = ?")
        params.append(ctx.arg("statut"))
    immos = db.lignes(
        f"SELECT * FROM immobilisations WHERE {' AND '.join(conditions)} "
        "ORDER BY compte, code", params
    )
    annee = ctx.arg_int("annee") or int(util.aujourdhui()[:4])
    for immo in immos:
        plan = plan_amortissement(immo)
        realise = [p for p in plan if p["annee"] <= annee]
        immo["cumul_amortissement"] = realise[-1]["cumul"] if realise else 0
        immo["vnc"] = immo["valeur_acquisition"] - immo["cumul_amortissement"]
        immo["dotation_annee"] = next(
            (p["dotation"] for p in plan if p["annee"] == annee), 0)
    return {
        "immobilisations": immos,
        "totaux": {
            "brut": sum(i["valeur_acquisition"] for i in immos),
            "amortissements": sum(i["cumul_amortissement"] for i in immos),
            "vnc": sum(i["vnc"] for i in immos),
            "dotation": sum(i["dotation_annee"] for i in immos),
        },
    }


@route("GET", "/api/immobilisations/<id>")
def api_detail(ctx):
    identifiant = int(ctx.params["id"])
    immo = db.ligne("SELECT * FROM immobilisations WHERE id = ?", (identifiant,))
    if not immo:
        raise ErreurApplicative("Immobilisation introuvable.", 404)
    immo["plan"] = plan_amortissement(immo)
    immo["comptabilises"] = db.lignes(
        "SELECT * FROM amortissements WHERE immo_id = ? ORDER BY annee", (identifiant,))
    return immo


@route("POST", "/api/immobilisations")
def api_cree(ctx):
    ctx.interdit_lecture_seule()
    societe_id = ctx.entier("societe_id")
    compte = str(ctx.champ_requis("compte")).strip()
    compta.exige_compte(societe_id, compte)
    valeur = ctx.montant("valeur_acquisition")
    if valeur <= 0:
        raise ErreurApplicative("Indiquez la valeur d'acquisition.")
    duree = ctx.entier("duree_mois") or DUREES_INDICATIVES.get(compte, 60)
    with db.transaction():
        code = util.nettoie(ctx.champ("code")) or f"IMM{db.valeur('SELECT COUNT(*) FROM immobilisations WHERE societe_id = ?', (societe_id,), 0) + 1:04d}"
        if db.ligne("SELECT id FROM immobilisations WHERE societe_id = ? AND code = ?",
                    (societe_id, code)):
            raise ErreurApplicative(f"Le code « {code} » existe déjà.")
        identifiant = db.insere("immobilisations", {
            "societe_id": societe_id, "code": code,
            "designation": ctx.champ_requis("designation"),
            "compte": compte,
            "compte_amort": util.nettoie(ctx.champ("compte_amort"))
                            or compte_amortissement(compte),
            "compte_dotation": ctx.champ("compte_dotation", "68112"),
            "date_acquisition": ctx.date("date_acquisition", util.aujourdhui()),
            "date_mise_service": ctx.date("date_mise_service")
                                 or ctx.date("date_acquisition", util.aujourdhui()),
            "valeur_acquisition": valeur,
            "valeur_residuelle": ctx.montant("valeur_residuelle"),
            "duree_mois": duree,
            "mode": ctx.champ("mode", "lineaire"),
            "coefficient": ctx.entier("coefficient", 1000) or 1000,
            "statut": "en_service",
            "programme_id": ctx.entier("programme_id"),
        })
        db.trace("creation", "immobilisation", identifiant, code, ctx.nom_utilisateur)

        # L'acquisition peut être comptabilisée directement depuis le registre,
        # lorsqu'elle n'a pas déjà été saisie via une facture d'achat.
        ecriture_id = None
        if ctx.booleen("comptabiliser"):
            ecriture_id = _comptabilise_acquisition(ctx, identifiant)
    return {"id": identifiant, "code": code, "ecriture_id": ecriture_id}


def _comptabilise_acquisition(ctx, immo_id: int) -> int:
    """Entrée de l'immobilisation à l'actif.

        2xx Immobilisation        D  valeur HT
        44562 TVA déd. immo       D  TVA récupérable
            404 Fournisseur d'immo    C  montant TTC
    """
    immo = db.ligne("SELECT * FROM immobilisations WHERE id = ?", (immo_id,))
    taux_tva = ctx.taux("taux_tva", 1900)
    tva = util.applique_taux(immo["valeur_acquisition"], taux_tva)
    tiers_id = ctx.entier("fournisseur_id")
    libelle = f"Acquisition — {immo['designation']}"

    lignes = [{"compte": immo["compte"], "debit": immo["valeur_acquisition"], "credit": 0,
               "libelle": libelle, "programme_id": immo["programme_id"]}]
    if tva:
        lignes.append({"compte": "44562", "debit": tva, "credit": 0,
                       "libelle": f"TVA déductible sur immobilisation — {immo['code']}"})
    lignes.append({"compte": "404", "debit": 0,
                   "credit": immo["valeur_acquisition"] + tva,
                   "tiers_id": tiers_id, "libelle": libelle})

    return compta.enregistre_ecriture(
        immo["societe_id"], "AC", immo["date_acquisition"], libelle, lignes,
        piece=util.nettoie(ctx.champ("piece")) or immo["code"],
        module="immobilisations", source_type="acquisition", source_id=immo_id,
        utilisateur=ctx.nom_utilisateur,
    )


@route("PUT", "/api/immobilisations/<id>")
def api_modifie(ctx):
    ctx.interdit_lecture_seule()
    with db.transaction():
        db.modifie("immobilisations", int(ctx.params["id"]), {
            "designation": ctx.champ_requis("designation"),
            "compte_amort": util.nettoie(ctx.champ("compte_amort")),
            "compte_dotation": ctx.champ("compte_dotation", "68112"),
            "date_acquisition": ctx.date("date_acquisition"),
            "date_mise_service": ctx.date("date_mise_service"),
            "valeur_acquisition": ctx.montant("valeur_acquisition"),
            "valeur_residuelle": ctx.montant("valeur_residuelle"),
            "duree_mois": ctx.entier("duree_mois", 60),
            "mode": ctx.champ("mode", "lineaire"),
            "coefficient": ctx.entier("coefficient", 1000),
            "statut": ctx.champ("statut", "en_service"),
        })
    return {"ok": True}


@route("POST", "/api/immobilisations/dotations")
def api_dotations(ctx):
    """Comptabilise la dotation aux amortissements de l'exercice."""
    ctx.interdit_lecture_seule()
    societe_id = ctx.entier("societe_id")
    ex = compta.exercice(ctx.entier("exercice_id"))
    annee = int(ex["date_fin"][:4])
    immos = db.lignes(
        "SELECT * FROM immobilisations WHERE societe_id = ? AND statut = 'en_service'",
        (societe_id,))

    par_couple: dict[tuple[str, str], int] = {}
    details = []
    for immo in immos:
        deja = db.ligne(
            "SELECT id FROM amortissements WHERE immo_id = ? AND annee = ? "
            "AND comptabilise = 1", (immo["id"], annee))
        if deja:
            continue
        plan = plan_amortissement(immo)
        ligne_annee = next((p for p in plan if p["annee"] == annee), None)
        if not ligne_annee or ligne_annee["dotation"] <= 0:
            continue
        cle = (immo["compte_dotation"], immo["compte_amort"])
        par_couple[cle] = par_couple.get(cle, 0) + ligne_annee["dotation"]
        details.append((immo, ligne_annee))

    if not par_couple:
        return {"message": "Aucune dotation à comptabiliser pour cet exercice.",
                "dotations": 0}

    lignes = []
    for (compte_dotation, compte_amort), montant in sorted(par_couple.items()):
        lignes.append({"compte": compte_dotation, "debit": montant, "credit": 0,
                       "libelle": f"Dotation aux amortissements {annee}"})
        lignes.append({"compte": compte_amort, "debit": 0, "credit": montant,
                       "libelle": f"Amortissement de l'exercice {annee}"})

    with db.transaction():
        ecriture_id = compta.enregistre_ecriture(
            societe_id, "OD", ex["date_fin"],
            f"Dotations aux amortissements — exercice {ex['libelle']}", lignes,
            module="immobilisations", source_type="dotation", source_id=ex["id"],
            utilisateur=ctx.nom_utilisateur,
        )
        for immo, ligne_annee in details:
            db.execute(
                "INSERT INTO amortissements (immo_id, exercice_id, annee, base, dotation, "
                "cumul, vnc, comptabilise, ecriture_id) VALUES (?,?,?,?,?,?,?,1,?) "
                "ON CONFLICT(immo_id, annee) DO UPDATE SET dotation = excluded.dotation, "
                "cumul = excluded.cumul, vnc = excluded.vnc, comptabilise = 1, "
                "ecriture_id = excluded.ecriture_id",
                (immo["id"], ex["id"], annee, ligne_annee["base"], ligne_annee["dotation"],
                 ligne_annee["cumul"], ligne_annee["vnc"], ecriture_id),
            )
    return {"ecriture_id": ecriture_id, "dotations": len(details),
            "montant": sum(par_couple.values())}


@route("POST", "/api/immobilisations/<id>/ceder")
def api_cede(ctx):
    """Cession : sortie de l'actif, constatation de la plus ou moins-value."""
    ctx.interdit_lecture_seule()
    identifiant = int(ctx.params["id"])
    immo = db.ligne("SELECT * FROM immobilisations WHERE id = ?", (identifiant,))
    if not immo:
        raise ErreurApplicative("Immobilisation introuvable.", 404)
    if immo["statut"] == "cede":
        raise ErreurApplicative("Cette immobilisation est déjà cédée.")
    date = ctx.date("date", util.aujourdhui())
    prix = ctx.montant("valeur_cession")
    annee = int(date[:4])
    plan = plan_amortissement(immo)
    cumul = next((p["cumul"] for p in reversed(plan) if p["annee"] < annee), 0)
    vnc = immo["valeur_acquisition"] - cumul
    plus_value = prix - vnc

    lignes = [
        {"compte": immo["compte_amort"], "debit": cumul, "credit": 0,
         "libelle": f"Sortie des amortissements — {immo['designation']}"},
        {"compte": immo["compte"], "debit": 0, "credit": immo["valeur_acquisition"],
         "libelle": f"Sortie de l'actif — {immo['designation']}"},
    ]
    if prix:
        lignes.append({"compte": "462", "debit": prix, "credit": 0,
                       "tiers_id": ctx.entier("acquereur_id"),
                       "libelle": f"Créance sur cession — {immo['designation']}"})
    if plus_value > 0:
        lignes.append({"compte": "752", "debit": 0, "credit": plus_value,
                       "libelle": "Plus-value de cession"})
    elif plus_value < 0:
        lignes.append({"compte": "652", "debit": -plus_value, "credit": 0,
                       "libelle": "Moins-value de cession"})

    with db.transaction():
        if plus_value < 0 and not compta.compte_existe(immo["societe_id"], "652"):
            db.insere("comptes", {
                "societe_id": immo["societe_id"], "numero": "652",
                "intitule": "Moins-values sur sortie d'actifs immobilisés non financiers",
                "classe": 6, "nature": "charge", "rubrique": "autres_charges_op",
                "lettrable": 0, "actif": 1,
            })
        ecriture_id = compta.enregistre_ecriture(
            immo["societe_id"], "OD", date,
            f"Cession — {immo['designation']}", lignes,
            module="immobilisations", source_type="cession", source_id=identifiant,
            utilisateur=ctx.nom_utilisateur,
        )
        db.modifie("immobilisations", identifiant, {
            "statut": "cede", "date_cession": date, "valeur_cession": prix,
        })
    return {"ecriture_id": ecriture_id, "vnc": vnc, "plus_value": plus_value}


@route("GET", "/api/export/immobilisations")
def api_export(ctx):
    societe_id = ctx.arg_int("societe")
    soc = compta.societe(societe_id)
    annee = ctx.arg_int("annee") or int(util.aujourdhui()[:4])
    donnees = api_liste(ctx)

    classeur = tableur.Classeur()
    f = classeur.feuille("Immobilisations")
    f.titre(f"{soc['raison_sociale']} — Tableau des immobilisations et amortissements")
    f.ajoute(tableur.texte(f"Exercice {annee}"))
    f.vide()
    f.entetes("Code", "Désignation", "Compte", "Acquisition", "Mise en service",
              "Valeur brute", "Durée (mois)", "Mode", "Dotation exercice",
              "Cumul amortissements", "Valeur nette", "Statut")
    f.largeurs_auto(11, 40, 10, 14, 15, 17, 13, 12, 17, 20, 17, 13)
    for i in donnees["immobilisations"]:
        f.ajoute(
            tableur.texte(i["code"]), tableur.texte(i["designation"]),
            tableur.texte(i["compte"]), tableur.date_cel(i["date_acquisition"]),
            tableur.date_cel(i["date_mise_service"]),
            tableur.monnaie(i["valeur_acquisition"]),
            tableur.nombre(i["duree_mois"]), tableur.texte(i["mode"]),
            tableur.monnaie(i["dotation_annee"]),
            tableur.monnaie(i["cumul_amortissement"]), tableur.monnaie(i["vnc"]),
            tableur.texte(i["statut"]),
        )
    t = donnees["totaux"]
    f.ajoute(tableur.texte("TOTAUX", tableur.GRAS), *[tableur.texte("")] * 4,
             tableur.monnaie(t["brut"], total=True), tableur.texte(""),
             tableur.texte(""), tableur.monnaie(t["dotation"], total=True),
             tableur.monnaie(t["amortissements"], total=True),
             tableur.monnaie(t["vnc"], total=True))
    return Reponse(classeur.octets(),
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   f"immobilisations_{soc['code']}_{annee}.xlsx")
