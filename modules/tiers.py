"""Tiers : clients, fournisseurs, propriétaires mandants, salariés, notaires.

Chaque tiers est rattaché à un compte collectif du plan SCF, ce qui permet
de produire une balance auxiliaire et de lettrer les comptes.
"""

from __future__ import annotations

from noyau import base as db
from noyau import util
from noyau import tableur
from noyau.serveur import ErreurApplicative, route, Reponse

COMPTES_PAR_TYPE = {
    "client": "411",
    "fournisseur": "401",
    "mandant": "4671",
    "salarie": "421",
    "notaire": "401",
    "administration": "401",
    "autre": "467",
}

LIBELLES_TYPE = {
    "client": "Client",
    "fournisseur": "Fournisseur",
    "mandant": "Propriétaire mandant",
    "salarie": "Salarié",
    "notaire": "Notaire",
    "administration": "Administration",
    "autre": "Autre tiers",
}


def tiers_ou_erreur(tiers_id: int) -> dict:
    t = db.ligne("SELECT * FROM tiers WHERE id = ?", (tiers_id,))
    if not t:
        raise ErreurApplicative("Tiers introuvable.", 404)
    return t


def compte_du_tiers(t: dict) -> str:
    return t.get("compte_comptable") or COMPTES_PAR_TYPE.get(t["type"], "467")


@route("GET", "/api/tiers")
def api_liste(ctx):
    societe_id = ctx.arg_int("societe")
    conditions = ["societe_id = ?"]
    params: list = [societe_id]
    if ctx.arg("type"):
        types = ctx.arg("type").split(",")
        conditions.append("type IN (" + ",".join("?" for _ in types) + ")")
        params += types
    if ctx.arg("q"):
        conditions.append("(raison_sociale LIKE ? OR code LIKE ? OR telephone LIKE ? "
                          "OR nif LIKE ? OR nom LIKE ?)")
        motif = "%" + ctx.arg("q") + "%"
        params += [motif, motif, motif, motif, motif]
    if ctx.arg("actifs_seuls") == "1":
        conditions.append("actif = 1")
    limite = min(ctx.arg_int("limite", 300) or 300, 2000)
    return {"tiers": db.lignes(
        f"SELECT * FROM tiers WHERE {' AND '.join(conditions)} "
        "ORDER BY raison_sociale LIMIT ?", params + [limite]
    )}


@route("GET", "/api/tiers/<id>")
def api_detail(ctx):
    identifiant = int(ctx.params["id"])
    t = tiers_ou_erreur(identifiant)
    compte = compte_du_tiers(t)

    mouvements = db.lignes(
        "SELECT l.*, e.date, e.numero AS num_ecriture, e.libelle AS libelle_ecriture, "
        "       j.code AS journal "
        "FROM lignes l JOIN ecritures e ON e.id = l.ecriture_id "
        "JOIN journaux j ON j.id = e.journal_id "
        "WHERE l.tiers_id = ? ORDER BY e.date DESC, l.id DESC LIMIT 300",
        (identifiant,),
    )
    total_debit = sum(m["debit"] for m in mouvements)
    total_credit = sum(m["credit"] for m in mouvements)

    t["compte"] = compte
    t["solde"] = total_debit - total_credit
    t["total_debit"] = total_debit
    t["total_credit"] = total_credit
    t["mouvements"] = mouvements
    t["factures"] = db.lignes(
        "SELECT id, numero, date, sens, objet, montant_ttc, montant_regle, statut "
        "FROM factures WHERE tiers_id = ? ORDER BY date DESC LIMIT 100", (identifiant,)
    )
    t["non_lettre"] = db.ligne(
        "SELECT COALESCE(SUM(debit),0) AS debit, COALESCE(SUM(credit),0) AS credit "
        "FROM lignes WHERE tiers_id = ? AND (lettrage IS NULL OR lettrage = '')",
        (identifiant,),
    )
    if t["type"] == "mandant":
        t["biens"] = db.lignes(
            "SELECT * FROM biens WHERE proprietaire_id = ?", (identifiant,))
        t["baux"] = db.lignes(
            "SELECT b.*, bi.designation AS bien FROM baux b "
            "LEFT JOIN biens bi ON bi.id = b.bien_id WHERE b.proprietaire_id = ?",
            (identifiant,))
    if t["type"] == "client":
        t["contrats_vsp"] = db.lignes(
            "SELECT c.*, l.numero AS lot, p.intitule AS programme "
            "FROM contrats_vsp c JOIN lots l ON l.id = c.lot_id "
            "JOIN programmes p ON p.id = c.programme_id WHERE c.acquereur_id = ?",
            (identifiant,))
    return t


