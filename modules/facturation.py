"""Facturation et règlements.

Une facture validée génère automatiquement son écriture comptable, dans le
journal des ventes ou des achats, avec ventilation de la TVA et du droit de
timbre. Les axes analytiques (programme / lot / bien) sont reportés sur les
lignes afin d'alimenter le coût de revient des programmes immobiliers.
"""

from __future__ import annotations

from noyau import base as db
from noyau import tableur
from noyau import util
from noyau.serveur import ErreurApplicative, route, Reponse
from modules import comptabilite as compta
from modules.tiers import compte_du_tiers, tiers_ou_erreur

SENS_VALIDES = {"vente", "achat", "avoir_vente", "avoir_achat", "proforma"}

LIBELLES_SENS = {
    "vente": "Factures de vente", "achat": "Factures d'achat",
    "avoir_vente": "Avoirs clients", "avoir_achat": "Avoirs fournisseurs",
    "proforma": "Factures proforma",
}

COMPTE_TVA_COLLECTEE = "4457"
COMPTE_TVA_DEDUCTIBLE = "44566"
COMPTE_TVA_DEDUCTIBLE_IMMO = "44562"
COMPTE_TIMBRE = "4472"


def facture_ou_erreur(facture_id: int) -> dict:
    f = db.ligne("SELECT * FROM factures WHERE id = ?", (facture_id,))
    if not f:
        raise ErreurApplicative("Facture introuvable.", 404)
    return f


def calcule_lignes(lignes_saisies: list[dict]) -> tuple[list[dict], int, int]:
    """Normalise les lignes et calcule HT/TVA par ligne."""
    preparees = []
    total_ht = total_tva = 0
    for index, l in enumerate(lignes_saisies):
        designation = (l.get("designation") or "").strip()
        if not designation:
            continue
        quantite = int(round(float(l.get("quantite") or 1) * 1000))
        prix_unitaire = util.centimes(l.get("prix_unitaire"))
        remise = util.vers_taux(l.get("remise_taux") or 0)
        taux_tva = util.vers_taux(l.get("taux_tva") if l.get("taux_tva") is not None else 19)

        brut = util.part_proportionnelle(prix_unitaire, quantite, 1000)
        montant_ht = brut - util.applique_taux(brut, remise)
        montant_tva = util.applique_taux(montant_ht, taux_tva)

        preparees.append({
            "ordre": index,
            "designation": designation[:250],
            "quantite": quantite,
            "unite": l.get("unite"),
            "prix_unitaire": prix_unitaire,
            "remise_taux": remise,
            "taux_tva": taux_tva,
            "montant_ht": montant_ht,
            "montant_tva": montant_tva,
            "compte": (l.get("compte") or "").strip() or None,
        })
        total_ht += montant_ht
        total_tva += montant_tva
    if not preparees:
        raise ErreurApplicative("La facture doit comporter au moins une ligne.")
    return preparees, total_ht, total_tva


def base_timbre(mode_reglement: str | None, montant_ttc: int,
                montant_espece: int = 0) -> int:
    """Ce sur quoi porte le droit de timbre : la part réglée en espèces.

    Le client apporte souvent un chèque **et** des espèces pour une même
    vente. Le timbre ne se calcule alors ni sur rien, ni sur tout : sur la
    part en espèces, et sur elle seule.
    """
    if mode_reglement == "espece":
        return max(0, montant_ttc)
    if mode_reglement == "mixte":
        return max(0, min(int(montant_espece or 0), max(0, montant_ttc)))
    return 0


def calcule_timbre(societe_id: int, mode_reglement: str | None, montant_ttc: int,
                   annee: int, montant_espece: int = 0) -> int:
    """Droit de timbre applicable aux règlements en espèces."""
    base = base_timbre(mode_reglement, montant_ttc, montant_espece)
    if base <= 0:
        return 0
    taux = db.parametre_fiscal_int(annee, "timbre_taux", 100)
    minimum = db.parametre_fiscal_int(annee, "timbre_minimum", 500)
    seuil = db.parametre_fiscal_int(annee, "timbre_seuil_espece", 0)
    if base < seuil:
        return 0
    return max(util.applique_taux(base, taux), minimum)


def _filtres_factures(ctx) -> tuple[str, list]:
    """Conditions de sélection communes à la liste et à l'export."""
    conditions = ["f.societe_id = ?"]
    params: list = [ctx.arg_int("societe")]
    for argument, colonne in (("sens", "f.sens"), ("statut", "f.statut")):
        if ctx.arg(argument):
            conditions.append(f"{colonne} = ?")
            params.append(ctx.arg(argument))
    for argument, colonne in (("tiers", "f.tiers_id"), ("programme", "f.programme_id")):
        if ctx.arg(argument):
            conditions.append(f"{colonne} = ?")
            params.append(ctx.arg_int(argument))
    for argument, comparaison in (("du", ">="), ("au", "<=")):
        if ctx.arg(argument):
            conditions.append(f"f.date {comparaison} ?")
            params.append(ctx.arg(argument))
    if ctx.arg("q"):
        conditions.append("(f.numero LIKE ? OR f.objet LIKE ? OR t.raison_sociale LIKE ?)")
        motif = "%" + ctx.arg("q") + "%"
        params += [motif, motif, motif]
    fragment, params_perimetre = compta.clause_perimetre(ctx.perimetre(), "f")
    if fragment:
        conditions.append(fragment.replace(" AND ", "", 1))
        params += params_perimetre
    return " AND ".join(conditions), params


@route("GET", "/api/factures")
def api_liste(ctx):
    filtre, params = _filtres_factures(ctx)
    limite = min(ctx.arg_int("limite", 200) or 200, 2000)
    factures = db.lignes(
        "SELECT f.*, t.raison_sociale AS tiers_nom, t.code AS tiers_code "
        "FROM factures f LEFT JOIN tiers t ON t.id = f.tiers_id "
        f"WHERE {filtre} ORDER BY f.date DESC, f.id DESC LIMIT ?",
        params + [limite],
    )
    totaux = db.ligne(
        "SELECT COALESCE(SUM(f.montant_ht),0) AS ht, COALESCE(SUM(f.montant_tva),0) AS tva, "
        "  COALESCE(SUM(f.net_a_payer),0) AS ttc, "
        "  COALESCE(SUM(f.net_a_payer - f.montant_regle),0) AS reste "
        "FROM factures f LEFT JOIN tiers t ON t.id = f.tiers_id "
        f"WHERE {filtre} AND f.statut <> 'annulee'",
        params,
    )
    return {"factures": factures, "totaux": totaux}


