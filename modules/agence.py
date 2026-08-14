"""Agence immobilière : portefeuille de biens, mandats, transactions de vente
et gestion locative.

Principe comptable structurant : **les loyers encaissés pour le compte des
propriétaires ne sont jamais un produit de l'agence.** Ils transitent par le
compte 4671 « Propriétaires mandants ». Seuls les honoraires (entremise,
gestion, commission de vente) constituent le chiffre d'affaires de l'agence,
en compte 706x. C'est ce qui distingue le chiffre d'affaires réel de l'agence
du volume d'argent qui transite par ses comptes — et c'est ce qui est
contrôlé en cas de vérification fiscale.
"""

from __future__ import annotations

from noyau import base as db
from noyau import util
from noyau import tableur
from noyau.serveur import ErreurApplicative, route, Reponse
from modules import comptabilite as compta
from modules.tiers import compte_du_tiers

COMPTE_MANDANT = "4671"
COMPTE_DEPOT_GARANTIE = "4672"
COMPTE_COMMISSION_VENTE = "7061"
COMPTE_HONORAIRES_LOCATION = "7062"
COMPTE_HONORAIRES_GESTION = "7063"
COMPTE_TVA_COLLECTEE = "4457"

TYPES_BIEN = ["appartement", "villa", "local_commercial", "bureau", "terrain",
              "hangar", "garage", "immeuble"]


# ===========================================================================
# BIENS
# ===========================================================================

@route("GET", "/api/biens")
def api_biens(ctx):
    societe_id = ctx.arg_int("societe")
    conditions = ["b.societe_id = ?"]
    params: list = [societe_id]
    if ctx.arg("statut"):
        conditions.append("b.statut = ?")
        params.append(ctx.arg("statut"))
    if ctx.arg("type"):
        conditions.append("b.type_bien = ?")
        params.append(ctx.arg("type"))
    if ctx.arg("proprietaire"):
        conditions.append("b.proprietaire_id = ?")
        params.append(ctx.arg_int("proprietaire"))
    if ctx.arg("q"):
        conditions.append("(b.designation LIKE ? OR b.reference LIKE ? "
                          "OR b.adresse LIKE ? OR b.commune LIKE ?)")
        motif = "%" + ctx.arg("q") + "%"
        params += [motif, motif, motif, motif]
    return {"biens": db.lignes(
        "SELECT b.*, t.raison_sociale AS proprietaire "
        "FROM biens b LEFT JOIN tiers t ON t.id = b.proprietaire_id "
        f"WHERE {' AND '.join(conditions)} ORDER BY b.reference DESC LIMIT 500", params
    )}


@route("GET", "/api/biens/<id>")
def api_bien(ctx):
    identifiant = int(ctx.params["id"])
    b = db.ligne(
        "SELECT b.*, t.raison_sociale AS proprietaire, t.telephone AS proprietaire_tel "
        "FROM biens b LEFT JOIN tiers t ON t.id = b.proprietaire_id WHERE b.id = ?",
        (identifiant,),
    )
    if not b:
        raise ErreurApplicative("Bien introuvable.", 404)
    b["mandats"] = db.lignes("SELECT * FROM mandats WHERE bien_id = ? ORDER BY date_debut DESC",
                             (identifiant,))
    b["baux"] = db.lignes(
        "SELECT b.*, t.raison_sociale AS locataire FROM baux b "
        "LEFT JOIN tiers t ON t.id = b.locataire_id WHERE b.bien_id = ? "
        "ORDER BY b.date_debut DESC", (identifiant,)
    )
    b["transactions"] = db.lignes(
        "SELECT * FROM transactions WHERE bien_id = ? ORDER BY date_compromis DESC",
        (identifiant,)
    )
    return b


@route("POST", "/api/biens")
def api_cree_bien(ctx):
    ctx.interdit_lecture_seule()
    societe_id = ctx.entier("societe_id")
    with db.transaction():
        reference = util.nettoie(ctx.champ("reference")) or db.numero_suivant(societe_id, "bien")
        if db.ligne("SELECT id FROM biens WHERE societe_id = ? AND reference = ?",
                    (societe_id, reference)):
            raise ErreurApplicative(f"La référence « {reference} » existe déjà.")
        identifiant = db.insere("biens", {
            "societe_id": societe_id, "reference": reference,
            "type_bien": ctx.champ("type_bien", "appartement"),
            "designation": ctx.champ_requis("designation"),
            "adresse": util.nettoie(ctx.champ("adresse")),
            "commune": util.nettoie(ctx.champ("commune")),
            "wilaya": util.nettoie(ctx.champ("wilaya")),
            "surface": int(round(float(ctx.champ("surface") or 0) * 100)),
            "nb_pieces": util.nettoie(ctx.champ("nb_pieces")),
            "etage": util.nettoie(ctx.champ("etage")),
            "nature_juridique": util.nettoie(ctx.champ("nature_juridique")),
            "num_acte": util.nettoie(ctx.champ("num_acte")),
            "proprietaire_id": ctx.entier("proprietaire_id"),
            "prix_demande": ctx.montant("prix_demande"),
            "loyer_mensuel": ctx.montant("loyer_mensuel"),
            "statut": ctx.champ("statut", "disponible"),
            "description": util.nettoie(ctx.champ("description")),
            "cree_le": util.maintenant(),
        })
        db.trace("creation", "bien", identifiant, reference, ctx.nom_utilisateur)
    return {"id": identifiant, "reference": reference}


