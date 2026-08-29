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


def normalise_primes(brutes) -> list:
    """Met des primes saisies sous leur forme unique : montants en centimes.

    Accepte ce que l'interface envoie (une liste de lignes), ce qu'un import
    Excel dépose (un seul montant, en dinars) et l'absence de prime. Un seul
    passage de conversion, à l'entrée : ensuite, un montant de prime est un
    entier de centimes, comme partout ailleurs dans l'application.
    """
    if brutes in (None, "", []):
        return []
    if isinstance(brutes, str):
        try:
            brutes = json.loads(brutes)
        except ValueError:
            brutes = util.centimes(brutes) and [{"libelle": "Primes",
                                                 "montant": brutes}] or []
    if isinstance(brutes, (int, float)):
        brutes = [{"libelle": "Primes", "montant": brutes}]
    if isinstance(brutes, dict):
        brutes = [brutes]
    propres = []
    for brute in brutes:
        if not isinstance(brute, dict):
            brute = {"libelle": "Primes", "montant": brute}
        montant = util.centimes(brute.get("montant"))
        if not montant:
            continue
        propres.append({
            "libelle": util.nettoie(brute.get("libelle")) or "Prime",
            "montant": montant,
            "soumis_cnas": bool(brute.get("soumis_cnas", True)),
            "soumis_irg": bool(brute.get("soumis_irg", True)),
        })
    return propres


#: Ce qu'une retenue peut être, et le compte où elle se solde. Un acompte
#: déjà versé s'impute au 425 — il éteint l'avance consentie ; une saisie ou
#: une opposition au 427. Ce sont des propositions : le comptable garde la
#: main sur le compte, c'est son métier.
RETENUES_USUELLES = (
    ("Avance sur salaire", "425"),
    ("Acompte", "425"),
    ("Remboursement de prêt", "425"),
    ("Absence non rémunérée", "427"),
    ("Opposition / saisie-arrêt", "427"),
    ("Retenue diverse", "427"),
)

#: Le compte d'une retenue dont on n'a rien dit.
COMPTE_RETENUE_DEFAUT = "427"


def normalise_retenues(brutes) -> list:
    """Les retenues d'un bulletin : un libellé, un montant, rien de plus.

    Elles se déduisent du net après CNAS et IRG — une avance sur salaire, un
    acompte, un remboursement de prêt ne changent ni l'assiette des
    cotisations ni celle de l'impôt : le salarié les a bien gagnés, il en a
    seulement déjà reçu une partie.
    """
    if brutes in (None, "", []):
        return []
    if isinstance(brutes, (int, float, str)):
        # Un montant seul, sans libellé : c'est ce que l'ancienne colonne
        # « autres retenues » portait. On le garde, en le nommant.
        montant = util.centimes(brutes)
        return ([{"libelle": "Retenues diverses", "montant": montant,
                  "compte": COMPTE_RETENUE_DEFAUT}] if montant else [])
    if isinstance(brutes, dict):
        brutes = [brutes]
    propres = []
    for brute in brutes:
        if not isinstance(brute, dict):
            brute = {"montant": brute}
        montant = util.centimes(brute.get("montant"))
        if not montant:
            continue
        libelle = util.nettoie(brute.get("libelle")) or "Retenue"
        propres.append({
            "libelle": libelle, "montant": montant,
            "compte": (util.nettoie(brute.get("compte"))
                       or compte_retenue_propose(libelle)),
        })
    return propres


def compte_retenue_propose(libelle: str) -> str:
    """Le compte qui va d'habitude avec ce libellé — à titre de proposition."""
    propre = util.sans_accents(str(libelle or "")).lower()
    for nom, compte in RETENUES_USUELLES:
        if util.sans_accents(nom).lower() in propre:
            return compte
    return COMPTE_RETENUE_DEFAUT


def primes_du_salarie(salarie) -> list:
    """Les primes de la fiche, déjà en centimes — relues sans rien convertir.

    Tolère ce qu'un import a pu y déposer avant que la colonne ne soit
    normalisée : un nombre seul plutôt qu'une liste.
    """
    brut = salarie["primes"] if salarie else None
    if not brut:
        return []
    try:
        valeur = json.loads(brut) if isinstance(brut, str) else brut
    except ValueError:
        return []
    if isinstance(valeur, (int, float)):
        valeur = [{"libelle": "Primes", "montant": int(valeur)}]
    if isinstance(valeur, dict):
        valeur = [valeur]
    propres = []
    for prime in valeur or []:
        if not isinstance(prime, dict):
            continue
        montant = int(prime.get("montant") or 0)
        if not montant:
            continue
        propres.append({
            "libelle": prime.get("libelle") or "Prime", "montant": montant,
            "soumis_cnas": bool(prime.get("soumis_cnas", True)),
            "soumis_irg": bool(prime.get("soumis_irg", True)),
        })
    return propres