@route("POST", "/api/tiers")
def api_cree(ctx):
    ctx.interdit_lecture_seule()
    societe_id = ctx.entier("societe_id")
    type_tiers = ctx.champ("type", "client")
    if type_tiers not in COMPTES_PAR_TYPE:
        raise ErreurApplicative("Type de tiers invalide.")

    nif = util.nettoie(ctx.champ("nif"))
    valide, message = util.valide_nif(nif)
    if not valide:
        raise ErreurApplicative(message)

    raison = ctx.champ("raison_sociale")
    if not raison:
        nom, prenom = ctx.champ("nom"), ctx.champ("prenom")
        if not nom:
            raise ErreurApplicative(
                "Indiquez la raison sociale (personne morale) ou le nom (personne physique)."
            )
        raison = f"{nom} {prenom or ''}".strip()

    with db.transaction():
        code = util.nettoie(ctx.champ("code")) or db.numero_suivant(
            societe_id, f"tiers_{type_tiers}"
            if f"tiers_{type_tiers}" in db.FORMATS_DEFAUT else "tiers_autre"
        )
        if db.ligne("SELECT id FROM tiers WHERE societe_id = ? AND code = ?",
                    (societe_id, code)):
            raise ErreurApplicative(f"Le code tiers « {code} » existe déjà.")
        identifiant = db.insere("tiers", {
            "societe_id": societe_id,
            "code": code,
            "type": type_tiers,
            "raison_sociale": raison,
            "forme": ctx.champ("forme", "physique"),
            "civilite": util.nettoie(ctx.champ("civilite")),
            "nom": util.nettoie(ctx.champ("nom")),
            "prenom": util.nettoie(ctx.champ("prenom")),
            "date_naissance": ctx.date("date_naissance"),
            "lieu_naissance": util.nettoie(ctx.champ("lieu_naissance")),
            "piece_identite": util.nettoie(ctx.champ("piece_identite")),
            "adresse": util.nettoie(ctx.champ("adresse")),
            "commune": util.nettoie(ctx.champ("commune")),
            "wilaya": util.nettoie(ctx.champ("wilaya")),
            "telephone": util.nettoie(ctx.champ("telephone")),
            "telephone2": util.nettoie(ctx.champ("telephone2")),
            "email": util.nettoie(ctx.champ("email")),
            "nif": nif,
            "nis": util.nettoie(ctx.champ("nis")),
            "rc": util.nettoie(ctx.champ("rc")),
            "article_imposition": util.nettoie(ctx.champ("article_imposition")),
            "banque_rib": util.nettoie(ctx.champ("banque_rib")),
            "compte_comptable": util.nettoie(ctx.champ("compte_comptable"))
                                 or COMPTES_PAR_TYPE[type_tiers],
            "plafond_credit_cts": ctx.montant("plafond_credit"),
            "notes": util.nettoie(ctx.champ("notes")),
            "actif": 1,
            "cree_le": util.maintenant(),
        })
        db.trace("creation", "tiers", identifiant, raison, ctx.nom_utilisateur)
    return {"id": identifiant, "code": code}


