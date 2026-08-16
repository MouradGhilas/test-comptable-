"""Trésorerie : caisses, banques, mouvements, rapprochement bancaire.

En promotion immobilière, le compte dédié à l'encaissement des fonds VSP est
identifié comme « séquestre » et rattaché à un programme, afin de pouvoir
justifier à tout moment l'emploi des avances reçues des acquéreurs.
"""

from __future__ import annotations

from noyau import base as db
from noyau import util
from noyau import tableur
from noyau.serveur import ErreurApplicative, route, Reponse
from modules import comptabilite as compta


@route("GET", "/api/tresorerie")
def api_liste(ctx):
    societe_id = ctx.arg_int("societe")
    au = ctx.arg("au") or util.aujourdhui()
    comptes = db.lignes(
        "SELECT ct.*, p.intitule AS programme FROM comptes_tresorerie ct "
        "LEFT JOIN programmes p ON p.id = ct.programme_id "
        "WHERE ct.societe_id = ? ORDER BY ct.type DESC, ct.code", (societe_id,)
    )
    for c in comptes:
        solde = compta.solde_compte(societe_id, c["compte"], None, au, prefixe=False)
        c["solde"] = solde["solde"]
        c["total_debit"] = solde["debit"]
        c["total_credit"] = solde["credit"]
    return {"comptes": comptes, "total": sum(c["solde"] for c in comptes), "au": au}


@route("POST", "/api/tresorerie")
def api_cree(ctx):
    ctx.interdit_lecture_seule()
    societe_id = ctx.entier("societe_id")
    compte = str(ctx.champ_requis("compte")).strip()
    compta.exige_compte(societe_id, compte)
    code = str(ctx.champ_requis("code")).upper()[:16]
    if db.ligne("SELECT id FROM comptes_tresorerie WHERE societe_id = ? AND code = ?",
                (societe_id, code)):
        raise ErreurApplicative(f"Le code « {code} » existe déjà.")
    with db.transaction():
        identifiant = db.insere("comptes_tresorerie", {
            "societe_id": societe_id, "code": code,
            "libelle": ctx.champ_requis("libelle"),
            "type": ctx.champ("type", "banque"),
            "compte": compte,
            "banque": util.nettoie(ctx.champ("banque")),
            "agence": util.nettoie(ctx.champ("agence")),
            "rib": util.nettoie(ctx.champ("rib")),
            "devise": ctx.champ("devise", "DZD"),
            "est_sequestre": ctx.booleen("est_sequestre"),
            "programme_id": ctx.entier("programme_id"),
            "actif": 1,
        })
    return {"id": identifiant}


@route("PUT", "/api/tresorerie/<id>")
def api_modifie(ctx):
    ctx.interdit_lecture_seule()
    identifiant = int(ctx.params["id"])
    with db.transaction():
        db.modifie("comptes_tresorerie", identifiant, {
            "libelle": ctx.champ_requis("libelle"),
            "type": ctx.champ("type", "banque"),
            "banque": util.nettoie(ctx.champ("banque")),
            "agence": util.nettoie(ctx.champ("agence")),
            "rib": util.nettoie(ctx.champ("rib")),
            "est_sequestre": ctx.booleen("est_sequestre"),
            "programme_id": ctx.entier("programme_id"),
            "actif": ctx.booleen("actif", True),
        })
    return {"ok": True}