@route("GET", "/api/factures/<id>")
def api_detail(ctx):
    identifiant = int(ctx.params["id"])
    f = facture_ou_erreur(identifiant)
    f["lignes"] = db.lignes(
        "SELECT * FROM facture_lignes WHERE facture_id = ? ORDER BY ordre", (identifiant,)
    )
    if f["tiers_id"]:
        f["tiers"] = db.ligne("SELECT * FROM tiers WHERE id = ?", (f["tiers_id"],))
    f["societe"] = db.ligne("SELECT * FROM societes WHERE id = ?", (f["societe_id"],))
    f["reglements"] = db.lignes(
        "SELECT r.*, ct.libelle AS compte_tresorerie FROM reglements r "
        "LEFT JOIN comptes_tresorerie ct ON ct.id = r.tresorerie_id "
        "WHERE r.facture_id = ? ORDER BY r.date", (identifiant,)
    )
    if f["ecriture_id"]:
        f["ecriture"] = db.ligne(
            "SELECT e.*, j.code AS journal FROM ecritures e "
            "JOIN journaux j ON j.id = e.journal_id WHERE e.id = ?", (f["ecriture_id"],)
        )
    if f.get("ecriture_hors_id"):
        f["ecriture_hors"] = db.ligne(
            "SELECT e.*, j.code AS journal FROM ecritures e "
            "JOIN journaux j ON j.id = e.journal_id WHERE e.id = ?",
            (f["ecriture_hors_id"],)
        )
    if f.get("tresorerie_hors_id"):
        f["tresorerie_hors"] = db.valeur(
            "SELECT libelle FROM comptes_tresorerie WHERE id = ?",
            (f["tresorerie_hors_id"],))
    # Le prix réellement convenu, celui qui doit tomber juste : ni la facture
    # seule, ni la part réglée à côté seule.
    hors = f.get("montant_hors") or 0
    hors_regle = f.get("montant_hors_regle") or 0
    f["prix_reel"] = f["net_a_payer"] + hors
    f["reste_declare"] = f["net_a_payer"] - f["montant_regle"]
    f["reste_hors"] = hors - hors_regle
    f["total_regle"] = f["montant_regle"] + hors_regle
    f["reste_total"] = f["prix_reel"] - f["total_regle"]
    return f


CLES_COMPTEUR = {"vente": "facture_vente", "achat": "facture_achat",
                 "avoir_vente": "avoir_vente", "avoir_achat": "avoir_achat",
                 "proforma": "proforma"}


def perimetre_facture(valeur, defaut: str) -> str:
    """« Déclaré + non déclaré » est une facture déclarée, plus une part à côté.

    L'écran propose trois choix là où la base n'en connaît que deux : la
    troisième valeur décrit la vente, pas le périmètre de la facture.
    """
    if str(valeur or "").strip().lower() in ("totalite", "totalité", "les_deux"):
        return "declare"
    return compta.normalise_perimetre(valeur, defaut)


def _controle_part_hors(societe_id: int, sens: str, montant, compte,
                        tresorerie_id, perimetre: str,
                        lignes_pretes: list[dict]) -> tuple:
    """Vérifie la part non déclarée d'une vente, et complète ce qui manque.

    Une vente réelle est souvent double : une part facturée, déclarée, et une
    part réglée à côté. Les deux se saisissent ensemble — c'est le prix
    convenu qui doit tomber juste, pas l'une des deux moitiés.

    Deux choses seulement sont exigées, et chacune parce que l'écriture ne
    peut pas s'écrire sans : un montant et un compte. Le reste est déduit,
    et la trésorerie est facultative — elle dit « déjà encaissée », pas
    « obligatoire ».
    """
    montant = max(0, int(montant or 0))
    if not montant:
        return 0, None, None
    if sens == "proforma":
        raise ErreurApplicative(
            "Une proforma n'est qu'une offre de prix : elle ne porte pas de "
            "part non déclarée. Portez-la sur la facture définitive.")
    if perimetre != "declare":
        raise ErreurApplicative(
            "Une facture déjà « hors déclaration » est entièrement hors "
            "déclaration : elle ne porte pas en plus une part non déclarée. "
            "Choisissez le périmètre « Déclaré + non déclaré ».")

    compte = util.nettoie(compte) or _compte_hors_defaut(sens, lignes_pretes)
    if not compte:
        raise ErreurApplicative(
            "Indiquez le compte de la part non déclarée "
            f"({'produit' if sens.endswith('vente') or sens == 'vente' else 'charge'}).")
    if not compta.compte_existe(societe_id, compte):
        raise ErreurApplicative(
            f"Le compte {compte} n'est pas au plan comptable. Créez-le dans "
            "Paramètres → Plan comptable, puis revenez.")

    # La trésorerie n'est plus exigée : une part non déclarée naît due, comme
    # toute créance. Renseignée, elle veut dire « encaissée tout de suite »,
    # et le règlement suit la validation. Vide, la somme reste à recevoir et
    # se voit dans le reste dû du client.
    tresorerie_id = int(tresorerie_id or 0) or None
    if tresorerie_id and not db.ligne(
            "SELECT id FROM comptes_tresorerie WHERE id = ? AND societe_id = ?",
            (tresorerie_id, societe_id)):
        raise ErreurApplicative("Compte de trésorerie introuvable.")
    return montant, compte, tresorerie_id


def _compte_hors_defaut(sens: str, lignes_pretes: list[dict]) -> str | None:
    """Le compte de la part non déclarée suit celui de la part déclarée.

    Une vente de logement reste une vente de logement, déclarée ou non : le
    compte proposé est celui de la première ligne de la facture.
    """
    for l in lignes_pretes:
        if l.get("compte"):
            return l["compte"]
    return "706" if "vente" in sens else "607"


