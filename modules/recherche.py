"""Recherche globale : un seul champ pour retrouver n'importe quoi.

Un comptable ne se souvient pas de l'écran où se trouve ce qu'il cherche ;
il se souvient d'un nom, d'un numéro de facture, ou d'un montant. Cette
route interroge d'un coup les écritures, les tiers, les factures, les
comptes, les biens, les baux, les programmes, les lots, les contrats et les
salariés, et rend à chaque résultat le chemin qui y mène.

Le cas le plus utile est aussi le moins évident : **chercher un montant**.
« 125 000 » retrouve la ligne d'écriture qui le porte, au débit comme au
crédit — c'est ainsi qu'on remonte à l'origine d'un solde qui ne tombe pas
juste.
"""

from __future__ import annotations

from urllib.parse import quote

from noyau import base as db
from noyau import util
from noyau.serveur import ErreurApplicative, route

#: Au-delà, l'écran ne serait plus lisible : on annonce le nombre total et
#: on renvoie vers l'écran spécialisé, qui sait filtrer.
PAR_GROUPE = 6


def _montant_cherche(texte: str) -> int | None:
    """« 125 000 », « 125000,50 », « 1 250,00 DA » -> centimes. None sinon."""
    nettoye = (texte.replace(" ", "").replace(" ", "")
               .replace("DA", "").replace("da", "").replace(",", "."))
    if not nettoye or not nettoye.replace(".", "", 1).lstrip("-").isdigit():
        return None
    try:
        return util.centimes(nettoye)
    except (TypeError, ValueError):
        return None


def echappe_like(texte: str) -> str:
    """Neutralise les jokers de LIKE.

    Sans cela, chercher « 50% » — une remise, un avancement — reviendrait à
    demander tout ce qui commence par « 50 ». Le caractère cherché doit être
    cherché tel quel.
    """
    return (texte.replace("\\", "\\\\")
                 .replace("%", "\\%").replace("_", "\\_"))


def _groupe(cle, libelle, icone, resultats, total=None):
    return {"cle": cle, "libelle": libelle, "icone": icone,
            "resultats": resultats[:PAR_GROUPE],
            "total": total if total is not None else len(resultats)}