@route("PUT", "/api/biens/<id>")
def api_modifie_bien(ctx):
    ctx.interdit_lecture_seule()
    identifiant = int(ctx.params["id"])
    with db.transaction():
        db.modifie("biens", identifiant, {
            "type_bien": ctx.champ("type_bien", "appartement"),
            "designation": ctx.champ_requis("designation"),
            "adresse": util.nettoie(ctx.champ("adresse")),
            "commune": util.nettoie(ctx.champ("commune")),
            "wilaya": util.nettoie(ctx.champ("wilaya")),
            "surface": int(round(float(ctx.champ("surface") or 0) * 100)),
            "nb_pieces": util.nettoie(ctx.champ("nb_pieces")),
            "etage": util.nettoie(ctx.champ("etage")),
            "nature_juridique": util.nettoie(ctx.champ("nature_juridique")),
            "num_acte": util.nettoie(ctx.champ("num_acte")),
            "proprietaire_id": ctx.entier("proprietaire_id"),
            "prix_demande": ctx.montant("prix_demande"),
            "loyer_mensuel": ctx.montant("loyer_mensuel"),
            "statut": ctx.champ("statut", "disponible"),
            "description": util.nettoie(ctx.champ("description")),
        })
    return {"ok": True}


@route("DELETE", "/api/biens/<id>")
def api_supprime_bien(ctx):
    ctx.exige_role("admin", "comptable")
    identifiant = int(ctx.params["id"])
    for table, libelle in (("mandats", "mandat"), ("baux", "bail"),
                           ("transactions", "transaction")):
        if db.valeur(f"SELECT COUNT(*) FROM {table} WHERE bien_id = ?", (identifiant,), 0):
            raise ErreurApplicative(
                f"Ce bien est rattaché à au moins un {libelle} : suppression impossible."
            )
    with db.transaction():
        db.supprime("biens", identifiant)
    return {"ok": True}


# ===========================================================================
# MANDATS
# ===========================================================================

@route("GET", "/api/mandats")
def api_mandats(ctx):
    societe_id = ctx.arg_int("societe")
    conditions = ["m.societe_id = ?"]
    params: list = [societe_id]
    if ctx.arg("statut"):
        conditions.append("m.statut = ?")
        params.append(ctx.arg("statut"))
    if ctx.arg("type"):
        conditions.append("m.type_mandat = ?")
        params.append(ctx.arg("type"))
    return {"mandats": db.lignes(
        "SELECT m.*, b.designation AS bien, b.reference AS bien_reference, "
        "       t.raison_sociale AS mandant "
        "FROM mandats m LEFT JOIN biens b ON b.id = m.bien_id "
        "LEFT JOIN tiers t ON t.id = m.mandant_id "
        f"WHERE {' AND '.join(conditions)} ORDER BY m.date_debut DESC LIMIT 500", params
    )}


@route("POST", "/api/mandats")
def api_cree_mandat(ctx):
    ctx.interdit_lecture_seule()
    societe_id = ctx.entier("societe_id")
    bien_id = ctx.entier("bien_id")
    if not bien_id:
        raise ErreurApplicative("Sélectionnez le bien objet du mandat.")
    with db.transaction():
        numero = util.nettoie(ctx.champ("numero")) or db.numero_suivant(societe_id, "mandat")
        identifiant = db.insere("mandats", {
            "societe_id": societe_id, "numero": numero, "bien_id": bien_id,
            "mandant_id": ctx.entier("mandant_id"),
            "type_mandat": ctx.champ("type_mandat", "vente"),
            "exclusif": ctx.booleen("exclusif"),
            "date_debut": ctx.date("date_debut", util.aujourdhui()),
            "date_fin": ctx.date("date_fin"),
            "prix_mandat": ctx.montant("prix_mandat"),
            "taux_commission": ctx.taux("taux_commission"),
            "commission_forfait": ctx.montant("commission_forfait"),
            "charge_commission": ctx.champ("charge_commission", "vendeur"),
            "statut": "actif",
            "notes": util.nettoie(ctx.champ("notes")),
            "cree_le": util.maintenant(),
        })
        db.trace("creation", "mandat", identifiant, numero, ctx.nom_utilisateur)
    return {"id": identifiant, "numero": numero}


@route("PUT", "/api/mandats/<id>")
def api_modifie_mandat(ctx):
    ctx.interdit_lecture_seule()
    with db.transaction():
        db.modifie("mandats", int(ctx.params["id"]), {
            "type_mandat": ctx.champ("type_mandat", "vente"),
            "exclusif": ctx.booleen("exclusif"),
            "date_debut": ctx.date("date_debut"),
            "date_fin": ctx.date("date_fin"),
            "prix_mandat": ctx.montant("prix_mandat"),
            "taux_commission": ctx.taux("taux_commission"),
            "commission_forfait": ctx.montant("commission_forfait"),
            "charge_commission": ctx.champ("charge_commission", "vendeur"),
            "statut": ctx.champ("statut", "actif"),
            "notes": util.nettoie(ctx.champ("notes")),
        })
    return {"ok": True}