def cree_facture(societe_id: int, sens: str, date: str, lignes: list[dict], *,
                 tiers_id: int | None = None, numero: str | None = None,
                 date_echeance: str | None = None, objet: str | None = None,
                 reference: str | None = None, origine: str | None = None,
                 programme_id=None, lot_id=None, bien_id=None, bail_id=None,
                 contrat_vsp_id=None, mode_reglement: str | None = None,
                 montant_espece: int = 0,
                 montant_hors: int = 0, compte_hors: str | None = None,
                 tresorerie_hors_id=None,
                 perimetre: str | None = None, notes: str | None = None,
                 conditions: str | None = None, utilisateur: str | None = None,
                 valider: bool = False) -> dict:
    """Crée une facture. Chemin unique, partagé par la saisie et l'import.

    À appeler dans une transaction.
    """
    if sens not in SENS_VALIDES:
        raise ErreurApplicative("Type de facture invalide.")
    ex = compta.exercice_pour_date(societe_id, date)
    compta.exige_exercice_ouvert(ex)
    if not tiers_id and sens != "proforma":
        raise ErreurApplicative("Sélectionnez le tiers de la facture.")

    lignes_pretes, total_ht, total_tva = calcule_lignes(lignes)
    ttc = total_ht + total_tva
    montant_espece = max(0, int(montant_espece or 0))
    timbre = calcule_timbre(societe_id, mode_reglement, ttc, int(date[:4]),
                            montant_espece)
    perimetre = perimetre_facture(
        perimetre,
        db.valeur("SELECT perimetre_defaut FROM societes WHERE id = ?",
                  (societe_id,), "declare"))
    montant_hors, compte_hors, tresorerie_hors_id = _controle_part_hors(
        societe_id, sens, montant_hors, compte_hors, tresorerie_hors_id,
        perimetre, lignes_pretes)

    numero = util.nettoie(numero)
    if sens == "achat" and not numero:
        raise ErreurApplicative(
            "Saisissez le numéro de la facture du fournisseur (numéro d'origine)."
        )
    if not numero:
        numero = db.numero_suivant(societe_id, CLES_COMPTEUR[sens], int(date[:4]))
    if db.ligne("SELECT id FROM factures WHERE societe_id = ? AND sens = ? AND numero = ?",
                (societe_id, sens, numero)):
        raise ErreurApplicative(f"La facture n° {numero} existe déjà.")

    facture_id = db.insere("factures", {
        "societe_id": societe_id, "exercice_id": ex["id"], "sens": sens,
        "numero": numero, "date": date,
        "date_echeance": date_echeance,
        "tiers_id": tiers_id,
        "objet": util.nettoie(objet),
        "reference": util.nettoie(reference),
        "origine": util.nettoie(origine),
        "programme_id": programme_id,
        "lot_id": lot_id,
        "bien_id": bien_id,
        "bail_id": bail_id,
        "contrat_vsp_id": contrat_vsp_id,
        "montant_ht": total_ht, "montant_tva": total_tva, "montant_ttc": ttc,
        "timbre": timbre, "net_a_payer": ttc + timbre, "montant_regle": 0,
        "mode_reglement": mode_reglement,
        "montant_espece": montant_espece,
        "montant_hors": montant_hors, "compte_hors": compte_hors,
        "tresorerie_hors_id": tresorerie_hors_id,
        "statut": "brouillon",
        "perimetre": perimetre,
        "notes": util.nettoie(notes),
        "conditions": util.nettoie(conditions),
        "cree_le": util.maintenant(), "cree_par": utilisateur,
    })
    for l in lignes_pretes:
        l["facture_id"] = facture_id
        db.insere("facture_lignes", l)
    db.trace("creation", "facture", facture_id, numero, utilisateur)

    if valider:
        _valide(facture_id, utilisateur)
    return {"id": facture_id, "numero": numero}


@route("POST", "/api/factures")
def api_cree(ctx):
    ctx.interdit_lecture_seule()
    with db.transaction():
        return cree_facture(
            ctx.entier("societe_id"),
            ctx.champ("sens", "vente"),
            ctx.date("date", util.aujourdhui()),
            ctx.champ("lignes") or [],
            tiers_id=ctx.entier("tiers_id"),
            numero=ctx.champ("numero"),
            date_echeance=ctx.date("date_echeance"),
            objet=ctx.champ("objet"),
            reference=ctx.champ("reference"),
            origine=ctx.champ("origine"),
            programme_id=ctx.entier("programme_id"),
            lot_id=ctx.entier("lot_id"),
            bien_id=ctx.entier("bien_id"),
            bail_id=ctx.entier("bail_id"),
            contrat_vsp_id=ctx.entier("contrat_vsp_id"),
            mode_reglement=ctx.champ("mode_reglement"),
            montant_espece=ctx.montant("montant_espece"),
            montant_hors=ctx.montant("montant_hors"),
            compte_hors=ctx.champ("compte_hors"),
            tresorerie_hors_id=ctx.entier("tresorerie_hors_id"),
            perimetre=ctx.champ("perimetre"),
            notes=ctx.champ("notes"),
            conditions=ctx.champ("conditions"),
            utilisateur=ctx.nom_utilisateur,
            valider=bool(ctx.booleen("valider")),
        )