@route("GET", "/api/tresorerie/<id>/mouvements")
def api_mouvements(ctx):
    identifiant = int(ctx.params["id"])
    tres = db.ligne("SELECT * FROM comptes_tresorerie WHERE id = ?", (identifiant,))
    if not tres:
        raise ErreurApplicative("Compte de trésorerie introuvable.", 404)
    du = ctx.arg("du")
    au = ctx.arg("au") or util.aujourdhui()

    solde_initial = 0
    if du:
        avant = compta.solde_compte(tres["societe_id"], tres["compte"], None,
                                    _veille(du), prefixe=False)
        solde_initial = avant["solde"]

    conditions = ["e.societe_id = ?", "l.compte = ?", "e.date <= ?"]
    params: list = [tres["societe_id"], tres["compte"], au]
    if du:
        conditions.append("e.date >= ?")
        params.append(du)
    mouvements = db.lignes(
        "SELECT l.*, e.date, e.numero AS num_ecriture, e.piece, "
        "       e.libelle AS libelle_ecriture, j.code AS journal, "
        "       t.raison_sociale AS tiers, "
        "       (SELECT COUNT(*) FROM rapprochement_lignes rl WHERE rl.ligne_id = l.id) AS pointee "
        "FROM lignes l JOIN ecritures e ON e.id = l.ecriture_id "
        "JOIN journaux j ON j.id = e.journal_id "
        "LEFT JOIN tiers t ON t.id = l.tiers_id "
        f"WHERE {' AND '.join(conditions)} ORDER BY e.date, e.id, l.ordre",
        params,
    )
    solde = solde_initial
    for m in mouvements:
        solde += m["debit"] - m["credit"]
        m["solde_progressif"] = solde
    return {
        "compte": tres, "mouvements": mouvements, "solde_initial": solde_initial,
        "solde_final": solde,
        "total_entrees": sum(m["debit"] for m in mouvements),
        "total_sorties": sum(m["credit"] for m in mouvements),
    }


def _veille(date: str) -> str:
    import datetime
    return (datetime.date.fromisoformat(date[:10]) - datetime.timedelta(days=1)).isoformat()


@route("POST", "/api/tresorerie/mouvement")
def api_saisie_rapide(ctx):
    """Saisie directe d'une entrée/sortie de caisse ou de banque (sans facture)."""
    ctx.interdit_lecture_seule()
    societe_id = ctx.entier("societe_id")
    tresorerie_id = ctx.entier("tresorerie_id")
    tres = db.ligne("SELECT * FROM comptes_tresorerie WHERE id = ?", (tresorerie_id,))
    if not tres:
        raise ErreurApplicative("Compte de trésorerie introuvable.", 404)
    montant = ctx.montant("montant")
    if montant <= 0:
        raise ErreurApplicative("Le montant doit être positif.")
    sens = ctx.champ("sens", "sortie")
    contrepartie = str(ctx.champ_requis("compte")).strip()
    compta.exige_compte(societe_id, contrepartie)
    date = ctx.date("date", util.aujourdhui())
    libelle = ctx.champ_requis("libelle")
    journal = "BQ" if tres["type"] in ("banque", "ccp") else "CA"
    tiers_id = ctx.entier("tiers_id")

    if sens == "entree":
        lignes = [
            {"compte": tres["compte"], "debit": montant, "credit": 0, "libelle": libelle},
            {"compte": contrepartie, "debit": 0, "credit": montant,
             "tiers_id": tiers_id, "libelle": libelle,
             "programme_id": ctx.entier("programme_id"),
             "lot_id": ctx.entier("lot_id"), "bien_id": ctx.entier("bien_id")},
        ]
    else:
        lignes = [
            {"compte": contrepartie, "debit": montant, "credit": 0,
             "tiers_id": tiers_id, "libelle": libelle,
             "programme_id": ctx.entier("programme_id"),
             "lot_id": ctx.entier("lot_id"), "bien_id": ctx.entier("bien_id")},
            {"compte": tres["compte"], "debit": 0, "credit": montant, "libelle": libelle},
        ]

    with db.transaction():
        # Contrôle de bon sens : la caisse ne peut pas devenir créditrice
        if sens == "sortie" and tres["type"] == "caisse":
            solde = compta.solde_compte(societe_id, tres["compte"], None, date,
                                        prefixe=False)["solde"]
            if solde - montant < 0:
                raise ErreurApplicative(
                    f"Solde de caisse insuffisant au {util.date_fr(date)} : "
                    f"{util.formate_montant(solde)} disponible(s) pour une sortie de "
                    f"{util.formate_montant(montant)}."
                )
        ecriture_id = compta.enregistre_ecriture(
            societe_id, journal, date, libelle, lignes,
            piece=util.nettoie(ctx.champ("piece")),
            module="tresorerie", source_type="mouvement",
            utilisateur=ctx.nom_utilisateur, perimetre=ctx.champ("perimetre"),
        )
    return {"ecriture_id": ecriture_id}