# ===========================================================================
# TRANSACTIONS DE VENTE — commission de l'agence
# ===========================================================================

@route("GET", "/api/transactions")
def api_transactions(ctx):
    societe_id = ctx.arg_int("societe")
    conditions = ["tr.societe_id = ?"]
    params: list = [societe_id]
    if ctx.arg("statut"):
        conditions.append("tr.statut = ?")
        params.append(ctx.arg("statut"))
    return {"transactions": db.lignes(
        "SELECT tr.*, b.designation AS bien, v.raison_sociale AS vendeur, "
        "       a.raison_sociale AS acquereur, f.numero AS facture_numero, f.statut AS facture_statut "
        "FROM transactions tr "
        "LEFT JOIN biens b ON b.id = tr.bien_id "
        "LEFT JOIN tiers v ON v.id = tr.vendeur_id "
        "LEFT JOIN tiers a ON a.id = tr.acquereur_id "
        "LEFT JOIN factures f ON f.id = tr.facture_id "
        f"WHERE {' AND '.join(conditions)} ORDER BY tr.date_compromis DESC LIMIT 500", params
    )}


@route("POST", "/api/transactions")
def api_cree_transaction(ctx):
    ctx.interdit_lecture_seule()
    societe_id = ctx.entier("societe_id")
    prix_vente = ctx.montant("prix_vente")
    if prix_vente <= 0:
        raise ErreurApplicative("Indiquez le prix de vente.")

    mandat_id = ctx.entier("mandat_id")
    commission_ht = ctx.montant("commission_ht")
    if not commission_ht and mandat_id:
        mandat = db.ligne("SELECT * FROM mandats WHERE id = ?", (mandat_id,))
        if mandat:
            commission_ht = (mandat["commission_forfait"]
                             or util.applique_taux(prix_vente, mandat["taux_commission"]))
    if commission_ht <= 0:
        raise ErreurApplicative(
            "La commission est nulle : renseignez-la ou rattachez un mandat "
            "comportant un taux."
        )
    taux_tva = ctx.taux("taux_tva", 1900)
    commission_ttc = commission_ht + util.applique_taux(commission_ht, taux_tva)

    with db.transaction():
        numero = util.nettoie(ctx.champ("numero")) or db.numero_suivant(societe_id, "transaction")
        identifiant = db.insere("transactions", {
            "societe_id": societe_id, "numero": numero,
            "bien_id": ctx.entier("bien_id"), "mandat_id": mandat_id,
            "vendeur_id": ctx.entier("vendeur_id"),
            "acquereur_id": ctx.entier("acquereur_id"),
            "date_compromis": ctx.date("date_compromis"),
            "date_acte": ctx.date("date_acte"),
            "notaire_id": ctx.entier("notaire_id"),
            "prix_vente": prix_vente, "commission_ht": commission_ht,
            "taux_tva": taux_tva, "commission_ttc": commission_ttc,
            "statut": ctx.champ("statut", "en_cours"),
            "notes": util.nettoie(ctx.champ("notes")),
            "cree_le": util.maintenant(),
        })
        db.trace("creation", "transaction", identifiant, numero, ctx.nom_utilisateur)
    return {"id": identifiant, "numero": numero, "commission_ttc": commission_ttc}


@route("POST", "/api/transactions/<id>/facturer")
def api_facture_commission(ctx):
    """Émet la facture d'honoraires et comptabilise la commission."""
    ctx.interdit_lecture_seule()
    from modules import facturation

    identifiant = int(ctx.params["id"])
    tr = db.ligne("SELECT * FROM transactions WHERE id = ?", (identifiant,))
    if not tr:
        raise ErreurApplicative("Transaction introuvable.", 404)
    if tr["facture_id"]:
        raise ErreurApplicative("Cette transaction est déjà facturée.")

    mandat = db.ligne("SELECT * FROM mandats WHERE id = ?", (tr["mandat_id"],)) \
        if tr["mandat_id"] else None
    charge = (mandat["charge_commission"] if mandat else "vendeur")
    client_id = ctx.entier("tiers_id") or (
        tr["acquereur_id"] if charge == "acquereur" else tr["vendeur_id"]
    )
    if not client_id:
        raise ErreurApplicative(
            "Indiquez à qui la commission est facturée (vendeur ou acquéreur)."
        )
    bien = db.ligne("SELECT * FROM biens WHERE id = ?", (tr["bien_id"],)) \
        if tr["bien_id"] else None
    date = ctx.date("date", tr["date_acte"] or util.aujourdhui())
    ex = compta.exercice_pour_date(tr["societe_id"], date)

    designation = (
        f"Commission sur vente immobilière — {bien['designation'] if bien else 'bien'}"
        f" — prix de vente {util.formate_montant(tr['prix_vente'])}"
    )

    with db.transaction():
        numero = db.numero_suivant(tr["societe_id"], "facture_vente", int(date[:4]))
        tva = util.applique_taux(tr["commission_ht"], tr["taux_tva"])
        facture_id = db.insere("factures", {
            "societe_id": tr["societe_id"], "exercice_id": ex["id"], "sens": "vente",
            "numero": numero, "date": date, "tiers_id": client_id,
            "objet": f"Honoraires d'agence — transaction n° {tr['numero']}",
            "reference": tr["numero"], "origine": "commission_vente",
            "bien_id": tr["bien_id"],
            "montant_ht": tr["commission_ht"], "montant_tva": tva,
            "montant_ttc": tr["commission_ht"] + tva, "timbre": 0,
            "net_a_payer": tr["commission_ht"] + tva, "montant_regle": 0,
            "statut": "brouillon", "cree_le": util.maintenant(),
            "cree_par": ctx.nom_utilisateur,
        })
        db.insere("facture_lignes", {
            "facture_id": facture_id, "ordre": 0, "designation": designation,
            "quantite": 1000, "prix_unitaire": tr["commission_ht"], "remise_taux": 0,
            "taux_tva": tr["taux_tva"], "montant_ht": tr["commission_ht"],
            "montant_tva": tva, "compte": COMPTE_COMMISSION_VENTE,
        })
        facturation._valide(facture_id, ctx.nom_utilisateur)
        db.modifie("transactions", identifiant,
                   {"facture_id": facture_id, "statut": "signee"})
        if tr["bien_id"]:
            db.modifie("biens", tr["bien_id"], {"statut": "vendu"})
        if tr["mandat_id"]:
            db.modifie("mandats", tr["mandat_id"], {"statut": "realise"})
        db.trace("facturation", "transaction", identifiant, numero, ctx.nom_utilisateur)

    return {"facture_id": facture_id, "numero": numero}