@route("PUT", "/api/tiers/<id>")
def api_modifie(ctx):
    ctx.interdit_lecture_seule()
    identifiant = int(ctx.params["id"])
    tiers_ou_erreur(identifiant)
    nif = util.nettoie(ctx.champ("nif"))
    valide, message = util.valide_nif(nif)
    if not valide:
        raise ErreurApplicative(message)
    with db.transaction():
        db.modifie("tiers", identifiant, {
            "type": ctx.champ("type", "client"),
            "raison_sociale": ctx.champ_requis("raison_sociale"),
            "forme": ctx.champ("forme", "physique"),
            "civilite": util.nettoie(ctx.champ("civilite")),
            "nom": util.nettoie(ctx.champ("nom")),
            "prenom": util.nettoie(ctx.champ("prenom")),
            "date_naissance": ctx.date("date_naissance"),
            "lieu_naissance": util.nettoie(ctx.champ("lieu_naissance")),
            "piece_identite": util.nettoie(ctx.champ("piece_identite")),
            "adresse": util.nettoie(ctx.champ("adresse")),
            "commune": util.nettoie(ctx.champ("commune")),
            "wilaya": util.nettoie(ctx.champ("wilaya")),
            "telephone": util.nettoie(ctx.champ("telephone")),
            "telephone2": util.nettoie(ctx.champ("telephone2")),
            "email": util.nettoie(ctx.champ("email")),
            "nif": nif,
            "nis": util.nettoie(ctx.champ("nis")),
            "rc": util.nettoie(ctx.champ("rc")),
            "article_imposition": util.nettoie(ctx.champ("article_imposition")),
            "banque_rib": util.nettoie(ctx.champ("banque_rib")),
            "compte_comptable": util.nettoie(ctx.champ("compte_comptable")),
            "plafond_credit_cts": ctx.montant("plafond_credit"),
            "notes": util.nettoie(ctx.champ("notes")),
            "actif": ctx.booleen("actif", True),
        })
        db.trace("modification", "tiers", identifiant, None, ctx.nom_utilisateur)
    return {"ok": True}


@route("DELETE", "/api/tiers/<id>")
def api_supprime(ctx):
    ctx.exige_role("admin", "comptable")
    identifiant = int(ctx.params["id"])
    utilise = db.valeur("SELECT COUNT(*) FROM lignes WHERE tiers_id = ?", (identifiant,), 0)
    if utilise:
        raise ErreurApplicative(
            f"Ce tiers apparaît dans {utilise} ligne(s) comptable(s). "
            "Désactivez-le au lieu de le supprimer."
        )
    with db.transaction():
        db.supprime("tiers", identifiant)
        db.trace("suppression", "tiers", identifiant, None, ctx.nom_utilisateur)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Balance auxiliaire et suivi des créances
# ---------------------------------------------------------------------------

@route("GET", "/api/balance-auxiliaire")
def api_balance_auxiliaire(ctx):
    """Solde par tiers, avec ventilation par ancienneté des créances."""
    societe_id = ctx.arg_int("societe")
    type_tiers = ctx.arg("type", "client")
    au = ctx.arg("au") or util.aujourdhui()

    donnees = db.lignes(
        "SELECT t.id, t.code, t.raison_sociale, t.type, t.telephone, "
        "  COALESCE(SUM(l.debit),0) AS debit, COALESCE(SUM(l.credit),0) AS credit "
        "FROM tiers t "
        "LEFT JOIN lignes l ON l.tiers_id = t.id "
        "LEFT JOIN ecritures e ON e.id = l.ecriture_id AND e.date <= ? "
        "WHERE t.societe_id = ? AND t.type = ? "
        "GROUP BY t.id ORDER BY t.raison_sociale",
        (au, societe_id, type_tiers),
    )
    resultat = []
    for t in donnees:
        solde = t["debit"] - t["credit"]
        if solde == 0 and ctx.arg("tous") != "1":
            continue
        t["solde"] = solde
        resultat.append(t)

    # Balance âgée sur les lignes non lettrées
    tranches = db.lignes(
        "SELECT l.tiers_id, "
        "  SUM(CASE WHEN julianday(?) - julianday(COALESCE(l.echeance, e.date)) <= 30 "
        "      THEN l.debit - l.credit ELSE 0 END) AS t0_30, "
        "  SUM(CASE WHEN julianday(?) - julianday(COALESCE(l.echeance, e.date)) > 30 "
        "      AND julianday(?) - julianday(COALESCE(l.echeance, e.date)) <= 60 "
        "      THEN l.debit - l.credit ELSE 0 END) AS t31_60, "
        "  SUM(CASE WHEN julianday(?) - julianday(COALESCE(l.echeance, e.date)) > 60 "
        "      AND julianday(?) - julianday(COALESCE(l.echeance, e.date)) <= 90 "
        "      THEN l.debit - l.credit ELSE 0 END) AS t61_90, "
        "  SUM(CASE WHEN julianday(?) - julianday(COALESCE(l.echeance, e.date)) > 90 "
        "      THEN l.debit - l.credit ELSE 0 END) AS t90_plus "
        "FROM lignes l JOIN ecritures e ON e.id = l.ecriture_id "
        "WHERE e.societe_id = ? AND e.date <= ? AND (l.lettrage IS NULL OR l.lettrage = '') "
        "AND l.tiers_id IS NOT NULL GROUP BY l.tiers_id",
        (au, au, au, au, au, au, societe_id, au),
    )
    par_tiers = {t["tiers_id"]: t for t in tranches}
    for t in resultat:
        age = par_tiers.get(t["id"], {})
        t["age"] = {
            "t0_30": int(age.get("t0_30") or 0),
            "t31_60": int(age.get("t31_60") or 0),
            "t61_90": int(age.get("t61_90") or 0),
            "t90_plus": int(age.get("t90_plus") or 0),
        }
    return {
        "lignes": resultat,
        "total": sum(t["solde"] for t in resultat),
        "total_age": {
            cle: sum(t["age"][cle] for t in resultat)
            for cle in ("t0_30", "t31_60", "t61_90", "t90_plus")
        },
    }