@route("PUT", "/api/factures/<id>")
def api_modifie(ctx):
    ctx.interdit_lecture_seule()
    identifiant = int(ctx.params["id"])
    f = facture_ou_erreur(identifiant)
    if f["statut"] not in ("brouillon",):
        raise ErreurApplicative(
            "Seule une facture en brouillon est modifiable. Pour une facture validée, "
            "établissez un avoir."
        )
    lignes_pretes, total_ht, total_tva = calcule_lignes(ctx.champ("lignes") or [])
    date = ctx.date("date", f["date"])
    mode = ctx.champ("mode_reglement")
    ttc = total_ht + total_tva
    espece = max(0, ctx.montant("montant_espece"))
    timbre = calcule_timbre(f["societe_id"], mode, ttc, int(date[:4]), espece)
    perimetre = perimetre_facture(ctx.champ("perimetre"), f["perimetre"])
    montant_hors, compte_hors, tresorerie_hors_id = _controle_part_hors(
        f["societe_id"], f["sens"], ctx.montant("montant_hors"),
        ctx.champ("compte_hors"), ctx.entier("tresorerie_hors_id"),
        perimetre, lignes_pretes)

    with db.transaction():
        db.execute("DELETE FROM facture_lignes WHERE facture_id = ?", (identifiant,))
        for l in lignes_pretes:
            l["facture_id"] = identifiant
            db.insere("facture_lignes", l)
        db.modifie("factures", identifiant, {
            "date": date,
            "date_echeance": ctx.date("date_echeance"),
            "tiers_id": ctx.entier("tiers_id"),
            "objet": util.nettoie(ctx.champ("objet")),
            "reference": util.nettoie(ctx.champ("reference")),
            "origine": util.nettoie(ctx.champ("origine")),
            "programme_id": ctx.entier("programme_id"),
            "lot_id": ctx.entier("lot_id"),
            "bien_id": ctx.entier("bien_id"),
            "montant_ht": total_ht, "montant_tva": total_tva, "montant_ttc": ttc,
            "timbre": timbre, "net_a_payer": ttc + timbre,
            "mode_reglement": mode,
            "montant_espece": espece,
            "montant_hors": montant_hors, "compte_hors": compte_hors,
            "tresorerie_hors_id": tresorerie_hors_id,
            "perimetre": perimetre,
            "notes": util.nettoie(ctx.champ("notes")),
            "conditions": util.nettoie(ctx.champ("conditions")),
        })
        db.trace("modification", "facture", identifiant, None, ctx.nom_utilisateur)
        if ctx.booleen("valider"):
            _valide(identifiant, ctx.nom_utilisateur)
    return {"ok": True}


@route("POST", "/api/factures/<id>/valider")
def api_valide(ctx):
    ctx.interdit_lecture_seule()
    with db.transaction():
        ecriture_id = _valide(int(ctx.params["id"]), ctx.nom_utilisateur)
    return {"ok": True, "ecriture_id": ecriture_id}


def _valide(facture_id: int, utilisateur: str | None) -> int | None:
    """Comptabilise la facture. À appeler dans une transaction."""
    f = facture_ou_erreur(facture_id)
    if f["statut"] != "brouillon":
        raise ErreurApplicative("Cette facture est déjà validée.")
    if f["sens"] == "proforma":
        db.modifie("factures", facture_id, {"statut": "validee"})
        return None

    lignes_facture = db.lignes(
        "SELECT * FROM facture_lignes WHERE facture_id = ? ORDER BY ordre", (facture_id,)
    )
    if not lignes_facture:
        raise ErreurApplicative("Facture sans ligne : validation impossible.")

    tiers = db.ligne("SELECT * FROM tiers WHERE id = ?", (f["tiers_id"],))
    if not tiers:
        raise ErreurApplicative("La facture doit être rattachée à un tiers.")

    est_vente = f["sens"] in ("vente", "avoir_vente")
    est_avoir = f["sens"].startswith("avoir")
    journal = "VE" if est_vente else "AC"
    compte_tiers = compte_du_tiers(tiers)

    lignes_ecriture: list[dict] = []
    libelle = f"{'Facture' if not est_avoir else 'Avoir'} n° {f['numero']} — " \
              f"{tiers['raison_sociale']}"

    def ajoute(compte, debit=0, credit=0, **extra):
        if est_avoir:
            debit, credit = credit, debit
        if debit or credit:
            lignes_ecriture.append({
                "compte": compte, "debit": debit, "credit": credit,
                "tiers_id": extra.pop("tiers_id", None),
                "libelle": extra.pop("libelle", libelle),
                "programme_id": f["programme_id"], "lot_id": f["lot_id"],
                "bien_id": f["bien_id"], "echeance": extra.pop("echeance", None),
                **extra,
            })

    if est_vente:
        ajoute(compte_tiers, debit=f["net_a_payer"], tiers_id=tiers["id"],
               echeance=f["date_echeance"])
        for l in lignes_facture:
            compte_produit = l["compte"] or "706"
            ajoute(compte_produit, credit=l["montant_ht"],
                   libelle=l["designation"][:200])
        if f["montant_tva"]:
            ajoute(COMPTE_TVA_COLLECTEE, credit=f["montant_tva"],
                   libelle=f"TVA collectée — {f['numero']}")
        if f["timbre"]:
            ajoute(COMPTE_TIMBRE, credit=f["timbre"],
                   libelle=f"Droit de timbre — {f['numero']}")
    else:
        for l in lignes_facture:
            compte_charge = l["compte"] or "607"
            ajoute(compte_charge, debit=l["montant_ht"], libelle=l["designation"][:200],
                   poste_budget=None)
        if f["montant_tva"]:
            compte_tva = (COMPTE_TVA_DEDUCTIBLE_IMMO
                          if any((l["compte"] or "").startswith("2") for l in lignes_facture)
                          else COMPTE_TVA_DEDUCTIBLE)
            ajoute(compte_tva, debit=f["montant_tva"],
                   libelle=f"TVA déductible — {f['numero']}")
        if f["timbre"]:
            ajoute("6452", debit=f["timbre"], libelle=f"Droit de timbre — {f['numero']}")
        compte_fournisseur = "404" if any(
            (l["compte"] or "").startswith("2") for l in lignes_facture
        ) else compte_tiers
        ajoute(compte_fournisseur, credit=f["net_a_payer"], tiers_id=tiers["id"],
               echeance=f["date_echeance"])

    operation = f.get("operation_ref") or (
        f"OP-{util.maintenant().replace('-', '').replace(':', '').replace(' ', '-')}"
        if f.get("montant_hors") else None)

    ecriture_id = compta.enregistre_ecriture(
        f["societe_id"], journal, f["date"], libelle, lignes_ecriture,
        piece=f["numero"], reference=f["reference"], module="facturation",
        source_type="facture", source_id=facture_id, utilisateur=utilisateur,
        perimetre=f.get("perimetre"), operation_ref=operation,
    )
    maj = {"statut": "validee", "ecriture_id": ecriture_id}
    if operation:
        maj["operation_ref"] = operation
        maj["ecriture_hors_id"] = _ecriture_part_hors(f, operation, utilisateur)
    db.modifie("factures", facture_id, maj)

    # « Encaissée tout de suite » : le règlement suit la facture dans la
    # foulée, plutôt que de laisser une créance qu'il faudrait solder à la
    # main le jour même.
    if f.get("montant_hors") and f.get("tresorerie_hors_id"):
        cree_reglement(
            f["societe_id"],
            sens="encaissement" if f["sens"] in ("vente", "avoir_vente")
                 else "decaissement",
            date=f["date"], montant=f["montant_hors"],
            tresorerie_id=f["tresorerie_hors_id"], facture_id=facture_id,
            tiers_id=f["tiers_id"], mode="espece",
            libelle=f"Facture n° {f['numero']} — part non déclarée",
            part="hors_declaration", operation_ref=operation,
            utilisateur=utilisateur)

    db.trace("validation", "facture", facture_id, f["numero"], utilisateur)
    return ecriture_id