def calcule_bulletin(societe_id: int, salarie: dict, periode: str,
                     saisie: dict | None = None) -> dict:
    """Calcule un bulletin sans l'enregistrer."""
    saisie = saisie or {}
    annee = int(periode[:4])

    jours = int(round(float(saisie.get("jours_travailles", 30)) * 1000))
    salaire_base = util.centimes(saisie.get("salaire_base")) or salarie["salaire_base"]
    if jours != 30000:
        salaire_base = util.part_proportionnelle(salaire_base, jours, 30000)

    # Deux provenances, deux conventions, et c'est là que ça se jouait : ce
    # qui vient d'une saisie est en dinars tels que tapés, ce qui vient de la
    # fiche du salarié est déjà en centimes. Les confondre multipliait toutes
    # les primes par cent — dans le bulletin, la base CNAS et l'IRG.
    if saisie.get("primes") is not None:
        primes_saisies = normalise_primes(saisie.get("primes"))
    else:
        primes_saisies = primes_du_salarie(salarie)

    primes_soumises = primes_non_soumises = 0
    detail_primes = []
    for prime in primes_saisies:
        montant = int(prime.get("montant") or 0)
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

    # Les retenues sont détaillées, ligne à ligne : un bulletin qui annonce
    # « autres retenues : 5 000 » sans dire lesquelles ne se remet pas à un
    # salarié. Le total reste dans sa colonne, pour les états et l'écriture.
    if saisie.get("retenues") is not None:
        retenues = normalise_retenues(saisie.get("retenues"))
    else:
        retenues = normalise_retenues(saisie.get("autres_retenues", 0))
    autres_retenues = sum(r["montant"] for r in retenues)
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
        "irg": irg, "retenues": retenues, "autres_retenues": autres_retenues,
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
        s["primes"] = primes_du_salarie(s)
    return {"salaries": salaries}


@route("POST", "/api/salaries")
def api_cree_salarie(ctx):
    ctx.interdit_lecture_seule()
    societe_id = ctx.entier("societe_id")
    with db.transaction():
        matricule = util.nettoie(ctx.champ("matricule"))
        if matricule:
            if db.ligne("SELECT id FROM salaries WHERE societe_id = ? AND "
                        "matricule = ?", (societe_id, matricule)):
                raise ErreurApplicative(
                    f"Le matricule « {matricule} » existe déjà.")
        else:
            # Le compteur ignore les salariés arrivés par un import ou par une
            # reprise : il proposait alors un matricule déjà pris, et le
            # bouton « Enregistrer » restait sans effet. On avance jusqu'au
            # premier libre plutôt que de renvoyer l'utilisateur à sa saisie.
            for _ in range(1000):
                matricule = db.numero_suivant(societe_id, "tiers_salarie")
                if not db.ligne("SELECT id FROM salaries WHERE societe_id = ? "
                                "AND matricule = ?", (societe_id, matricule)):
                    break
            else:
                raise ErreurApplicative(
                    "Impossible d'attribuer un matricule libre. Saisissez-le "
                    "vous-même.")
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
            "primes": json.dumps(normalise_primes(ctx.champ("primes")),
                                 ensure_ascii=False),
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
            "primes": json.dumps(normalise_primes(ctx.champ("primes")),
                                 ensure_ascii=False),
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


@route("GET", "/api/bulletins/<id>")
def api_bulletin(ctx):
    """Un bulletin et son détail de calcul — primes et retenues comprises."""
    bulletin = db.ligne(
        "SELECT b.*, s.nom, s.prenom, s.matricule, s.poste "
        "FROM bulletins b JOIN salaries s ON s.id = b.salarie_id WHERE b.id = ?",
        (int(ctx.params["id"]),))
    if not bulletin:
        raise ErreurApplicative("Bulletin introuvable.", 404)
    try:
        bulletin["detail"] = json.loads(bulletin["detail"] or "{}")
    except ValueError:
        bulletin["detail"] = {}
    return bulletin


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