@route("GET", "/api/export/balance-auxiliaire")
def api_export_balance_auxiliaire(ctx):
    from modules import comptabilite as compta
    societe_id = ctx.arg_int("societe")
    soc = compta.societe(societe_id)
    type_tiers = ctx.arg("type", "client")
    donnees = api_balance_auxiliaire(ctx)

    classeur = tableur.Classeur()
    f = classeur.feuille("Balance auxiliaire")
    f.titre(f"{soc['raison_sociale']} — Balance auxiliaire "
            f"{LIBELLES_TYPE.get(type_tiers, type_tiers)}s")
    f.ajoute(tableur.texte(f"Arrêtée au {util.date_fr(ctx.arg('au') or util.aujourdhui())}"))
    f.vide()
    f.entetes("Code", "Tiers", "Téléphone", "Débit", "Crédit", "Solde",
              "0-30 j", "31-60 j", "61-90 j", "+ 90 j")
    f.largeurs_auto(10, 40, 16, 15, 15, 15, 14, 14, 14, 14)
    for t in donnees["lignes"]:
        f.ajoute(
            tableur.texte(t["code"]), tableur.texte(t["raison_sociale"]),
            tableur.texte(t["telephone"]), tableur.monnaie(t["debit"]),
            tableur.monnaie(t["credit"]), tableur.monnaie(t["solde"]),
            tableur.monnaie(t["age"]["t0_30"]), tableur.monnaie(t["age"]["t31_60"]),
            tableur.monnaie(t["age"]["t61_90"]), tableur.monnaie(t["age"]["t90_plus"]),
        )
    f.ajoute(
        tableur.texte("TOTAL", tableur.GRAS), tableur.texte(""), tableur.texte(""),
        tableur.texte(""), tableur.texte(""),
        tableur.monnaie(donnees["total"], total=True),
        *[tableur.monnaie(donnees["total_age"][c], total=True)
          for c in ("t0_30", "t31_60", "t61_90", "t90_plus")],
    )
    return Reponse(classeur.octets(),
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   f"balance_auxiliaire_{type_tiers}_{soc['code']}.xlsx")


@route("GET", "/api/relances")
def api_relances(ctx):
    """Créances échues non lettrées, pour relancer les clients."""
    societe_id = ctx.arg_int("societe")
    aujourdhui = util.aujourdhui()
    jours = ctx.arg_int("jours", 0) or 0
    return {"lignes": db.lignes(
        "SELECT t.id AS tiers_id, t.code, t.raison_sociale, t.telephone, t.email, "
        "  e.date, e.numero AS num_ecriture, e.libelle, l.echeance, "
        "  l.debit - l.credit AS montant, "
        "  CAST(julianday(?) - julianday(COALESCE(l.echeance, e.date)) AS INTEGER) AS retard "
        "FROM lignes l JOIN ecritures e ON e.id = l.ecriture_id "
        "JOIN tiers t ON t.id = l.tiers_id "
        "WHERE e.societe_id = ? AND l.compte LIKE '41%' "
        "AND (l.lettrage IS NULL OR l.lettrage = '') AND l.debit > l.credit "
        "AND julianday(?) - julianday(COALESCE(l.echeance, e.date)) >= ? "
        "ORDER BY retard DESC",
        (aujourdhui, societe_id, aujourdhui, jours),
    )}
