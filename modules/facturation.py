"""Facturation et règlements.

Une facture validée génère automatiquement son écriture comptable, dans le
journal des ventes ou des achats, avec ventilation de la TVA et du droit de
timbre. Les axes analytiques (programme / lot / bien) sont reportés sur les
lignes afin d'alimenter le coût de revient des programmes immobiliers.
"""

from __future__ import annotations

from noyau import base as db
from noyau import util
from noyau.serveur import ErreurApplicative, route
from modules import comptabilite as compta
from modules.tiers import compte_du_tiers, tiers_ou_erreur

SENS_VALIDES = {"vente", "achat", "avoir_vente", "avoir_achat", "proforma"}

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


def calcule_timbre(societe_id: int, mode_reglement: str | None, montant_ttc: int,
                   annee: int) -> int:
    """Droit de timbre applicable aux règlements en espèces."""
    if mode_reglement != "espece":
        return 0
    taux = db.parametre_fiscal_int(annee, "timbre_taux", 100)
    minimum = db.parametre_fiscal_int(annee, "timbre_minimum", 500)
    seuil = db.parametre_fiscal_int(annee, "timbre_seuil_espece", 0)
    if montant_ttc < seuil:
        return 0
    montant = util.applique_taux(montant_ttc, taux)
    return max(montant, minimum) if montant_ttc > 0 else 0


