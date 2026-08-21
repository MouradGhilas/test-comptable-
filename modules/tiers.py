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


#: Ce que chaque niveau dit, et à partir de quand il se justifie d'ordinaire.
#: Ce ne sont que des repères : c'est le comptable qui décide.
NIVEAUX_RELANCE = {
    1: ("Rappel", "Un simple oubli est l'explication la plus fréquente.", 15),
    2: ("Relance", "La créance est échue depuis un moment et un premier "
                   "rappel est resté sans effet.", 45),
    3: ("Mise en demeure", "Dernier courrier avant recouvrement. Il fait "
                           "courir les intérêts de retard et sert de preuve.", 90),
}


def creances_echues(societe_id: int, jours: int = 0, perimetre=None,
                    tiers_id: int | None = None) -> list[dict]:
    """Les pièces client échues et non lettrées, ligne à ligne."""
    from modules import comptabilite as compta
    clause, params = compta.clause_perimetre(perimetre)
    aujourdhui = util.aujourdhui()
    conditions = ""
    if tiers_id:
        conditions = " AND t.id = ?"
    return db.lignes(
        "SELECT t.id AS tiers_id, t.code, t.raison_sociale, t.telephone, "
        "  t.email, t.adresse, t.commune, t.wilaya, t.nif, "
        "  e.id AS ecriture_id, e.date, e.numero AS num_ecriture, e.piece, "
        "  e.libelle, l.echeance, l.compte, "
        "  l.debit - l.credit AS montant, "
        "  CAST(julianday(?) - julianday(COALESCE(l.echeance, e.date)) "
        "       AS INTEGER) AS retard "
        "FROM lignes l JOIN ecritures e ON e.id = l.ecriture_id "
        "JOIN tiers t ON t.id = l.tiers_id "
        f"WHERE e.societe_id = ? AND substr(l.compte,1,3) = '411' "
        f"AND (l.lettrage IS NULL OR l.lettrage = '') AND l.debit > l.credit "
        f"AND julianday(?) - julianday(COALESCE(l.echeance, e.date)) >= ?"
        f"{clause}{conditions} "
        "ORDER BY retard DESC",
        [aujourdhui, societe_id, aujourdhui, jours, *params]
        + ([tiers_id] if tiers_id else []))


def relances_par_client(societe_id: int, jours: int = 0, perimetre=None) -> dict:
    """Ce que chaque client doit, depuis quand, et quand il a été relancé.

    La balance auxiliaire donne un solde ; elle ne dit pas depuis combien de
    temps il traîne, ni si on a déjà écrit. C'est pourtant ce qui décide
    d'un coup de téléphone ou d'une mise en demeure.
    """
    lignes = creances_echues(societe_id, jours, perimetre)
    clients: dict = {}
    for l in lignes:
        c = clients.setdefault(l["tiers_id"], {
            "tiers_id": l["tiers_id"], "code": l["code"],
            "raison_sociale": l["raison_sociale"], "telephone": l["telephone"],
            "email": l["email"], "pieces": [], "total": 0, "retard_max": 0,
        })
        c["pieces"].append({
            "ecriture_id": l["ecriture_id"], "date": l["date"],
            "numero": l["piece"] or l["num_ecriture"], "libelle": l["libelle"],
            "echeance": l["echeance"], "montant": l["montant"],
            "retard": l["retard"],
        })
        c["total"] += l["montant"]
        c["retard_max"] = max(c["retard_max"], l["retard"])

    # La dernière relance envoyée à chacun : relancer deux fois en huit jours
    # dessert autant qu'oublier six mois.
    derniere = {r["tiers_id"]: r for r in db.lignes(
        "SELECT tiers_id, MAX(date) AS date, niveau, moyen FROM relances "
        "WHERE societe_id = ? GROUP BY tiers_id", (societe_id,))}
    for c in clients.values():
        d = derniere.get(c["tiers_id"])
        c["derniere_relance"] = d or None
        c["jours_depuis_relance"] = (
            util.jours_ecart(d["date"], util.aujourdhui()) if d else None)
        # Le niveau que la situation appelle, à défaut de celui qu'on choisira.
        c["niveau_suggere"] = (
            3 if c["retard_max"] >= NIVEAUX_RELANCE[3][2]
            else 2 if c["retard_max"] >= NIVEAUX_RELANCE[2][2] else 1)
        if d and d["niveau"] >= c["niveau_suggere"]:
            c["niveau_suggere"] = min(3, d["niveau"] + 1)

    ordonnes = sorted(clients.values(), key=lambda c: -c["total"])
    return {
        "clients": ordonnes,
        "jours": jours,
        "total": sum(c["total"] for c in ordonnes),
        "nb_pieces": sum(len(c["pieces"]) for c in ordonnes),
        "niveaux": {n: {"libelle": v[0], "quand": v[1], "seuil": v[2]}
                    for n, v in NIVEAUX_RELANCE.items()},
    }


@route("GET", "/api/relances")
def api_relances(ctx):
    """Créances échues non lettrées, groupées par client."""
    return relances_par_client(ctx.arg_int("societe"),
                               ctx.arg_int("jours", 0) or 0,
                               ctx.perimetre())