@route("GET", "/api/recherche")
def api_recherche(ctx):
    societe_id = ctx.arg_int("societe")
    if not societe_id:
        raise ErreurApplicative("Aucun dossier sélectionné.")
    texte = (ctx.arg("q") or "").strip()
    if len(texte) < 2:
        raise ErreurApplicative("Tapez au moins deux caractères.")
    echappe = echappe_like(texte)
    motif = f"%{echappe}%"
    montant = _montant_cherche(texte)
    groupes = []

    # -- Écritures : par libellé, numéro, pièce ou référence ---------------
    lignes = db.lignes(
        "SELECT e.id, e.date, e.numero, e.piece, e.libelle, e.perimetre, "
        "       j.code AS journal, "
        "       (SELECT COALESCE(SUM(debit),0) FROM lignes WHERE ecriture_id = e.id) AS total "
        "FROM ecritures e JOIN journaux j ON j.id = e.journal_id "
        "WHERE e.societe_id = ? AND (e.libelle LIKE ? ESCAPE '\\' OR e.numero LIKE ? ESCAPE '\\' "
        "      OR e.piece LIKE ? ESCAPE '\\' OR e.reference LIKE ? ESCAPE '\\') "
        "ORDER BY e.date DESC, e.id DESC LIMIT 40",
        (societe_id, motif, motif, motif, motif))
    groupes.append(_groupe("ecritures", "Écritures", "📘", [{
        "titre": e["libelle"],
        "detail": f"{util.date_fr(e['date'])} · {e['journal']} {e['numero'] or ''}"
                  + (f" · pièce {e['piece']}" if e["piece"] else ""),
        "montant": e["total"],
        "perimetre": e["perimetre"],
        "route": f"/comptabilite/ecritures?ecriture={e['id']}",
    } for e in lignes]))

    # -- Le montant : ce qu'aucun autre écran ne sait chercher -------------
    if montant:
        portant = db.lignes(
            "SELECT e.id, e.date, e.numero, e.libelle, e.perimetre, "
            "       j.code AS journal, l.compte, l.debit, l.credit, "
            "       l.libelle AS libelle_ligne "
            "FROM lignes l JOIN ecritures e ON e.id = l.ecriture_id "
            "JOIN journaux j ON j.id = e.journal_id "
            "WHERE e.societe_id = ? AND (l.debit = ? OR l.credit = ?) "
            "ORDER BY e.date DESC, e.id DESC LIMIT 40",
            (societe_id, montant, montant))
        groupes.append(_groupe("montant", f"Montant {util.formate_montant(montant)}",
                               "🔢", [{
            "titre": p["libelle_ligne"] or p["libelle"],
            "detail": f"{util.date_fr(p['date'])} · {p['journal']} {p['numero'] or ''}"
                      f" · compte {p['compte']} "
                      f"{'au débit' if p['debit'] else 'au crédit'}",
            "montant": p["debit"] or p["credit"],
            "perimetre": p["perimetre"],
            "route": f"/comptabilite/ecritures?ecriture={p['id']}",
        } for p in portant]))

    # -- Tiers -------------------------------------------------------------
    tiers = db.lignes(
        "SELECT id, code, type, raison_sociale, nif, telephone, actif FROM tiers "
        "WHERE societe_id = ? AND (raison_sociale LIKE ? ESCAPE '\\' OR code LIKE ? ESCAPE '\\' "
        "      OR nif LIKE ? ESCAPE '\\' OR telephone LIKE ? ESCAPE '\\') "
        "ORDER BY raison_sociale LIMIT 40",
        (societe_id, motif, motif, motif, motif))
    groupes.append(_groupe("tiers", "Tiers", "👥", [{
        "titre": t["raison_sociale"],
        "detail": " · ".join(x for x in (t["type"], t["code"], t["telephone"],
                                         "" if t["actif"] else "inactif") if x),
        "route": f"/tiers?q={quote(t['raison_sociale'])}",
    } for t in tiers]))

    # -- Factures ----------------------------------------------------------
    factures = db.lignes(
        "SELECT f.id, f.sens, f.numero, f.date, f.objet, f.net_a_payer, "
        "       f.statut, t.raison_sociale AS tiers "
        "FROM factures f LEFT JOIN tiers t ON t.id = f.tiers_id "
        "WHERE f.societe_id = ? AND (f.numero LIKE ? ESCAPE '\\' OR f.objet LIKE ? ESCAPE '\\' "
        "      OR t.raison_sociale LIKE ? ESCAPE '\\') "
        "ORDER BY f.date DESC LIMIT 40",
        (societe_id, motif, motif, motif))
    groupes.append(_groupe("factures", "Factures", "🧾", [{
        "titre": f"{f['numero']} — {f['tiers'] or ''}".strip(" —"),
        "detail": f"{util.date_fr(f['date'])} · {f['sens']} · {f['statut']}"
                  + (f" · {f['objet']}" if f["objet"] else ""),
        "montant": f["net_a_payer"],
        "route": f"/factures?sens={f['sens']}&q={quote(f['numero'])}",
    } for f in factures]))

    # -- Comptes du plan ---------------------------------------------------
    comptes = db.lignes(
        "SELECT numero, intitule FROM comptes "
        "WHERE (societe_id = ? OR societe_id IS NULL) AND actif = 1 "
        "AND (numero LIKE ? ESCAPE '\\' OR intitule LIKE ? ESCAPE '\\') ORDER BY numero LIMIT 40",
        (societe_id, f"{echappe}%", motif))
    groupes.append(_groupe("comptes", "Plan comptable", "📗", [{
        "titre": f"{c['numero']} — {c['intitule']}",
        "detail": "grand livre du compte",
        "route": f"/comptabilite/grand-livre?compte_debut={c['numero']}"
                 f"&compte_fin={c['numero']}",
    } for c in comptes]))

    # -- Métier : biens, baux, programmes, lots, contrats, salariés --------
    biens = db.lignes(
        "SELECT id, reference, designation, commune, statut FROM biens "
        "WHERE societe_id = ? AND (reference LIKE ? ESCAPE '\\' OR designation LIKE ? ESCAPE '\\' "
        "      OR commune LIKE ? ESCAPE '\\') ORDER BY reference LIMIT 40",
        (societe_id, motif, motif, motif))
    groupes.append(_groupe("biens", "Biens", "🏠", [{
        "titre": b["designation"] or b["reference"],
        "detail": " · ".join(x for x in (b["reference"], b["commune"],
                                         b["statut"]) if x),
        "route": f"/agence/biens?q={quote(b['reference'] or '')}",
    } for b in biens]))

    contrats = db.lignes(
        "SELECT c.id, c.numero, c.statut, c.prix_total, l.numero AS lot, "
        "       p.intitule AS programme, t.raison_sociale AS acquereur "
        "FROM contrats_vsp c JOIN lots l ON l.id = c.lot_id "
        "JOIN programmes p ON p.id = c.programme_id "
        "JOIN tiers t ON t.id = c.acquereur_id "
        "WHERE c.societe_id = ? AND (c.numero LIKE ? ESCAPE '\\' OR l.numero LIKE ? ESCAPE '\\' "
        "      OR t.raison_sociale LIKE ? ESCAPE '\\' OR c.num_acte_notarie LIKE ? ESCAPE '\\') "
        "ORDER BY c.date_contrat DESC LIMIT 40",
        (societe_id, motif, motif, motif, motif))
    groupes.append(_groupe("contrats", "Contrats de vente sur plan", "📄", [{
        "titre": f"{c['numero']} — {c['acquereur']}",
        "detail": f"{c['programme']} · lot {c['lot']} · {c['statut']}",
        "montant": c["prix_total"],
        "route": f"/promotion/contrat/{c['id']}",
    } for c in contrats]))

    programmes = db.lignes(
        "SELECT id, code, intitule, commune, statut FROM programmes "
        "WHERE societe_id = ? AND (code LIKE ? ESCAPE '\\' OR intitule LIKE ? ESCAPE '\\' "
        "      OR commune LIKE ? ESCAPE '\\') ORDER BY intitule LIMIT 40",
        (societe_id, motif, motif, motif))
    groupes.append(_groupe("programmes", "Programmes immobiliers", "🏗️", [{
        "titre": f"{p['code']} — {p['intitule']}",
        "detail": " · ".join(x for x in (p["commune"], p["statut"]) if x),
        "route": f"/promotion/programme/{p['id']}",
    } for p in programmes]))

    baux = db.lignes(
        "SELECT b.id, b.numero, b.statut, b.loyer_mensuel, "
        "       bi.designation AS bien, l.raison_sociale AS locataire "
        "FROM baux b LEFT JOIN biens bi ON bi.id = b.bien_id "
        "LEFT JOIN tiers l ON l.id = b.locataire_id "
        "WHERE b.societe_id = ? AND (b.numero LIKE ? ESCAPE '\\' OR l.raison_sociale LIKE ? ESCAPE '\\' "
        "      OR bi.designation LIKE ? ESCAPE '\\') ORDER BY b.id DESC LIMIT 40",
        (societe_id, motif, motif, motif))
    groupes.append(_groupe("baux", "Baux", "🔑", [{
        "titre": f"{b['numero']} — {b['locataire'] or ''}".strip(" —"),
        "detail": " · ".join(x for x in (b["bien"], b["statut"]) if x),
        "montant": b["loyer_mensuel"],
        "route": "/agence/baux",
    } for b in baux]))

    salaries = db.lignes(
        "SELECT id, matricule, nom, prenom, poste, actif FROM salaries "
        "WHERE societe_id = ? AND (matricule LIKE ? ESCAPE '\\' OR nom LIKE ? ESCAPE '\\' "
        "      OR prenom LIKE ? ESCAPE '\\' OR poste LIKE ? ESCAPE '\\') ORDER BY nom LIMIT 40",
        (societe_id, motif, motif, motif, motif))
    groupes.append(_groupe("salaries", "Salariés", "👤", [{
        "titre": f"{s['nom']} {s['prenom'] or ''}".strip(),
        "detail": " · ".join(x for x in (s["matricule"], s["poste"],
                                         "" if s["actif"] else "sorti") if x),
        "route": "/paie/salaries",
    } for s in salaries]))

    groupes = [g for g in groupes if g["resultats"]]
    return {
        "q": texte,
        "montant": montant,
        "groupes": groupes,
        "total": sum(g["total"] for g in groupes),
    }