# ===========================================================================
# BAUX
# ===========================================================================

@route("GET", "/api/baux")
def api_baux(ctx):
    societe_id = ctx.arg_int("societe")
    conditions = ["b.societe_id = ?"]
    params: list = [societe_id]
    if ctx.arg("statut"):
        conditions.append("b.statut = ?")
        params.append(ctx.arg("statut"))
    if ctx.arg("proprietaire"):
        conditions.append("b.proprietaire_id = ?")
        params.append(ctx.arg_int("proprietaire"))
    return {"baux": db.lignes(
        "SELECT b.*, bi.designation AS bien, bi.reference AS bien_reference, "
        "       p.raison_sociale AS proprietaire, l.raison_sociale AS locataire, "
        "       l.telephone AS locataire_tel "
        "FROM baux b LEFT JOIN biens bi ON bi.id = b.bien_id "
        "LEFT JOIN tiers p ON p.id = b.proprietaire_id "
        "LEFT JOIN tiers l ON l.id = b.locataire_id "
        f"WHERE {' AND '.join(conditions)} ORDER BY b.date_debut DESC LIMIT 500", params
    )}


@route("GET", "/api/baux/<id>")
def api_bail(ctx):
    identifiant = int(ctx.params["id"])
    b = db.ligne(
        "SELECT b.*, bi.designation AS bien, bi.adresse AS bien_adresse, "
        "       p.raison_sociale AS proprietaire, l.raison_sociale AS locataire "
        "FROM baux b LEFT JOIN biens bi ON bi.id = b.bien_id "
        "LEFT JOIN tiers p ON p.id = b.proprietaire_id "
        "LEFT JOIN tiers l ON l.id = b.locataire_id WHERE b.id = ?", (identifiant,)
    )
    if not b:
        raise ErreurApplicative("Bail introuvable.", 404)
    b["quittances"] = db.lignes(
        "SELECT * FROM quittances WHERE bail_id = ? ORDER BY periode DESC", (identifiant,)
    )
    b["total_encaisse"] = sum(q["montant_encaisse"] for q in b["quittances"])
    b["total_reverse"] = sum(q["montant_reverse"] for q in b["quittances"])
    b["impayes"] = sum(q["total"] - q["montant_encaisse"] for q in b["quittances"]
                       if q["statut"] in ("a_encaisser", "impayee"))
    return b


@route("POST", "/api/baux")
def api_cree_bail(ctx):
    ctx.interdit_lecture_seule()
    societe_id = ctx.entier("societe_id")
    bien_id = ctx.entier("bien_id")
    if not bien_id:
        raise ErreurApplicative("Sélectionnez le bien loué.")
    loyer = ctx.montant("loyer_mensuel")
    if loyer <= 0:
        raise ErreurApplicative("Indiquez le montant du loyer mensuel.")
    date_debut = ctx.date("date_debut", util.aujourdhui())
    duree = ctx.entier("duree_mois", 12) or 12
    date_fin = ctx.date("date_fin") or util.ajoute_mois(date_debut, duree)

    with db.transaction():
        numero = util.nettoie(ctx.champ("numero")) or db.numero_suivant(societe_id, "bail")
        bien = db.ligne("SELECT * FROM biens WHERE id = ?", (bien_id,))
        identifiant = db.insere("baux", {
            "societe_id": societe_id, "numero": numero, "bien_id": bien_id,
            "proprietaire_id": ctx.entier("proprietaire_id")
                               or (bien["proprietaire_id"] if bien else None),
            "locataire_id": ctx.entier("locataire_id"),
            "usage": ctx.champ("usage", "habitation"),
            "date_debut": date_debut, "date_fin": date_fin, "duree_mois": duree,
            "loyer_mensuel": loyer,
            "charges_mensuelles": ctx.montant("charges_mensuelles"),
            "caution": ctx.montant("caution"),
            "jour_echeance": ctx.entier("jour_echeance", 5) or 5,
            "periodicite_mois": ctx.entier("periodicite_mois", 1) or 1,
            "taux_gestion": ctx.taux("taux_gestion"),
            "honoraires_entremise": ctx.montant("honoraires_entremise"),
            "enregistre": ctx.booleen("enregistre"),
            "date_enregistrement": ctx.date("date_enregistrement"),
            "encaisse_par_agence": ctx.booleen("encaisse_par_agence", True),
            "statut": "actif",
            "notes": util.nettoie(ctx.champ("notes")),
            "cree_le": util.maintenant(),
        })
        if bien:
            db.modifie("biens", bien_id, {"statut": "loue"})
        db.trace("creation", "bail", identifiant, numero, ctx.nom_utilisateur)
    return {"id": identifiant, "numero": numero}


