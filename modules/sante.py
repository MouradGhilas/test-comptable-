"""Santé du dossier : les anomalies pendant qu'elles coûtent encore peu.

La clôture a ses propres contrôles, et ils bloquent : c'est leur rôle. Mais
une erreur découverte à la clôture a onze mois d'ancienneté, et onze mois
d'écritures posées par-dessus. Ces contrôles-ci tournent au fil de l'eau,
sur le dossier tel qu'il est aujourd'hui.

Chacun répond à trois questions : ce qui ne va pas, pourquoi ça compte, et
où aller pour le corriger. Un contrôle qui ne mène nulle part ne sert à rien.
"""

from __future__ import annotations

from noyau import base as db
from noyau import util
from noyau.serveur import route
from modules import comptabilite as compta

#: Au-delà, une créance ou une dette non lettrée mérite qu'on s'y arrête.
JOURS_LETTRAGE = 90


def _anomalie(cle, niveau, titre, explication, *, nombre=0, montant=0,
              detail=None, route_ecran=None):
    return {
        "cle": cle, "niveau": niveau, "titre": titre,
        "explication": explication, "nombre": nombre, "montant": montant,
        "detail": detail or [], "route": route_ecran,
    }


def _equilibre(societe_id, ex, anomalies):
    t = db.ligne(
        "SELECT COALESCE(SUM(l.debit),0) d, COALESCE(SUM(l.credit),0) c "
        "FROM lignes l JOIN ecritures e ON e.id = l.ecriture_id "
        "WHERE e.exercice_id = ?", (ex["id"],))
    if t and t["d"] != t["c"]:
        anomalies.append(_anomalie(
            "equilibre", "critique", "La comptabilité n'est pas équilibrée",
            "Le total des débits doit égaler le total des crédits, toujours et "
            "sans exception. Un écart signale une écriture abîmée : aucun état "
            "financier n'est fiable tant qu'il subsiste.",
            montant=t["d"] - t["c"],
            route_ecran="/comptabilite/balance"))

    boiteuses = db.lignes(
        "SELECT e.id, e.numero, e.date, e.libelle, "
        "  COALESCE(SUM(l.debit),0) d, COALESCE(SUM(l.credit),0) c "
        "FROM ecritures e LEFT JOIN lignes l ON l.ecriture_id = e.id "
        "WHERE e.exercice_id = ? GROUP BY e.id HAVING d <> c LIMIT 20",
        (ex["id"],))
    if boiteuses:
        anomalies.append(_anomalie(
            "ecritures_boiteuses", "critique",
            f"{len(boiteuses)} écriture(s) déséquilibrée(s)",
            "Une écriture dont les débits et les crédits ne se répondent pas "
            "n'aurait pas dû entrer. Corrigez-la avant tout le reste.",
            nombre=len(boiteuses),
            detail=[f"{e['numero']} du {util.date_fr(e['date'])} — "
                    f"{e['libelle']} (écart {util.formate_montant(e['d'] - e['c'])})"
                    for e in boiteuses],
            route_ecran="/comptabilite/ecritures"))


def _numerotation(societe_id, ex, anomalies):
    """Un trou dans la séquence d'un journal, c'est ce qu'un contrôle cherche.

    La numérotation d'un journal doit être continue : un numéro manquant
    laisse penser qu'une pièce a été retirée après coup.
    """
    trous = []
    for jr in db.lignes(
            "SELECT DISTINCT j.id, j.code FROM ecritures e "
            "JOIN journaux j ON j.id = e.journal_id WHERE e.societe_id = ?",
            (societe_id,)):
        annees = db.lignes(
            "SELECT DISTINCT substr(date,1,4) AS an FROM ecritures "
            "WHERE journal_id = ?", (jr["id"],))
        for a in annees:
            numeros = sorted(
                int(e["numero"].rsplit("-", 1)[-1])
                for e in db.lignes(
                    "SELECT numero FROM ecritures WHERE journal_id = ? "
                    "AND substr(date,1,4) = ? AND numero IS NOT NULL",
                    (jr["id"], a["an"]))
                if e["numero"].rsplit("-", 1)[-1].isdigit())
            if not numeros:
                continue
            manquants = sorted(set(range(numeros[0], numeros[-1] + 1)) - set(numeros))
            if manquants:
                trous.append(f"journal {jr['code']} {a['an']} : "
                             f"{len(manquants)} numéro(s) manquant(s) "
                             f"({', '.join(str(m) for m in manquants[:6])}"
                             f"{'…' if len(manquants) > 6 else ''})")
    if trous:
        anomalies.append(_anomalie(
            "numerotation", "critique",
            f"{len(trous)} séquence(s) de journal à trous",
            "La numérotation d'un journal doit être continue. Un numéro "
            "manquant laisse penser qu'une pièce a été retirée après coup — "
            "c'est précisément ce qu'un contrôle fiscal cherche. Un brouillon "
            "supprimé en est la cause la plus fréquente.",
            nombre=len(trous), detail=trous,
            route_ecran="/comptabilite/ecritures"))