def retenues_par_compte(bulletins: list) -> dict:
    """Les retenues du mois, regroupées par compte d'imputation.

    Une avance déjà versée s'éteint au 425, une opposition se solde au 427 :
    les additionner toutes sur un seul compte obligerait à reprendre
    l'écriture à la main tous les mois.
    """
    par_compte: dict = {}
    for bulletin in bulletins:
        try:
            detail = json.loads(bulletin["detail"] or "{}")
        except ValueError:
            detail = {}
        lignes = detail.get("retenues") or []
        if not lignes and bulletin["autres_retenues"]:
            lignes = [{"compte": COMPTE_RETENUE_DEFAUT,
                       "montant": bulletin["autres_retenues"]}]
        for ligne in lignes:
            compte = str(ligne.get("compte") or COMPTE_RETENUE_DEFAUT)
            par_compte[compte] = par_compte.get(compte, 0) + int(ligne.get("montant") or 0)
    return {c: m for c, m in par_compte.items() if m}


@route("POST", "/api/bulletins/comptabiliser")
def api_comptabilise_paie(ctx):
    """Écriture de paie du mois, tous salariés confondus.

        631 Rémunérations du personnel   D  brut total
        635 Cotisations sociales         D  part patronale
            421 Personnel — rému. dues       C  net à payer
            431 Sécurité sociale (CNAS)      C  part salariale + patronale
            4421 IRG / Salaires              C  retenue IRG
            425 / 427 Retenues               C  selon le compte de chaque retenue
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
    for compte, montant in sorted(retenues_par_compte(bulletins).items()):
        lignes.append({"compte": compte, "debit": 0, "credit": montant,
                       "libelle": f"Retenues sur salaires — "
                                  f"{util.libelle_periode(periode)}"})

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


@route("POST", "/api/bulletins/reprendre")
def api_reprend_paie(ctx):
    """Rouvrir les bulletins d'un mois déjà comptabilisé.

    Une retenue oubliée, un salarié parti en cours de mois, un jour
    d'absence qui remonte après coup : la paie du mois se refait. Jusqu'ici
    un bulletin comptabilisé était définitif et rien ne permettait d'y
    revenir — l'écriture de paie n'avait pas de marche arrière.

    Les écritures ne sont pas effacées : elles sont **extournées**, donc
    toujours lisibles au journal. Les bulletins repassent en brouillon, se
    corrigent, et se recomptabilisent.
    """
    ctx.interdit_lecture_seule()
    ctx.exige_role("admin", "comptable")
    societe_id = ctx.entier("societe_id")
    periode = ctx.champ_requis("periode")
    if ctx.champ("confirmation") != "REPRENDRE":
        raise ErreurApplicative(
            f"Reprendre la paie de {util.libelle_periode(periode)} extourne "
            "ses écritures et repasse les bulletins en brouillon. Saisissez "
            "REPRENDRE pour confirmer.")
    bulletins = db.lignes(
        "SELECT * FROM bulletins WHERE societe_id = ? AND periode = ? "
        "AND statut <> 'brouillon'", (societe_id, periode))
    if not bulletins:
        raise ErreurApplicative(
            f"Aucun bulletin comptabilisé pour {util.libelle_periode(periode)}.")

    date = ctx.date("date", util.aujourdhui())
    extournees = []
    with db.transaction():
        # L'écriture de paie, et celle du règlement s'il a eu lieu.
        a_extourner = {b["ecriture_id"] for b in bulletins if b["ecriture_id"]}
        for reglement in db.lignes(
                "SELECT id FROM ecritures WHERE societe_id = ? AND "
                "source_type = 'paiement_salaires' AND libelle LIKE ? "
                "AND id NOT IN (SELECT COALESCE(source_id, -1) FROM ecritures "
                "               WHERE source_type = 'extourne')",
                (societe_id, f"%{util.libelle_periode(periode)}%")):
            a_extourner.add(reglement["id"])
        for identifiant in sorted(a_extourner):
            nouvelle = compta.extourne_ecriture(identifiant, date,
                                                ctx.nom_utilisateur)
            extournees.append(db.valeur(
                "SELECT numero FROM ecritures WHERE id = ?", (nouvelle,),
                str(nouvelle)))
        db.execute(
            "UPDATE bulletins SET statut = 'brouillon', ecriture_id = NULL "
            "WHERE societe_id = ? AND periode = ?", (societe_id, periode))
        db.trace("reprise", "paie", None,
                 {"periode": periode, "bulletins": len(bulletins),
                  "extournees": extournees}, ctx.nom_utilisateur)
    return {
        "bulletins": len(bulletins), "extournees": extournees,
        "message": f"{len(bulletins)} bulletin(s) repassés en brouillon. "
                   + (f"Écriture(s) extournée(s) : {', '.join(extournees)}. "
                      if extournees else "")
                   + "Corrigez-les, puis recomptabilisez la paie.",
    }


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