@route("PUT", "/api/baux/<id>")
def api_modifie_bail(ctx):
    ctx.interdit_lecture_seule()
    with db.transaction():
        db.modifie("baux", int(ctx.params["id"]), {
            "locataire_id": ctx.entier("locataire_id"),
            "proprietaire_id": ctx.entier("proprietaire_id"),
            "usage": ctx.champ("usage", "habitation"),
            "date_debut": ctx.date("date_debut"),
            "date_fin": ctx.date("date_fin"),
            "duree_mois": ctx.entier("duree_mois", 12),
            "loyer_mensuel": ctx.montant("loyer_mensuel"),
            "charges_mensuelles": ctx.montant("charges_mensuelles"),
            "caution": ctx.montant("caution"),
            "jour_echeance": ctx.entier("jour_echeance", 5),
            "taux_gestion": ctx.taux("taux_gestion"),
            "honoraires_entremise": ctx.montant("honoraires_entremise"),
            "enregistre": ctx.booleen("enregistre"),
            "date_enregistrement": ctx.date("date_enregistrement"),
            "encaisse_par_agence": ctx.booleen("encaisse_par_agence", True),
            "statut": ctx.champ("statut", "actif"),
            "notes": util.nettoie(ctx.champ("notes")),
        })
    return {"ok": True}


@route("POST", "/api/baux/<id>/caution")
def api_encaisse_caution(ctx):
    """Encaissement du dépôt de garantie : dette envers le locataire (4672)."""
    ctx.interdit_lecture_seule()
    identifiant = int(ctx.params["id"])
    bail = db.ligne("SELECT * FROM baux WHERE id = ?", (identifiant,))
    if not bail:
        raise ErreurApplicative("Bail introuvable.", 404)
    montant = ctx.montant("montant") or bail["caution"]
    if montant <= 0:
        raise ErreurApplicative("Montant de caution invalide.")
    tresorerie = _tresorerie(ctx)
    date = ctx.date("date", util.aujourdhui())
    libelle = f"Dépôt de garantie — bail n° {bail['numero']}"
    with db.transaction():
        ecriture_id = compta.enregistre_ecriture(
            bail["societe_id"], _journal(tresorerie), date, libelle, [
                {"compte": tresorerie["compte"], "debit": montant, "credit": 0,
                 "libelle": libelle},
                {"compte": COMPTE_DEPOT_GARANTIE, "debit": 0, "credit": montant,
                 "tiers_id": bail["locataire_id"], "libelle": libelle,
                 "bien_id": bail["bien_id"]},
            ],
            module="agence", source_type="caution", source_id=identifiant,
            utilisateur=ctx.nom_utilisateur,
        )
    return {"ecriture_id": ecriture_id}


# ===========================================================================
# QUITTANCES DE LOYER & GESTION LOCATIVE
# ===========================================================================

@route("GET", "/api/quittances")
def api_quittances(ctx):
    societe_id = ctx.arg_int("societe")
    conditions = ["q.societe_id = ?"]
    params: list = [societe_id]
    if ctx.arg("periode"):
        conditions.append("q.periode = ?")
        params.append(ctx.arg("periode"))
    if ctx.arg("statut"):
        if ctx.arg("statut") == "impayee":
            conditions.append("q.statut IN ('a_encaisser','impayee') AND q.date_echeance < ?")
            params.append(util.aujourdhui())
        else:
            conditions.append("q.statut = ?")
            params.append(ctx.arg("statut"))
    if ctx.arg("bail"):
        conditions.append("q.bail_id = ?")
        params.append(ctx.arg_int("bail"))
    if ctx.arg("proprietaire"):
        conditions.append("b.proprietaire_id = ?")
        params.append(ctx.arg_int("proprietaire"))
    quittances = db.lignes(
        "SELECT q.*, b.numero AS bail_numero, bi.designation AS bien, "
        "       p.raison_sociale AS proprietaire, l.raison_sociale AS locataire, "
        "       l.telephone AS locataire_tel "
        "FROM quittances q JOIN baux b ON b.id = q.bail_id "
        "LEFT JOIN biens bi ON bi.id = b.bien_id "
        "LEFT JOIN tiers p ON p.id = b.proprietaire_id "
        "LEFT JOIN tiers l ON l.id = b.locataire_id "
        f"WHERE {' AND '.join(conditions)} ORDER BY q.periode DESC, q.date_echeance LIMIT 800",
        params,
    )
    return {
        "quittances": quittances,
        "totaux": {
            "attendu": sum(q["total"] for q in quittances),
            "encaisse": sum(q["montant_encaisse"] for q in quittances),
            "reverse": sum(q["montant_reverse"] for q in quittances),
            "honoraires": sum(q["honoraires_gestion_ht"] for q in quittances),
            "impaye": sum(q["total"] - q["montant_encaisse"] for q in quittances
                          if q["statut"] in ("a_encaisser", "impayee")),
        },
    }