def _caisse(societe_id, ex, anomalies):
    """Une caisse ne peut pas être créditrice : on ne sort pas d'un tiroir
    plus d'argent qu'il n'en contient."""
    mouvements = db.lignes(
        "SELECT e.date, SUM(l.debit - l.credit) AS mvt "
        "FROM lignes l JOIN ecritures e ON e.id = l.ecriture_id "
        "WHERE e.societe_id = ? AND l.compte LIKE '53%' AND e.date <= ? "
        "GROUP BY e.date ORDER BY e.date", (societe_id, ex["date_fin"]))
    solde, pire, quand = 0, 0, None
    for m in mouvements:
        solde += m["mvt"]
        if solde < pire:
            pire, quand = solde, m["date"]
    if pire < 0:
        anomalies.append(_anomalie(
            "caisse", "critique", "La caisse est passée en négatif",
            "Une caisse créditrice est physiquement impossible : il manque un "
            "encaissement, ou un décaissement a été saisi deux fois. Le solde "
            "le plus bas atteint est indiqué ci-contre.",
            montant=pire,
            detail=[f"au plus bas le {util.date_fr(quand)}"],
            route_ecran="/tresorerie"))


def _tiers_inverses(societe_id, ex, anomalies):
    # Seuls les comptes ordinaires : 419 « clients créditeurs » et 409
    # « fournisseurs débiteurs » existent précisément pour porter les avances,
    # et y être inversé est normal. Une avance sur vente sur plan n'est pas
    # une anomalie.
    lignes = db.lignes(
        "SELECT t.raison_sociale, t.type, "
        "  COALESCE(SUM(l.debit - l.credit),0) AS solde "
        "FROM lignes l JOIN ecritures e ON e.id = l.ecriture_id "
        "JOIN tiers t ON t.id = l.tiers_id "
        "WHERE e.societe_id = ? AND e.date <= ? "
        "AND t.type IN ('client','fournisseur') "
        "AND ((t.type = 'client' AND substr(l.compte,1,3) = '411') "
        "  OR (t.type = 'fournisseur' AND substr(l.compte,1,3) = '401')) "
        "GROUP BY t.id HAVING (t.type = 'client' AND solde < 0) "
        "   OR (t.type = 'fournisseur' AND solde > 0)",
        (societe_id, ex["date_fin"]))
    if lignes:
        anomalies.append(_anomalie(
            "tiers_inverses", "alerte",
            f"{len(lignes)} tiers au solde inversé",
            "Un client créditeur, ou un fournisseur débiteur, tient rarement "
            "debout : c'est le plus souvent un règlement saisi deux fois, ou "
            "un acompte qui n'a jamais été lettré avec sa facture.",
            nombre=len(lignes),
            montant=sum(abs(l["solde"]) for l in lignes),
            detail=[f"{l['raison_sociale']} ({l['type']}) : "
                    f"{util.formate_montant(l['solde'])}" for l in lignes[:12]],
            route_ecran="/tiers"))