def _ecriture_part_hors(f: dict, operation: str, utilisateur: str | None) -> int:
    """L'écriture de la part non déclarée : une créance sur le client.

    Elle allait droit à la caisse, et se trouvait donc réputée encaissée le
    jour même. « Si je fais le non déclaré, je ne peux pas désigner combien le
    client a payé ou pas encore » : c'était exact, et c'était un défaut de
    conception, pas un manque d'écran. Une part non déclarée est une créance
    comme une autre — elle naît due, et se solde quand elle est payée.

    Elle s'équilibre seule, comme la part déclarée s'équilibre seule, et porte
    la même référence d'opération : le journal les montre côte à côte. Pas de
    TVA, pas de droit de timbre : cette part ne passe par aucun mécanisme
    déclaratif.
    """
    tiers = db.ligne("SELECT * FROM tiers WHERE id = ?", (f["tiers_id"],))
    if not tiers:
        raise ErreurApplicative("La facture doit être rattachée à un tiers.")
    montant = f["montant_hors"]
    est_vente = f["sens"] in ("vente", "avoir_vente")
    est_avoir = f["sens"].startswith("avoir")
    libelle = (f"{'Facture' if not est_avoir else 'Avoir'} n° {f['numero']} — "
               "part non déclarée")

    axes = {"programme_id": f["programme_id"], "lot_id": f["lot_id"],
            "bien_id": f["bien_id"]}
    cote_tiers = {"compte": compte_du_tiers(tiers), "tiers_id": tiers["id"],
                  "libelle": libelle, "echeance": f["date_echeance"], **axes}
    contrepartie = {"compte": f["compte_hors"], "libelle": libelle, **axes}
    if est_vente:
        lignes = [{**cote_tiers, "debit": montant, "credit": 0},
                  {**contrepartie, "debit": 0, "credit": montant}]
    else:
        lignes = [{**contrepartie, "debit": montant, "credit": 0},
                  {**cote_tiers, "debit": 0, "credit": montant}]
    if est_avoir:
        for l in lignes:
            l["debit"], l["credit"] = l["credit"], l["debit"]

    return compta.enregistre_ecriture(
        f["societe_id"], "VE" if est_vente else "AC", f["date"], libelle, lignes,
        piece=f["numero"], reference=f["reference"], module="facturation",
        source_type="facture", source_id=f["id"], utilisateur=utilisateur,
        perimetre="hors_declaration", operation_ref=operation,
    )


@route("POST", "/api/factures/<id>/annuler")
def api_annule(ctx):
    ctx.exige_role("admin", "comptable")
    identifiant = int(ctx.params["id"])
    f = facture_ou_erreur(identifiant)
    if f["montant_regle"]:
        raise ErreurApplicative(
            "Cette facture a été réglée : supprimez d'abord les règlements."
        )
    with db.transaction():
        # Les deux parts d'une même vente s'annulent ensemble : en extourner
        # une seule laisserait la vente à moitié debout.
        for cle in ("ecriture_id", "ecriture_hors_id"):
            if f.get(cle):
                compta.extourne_ecriture(f[cle], util.aujourdhui(),
                                         ctx.nom_utilisateur)
        db.modifie("factures", identifiant, {"statut": "annulee"})
        db.trace("annulation", "facture", identifiant, f["numero"], ctx.nom_utilisateur)
    return {"ok": True}


@route("DELETE", "/api/factures/<id>")
def api_supprime(ctx):
    ctx.exige_role("admin", "comptable")
    identifiant = int(ctx.params["id"])
    f = facture_ou_erreur(identifiant)
    if f["statut"] != "brouillon":
        raise ErreurApplicative(
            "Seule une facture en brouillon peut être supprimée. "
            "Utilisez « Annuler » pour une facture validée."
        )
    with db.transaction():
        db.supprime("factures", identifiant)
        db.trace("suppression", "facture", identifiant, f["numero"], ctx.nom_utilisateur)
    return {"ok": True}


@route("POST", "/api/factures/<id>/avoir")
def api_cree_avoir(ctx):
    """Génère l'avoir total ou partiel d'une facture validée."""
    ctx.interdit_lecture_seule()
    identifiant = int(ctx.params["id"])
    f = facture_ou_erreur(identifiant)
    if f["statut"] == "brouillon":
        raise ErreurApplicative("Validez la facture avant d'émettre un avoir.")
    sens_avoir = "avoir_vente" if f["sens"] == "vente" else "avoir_achat"
    lignes_origine = db.lignes(
        "SELECT * FROM facture_lignes WHERE facture_id = ? ORDER BY ordre", (identifiant,)
    )
    date = ctx.date("date", util.aujourdhui())
    ex = compta.exercice_pour_date(f["societe_id"], date)

    with db.transaction():
        numero = db.numero_suivant(f["societe_id"], sens_avoir, int(date[:4]))
        avoir_id = db.insere("factures", {
            "societe_id": f["societe_id"], "exercice_id": ex["id"], "sens": sens_avoir,
            "numero": numero, "date": date, "tiers_id": f["tiers_id"],
            "objet": ctx.champ("motif") or f"Avoir sur facture n° {f['numero']}",
            "reference": f["numero"], "origine": f["origine"],
            "programme_id": f["programme_id"], "lot_id": f["lot_id"],
            "bien_id": f["bien_id"],
            "montant_ht": f["montant_ht"], "montant_tva": f["montant_tva"],
            "montant_ttc": f["montant_ttc"], "timbre": f["timbre"],
            "net_a_payer": f["net_a_payer"], "montant_regle": 0,
            "statut": "brouillon", "perimetre": f["perimetre"],
            "cree_le": util.maintenant(), "cree_par": ctx.nom_utilisateur,
        })
        for l in lignes_origine:
            db.insere("facture_lignes", {
                "facture_id": avoir_id, "ordre": l["ordre"],
                "designation": l["designation"], "quantite": l["quantite"],
                "unite": l["unite"], "prix_unitaire": l["prix_unitaire"],
                "remise_taux": l["remise_taux"], "taux_tva": l["taux_tva"],
                "montant_ht": l["montant_ht"], "montant_tva": l["montant_tva"],
                "compte": l["compte"],
            })
        _valide(avoir_id, ctx.nom_utilisateur)
    return {"id": avoir_id, "numero": numero}


