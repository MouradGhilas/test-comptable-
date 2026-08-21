"""Déclarations de début d'année : DAS et état des clients.

Deux documents que rien n'aidait à produire, et qui coûtent plusieurs jours
chaque janvier : la déclaration annuelle des salaires (série G n° 29) et
l'état des clients annexé à la déclaration annuelle de résultat.

Les deux se déduisent entièrement de ce qui est déjà saisi — bulletins de
paie d'un côté, factures de vente de l'autre. Le travail n'est pas de les
remplir, c'est de les recouper : chacun est livré avec le contrôle qui dit
si les douze mois déclarés correspondent bien à l'année.

Dates limites et seuils viennent de `reference/parametres_fiscaux.json` et
sont, comme tous les paramètres fiscaux, **à vérifier** contre la loi de
finances de l'année.
"""

from __future__ import annotations

from noyau import base as db
from noyau import tableur
from noyau import util
from noyau.serveur import ErreurApplicative, route, Reponse
from modules import comptabilite as compta

#: Périmètre d'une déclaration : le déclaré, jamais autre chose.
PERIMETRE = "declare"

COMPTE_IRG_SALAIRES = "4421"


def _annee(ctx) -> int:
    annee = ctx.arg_int("annee")
    if not annee:
        ex = db.ligne("SELECT date_debut FROM exercices WHERE id = ?",
                      (ctx.arg_int("exercice"),))
        annee = int((ex["date_debut"] if ex else util.aujourdhui())[:4])
    return annee


def _date_limite_das(annee: int) -> str | None:
    brut = db.parametre_fiscal(annee, "das_date_limite")
    if not brut:
        return None
    brut = str(brut)
    return brut if len(brut) == 10 else f"{annee + 1}-{brut}"


def declaration_salaires(societe_id: int, annee: int) -> dict:
    """Le récapitulatif annuel des salaires, salarié par salarié."""
    soc = compta.societe(societe_id)
    debut, fin = f"{annee}-01", f"{annee}-12"

    salaries = db.lignes(
        "SELECT s.matricule, s.nom, s.prenom, s.num_secu, s.poste, "
        "       s.date_embauche, s.date_sortie, "
        "       COUNT(b.id) AS mois, "
        "       COALESCE(SUM(b.salaire_brut),0) AS brut, "
        "       COALESCE(SUM(b.base_cnas),0) AS base_cnas, "
        "       COALESCE(SUM(b.cnas_salarie),0) AS cnas_salarie, "
        "       COALESCE(SUM(b.cnas_patronale),0) AS cnas_patronale, "
        "       COALESCE(SUM(b.base_irg),0) AS base_irg, "
        "       COALESCE(SUM(b.irg),0) AS irg, "
        "       COALESCE(SUM(b.net_a_payer),0) AS net, "
        "       COALESCE(SUM(b.cout_employeur),0) AS cout_employeur "
        "FROM bulletins b JOIN salaries s ON s.id = b.salarie_id "
        "WHERE b.societe_id = ? AND b.periode >= ? AND b.periode <= ? "
        "GROUP BY s.id ORDER BY s.nom, s.prenom",
        (societe_id, debut, fin))

    champs = ("brut", "base_cnas", "cnas_salarie", "cnas_patronale",
              "base_irg", "irg", "net", "cout_employeur")
    totaux = {c: sum(s[c] for s in salaries) for c in champs}
    totaux["mois"] = sum(s["mois"] for s in salaries)

    # -- Le recoupement : douze G50 déposées doivent porter le même IRG que
    # -- les bulletins de l'année, et les comptes doivent dire pareil.
    irg_g50 = db.valeur(
        "SELECT COALESCE(SUM(irg_salaires),0) FROM declarations_g50 "
        "WHERE societe_id = ? AND periode >= ? AND periode <= ?",
        (societe_id, debut, fin), 0)
    irg_comptes = db.valeur(
        "SELECT COALESCE(SUM(l.credit - l.debit),0) FROM lignes l "
        "JOIN ecritures e ON e.id = l.ecriture_id "
        "WHERE e.societe_id = ? AND l.compte LIKE ? "
        "AND substr(e.date,1,4) = ? AND e.perimetre = ? "
        "AND COALESCE(e.source_type,'') NOT IN ('g50','g50_tap')",
        (societe_id, COMPTE_IRG_SALAIRES + "%", str(annee), PERIMETRE), 0)
    mois_declares = db.valeur(
        "SELECT COUNT(*) FROM declarations_g50 WHERE societe_id = ? "
        "AND periode >= ? AND periode <= ?", (societe_id, debut, fin), 0)

    return {
        "annee": annee,
        "societe": soc,
        # Le paramètre est un jour dans l'année (« 04-30 ») : la DAS d'une
        # année se dépose l'année suivante.
        "date_limite": _date_limite_das(annee),
        "salaries": salaries,
        "totaux": totaux,
        "controle": {
            "irg_bulletins": totaux["irg"],
            "irg_g50": irg_g50,
            "irg_comptes": irg_comptes,
            "ecart_g50": totaux["irg"] - irg_g50,
            "ecart_comptes": totaux["irg"] - irg_comptes,
            "mois_declares": mois_declares,
        },
    }