@route("POST", "/api/quittances/generer")
def api_genere_quittances(ctx):
    """Génère les quittances du mois pour tous les baux actifs concernés."""
    ctx.interdit_lecture_seule()
    societe_id = ctx.entier("societe_id")
    periode = ctx.champ("periode") or util.periode_de(util.aujourdhui())
    if len(periode) != 7:
        raise ErreurApplicative("Période attendue au format AAAA-MM.")
    fin_periode = util.fin_de_mois(periode)
    debut_periode = periode + "-01"

    baux = db.lignes(
        "SELECT * FROM baux WHERE societe_id = ? AND statut = 'actif' "
        "AND date_debut <= ? AND (date_fin IS NULL OR date_fin >= ?)",
        (societe_id, fin_periode, debut_periode),
    )
    creees, ignorees = 0, 0
    with db.transaction():
        for bail in baux:
            # Respect de la périodicité (bail trimestriel, semestriel…)
            if bail["periodicite_mois"] > 1:
                mois_ecoules = ((int(periode[:4]) - int(bail["date_debut"][:4])) * 12
                                + int(periode[5:7]) - int(bail["date_debut"][5:7]))
                if mois_ecoules % bail["periodicite_mois"] != 0:
                    continue
            if db.ligne("SELECT id FROM quittances WHERE societe_id = ? AND bail_id = ? "
                        "AND periode = ?", (societe_id, bail["id"], periode)):
                ignorees += 1
                continue

            multiplicateur = bail["periodicite_mois"] or 1
            loyer = bail["loyer_mensuel"] * multiplicateur
            charges = bail["charges_mensuelles"] * multiplicateur
            total = loyer + charges
            honoraires_ht = util.applique_taux(loyer, bail["taux_gestion"])
            tva_honoraires = util.applique_taux(honoraires_ht, 1900)

            numero = db.numero_suivant(societe_id, "quittance", int(periode[:4]))
            db.insere("quittances", {
                "societe_id": societe_id, "bail_id": bail["id"], "numero": numero,
                "periode": periode,
                "date_echeance": util.jour_du_mois(periode, bail["jour_echeance"]),
                "loyer": loyer, "charges": charges, "total": total,
                "honoraires_gestion_ht": honoraires_ht,
                "tva_honoraires": tva_honoraires,
                "net_proprietaire": total - honoraires_ht - tva_honoraires,
                "montant_encaisse": 0, "montant_reverse": 0,
                "statut": "a_encaisser", "cree_le": util.maintenant(),
            })
            creees += 1
        db.trace("generation", "quittances", None,
                 {"periode": periode, "creees": creees}, ctx.nom_utilisateur)
    return {"creees": creees, "ignorees": ignorees, "periode": periode,
            "message": f"{creees} quittance(s) créée(s) pour "
                       f"{util.libelle_periode(periode)}."
                       + (f" {ignorees} existaient déjà." if ignorees else "")}