@route("POST", "/api/relances")
def api_note_relance(ctx):
    """Consigne une relance envoyée. N'écrit aucune écriture : une relance
    ne crée pas de dette, elle constate celle qui existe."""
    ctx.interdit_lecture_seule()
    societe_id = ctx.entier("societe_id")
    tiers_id = ctx.entier("tiers_id")
    if not tiers_id:
        raise ErreurApplicative("Client manquant.")
    niveau = max(1, min(3, ctx.entier("niveau", 1) or 1))
    pieces = creances_echues(societe_id, 0, ctx.champ("perimetre"), tiers_id)
    with db.transaction():
        identifiant = db.insere("relances", {
            "societe_id": societe_id, "tiers_id": tiers_id,
            "date": ctx.date("date", util.aujourdhui()),
            "niveau": niveau,
            "montant": sum(p["montant"] for p in pieces),
            "nb_pieces": len(pieces),
            "moyen": util.nettoie(ctx.champ("moyen")) or "courrier",
            "note": util.nettoie(ctx.champ("note")),
            "cree_le": util.maintenant(),
            "cree_par": ctx.nom_utilisateur,
        })
        db.trace("relance", "tiers", tiers_id,
                 {"niveau": niveau, "pieces": len(pieces)}, ctx.nom_utilisateur)
    return {"id": identifiant, "niveau": niveau, "nb_pieces": len(pieces)}


@route("GET", "/api/relances/historique")
def api_historique_relances(ctx):
    return {"relances": db.lignes(
        "SELECT r.*, t.raison_sociale FROM relances r "
        "JOIN tiers t ON t.id = r.tiers_id "
        "WHERE r.societe_id = ? ORDER BY r.date DESC, r.id DESC LIMIT 200",
        (ctx.arg_int("societe"),))}


# ---------------------------------------------------------------------------
# Relevé de compte d'un tiers
# ---------------------------------------------------------------------------
#
# La balance auxiliaire dit combien un client doit ; elle ne dit pas pourquoi.
# Pour relancer un client, ou pour justifier un solde à un fournisseur, il faut
# le détail : chaque mouvement, dans l'ordre, avec le solde qui court. C'est le
# document qu'on envoie, et celui qu'on oppose quand le tiers conteste.


def releve_tiers(societe_id: int, tiers_id: int, du: str, au: str,
                 perimetre=None, non_lettrees: bool = False) -> dict:
    """Détail des mouvements d'un tiers, avec solde d'ouverture et progressif."""
    t = db.ligne("SELECT * FROM tiers WHERE id = ? AND societe_id = ?",
                 (tiers_id, societe_id))
    if not t:
        raise ErreurApplicative("Tiers introuvable.", 404)

    from modules import comptabilite as compta
    clause, params = compta.clause_perimetre(perimetre)

    # Ce que le tiers devait déjà avant la période : sans lui, le relevé ne
    # justifie pas son solde final.
    anterieur = db.valeur(
        "SELECT COALESCE(SUM(l.debit - l.credit),0) FROM lignes l "
        "JOIN ecritures e ON e.id = l.ecriture_id "
        f"WHERE l.tiers_id = ? AND e.societe_id = ? AND e.date < ?{clause}",
        [tiers_id, societe_id, du, *params], 0)

    conditions = ""
    if non_lettrees:
        conditions = " AND (l.lettrage IS NULL OR l.lettrage = '')"
    mouvements = db.lignes(
        "SELECT l.id, l.compte, l.libelle, l.debit, l.credit, l.lettrage, "
        "       l.echeance, e.id AS ecriture_id, e.date, e.numero, e.piece, "
        "       e.libelle AS libelle_ecriture, e.perimetre, j.code AS journal, "
        "       c.intitule AS compte_intitule "
        "FROM lignes l JOIN ecritures e ON e.id = l.ecriture_id "
        "JOIN journaux j ON j.id = e.journal_id "
        "LEFT JOIN comptes c ON c.numero = l.compte "
        "     AND (c.societe_id = e.societe_id OR c.societe_id IS NULL) "
        f"WHERE l.tiers_id = ? AND e.societe_id = ? AND e.date >= ? AND e.date <= ?"
        f"{clause}{conditions} "
        "ORDER BY e.date, e.id, l.ordre",
        [tiers_id, societe_id, du, au, *params])

    solde = anterieur
    for m in mouvements:
        solde += m["debit"] - m["credit"]
        m["solde"] = solde
        m["lettree"] = bool(m["lettrage"])

    # Ce qui reste dû, par ancienneté : c'est ce qui décide d'une relance.
    tranches = db.ligne(
        "SELECT "
        "  COALESCE(SUM(CASE WHEN julianday(?) - julianday(COALESCE(l.echeance, e.date)) <= 30 "
        "      THEN l.debit - l.credit ELSE 0 END),0) AS t0_30, "
        "  COALESCE(SUM(CASE WHEN julianday(?) - julianday(COALESCE(l.echeance, e.date)) > 30 "
        "      AND julianday(?) - julianday(COALESCE(l.echeance, e.date)) <= 60 "
        "      THEN l.debit - l.credit ELSE 0 END),0) AS t31_60, "
        "  COALESCE(SUM(CASE WHEN julianday(?) - julianday(COALESCE(l.echeance, e.date)) > 60 "
        "      AND julianday(?) - julianday(COALESCE(l.echeance, e.date)) <= 90 "
        "      THEN l.debit - l.credit ELSE 0 END),0) AS t61_90, "
        "  COALESCE(SUM(CASE WHEN julianday(?) - julianday(COALESCE(l.echeance, e.date)) > 90 "
        "      THEN l.debit - l.credit ELSE 0 END),0) AS t90_plus "
        "FROM lignes l JOIN ecritures e ON e.id = l.ecriture_id "
        f"WHERE l.tiers_id = ? AND e.societe_id = ? AND e.date <= ? "
        f"AND (l.lettrage IS NULL OR l.lettrage = ''){clause}",
        [au, au, au, au, au, au, tiers_id, societe_id, au, *params]) or {}

    return {
        "tiers": t,
        "du": du, "au": au,
        "perimetre": perimetre or "tous",
        "libelle_perimetre": LIBELLES_PERIMETRE.get(perimetre or "tous",
                                                    "Tout — vue réelle"),
        "non_lettrees": non_lettrees,
        "solde_anterieur": anterieur,
        "mouvements": mouvements,
        "total_debit": sum(m["debit"] for m in mouvements),
        "total_credit": sum(m["credit"] for m in mouvements),
        "solde_final": solde,
        "age": {cle: int(tranches.get(cle) or 0)
                for cle in ("t0_30", "t31_60", "t61_90", "t90_plus")},
    }