# ---------------------------------------------------------------------------
# Règlements
# ---------------------------------------------------------------------------

@route("POST", "/api/reglements")
def api_cree_reglement(ctx):
    ctx.interdit_lecture_seule()
    with db.transaction():
        r = cree_reglement(
            ctx.entier("societe_id"),
            sens=ctx.champ("sens", "encaissement"),
            date=ctx.date("date", util.aujourdhui()),
            montant=ctx.montant("montant"),
            tresorerie_id=ctx.entier("tresorerie_id"),
            facture_id=ctx.entier("facture_id"),
            tiers_id=ctx.entier("tiers_id"),
            mode=ctx.champ("mode", "virement"),
            reference=ctx.champ("reference"),
            libelle=ctx.champ("libelle"),
            perimetre=ctx.champ("perimetre"),
            part=ctx.champ("part"),
            utilisateur=ctx.nom_utilisateur,
        )
    return r


@route("POST", "/api/reglements/multiple")
def api_cree_reglements(ctx):
    """Un même encaissement payé en plusieurs fois, en une seule saisie.

    Le client apporte un chèque **et** des espèces pour la même vente. Cela
    fait bien deux règlements — deux comptes de trésorerie, deux références,
    deux lignes au relevé — mais un seul geste, et c'est ainsi qu'il faut
    pouvoir le saisir. La référence d'opération les garde ensemble.
    """
    ctx.interdit_lecture_seule()
    societe_id = ctx.entier("societe_id")
    lignes = [l for l in (ctx.champ("lignes") or [])
              if util.centimes(l.get("montant")) > 0]
    if not lignes:
        raise ErreurApplicative("Saisissez au moins un montant.")

    sens = ctx.champ("sens", "encaissement")
    date = ctx.date("date", util.aujourdhui())
    facture_id = ctx.entier("facture_id")
    tiers_id = ctx.entier("tiers_id")
    horodatage = util.maintenant().replace("-", "").replace(":", "").replace(" ", "-")
    reference_op = f"REG-{horodatage}" if len(lignes) > 1 else None

    faits = []
    with db.transaction():
        for l in lignes:
            faits.append(cree_reglement(
                societe_id,
                sens=sens,
                date=util.date_iso(l.get("date")) or date,
                montant=util.centimes(l.get("montant")),
                tresorerie_id=int(l.get("tresorerie_id") or 0) or None,
                facture_id=facture_id,
                tiers_id=tiers_id,
                mode=l.get("mode") or "virement",
                reference=l.get("reference"),
                libelle=ctx.champ("libelle"),
                perimetre=ctx.champ("perimetre"),
                part=l.get("part"),
                operation_ref=reference_op,
                utilisateur=ctx.nom_utilisateur,
            ))
    return {"reglements": faits, "operation_ref": reference_op,
            "total": sum(f["montant"] for f in faits)}