@route("POST", "/api/quittances/<id>/encaisser")
def api_encaisse_quittance(ctx):
    """Encaissement du loyer + constatation des honoraires de gestion.

    Écriture générée (cas d'un encaissement par l'agence pour le compte du
    propriétaire) :
        Banque/Caisse          D  loyer + charges
            4671 Mandant           C  loyer + charges
        4671 Mandant           D  honoraires TTC
            7063 Honoraires        C  honoraires HT
            4457 TVA collectée     C  TVA sur honoraires
    """
    ctx.interdit_lecture_seule()
    identifiant = int(ctx.params["id"])
    q = db.ligne("SELECT * FROM quittances WHERE id = ?", (identifiant,))
    if not q:
        raise ErreurApplicative("Quittance introuvable.", 404)
    if q["statut"] in ("reversee",):
        raise ErreurApplicative("Cette quittance a déjà été reversée au propriétaire.")

    bail = db.ligne("SELECT * FROM baux WHERE id = ?", (q["bail_id"],))
    montant = ctx.montant("montant") or (q["total"] - q["montant_encaisse"])
    if montant <= 0:
        raise ErreurApplicative("Montant d'encaissement invalide.")
    if q["montant_encaisse"] + montant > q["total"]:
        raise ErreurApplicative(
            f"Montant supérieur au reste dû "
            f"({util.formate_montant(q['total'] - q['montant_encaisse'])})."
        )
    tresorerie = _tresorerie(ctx)
    date = ctx.date("date", util.aujourdhui())
    libelle = (f"Loyer {util.libelle_periode(q['periode'])} — quittance n° {q['numero']}")

    if not bail["encaisse_par_agence"]:
        raise ErreurApplicative(
            "Ce bail est marqué « encaissé directement par le propriétaire » : "
            "l'agence ne doit pas enregistrer l'encaissement du loyer. "
            "Facturez uniquement vos honoraires."
        )

    with db.transaction():
        lignes = [
            {"compte": tresorerie["compte"], "debit": montant, "credit": 0,
             "libelle": libelle},
            {"compte": COMPTE_MANDANT, "debit": 0, "credit": montant,
             "tiers_id": bail["proprietaire_id"], "libelle": libelle,
             "bien_id": bail["bien_id"]},
        ]
        # Les honoraires sont constatés une seule fois, au premier encaissement
        solde_apres = q["montant_encaisse"] + montant
        honoraires_a_constater = (q["honoraires_gestion_ht"] and not q["montant_encaisse"])
        if honoraires_a_constater:
            honoraires_ttc = q["honoraires_gestion_ht"] + q["tva_honoraires"]
            lignes += [
                {"compte": COMPTE_MANDANT, "debit": honoraires_ttc, "credit": 0,
                 "tiers_id": bail["proprietaire_id"],
                 "libelle": f"Honoraires de gestion — {util.libelle_periode(q['periode'])}",
                 "bien_id": bail["bien_id"]},
                {"compte": COMPTE_HONORAIRES_GESTION, "debit": 0,
                 "credit": q["honoraires_gestion_ht"],
                 "libelle": f"Honoraires de gestion locative — quittance {q['numero']}",
                 "bien_id": bail["bien_id"]},
            ]
            if q["tva_honoraires"]:
                lignes.append({
                    "compte": COMPTE_TVA_COLLECTEE, "debit": 0,
                    "credit": q["tva_honoraires"],
                    "libelle": f"TVA sur honoraires de gestion — {q['numero']}",
                })

        ecriture_id = compta.enregistre_ecriture(
            q["societe_id"], _journal(tresorerie), date, libelle, lignes,
            piece=q["numero"], module="agence", source_type="quittance",
            source_id=identifiant, utilisateur=ctx.nom_utilisateur,
        )
        db.modifie("quittances", identifiant, {
            "montant_encaisse": solde_apres,
            "date_encaissement": date,
            "statut": "encaissee" if solde_apres >= q["total"] else "a_encaisser",
            "ecriture_id": ecriture_id,
        })
        db.trace("encaissement", "quittance", identifiant,
                 util.formate_montant(montant), ctx.nom_utilisateur)
    return {"ecriture_id": ecriture_id}


@route("POST", "/api/quittances/reverser")
def api_reverse_proprietaire(ctx):
    """Reversement du net au propriétaire, pour une ou plusieurs quittances."""
    ctx.interdit_lecture_seule()
    identifiants = ctx.champ("quittances") or []
    if not identifiants:
        raise ErreurApplicative("Sélectionnez au moins une quittance à reverser.")
    marques = ",".join("?" for _ in identifiants)
    quittances = db.lignes(
        f"SELECT q.*, b.proprietaire_id, b.bien_id FROM quittances q "
        f"JOIN baux b ON b.id = q.bail_id WHERE q.id IN ({marques})", identifiants
    )
    if not quittances:
        raise ErreurApplicative("Quittances introuvables.")
    proprietaires = {q["proprietaire_id"] for q in quittances}
    if len(proprietaires) > 1:
        raise ErreurApplicative(
            "Les quittances sélectionnées concernent plusieurs propriétaires : "
            "faites un reversement par propriétaire."
        )
    proprietaire_id = quittances[0]["proprietaire_id"]

    total = 0
    for q in quittances:
        if q["montant_encaisse"] <= 0:
            raise ErreurApplicative(
                f"La quittance {q['numero']} n'a pas été encaissée : "
                "impossible de la reverser."
            )
        reste = q["net_proprietaire"] - q["montant_reverse"]
        # Reversement au prorata de ce qui a effectivement été encaissé
        if q["montant_encaisse"] < q["total"]:
            part = util.part_proportionnelle(q["net_proprietaire"],
                                             q["montant_encaisse"], q["total"])
            reste = part - q["montant_reverse"]
        if reste > 0:
            total += reste
            q["_a_reverser"] = reste
        else:
            q["_a_reverser"] = 0

    if total <= 0:
        raise ErreurApplicative("Rien à reverser sur cette sélection.")

    tresorerie = _tresorerie(ctx)
    date = ctx.date("date", util.aujourdhui())
    societe_id = quittances[0]["societe_id"]
    periodes = sorted({q["periode"] for q in quittances})
    libelle = ctx.champ("libelle") or (
        "Reversement propriétaire — "
        + (util.libelle_periode(periodes[0]) if len(periodes) == 1
           else f"{len(periodes)} périodes")
    )

    with db.transaction():
        ecriture_id = compta.enregistre_ecriture(
            societe_id, _journal(tresorerie), date, libelle, [
                {"compte": COMPTE_MANDANT, "debit": total, "credit": 0,
                 "tiers_id": proprietaire_id, "libelle": libelle},
                {"compte": tresorerie["compte"], "debit": 0, "credit": total,
                 "libelle": libelle},
            ],
            piece=util.nettoie(ctx.champ("reference")), module="agence",
            source_type="reversement", utilisateur=ctx.nom_utilisateur,
        )
        for q in quittances:
            if q["_a_reverser"] > 0:
                db.modifie("quittances", q["id"], {
                    "montant_reverse": q["montant_reverse"] + q["_a_reverser"],
                    "date_reversement": date,
                    "statut": "reversee",
                })
        db.trace("reversement", "quittances", None,
                 {"proprietaire": proprietaire_id, "montant": total,
                  "quittances": identifiants}, ctx.nom_utilisateur)
    return {"ecriture_id": ecriture_id, "montant": total}