def _brouillons(societe_id, ex, anomalies):
    n = db.valeur("SELECT COUNT(*) FROM ecritures WHERE exercice_id = ? "
                  "AND validee = 0", (ex["id"],), 0)
    if n:
        anomalies.append(_anomalie(
            "brouillons", "alerte", f"{n} écriture(s) encore en brouillon",
            "Une écriture en brouillon compte déjà dans vos états, mais reste "
            "modifiable. Relisez-la et validez-la : après validation, elle ne "
            "se corrige plus que par extourne, ce qui laisse une trace.",
            nombre=n, route_ecran="/comptabilite/ecritures"))


def _justificatifs(societe_id, ex, anomalies):
    n = db.valeur(
        "SELECT COUNT(*) FROM ecritures e WHERE e.exercice_id = ? "
        "AND NOT EXISTS (SELECT 1 FROM pieces_jointes p "
        "                WHERE p.entite = 'ecriture' AND p.entite_id = e.id)",
        (ex["id"],), 0)
    total = db.valeur("SELECT COUNT(*) FROM ecritures WHERE exercice_id = ?",
                      (ex["id"],), 0)
    if n:
        anomalies.append(_anomalie(
            "justificatifs", "info",
            f"{n} écriture(s) sans justificatif sur {total}",
            "Le jour d'un contrôle, c'est la pièce qu'on demande, pas le "
            "libellé. Vous pouvez rattacher la facture ou le reçu depuis le "
            "détail de chaque écriture.",
            nombre=n,
            route_ecran="/comptabilite/ecritures?sans_piece=1"))


def _lettrage(societe_id, ex, anomalies):
    lignes = db.lignes(
        "SELECT l.compte, COUNT(*) AS n, "
        "  COALESCE(SUM(ABS(l.debit - l.credit)),0) AS montant "
        "FROM lignes l JOIN ecritures e ON e.id = l.ecriture_id "
        "WHERE e.societe_id = ? AND (l.compte LIKE '40%' OR l.compte LIKE '41%') "
        "AND (l.lettrage IS NULL OR l.lettrage = '') "
        "AND julianday(?) - julianday(COALESCE(l.echeance, e.date)) > ? "
        "GROUP BY substr(l.compte,1,2)",
        (societe_id, util.aujourdhui(), JOURS_LETTRAGE))
    total = sum(l["n"] for l in lignes)
    if total:
        anomalies.append(_anomalie(
            "lettrage", "info",
            f"{total} ligne(s) ouvertes depuis plus de {JOURS_LETTRAGE} jours",
            "Une facture non lettrée avec son règlement reste comptée comme "
            "due. Tant qu'elle traîne, la balance des tiers et les relances "
            "disent autre chose que la réalité.",
            nombre=total,
            montant=sum(l["montant"] for l in lignes),
            route_ecran="/comptabilite/lettrage"))


def _tva_declaree(societe_id, ex, anomalies):
    """Ce que disent les comptes, comparé à ce qui a été déclaré.

    Une G50 déposée puis une écriture ajoutée sur le même mois, et les deux
    ne se répondent plus. Personne ne s'en aperçoit avant le contrôle.
    """
    ecarts = []
    for d in db.lignes(
            "SELECT periode, tva_collectee FROM declarations_g50 "
            "WHERE societe_id = ? AND periode >= ? AND periode <= ? "
            "ORDER BY periode",
            (societe_id, ex["date_debut"][:7], ex["date_fin"][:7])):
        # Ce que les opérations du mois ont collecté — l'écriture de
        # liquidation, qui solde le compte de TVA en fin de mois, n'est pas
        # une opération : la compter reviendrait à trouver zéro partout.
        collectee = db.valeur(
            "SELECT COALESCE(SUM(l.credit - l.debit),0) FROM lignes l "
            "JOIN ecritures e ON e.id = l.ecriture_id "
            "WHERE e.societe_id = ? AND l.compte LIKE '4457%' "
            "AND e.date >= ? AND e.date <= ? AND e.perimetre = 'declare' "
            "AND COALESCE(e.source_type,'') NOT IN ('g50','g50_tap')",
            (societe_id, d["periode"] + "-01", util.fin_de_mois(d["periode"])), 0)
        ecart = collectee - d["tva_collectee"]
        if ecart:
            ecarts.append(
                f"{util.libelle_periode(d['periode'])} : déclaré "
                f"{util.formate_montant(d['tva_collectee'])}, comptes "
                f"{util.formate_montant(collectee)} "
                f"(écart {util.formate_montant(ecart)})")
    if ecarts:
        anomalies.append(_anomalie(
            "tva_declaree", "alerte",
            f"{len(ecarts)} déclaration(s) G50 qui ne collent plus aux comptes",
            "La TVA collectée d'une G50 déjà déposée ne correspond plus à "
            "celle des comptes : une écriture a été ajoutée ou modifiée sur "
            "le mois après le dépôt. Il faudra une déclaration rectificative, "
            "ou une correction sur le mois suivant.",
            nombre=len(ecarts), detail=ecarts,
            route_ecran="/fiscalite/g50"))