def cree_reglement(societe_id: int, *, sens: str, date: str, montant: int,
                   tresorerie_id, facture_id=None, tiers_id=None,
                   mode: str = "virement", reference: str | None = None,
                   libelle: str | None = None, perimetre: str | None = None,
                   part: str | None = None, operation_ref: str | None = None,
                   utilisateur: str | None = None) -> dict:
    """Enregistre un règlement et son écriture. À appeler dans une transaction.

    `part` dit laquelle des deux moitiés d'une vente ce règlement solde :
    « declare » ou « hors_declaration ». Le client apporte souvent un chèque
    pour l'une et des espèces pour l'autre ; chacune a son reste dû.
    """
    if sens not in ("encaissement", "decaissement"):
        raise ErreurApplicative("Sens de règlement invalide.")
    if montant <= 0:
        raise ErreurApplicative("Le montant du règlement doit être positif.")
    ex = compta.exercice_pour_date(societe_id, date)
    compta.exige_exercice_ouvert(ex)

    tresorerie = db.ligne("SELECT * FROM comptes_tresorerie WHERE id = ?",
                          (tresorerie_id,)) if tresorerie_id else None
    if not tresorerie:
        raise ErreurApplicative("Sélectionnez le compte de trésorerie (banque ou caisse).")

    facture = db.ligne("SELECT * FROM factures WHERE id = ?", (facture_id,)) if facture_id else None
    tiers_id = tiers_id or (facture["tiers_id"] if facture else None)
    if not tiers_id:
        raise ErreurApplicative("Indiquez le tiers concerné par le règlement.")
    tiers = tiers_ou_erreur(tiers_id)

    part = compta.normalise_perimetre(part, "declare") if part else None
    if facture and part is None:
        # Sans précision, un règlement solde la part déclarée — sauf sur une
        # facture entièrement hors déclaration, où il n'y a que celle-là.
        part = ("hors_declaration" if facture["perimetre"] == "hors_declaration"
                else "declare")
    if facture:
        if part == "hors_declaration" and facture["perimetre"] == "declare":
            reste = (facture["montant_hors"] or 0) - (facture["montant_hors_regle"] or 0)
            nom_part = "la part non déclarée"
        else:
            reste = facture["net_a_payer"] - facture["montant_regle"]
            nom_part = ("la facture" if not facture["montant_hors"]
                        else "la part déclarée")
        if montant > reste:
            raise ErreurApplicative(
                f"Montant supérieur au reste dû sur {nom_part} "
                f"({util.formate_montant(reste)}). Corrigez le montant, ou "
                "changez la part que ce règlement solde."
            )

    compte_tiers = (compte_du_tiers(tiers) if not facture
                    else _compte_tiers_facture(facture, tiers))
    journal = "BQ" if tresorerie["type"] in ("banque", "ccp") else "CA"
    libelle = libelle or (
        f"{'Encaissement' if sens == 'encaissement' else 'Règlement'} "
        f"{tiers['raison_sociale']}"
        + (f" — facture {facture['numero']}" if facture else "")
    )

    perimetre = compta.normalise_perimetre(
        perimetre or part or (facture["perimetre"] if facture else None),
        db.valeur("SELECT perimetre_defaut FROM societes WHERE id = ?",
                  (societe_id,), "declare"))

    if sens == "encaissement":
        lignes_ecriture = [
            {"compte": tresorerie["compte"], "debit": montant, "credit": 0,
             "libelle": libelle},
            {"compte": compte_tiers, "debit": 0, "credit": montant,
             "tiers_id": tiers_id, "libelle": libelle},
        ]
    else:
        lignes_ecriture = [
            {"compte": compte_tiers, "debit": montant, "credit": 0,
             "tiers_id": tiers_id, "libelle": libelle},
            {"compte": tresorerie["compte"], "debit": 0, "credit": montant,
             "libelle": libelle},
        ]

    reference = util.nettoie(reference)
    ecriture_id = compta.enregistre_ecriture(
        societe_id, journal, date, libelle, lignes_ecriture,
        piece=reference,
        reference=facture["numero"] if facture else None,
        module="reglement", source_type="reglement", source_id=None,
        utilisateur=utilisateur, perimetre=perimetre,
        operation_ref=operation_ref,
    )
    reglement_id = db.insere("reglements", {
        "societe_id": societe_id, "exercice_id": ex["id"], "sens": sens,
        "date": date, "tiers_id": tiers_id, "tresorerie_id": tresorerie["id"],
        "montant": montant, "mode": mode or "virement",
        "reference": reference,
        "libelle": libelle, "facture_id": facture_id,
        "perimetre": perimetre, "operation_ref": operation_ref,
        "part": part,
        "ecriture_id": ecriture_id, "cree_le": util.maintenant(),
    })
    db.execute("UPDATE ecritures SET source_id = ? WHERE id = ?",
               (reglement_id, ecriture_id))

    if facture:
        sur_hors = (part == "hors_declaration"
                    and facture["perimetre"] == "declare"
                    and facture["montant_hors"])
        regle = facture["montant_regle"] + (0 if sur_hors else montant)
        hors_regle = (facture["montant_hors_regle"] or 0) + (montant if sur_hors else 0)
        # Une vente n'est soldée que lorsque ses deux parts le sont.
        du = facture["net_a_payer"] + (facture["montant_hors"] or 0)
        paye = regle + hors_regle
        statut = ("payee" if paye >= du
                  else "partielle" if paye > 0 else facture["statut"])
        db.modifie("factures", facture_id,
                   {"montant_regle": regle, "montant_hors_regle": hors_regle,
                    "statut": statut})
    db.trace("creation", "reglement", reglement_id, libelle, utilisateur)

    return {"id": reglement_id, "ecriture_id": ecriture_id, "montant": montant,
            "mode": mode or "virement"}


def _compte_tiers_facture(facture: dict, tiers: dict) -> str:
    """Le règlement doit solder le même compte que celui mouvementé à la facture."""
    if facture["ecriture_id"]:
        collectif = db.valeur(
            "SELECT compte FROM lignes WHERE ecriture_id = ? AND tiers_id = ? LIMIT 1",
            (facture["ecriture_id"], tiers["id"]),
        )
        if collectif:
            return collectif
    return compte_du_tiers(tiers)


@route("GET", "/api/reglements")
def api_liste_reglements(ctx):
    societe_id = ctx.arg_int("societe")
    conditions = ["r.societe_id = ?"]
    params: list = [societe_id]
    if ctx.arg("sens"):
        conditions.append("r.sens = ?")
        params.append(ctx.arg("sens"))
    if ctx.arg("du"):
        conditions.append("r.date >= ?")
        params.append(ctx.arg("du"))
    if ctx.arg("au"):
        conditions.append("r.date <= ?")
        params.append(ctx.arg("au"))
    if ctx.arg("tresorerie"):
        conditions.append("r.tresorerie_id = ?")
        params.append(ctx.arg_int("tresorerie"))
    return {"reglements": db.lignes(
        "SELECT r.*, t.raison_sociale AS tiers_nom, ct.libelle AS tresorerie, "
        "       f.numero AS facture_numero "
        "FROM reglements r LEFT JOIN tiers t ON t.id = r.tiers_id "
        "LEFT JOIN comptes_tresorerie ct ON ct.id = r.tresorerie_id "
        "LEFT JOIN factures f ON f.id = r.facture_id "
        f"WHERE {' AND '.join(conditions)} ORDER BY r.date DESC, r.id DESC LIMIT 500",
        params,
    )}


@route("DELETE", "/api/reglements/<id>")
def api_supprime_reglement(ctx):
    ctx.exige_role("admin", "comptable")
    identifiant = int(ctx.params["id"])
    r = db.ligne("SELECT * FROM reglements WHERE id = ?", (identifiant,))
    if not r:
        raise ErreurApplicative("Règlement introuvable.", 404)
    with db.transaction():
        if r["ecriture_id"]:
            compta.supprime_ecriture(r["ecriture_id"], ctx.nom_utilisateur, forcer=True)
        if r["facture_id"]:
            f = db.ligne("SELECT * FROM factures WHERE id = ?", (r["facture_id"],))
            if f:
                # Le règlement rend ce qu'il avait soldé, et à la bonne part.
                sur_hors = (r["part"] == "hors_declaration"
                            and f["perimetre"] == "declare"
                            and f["montant_hors"])
                regle = max(f["montant_regle"] - (0 if sur_hors else r["montant"]), 0)
                hors_regle = max((f["montant_hors_regle"] or 0)
                                 - (r["montant"] if sur_hors else 0), 0)
                du = f["net_a_payer"] + (f["montant_hors"] or 0)
                paye = regle + hors_regle
                statut = ("payee" if paye >= du
                          else "partielle" if paye > 0 else "validee")
                db.modifie("factures", r["facture_id"],
                           {"montant_regle": regle,
                            "montant_hors_regle": hors_regle,
                            "statut": statut})
        db.supprime("reglements", identifiant)
        db.trace("suppression", "reglement", identifiant, None, ctx.nom_utilisateur)
    return {"ok": True}