@route("POST", "/api/quittances/<id>/impayee")
def api_marque_impayee(ctx):
    ctx.interdit_lecture_seule()
    with db.transaction():
        db.modifie("quittances", int(ctx.params["id"]), {
            "statut": "impayee", "notes": util.nettoie(ctx.champ("motif")),
        })
    return {"ok": True}


@route("GET", "/api/situation-proprietaires")
def api_situation_proprietaires(ctx):
    """Ce que l'agence doit à chaque propriétaire (solde du compte 4671)."""
    societe_id = ctx.arg_int("societe")
    donnees = db.lignes(
        "SELECT t.id, t.code, t.raison_sociale, t.telephone, t.banque_rib, "
        "  COALESCE(SUM(l.credit - l.debit),0) AS solde "
        "FROM tiers t LEFT JOIN lignes l ON l.tiers_id = t.id AND l.compte LIKE '467%' "
        "LEFT JOIN ecritures e ON e.id = l.ecriture_id "
        "WHERE t.societe_id = ? AND t.type = 'mandant' "
        "GROUP BY t.id ORDER BY t.raison_sociale", (societe_id,)
    )
    for p in donnees:
        p["quittances_a_reverser"] = db.valeur(
            "SELECT COUNT(*) FROM quittances q JOIN baux b ON b.id = q.bail_id "
            "WHERE b.proprietaire_id = ? AND q.montant_encaisse > q.montant_reverse "
            "AND q.statut <> 'reversee'", (p["id"],), 0
        )
    return {"proprietaires": [p for p in donnees
                              if p["solde"] != 0 or p["quittances_a_reverser"]],
            "total_du": sum(p["solde"] for p in donnees if p["solde"] > 0)}


def _tresorerie(ctx) -> dict:
    tresorerie_id = ctx.entier("tresorerie_id")
    tres = db.ligne("SELECT * FROM comptes_tresorerie WHERE id = ?", (tresorerie_id,))
    if not tres:
        raise ErreurApplicative("Sélectionnez le compte de trésorerie (banque ou caisse).")
    return tres


def _journal(tresorerie: dict) -> str:
    return "BQ" if tresorerie["type"] in ("banque", "ccp") else "CA"


# ===========================================================================
# Exports
# ===========================================================================

@route("GET", "/api/export/quittances")
def api_export_quittances(ctx):
    societe_id = ctx.arg_int("societe")
    soc = compta.societe(societe_id)
    donnees = api_quittances(ctx)
    classeur = tableur.Classeur()
    f = classeur.feuille("Loyers")
    f.titre(f"{soc['raison_sociale']} — Suivi des loyers")
    if ctx.arg("periode"):
        f.ajoute(tableur.texte(f"Période : {util.libelle_periode(ctx.arg('periode'))}"))
    f.vide()
    f.entetes("Période", "N° quittance", "Bail", "Bien", "Propriétaire", "Locataire",
              "Échéance", "Loyer", "Charges", "Total", "Honoraires HT", "TVA",
              "Net propriétaire", "Encaissé", "Reversé", "Statut")
    f.largeurs_auto(11, 14, 13, 30, 26, 26, 12, 14, 13, 14, 14, 12, 16, 14, 14, 14)
    for q in donnees["quittances"]:
        f.ajoute(
            tableur.texte(q["periode"]), tableur.texte(q["numero"]),
            tableur.texte(q["bail_numero"]), tableur.texte(q["bien"]),
            tableur.texte(q["proprietaire"]), tableur.texte(q["locataire"]),
            tableur.date_cel(q["date_echeance"]),
            tableur.monnaie(q["loyer"]), tableur.monnaie(q["charges"]),
            tableur.monnaie(q["total"]), tableur.monnaie(q["honoraires_gestion_ht"]),
            tableur.monnaie(q["tva_honoraires"]), tableur.monnaie(q["net_proprietaire"]),
            tableur.monnaie(q["montant_encaisse"]), tableur.monnaie(q["montant_reverse"]),
            tableur.texte(q["statut"]),
        )
    t = donnees["totaux"]
    f.ajoute(tableur.texte("TOTAUX", tableur.GRAS), *[tableur.texte("")] * 8,
             tableur.monnaie(t["attendu"], total=True),
             tableur.monnaie(t["honoraires"], total=True), tableur.texte(""),
             tableur.texte(""), tableur.monnaie(t["encaisse"], total=True),
             tableur.monnaie(t["reverse"], total=True), tableur.texte(""))
    return Reponse(classeur.octets(),
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   f"loyers_{soc['code']}_{ctx.arg('periode') or 'tous'}.xlsx")