@route("POST", "/api/tresorerie/virement")
def api_virement(ctx):
    """Virement interne entre deux comptes de trésorerie (compte 58)."""
    ctx.interdit_lecture_seule()
    societe_id = ctx.entier("societe_id")
    source = db.ligne("SELECT * FROM comptes_tresorerie WHERE id = ?",
                      (ctx.entier("source_id"),))
    destination = db.ligne("SELECT * FROM comptes_tresorerie WHERE id = ?",
                           (ctx.entier("destination_id"),))
    if not source or not destination:
        raise ErreurApplicative("Comptes de trésorerie invalides.")
    if source["id"] == destination["id"]:
        raise ErreurApplicative("Les comptes source et destination sont identiques.")
    montant = ctx.montant("montant")
    if montant <= 0:
        raise ErreurApplicative("Le montant doit être positif.")
    date = ctx.date("date", util.aujourdhui())
    libelle = ctx.champ("libelle") or f"Virement {source['libelle']} → {destination['libelle']}"
    with db.transaction():
        ecriture_id = compta.enregistre_ecriture(
            societe_id, "OD", date, libelle, [
                {"compte": destination["compte"], "debit": montant, "credit": 0,
                 "libelle": libelle},
                {"compte": source["compte"], "debit": 0, "credit": montant,
                 "libelle": libelle},
            ],
            module="tresorerie", source_type="virement", utilisateur=ctx.nom_utilisateur,
        )
    return {"ecriture_id": ecriture_id}


# ---------------------------------------------------------------------------
# Rapprochement bancaire
# ---------------------------------------------------------------------------

@route("GET", "/api/rapprochements")
def api_liste_rapprochements(ctx):
    return {"rapprochements": db.lignes(
        "SELECT r.*, ct.libelle AS compte FROM rapprochements r "
        "JOIN comptes_tresorerie ct ON ct.id = r.tresorerie_id "
        "WHERE ct.societe_id = ? ORDER BY r.date_arrete DESC",
        (ctx.arg_int("societe"),)
    )}


@route("POST", "/api/rapprochements")
def api_cree_rapprochement(ctx):
    ctx.interdit_lecture_seule()
    with db.transaction():
        identifiant = db.insere("rapprochements", {
            "tresorerie_id": ctx.entier("tresorerie_id"),
            "date_arrete": ctx.date("date_arrete", util.aujourdhui()),
            "solde_releve": ctx.montant("solde_releve"),
            "cloture": 0, "cree_le": util.maintenant(),
        })
    return {"id": identifiant}


@route("GET", "/api/rapprochements/<id>")
def api_rapprochement(ctx):
    identifiant = int(ctx.params["id"])
    r = db.ligne(
        "SELECT r.*, ct.libelle AS compte_libelle, ct.compte, ct.societe_id "
        "FROM rapprochements r JOIN comptes_tresorerie ct ON ct.id = r.tresorerie_id "
        "WHERE r.id = ?", (identifiant,)
    )
    if not r:
        raise ErreurApplicative("Rapprochement introuvable.", 404)
    mouvements = db.lignes(
        "SELECT l.id, l.libelle, l.debit, l.credit, e.date, e.numero AS num_ecriture, "
        "  e.piece, t.raison_sociale AS tiers, "
        "  (SELECT COUNT(*) FROM rapprochement_lignes rl "
        "   WHERE rl.ligne_id = l.id AND rl.rapprochement_id = ?) AS pointee, "
        "  (SELECT COUNT(*) FROM rapprochement_lignes rl2 "
        "   WHERE rl2.ligne_id = l.id AND rl2.rapprochement_id <> ?) AS deja_rapprochee "
        "FROM lignes l JOIN ecritures e ON e.id = l.ecriture_id "
        "LEFT JOIN tiers t ON t.id = l.tiers_id "
        "WHERE e.societe_id = ? AND l.compte = ? AND e.date <= ? "
        "ORDER BY e.date, l.id",
        (identifiant, identifiant, r["societe_id"], r["compte"], r["date_arrete"]),
    )
    solde_comptable = sum(m["debit"] - m["credit"] for m in mouvements)
    pointe = sum(m["debit"] - m["credit"] for m in mouvements if m["pointee"])
    non_pointe = solde_comptable - pointe
    r["mouvements"] = mouvements
    r["solde_comptable"] = solde_comptable
    r["solde_pointe"] = pointe
    r["montant_non_pointe"] = non_pointe
    # Rapprochement : solde relevé + mouvements non pointés = solde comptable
    r["ecart"] = solde_comptable - (r["solde_releve"] + non_pointe)
    return r