def _factures_sans_ecriture(societe_id, ex, anomalies):
    lignes = db.lignes(
        "SELECT numero, date, net_a_payer FROM factures "
        "WHERE societe_id = ? AND exercice_id = ? "
        "AND statut NOT IN ('brouillon','annulee') AND ecriture_id IS NULL "
        "ORDER BY date LIMIT 20", (societe_id, ex["id"]))
    if lignes:
        anomalies.append(_anomalie(
            "factures_sans_ecriture", "critique",
            f"{len(lignes)} facture(s) validée(s) sans écriture comptable",
            "Une facture validée doit avoir produit son écriture. Sans elle, "
            "le chiffre d'affaires et la TVA de la période sont sous-évalués.",
            nombre=len(lignes),
            montant=sum(l["net_a_payer"] for l in lignes),
            detail=[f"{l['numero']} du {util.date_fr(l['date'])} — "
                    f"{util.formate_montant(l['net_a_payer'])}" for l in lignes],
            route_ecran="/factures"))


def _sauvegarde(societe_id, ex, anomalies):
    from modules import fichiers
    etat = fichiers.etat_copie_externe()
    if not etat.get("a_rappeler"):
        return
    jours = etat.get("jours")
    anomalies.append(_anomalie(
        "sauvegarde", "alerte",
        "Aucune copie hors de ce poste" if jours is None
        else f"Dernière copie hors du poste il y a {jours} jours",
        "Les sauvegardes vivent sur le même disque que la comptabilité. Une "
        "panne de disque, un vol ou un rançongiciel emporte les deux d'un "
        "coup. Copiez le dossier de sauvegarde sur une clé USB ou un disque "
        "externe — depuis Paramètres, Sauvegarde & données.",
        route_ecran="/parametres/sauvegarde"))


#: Ordre d'exécution : du plus grave au plus anodin.
CONTROLES = [_equilibre, _numerotation, _caisse, _factures_sans_ecriture,
             _tiers_inverses, _tva_declaree, _brouillons, _justificatifs,
             _lettrage, _sauvegarde]

POIDS = {"critique": 0, "alerte": 1, "info": 2}


@route("GET", "/api/sante")
def api_sante(ctx):
    """L'état du dossier, contrôle par contrôle."""
    societe_id = ctx.arg_int("societe")
    ex = compta.exercice(ctx.arg_int("exercice"))
    anomalies: list = []
    for controle in CONTROLES:
        try:
            controle(societe_id, ex, anomalies)
        except Exception as err:                                # noqa: BLE001
            # Un contrôle qui échoue ne doit pas emporter les autres : c'est
            # justement l'écran où l'on vient quand quelque chose cloche.
            anomalies.append(_anomalie(
                f"panne_{controle.__name__.strip('_')}", "info",
                "Un contrôle n'a pas pu s'exécuter",
                f"{controle.__name__} : {err}"))
    anomalies.sort(key=lambda a: POIDS.get(a["niveau"], 3))
    return {
        "exercice": {"id": ex["id"], "libelle": ex["libelle"],
                     "date_debut": ex["date_debut"], "date_fin": ex["date_fin"]},
        "anomalies": anomalies,
        "controles": len(CONTROLES),
        "critiques": sum(1 for a in anomalies if a["niveau"] == "critique"),
        "alertes": sum(1 for a in anomalies if a["niveau"] == "alerte"),
    }