def etat_clients(societe_id: int, annee: int, seuil: int = 0) -> dict:
    """Les ventes de l'année, client par client.

    Établi sur les factures de vente, qui portent l'identité fiscale du
    client. Le total est recoupé avec les comptes de produits : une vente
    passée directement en écriture n'a pas de facture, et manquerait donc
    à l'état sans que rien ne le dise.
    """
    soc = compta.societe(societe_id)
    lignes = db.lignes(
        "SELECT t.id AS tiers_id, t.raison_sociale, t.nif, t.nis, t.rc, "
        "       t.article_imposition, t.adresse, t.commune, t.wilaya, "
        "       COUNT(f.id) AS nb_factures, "
        "       COALESCE(SUM(f.montant_ht),0) AS ht, "
        "       COALESCE(SUM(f.montant_tva),0) AS tva, "
        "       COALESCE(SUM(f.montant_ttc),0) AS ttc "
        "FROM factures f LEFT JOIN tiers t ON t.id = f.tiers_id "
        "WHERE f.societe_id = ? AND substr(f.date,1,4) = ? "
        "AND f.sens = 'vente' AND f.statut NOT IN ('brouillon','annulee') "
        "AND f.perimetre = ? "
        "GROUP BY t.id ORDER BY ttc DESC",
        (societe_id, str(annee), PERIMETRE))
    retenus = [l for l in lignes if l["ttc"] >= seuil] if seuil else lignes
    ecartes = len(lignes) - len(retenus)

    ca_comptes = db.valeur(
        "SELECT COALESCE(SUM(l.credit - l.debit),0) FROM lignes l "
        "JOIN ecritures e ON e.id = l.ecriture_id "
        "WHERE e.societe_id = ? AND l.compte LIKE '70%' "
        "AND substr(e.date,1,4) = ? AND e.perimetre = ?",
        (societe_id, str(annee), PERIMETRE), 0)
    total_ht = sum(l["ht"] for l in lignes)

    sans_identite = [l["raison_sociale"] or "(client non renseigné)"
                     for l in retenus if not l["nif"]]
    return {
        "annee": annee,
        "societe": soc,
        "seuil": seuil,
        "clients": retenus,
        "ecartes": ecartes,
        "totaux": {
            "ht": sum(l["ht"] for l in retenus),
            "tva": sum(l["tva"] for l in retenus),
            "ttc": sum(l["ttc"] for l in retenus),
            "nb_factures": sum(l["nb_factures"] for l in retenus),
        },
        "controle": {
            "ht_factures": total_ht,
            "ca_comptes": ca_comptes,
            "ecart": total_ht - ca_comptes,
            "sans_nif": sans_identite,
        },
    }


@route("GET", "/api/declarations/das")
def api_das(ctx):
    return declaration_salaires(ctx.arg_int("societe"), _annee(ctx))


@route("GET", "/api/declarations/etat-clients")
def api_etat_clients(ctx):
    return etat_clients(ctx.arg_int("societe"), _annee(ctx),
                        util.centimes(ctx.arg("seuil") or 0))


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