@route("GET", "/api/factures")
def api_liste(ctx):
    societe_id = ctx.arg_int("societe")
    conditions = ["f.societe_id = ?"]
    params: list = [societe_id]
    if ctx.arg("sens"):
        conditions.append("f.sens = ?")
        params.append(ctx.arg("sens"))
    if ctx.arg("statut"):
        conditions.append("f.statut = ?")
        params.append(ctx.arg("statut"))
    if ctx.arg("tiers"):
        conditions.append("f.tiers_id = ?")
        params.append(ctx.arg_int("tiers"))
    if ctx.arg("programme"):
        conditions.append("f.programme_id = ?")
        params.append(ctx.arg_int("programme"))
    if ctx.arg("du"):
        conditions.append("f.date >= ?")
        params.append(ctx.arg("du"))
    if ctx.arg("au"):
        conditions.append("f.date <= ?")
        params.append(ctx.arg("au"))
    if ctx.arg("q"):
        conditions.append("(f.numero LIKE ? OR f.objet LIKE ? OR t.raison_sociale LIKE ?)")
        motif = "%" + ctx.arg("q") + "%"
        params += [motif, motif, motif]
    limite = min(ctx.arg_int("limite", 200) or 200, 2000)
    factures = db.lignes(
        "SELECT f.*, t.raison_sociale AS tiers_nom, t.code AS tiers_code "
        "FROM factures f LEFT JOIN tiers t ON t.id = f.tiers_id "
        f"WHERE {' AND '.join(conditions)} ORDER BY f.date DESC, f.id DESC LIMIT ?",
        params + [limite],
    )
    totaux = db.ligne(
        "SELECT COALESCE(SUM(f.montant_ht),0) AS ht, COALESCE(SUM(f.montant_tva),0) AS tva, "
        "  COALESCE(SUM(f.net_a_payer),0) AS ttc, "
        "  COALESCE(SUM(f.net_a_payer - f.montant_regle),0) AS reste "
        "FROM factures f LEFT JOIN tiers t ON t.id = f.tiers_id "
        f"WHERE {' AND '.join(conditions)} AND f.statut <> 'annulee'",
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
    return f


@route("POST", "/api/factures")
def api_cree(ctx):
    ctx.interdit_lecture_seule()
    societe_id = ctx.entier("societe_id")
    sens = ctx.champ("sens", "vente")
    if sens not in SENS_VALIDES:
        raise ErreurApplicative("Type de facture invalide.")
    date = ctx.date("date", util.aujourdhui())
    ex = compta.exercice_pour_date(societe_id, date)
    compta.exige_exercice_ouvert(ex)

    tiers_id = ctx.entier("tiers_id")
    if not tiers_id and sens != "proforma":
        raise ErreurApplicative("Sélectionnez le tiers de la facture.")

    lignes_pretes, total_ht, total_tva = calcule_lignes(ctx.champ("lignes") or [])
    mode = ctx.champ("mode_reglement")
    ttc = total_ht + total_tva
    timbre = calcule_timbre(societe_id, mode, ttc, int(date[:4]))

    with db.transaction():
        cle_compteur = {"vente": "facture_vente", "achat": "facture_achat",
                        "avoir_vente": "avoir_vente", "avoir_achat": "avoir_achat",
                        "proforma": "proforma"}[sens]
        numero = util.nettoie(ctx.champ("numero"))
        if sens == "achat" and not numero:
            raise ErreurApplicative(
                "Saisissez le numéro de la facture du fournisseur (numéro d'origine)."
            )
        if not numero:
            numero = db.numero_suivant(societe_id, cle_compteur, int(date[:4]))
        if db.ligne("SELECT id FROM factures WHERE societe_id = ? AND sens = ? AND numero = ?",
                    (societe_id, sens, numero)):
            raise ErreurApplicative(f"La facture n° {numero} existe déjà.")

        facture_id = db.insere("factures", {
            "societe_id": societe_id, "exercice_id": ex["id"], "sens": sens,
            "numero": numero, "date": date,
            "date_echeance": ctx.date("date_echeance"),
            "tiers_id": tiers_id,
            "objet": util.nettoie(ctx.champ("objet")),
            "reference": util.nettoie(ctx.champ("reference")),
            "origine": util.nettoie(ctx.champ("origine")),
            "programme_id": ctx.entier("programme_id"),
            "lot_id": ctx.entier("lot_id"),
            "bien_id": ctx.entier("bien_id"),
            "bail_id": ctx.entier("bail_id"),
            "contrat_vsp_id": ctx.entier("contrat_vsp_id"),
            "montant_ht": total_ht, "montant_tva": total_tva, "montant_ttc": ttc,
            "timbre": timbre, "net_a_payer": ttc + timbre, "montant_regle": 0,
            "mode_reglement": mode,
            "statut": "brouillon",
            "perimetre": compta.normalise_perimetre(
                ctx.champ("perimetre"),
                db.valeur("SELECT perimetre_defaut FROM societes WHERE id = ?",
                          (societe_id,), "declare")),
            "notes": util.nettoie(ctx.champ("notes")),
            "conditions": util.nettoie(ctx.champ("conditions")),
            "cree_le": util.maintenant(), "cree_par": ctx.nom_utilisateur,
        })
        for l in lignes_pretes:
            l["facture_id"] = facture_id
            db.insere("facture_lignes", l)
        db.trace("creation", "facture", facture_id, numero, ctx.nom_utilisateur)

        if ctx.booleen("valider"):
            _valide(facture_id, ctx.nom_utilisateur)

    return {"id": facture_id, "numero": numero}


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
    timbre = calcule_timbre(f["societe_id"], mode, ttc, int(date[:4]))

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
            "perimetre": compta.normalise_perimetre(
                ctx.champ("perimetre"), f["perimetre"]),
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

    ecriture_id = compta.enregistre_ecriture(
        f["societe_id"], journal, f["date"], libelle, lignes_ecriture,
        piece=f["numero"], reference=f["reference"], module="facturation",
        source_type="facture", source_id=facture_id, utilisateur=utilisateur,
        perimetre=f.get("perimetre"),
    )
    db.modifie("factures", facture_id, {"statut": "validee", "ecriture_id": ecriture_id})
    db.trace("validation", "facture", facture_id, f["numero"], utilisateur)
    return ecriture_id


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
        if f["ecriture_id"]:
            compta.extourne_ecriture(f["ecriture_id"], util.aujourdhui(), ctx.nom_utilisateur)
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
    societe_id = ctx.entier("societe_id")
    sens = ctx.champ("sens", "encaissement")
    if sens not in ("encaissement", "decaissement"):
        raise ErreurApplicative("Sens de règlement invalide.")
    montant = ctx.montant("montant")
    if montant <= 0:
        raise ErreurApplicative("Le montant du règlement doit être positif.")
    date = ctx.date("date", util.aujourdhui())
    ex = compta.exercice_pour_date(societe_id, date)
    compta.exige_exercice_ouvert(ex)

    tresorerie_id = ctx.entier("tresorerie_id")
    tresorerie = db.ligne("SELECT * FROM comptes_tresorerie WHERE id = ?", (tresorerie_id,))
    if not tresorerie:
        raise ErreurApplicative("Sélectionnez le compte de trésorerie (banque ou caisse).")

    facture_id = ctx.entier("facture_id")
    facture = db.ligne("SELECT * FROM factures WHERE id = ?", (facture_id,)) if facture_id else None
    tiers_id = ctx.entier("tiers_id") or (facture["tiers_id"] if facture else None)
    if not tiers_id:
        raise ErreurApplicative("Indiquez le tiers concerné par le règlement.")
    tiers = tiers_ou_erreur(tiers_id)

    if facture:
        reste = facture["net_a_payer"] - facture["montant_regle"]
        if montant > reste:
            raise ErreurApplicative(
                f"Montant supérieur au reste dû ({util.formate_montant(reste)}). "
                "Corrigez le montant ou créez un règlement sans facture rattachée."
            )

    compte_tiers = (compte_du_tiers(tiers) if not facture
                    else _compte_tiers_facture(facture, tiers))
    journal = "BQ" if tresorerie["type"] in ("banque", "ccp") else "CA"
    libelle = ctx.champ("libelle") or (
        f"{'Encaissement' if sens == 'encaissement' else 'Règlement'} "
        f"{tiers['raison_sociale']}"
        + (f" — facture {facture['numero']}" if facture else "")
    )

    perimetre = compta.normalise_perimetre(
        ctx.champ("perimetre") or (facture["perimetre"] if facture else None),
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

    with db.transaction():
        ecriture_id = compta.enregistre_ecriture(
            societe_id, journal, date, libelle, lignes_ecriture,
            piece=util.nettoie(ctx.champ("reference")),
            reference=facture["numero"] if facture else None,
            module="reglement", source_type="reglement", source_id=None,
            utilisateur=ctx.nom_utilisateur, perimetre=perimetre,
        )
        reglement_id = db.insere("reglements", {
            "societe_id": societe_id, "exercice_id": ex["id"], "sens": sens,
            "date": date, "tiers_id": tiers_id, "tresorerie_id": tresorerie_id,
            "montant": montant, "mode": ctx.champ("mode", "virement"),
            "reference": util.nettoie(ctx.champ("reference")),
            "libelle": libelle, "facture_id": facture_id,
            "perimetre": perimetre,
            "ecriture_id": ecriture_id, "cree_le": util.maintenant(),
        })
        db.execute("UPDATE ecritures SET source_id = ? WHERE id = ?",
                   (reglement_id, ecriture_id))

        if facture:
            regle = facture["montant_regle"] + montant
            statut = ("payee" if regle >= facture["net_a_payer"]
                      else "partielle" if regle > 0 else facture["statut"])
            db.modifie("factures", facture_id,
                       {"montant_regle": regle, "statut": statut})
        db.trace("creation", "reglement", reglement_id, libelle, ctx.nom_utilisateur)

    return {"id": reglement_id, "ecriture_id": ecriture_id}


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
                regle = max(f["montant_regle"] - r["montant"], 0)
                statut = ("payee" if regle >= f["net_a_payer"]
                          else "partielle" if regle > 0 else "validee")
                db.modifie("factures", r["facture_id"],
                           {"montant_regle": regle, "statut": statut})
        db.supprime("reglements", identifiant)
        db.trace("suppression", "reglement", identifiant, None, ctx.nom_utilisateur)
    return {"ok": True}


@route("GET", "/api/factures/<id>/impression")
def api_impression(ctx):
    """Données complètes pour l'édition imprimable de la facture."""
    from modules import documents
    identifiant = int(ctx.params["id"])
    f = api_detail(ctx)
    return documents.reponse_html(documents.facture_html(f))