#: Ce qu'un relevé doit annoncer sur lui-même : un document envoyé à un client
#: doit dire de quel périmètre il rend compte.
LIBELLES_PERIMETRE = {
    "tous": "Tout — vue réelle",
    "declare": "Déclaré uniquement",
    "hors_declaration": "Hors déclaration uniquement",
}


def _bornes_releve(ctx) -> tuple[str, str]:
    au = ctx.arg("au") or util.aujourdhui()
    du = ctx.arg("du") or f"{au[:4]}-01-01"
    return du, au


@route("GET", "/api/tiers/<id>/releve")
def api_releve_tiers(ctx):
    du, au = _bornes_releve(ctx)
    return releve_tiers(ctx.arg_int("societe"), int(ctx.params["id"]), du, au,
                        perimetre=ctx.perimetre(),
                        non_lettrees=ctx.arg("non_lettrees") == "1")


@route("GET", "/api/export/releve-tiers")
def api_export_releve_tiers(ctx):
    from modules import comptabilite as compta
    societe_id = ctx.arg_int("societe")
    soc = compta.societe(societe_id)
    du, au = _bornes_releve(ctx)
    d = releve_tiers(societe_id, ctx.arg_int("tiers"), du, au,
                     perimetre=ctx.perimetre(),
                     non_lettrees=ctx.arg("non_lettrees") == "1")

    classeur = tableur.Classeur()
    f = classeur.feuille("Relevé de compte")
    f.titre(f"{soc['raison_sociale']} — Relevé de compte "
            f"{d['tiers']['raison_sociale']}")
    f.ajoute(tableur.texte(f"Du {util.date_fr(du)} au {util.date_fr(au)}"
                           f" — {d['libelle_perimetre']}"))
    f.vide()
    f.entetes("Date", "Journal", "N° écriture", "Pièce", "Libellé", "Compte",
              "Échéance", "Lettrage", "Débit", "Crédit", "Solde")
    f.largeurs_auto(12, 9, 14, 16, 44, 10, 12, 10, 15, 15, 16)
    f.ajoute(tableur.texte(""), tableur.texte(""), tableur.texte(""),
             tableur.texte(""), tableur.texte("Solde antérieur", tableur.GRAS),
             tableur.texte(""), tableur.texte(""), tableur.texte(""),
             tableur.texte(""), tableur.texte(""),
             tableur.monnaie(d["solde_anterieur"]))
    for m in d["mouvements"]:
        f.ajoute(
            tableur.date_cel(m["date"]), tableur.texte(m["journal"]),
            tableur.texte(m["numero"] or ""), tableur.texte(m["piece"] or ""),
            tableur.texte(m["libelle"] or m["libelle_ecriture"]),
            tableur.texte(m["compte"]), tableur.date_cel(m["echeance"] or ""),
            tableur.texte(m["lettrage"] or ""),
            tableur.monnaie(m["debit"]), tableur.monnaie(m["credit"]),
            tableur.monnaie(m["solde"]),
        )
    f.ajoute(
        tableur.texte("TOTAUX", tableur.GRAS), *[tableur.texte("")] * 7,
        tableur.monnaie(d["total_debit"], total=True),
        tableur.monnaie(d["total_credit"], total=True),
        tableur.monnaie(d["solde_final"], total=True),
    )
    return Reponse(classeur.octets(),
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   f"releve_{d['tiers']['code'] or d['tiers']['id']}_{au}.xlsx")