@route("GET", "/api/export/das")
def api_export_das(ctx):
    d = declaration_salaires(ctx.arg_int("societe"), _annee(ctx))
    soc = d["societe"]
    classeur = tableur.Classeur()
    f = classeur.feuille("DAS")
    f.titre(f"{soc['raison_sociale']} — Déclaration annuelle des salaires "
            f"{d['annee']}")
    f.ajoute(tableur.texte(
        f"NIF {soc.get('nif') or '—'} · à déposer avant le "
        f"{util.date_fr(d['date_limite']) if d['date_limite'] else '(à vérifier)'}"))
    f.vide()
    f.entetes("Matricule", "Nom", "Prénom", "N° sécurité sociale", "Poste",
              "Embauche", "Sortie", "Mois payés", "Brut", "Base CNAS",
              "CNAS salarié", "Base IRG", "IRG retenu", "Net payé",
              "Coût employeur")
    f.largeurs_auto(12, 20, 18, 20, 22, 12, 12, 11, 15, 15, 15, 15, 15, 15, 15)
    for s in d["salaries"]:
        f.ajoute(
            tableur.texte(s["matricule"]), tableur.texte(s["nom"]),
            tableur.texte(s["prenom"]), tableur.texte(s["num_secu"] or ""),
            tableur.texte(s["poste"] or ""),
            tableur.date_cel(s["date_embauche"] or ""),
            tableur.date_cel(s["date_sortie"] or ""),
            tableur.texte(str(s["mois"])),
            tableur.monnaie(s["brut"]), tableur.monnaie(s["base_cnas"]),
            tableur.monnaie(s["cnas_salarie"]), tableur.monnaie(s["base_irg"]),
            tableur.monnaie(s["irg"]), tableur.monnaie(s["net"]),
            tableur.monnaie(s["cout_employeur"]))
    t = d["totaux"]
    f.ajoute(tableur.texte("TOTAL", tableur.GRAS), *[tableur.texte("")] * 6,
             tableur.texte(str(t["mois"])),
             *[tableur.monnaie(t[c], total=True) for c in
               ("brut", "base_cnas", "cnas_salarie", "base_irg", "irg", "net",
                "cout_employeur")])
    return Reponse(classeur.octets(),
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   f"das_{soc['code']}_{d['annee']}.xlsx")


@route("GET", "/api/export/etat-clients")
def api_export_etat_clients(ctx):
    d = etat_clients(ctx.arg_int("societe"), _annee(ctx),
                     util.centimes(ctx.arg("seuil") or 0))
    soc = d["societe"]
    classeur = tableur.Classeur()
    f = classeur.feuille("État des clients")
    f.titre(f"{soc['raison_sociale']} — État des clients {d['annee']}")
    f.ajoute(tableur.texte(f"NIF {soc.get('nif') or '—'} · "
                           f"{len(d['clients'])} client(s)"))
    f.vide()
    f.entetes("Client", "NIF", "NIS", "RC", "Article d'imposition", "Adresse",
              "Commune", "Wilaya", "Factures", "Montant HT", "TVA",
              "Montant TTC")
    f.largeurs_auto(34, 20, 20, 20, 20, 34, 18, 18, 10, 16, 16, 16)
    for c in d["clients"]:
        f.ajoute(
            tableur.texte(c["raison_sociale"] or ""), tableur.texte(c["nif"] or ""),
            tableur.texte(c["nis"] or ""), tableur.texte(c["rc"] or ""),
            tableur.texte(c["article_imposition"] or ""),
            tableur.texte(c["adresse"] or ""), tableur.texte(c["commune"] or ""),
            tableur.texte(c["wilaya"] or ""), tableur.texte(str(c["nb_factures"])),
            tableur.monnaie(c["ht"]), tableur.monnaie(c["tva"]),
            tableur.monnaie(c["ttc"]))
    t = d["totaux"]
    f.ajoute(tableur.texte("TOTAL", tableur.GRAS), *[tableur.texte("")] * 7,
             tableur.texte(str(t["nb_factures"])),
             tableur.monnaie(t["ht"], total=True),
             tableur.monnaie(t["tva"], total=True),
             tableur.monnaie(t["ttc"], total=True))
    return Reponse(classeur.octets(),
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   f"etat_clients_{soc['code']}_{d['annee']}.xlsx")