@route("GET", "/api/export/factures")
def api_export(ctx):
    """Export du journal des ventes ou des achats, tel qu'affiché à l'écran.

    Deux feuilles : les factures, puis le détail de leurs lignes. Les filtres
    de l'écran (type, statut, recherche, période, périmètre) sont repris tels
    quels, afin que le fichier corresponde à ce que le comptable a sous
    les yeux.
    """
    societe_id = ctx.arg_int("societe")
    soc = compta.societe(societe_id)
    sens = ctx.arg("sens") or "vente"
    filtre, params = _filtres_factures(ctx)
    factures = db.lignes(
        "SELECT f.*, t.raison_sociale AS tiers_nom, t.code AS tiers_code, "
        "  t.nif AS tiers_nif, t.rc AS tiers_rc "
        "FROM factures f LEFT JOIN tiers t ON t.id = f.tiers_id "
        f"WHERE {filtre} ORDER BY f.date, f.id", params)

    classeur = tableur.Classeur()
    f = classeur.feuille(LIBELLES_SENS.get(sens, "Factures")[:31])
    f.titre(f"{soc['raison_sociale']} — {LIBELLES_SENS.get(sens, 'Factures')}")
    f.ajoute(tableur.texte(compta.LIBELLES_VUE.get(
        compta.normalise_perimetre(ctx.perimetre() or "tous"), "Vue réelle")))
    if ctx.arg("du") or ctx.arg("au"):
        f.ajoute(tableur.texte(f"Du {util.date_fr(ctx.arg('du'))} "
                               f"au {util.date_fr(ctx.arg('au'))}"))
    f.vide()
    f.entetes("N°", "Date", "Échéance", "Tiers", "NIF", "Objet", "Référence",
              "Montant HT", "TVA", "Timbre", "Net à payer", "Réglé",
              "Reste dû", "Statut", "Périmètre", "Mode de règlement")
    f.largeurs_auto(14, 12, 12, 30, 18, 34, 16, 15, 14, 12, 15, 15, 15, 12, 16, 16)
    for facture in factures:
        f.ajoute(
            tableur.texte(facture["numero"]),
            tableur.date_cel(facture["date"]),
            tableur.date_cel(facture["date_echeance"]),
            tableur.texte(facture["tiers_nom"]),
            tableur.texte(facture["tiers_nif"]),
            tableur.texte(facture["objet"]),
            tableur.texte(facture["reference"]),
            tableur.monnaie(facture["montant_ht"]),
            tableur.monnaie(facture["montant_tva"]),
            tableur.monnaie(facture["timbre"]),
            tableur.monnaie(facture["net_a_payer"]),
            tableur.monnaie(facture["montant_regle"]),
            tableur.monnaie(facture["net_a_payer"] - facture["montant_regle"]),
            tableur.texte(facture["statut"]),
            tableur.texte(compta.PERIMETRES.get(facture["perimetre"], "")),
            tableur.texte(facture["mode_reglement"]),
        )
    vivantes = [x for x in factures if x["statut"] != "annulee"]
    f.ajoute(
        tableur.texte("TOTAL", tableur.GRAS), *[tableur.texte("")] * 6,
        tableur.monnaie(sum(x["montant_ht"] for x in vivantes), total=True),
        tableur.monnaie(sum(x["montant_tva"] for x in vivantes), total=True),
        tableur.monnaie(sum(x["timbre"] for x in vivantes), total=True),
        tableur.monnaie(sum(x["net_a_payer"] for x in vivantes), total=True),
        tableur.monnaie(sum(x["montant_regle"] for x in vivantes), total=True),
        tableur.monnaie(sum(x["net_a_payer"] - x["montant_regle"]
                            for x in vivantes), total=True),
    )

    detail = classeur.feuille("Lignes")
    detail.entetes("N° facture", "Date", "Tiers", "Désignation", "Quantité",
                   "Unité", "Prix unitaire", "Remise %", "Taux TVA",
                   "Montant HT", "TVA", "Compte")
    detail.largeurs_auto(14, 12, 30, 44, 11, 10, 15, 11, 11, 15, 14, 12)
    if factures:
        marques = ", ".join("?" for _ in factures)
        lignes = db.lignes(
            "SELECT fl.*, f.numero, f.date, t.raison_sociale AS tiers_nom "
            "FROM facture_lignes fl JOIN factures f ON f.id = fl.facture_id "
            "LEFT JOIN tiers t ON t.id = f.tiers_id "
            f"WHERE fl.facture_id IN ({marques}) "
            "ORDER BY f.date, f.id, fl.ordre", [x["id"] for x in factures])
        for l in lignes:
            detail.ajoute(
                tableur.texte(l["numero"]), tableur.date_cel(l["date"]),
                tableur.texte(l["tiers_nom"]), tableur.texte(l["designation"]),
                tableur.nombre(l["quantite"] / 1000, tableur.NORMAL),
                tableur.texte(l["unite"]),
                tableur.monnaie(l["prix_unitaire"]),
                tableur.nombre(l["remise_taux"] / 100, tableur.NORMAL),
                tableur.nombre(l["taux_tva"] / 100, tableur.NORMAL),
                tableur.monnaie(l["montant_ht"]), tableur.monnaie(l["montant_tva"]),
                tableur.texte(l["compte"]),
            )

    return Reponse(classeur.octets(),
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   f"{sens}_{soc['code']}_{util.aujourdhui()}.xlsx")


@route("GET", "/api/factures/<id>/impression")
def api_impression(ctx):
    """Données complètes pour l'édition imprimable de la facture."""
    from modules import documents
    identifiant = int(ctx.params["id"])
    f = api_detail(ctx)
    return documents.reponse_html(documents.facture_html(f))