@route("POST", "/api/rapprochements/<id>/pointer")
def api_pointe(ctx):
    ctx.interdit_lecture_seule()
    identifiant = int(ctx.params["id"])
    lignes_ids = ctx.champ("lignes") or []
    pointer = ctx.booleen("pointer", True)
    with db.transaction():
        for ligne_id in lignes_ids:
            if pointer:
                db.execute(
                    "INSERT OR IGNORE INTO rapprochement_lignes "
                    "(rapprochement_id, ligne_id, pointee) VALUES (?,?,1)",
                    (identifiant, ligne_id),
                )
            else:
                db.execute(
                    "DELETE FROM rapprochement_lignes WHERE rapprochement_id = ? "
                    "AND ligne_id = ?", (identifiant, ligne_id),
                )
    return {"ok": True}


@route("POST", "/api/rapprochements/<id>/cloturer")
def api_cloture_rapprochement(ctx):
    ctx.interdit_lecture_seule()
    identifiant = int(ctx.params["id"])
    detail = api_rapprochement(ctx)
    if detail["ecart"] != 0 and not ctx.booleen("forcer"):
        raise ErreurApplicative(
            f"Le rapprochement présente un écart de "
            f"{util.formate_montant(detail['ecart'])}. Pointez les mouvements manquants "
            "ou cochez « forcer » si l'écart est justifié."
        )
    with db.transaction():
        db.modifie("rapprochements", identifiant, {"cloture": 1})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Journal de caisse imprimable / export
# ---------------------------------------------------------------------------

@route("GET", "/api/export/tresorerie")
def api_export(ctx):
    identifiant = ctx.arg_int("tresorerie")
    tres = db.ligne("SELECT * FROM comptes_tresorerie WHERE id = ?", (identifiant,))
    if not tres:
        raise ErreurApplicative("Compte de trésorerie introuvable.", 404)
    soc = compta.societe(tres["societe_id"])
    du = ctx.arg("du")
    au = ctx.arg("au") or util.aujourdhui()

    ctx.requete.setdefault("du", [du] if du else [])
    donnees = api_mouvements(_ContexteFactice(ctx, {"id": str(identifiant)}))

    classeur = tableur.Classeur()
    f = classeur.feuille(tres["libelle"][:31])
    f.titre(f"{soc['raison_sociale']} — {tres['libelle']}")
    f.ajoute(tableur.texte(f"Du {util.date_fr(du) if du else 'origine'} au {util.date_fr(au)}"))
    f.vide()
    f.entetes("Date", "Journal", "N° écriture", "Pièce", "Libellé", "Tiers",
              "Entrée", "Sortie", "Solde")
    f.largeurs_auto(12, 8, 14, 14, 45, 28, 15, 15, 16)
    f.ajoute(tableur.texte(""), tableur.texte(""), tableur.texte(""), tableur.texte(""),
             tableur.texte("Solde initial", tableur.GRAS), tableur.texte(""),
             tableur.texte(""), tableur.texte(""),
             tableur.monnaie(donnees["solde_initial"], gras=True))
    for m in donnees["mouvements"]:
        f.ajoute(
            tableur.date_cel(m["date"]), tableur.texte(m["journal"]),
            tableur.texte(m["num_ecriture"]), tableur.texte(m["piece"]),
            tableur.texte(m["libelle"]), tableur.texte(m["tiers"]),
            tableur.monnaie(m["debit"]), tableur.monnaie(m["credit"]),
            tableur.monnaie(m["solde_progressif"]),
        )
    f.ajoute(tableur.texte("TOTAUX", tableur.GRAS), *[tableur.texte("")] * 5,
             tableur.monnaie(donnees["total_entrees"], total=True),
             tableur.monnaie(donnees["total_sorties"], total=True),
             tableur.monnaie(donnees["solde_final"], total=True))
    return Reponse(classeur.octets(),
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   f"{tres['code']}_{soc['code']}_{au}.xlsx")


class _ContexteFactice:
    """Réutilise une route interne avec d'autres paramètres d'URL."""

    def __init__(self, ctx, params):
        self._ctx = ctx
        self.params = params

    def __getattr__(self, nom):
        return getattr(self._ctx, nom)
