"""États financiers du SCF : bilan, compte de résultat (TCR) par nature et
tableau des flux de trésorerie.

La ventilation repose sur les numéros de comptes de la nomenclature SCF.
Les comptes « mixtes » (467, 445, 512…) sont affectés à l'actif ou au passif
selon le sens de leur solde, comme le veut la présentation réglementaire.
"""

from __future__ import annotations

from noyau import base as db
from noyau import util
from noyau import tableur
from noyau.serveur import ErreurApplicative, route, Reponse
from modules import comptabilite as compta

# ---------------------------------------------------------------------------
# Structure du bilan : (libellé, préfixes inclus, préfixes exclus, sens attendu)
#   sens : "debiteur" (actif), "crediteur" (passif), None = les deux
# ---------------------------------------------------------------------------

ACTIF = [
    ("actif_non_courant", "ACTIFS NON COURANTS", [
        ("Écart d'acquisition (goodwill)", ["207"], [], None),
        ("Immobilisations incorporelles", ["20"], ["207"], None),
        ("Amortissement des immobilisations incorporelles", ["280", "290"], [], None),
        ("Terrains", ["211", "212"], [], None),
        ("Bâtiments", ["213"], [], None),
        ("Autres immobilisations corporelles", ["215", "218", "22"], [], None),
        ("Amortissements et pertes de valeur des corporelles",
         ["281", "282", "291", "292"], [], None),
        ("Immobilisations en cours", ["23"], [], None),
        ("Titres mis en équivalence", ["265"], [], None),
        ("Autres participations et créances rattachées", ["261", "262", "266"], [], None),
        ("Autres titres immobilisés", ["271", "272", "273"], [], None),
        ("Prêts et autres actifs financiers non courants",
         ["274", "275", "276"], [], None),
        ("Impôts différés actif", ["133"], [], None),
    ]),
    ("actif_courant", "ACTIFS COURANTS", [
        ("Stocks et en-cours", ["3"], [], None),
        ("Clients", ["411", "413", "416", "417", "418", "491"], [], None),
        ("Autres débiteurs", ["409", "425", "462", "465", "486", "471"], [], "debiteur"),
        ("Comptes de tiers débiteurs (mandants, divers)", ["467"], [], "debiteur"),
        ("Impôts et assimilés", ["441", "4441", "4456", "44567", "443"], [], "debiteur"),
        ("Placements et autres actifs financiers courants", ["50"], [], None),
        ("Trésorerie", ["51", "53", "54", "58"], ["519"], "debiteur"),
    ]),
]

PASSIF = [
    ("capitaux_propres", "CAPITAUX PROPRES", [
        ("Capital émis", ["101"], [], None),
        ("Capital non appelé", ["109"], [], None),
        ("Primes et réserves", ["103", "106"], [], None),
        ("Écarts de réévaluation", ["104", "105"], [], None),
        ("Écart d'équivalence", ["107"], [], None),
        ("Résultat net de l'exercice", ["12"], [], None),
        ("Report à nouveau", ["11", "108"], [], None),
    ]),
    ("passif_non_courant", "PASSIFS NON COURANTS", [
        ("Emprunts et dettes financières", ["16", "17"], [], None),
        ("Impôts différés et provisionnés", ["134", "155"], [], None),
        ("Provisions et produits constatés d'avance",
         ["153", "156", "158", "131", "132", "138"], [], None),
    ]),
    ("passif_courant", "PASSIFS COURANTS", [
        ("Fournisseurs et comptes rattachés", ["401", "403", "404", "405", "408"], [], None),
        ("Impôts", ["442", "444", "445", "447"], ["4441", "4456", "44567"], "crediteur"),
        ("Avances et acomptes reçus des clients", ["419"], [], None),
        ("Personnel et organismes sociaux", ["42", "43"], ["425"], "crediteur"),
        ("Associés et groupe", ["45"], [], "crediteur"),
        ("Autres dettes (mandants, dépôts, divers)",
         ["467", "468", "487", "464"], [], "crediteur"),
        ("Trésorerie passif", ["519"], [], None),
    ]),
]


def _soldes(societe_id: int, date_debut: str, date_fin: str) -> dict[str, int]:
    return {
        r["compte"]: r["debit"] - r["credit"]
        for r in compta.soldes_par_compte(societe_id, date_debut, date_fin)
    }


def _agrege(soldes: dict[str, int], prefixes, exclus, sens) -> int:
    total = 0
    for compte, solde in soldes.items():
        if not any(compte.startswith(p) for p in prefixes):
            continue
        if exclus and any(compte.startswith(p) for p in exclus):
            continue
        if sens == "debiteur" and solde <= 0:
            continue
        if sens == "crediteur" and solde >= 0:
            continue
        total += solde
    return total


def construit_bilan(societe_id: int, date_debut: str, date_fin: str) -> dict:
    soldes = _soldes(societe_id, date_debut, date_fin)

    resultat = _resultat(soldes)
    # Le résultat de l'exercice n'est viré en compte 12 qu'à la clôture :
    # tant qu'il ne l'est pas, on l'affiche pour que le bilan s'équilibre.
    resultat_deja_vire = -sum(s for c, s in soldes.items() if c.startswith("12"))

    sections_actif = []
    total_actif = 0
    for cle, titre, postes in ACTIF:
        lignes_section = []
        for libelle, prefixes, exclus, sens in postes:
            montant = _agrege(soldes, prefixes, exclus, sens)
            if montant:
                lignes_section.append({"libelle": libelle, "montant": montant})
        sous_total = sum(l["montant"] for l in lignes_section)
        total_actif += sous_total
        sections_actif.append({"cle": cle, "titre": titre, "lignes": lignes_section,
                               "total": sous_total})

    sections_passif = []
    total_passif = 0
    for cle, titre, postes in PASSIF:
        lignes_section = []
        for libelle, prefixes, exclus, sens in postes:
            montant = -_agrege(soldes, prefixes, exclus, sens)
            if libelle == "Résultat net de l'exercice" and not resultat_deja_vire:
                montant = resultat
            if montant:
                lignes_section.append({"libelle": libelle, "montant": montant})
        sous_total = sum(l["montant"] for l in lignes_section)
        total_passif += sous_total
        sections_passif.append({"cle": cle, "titre": titre, "lignes": lignes_section,
                                "total": sous_total})

    return {
        "date_debut": date_debut, "date_fin": date_fin,
        "actif": sections_actif, "total_actif": total_actif,
        "passif": sections_passif, "total_passif": total_passif,
        "ecart": total_actif - total_passif,
        "equilibre": total_actif == total_passif,
        "resultat": resultat,
    }


def _resultat(soldes: dict[str, int]) -> int:
    produits = -sum(s for c, s in soldes.items() if c.startswith("7"))
    charges = sum(s for c, s in soldes.items() if c.startswith("6"))
    return produits - charges


# ---------------------------------------------------------------------------
# Compte de résultat (TCR) par nature
# ---------------------------------------------------------------------------

TCR = [
    ("produit", "Chiffre d'affaires", ["70"], []),
    ("produit", "Variation des stocks produits finis et en cours", ["72"], []),
    ("produit", "Production immobilisée", ["73"], []),
    ("produit", "Subventions d'exploitation", ["74"], []),
    ("total", "I. PRODUCTION DE L'EXERCICE", [], []),
    ("charge", "Achats consommés", ["60"], []),
    ("charge", "Services extérieurs et autres consommations", ["61", "62"], []),
    ("total", "II. CONSOMMATION DE L'EXERCICE", [], []),
    ("solde", "III. VALEUR AJOUTÉE D'EXPLOITATION (I − II)", [], []),
    ("charge", "Charges de personnel", ["63"], []),
    ("charge", "Impôts, taxes et versements assimilés", ["64"], []),
    ("solde", "IV. EXCÉDENT BRUT D'EXPLOITATION", [], []),
    ("produit", "Autres produits opérationnels", ["75"], []),
    ("charge", "Autres charges opérationnelles", ["65"], []),
    ("charge", "Dotations aux amortissements, provisions et pertes de valeur",
     ["68"], ["686"]),
    ("produit", "Reprises sur pertes de valeur et provisions", ["78"], ["786"]),
    ("solde", "V. RÉSULTAT OPÉRATIONNEL", [], []),
    ("produit", "Produits financiers", ["76", "786"], []),
    ("charge", "Charges financières", ["66", "686"], []),
    ("solde", "VI. RÉSULTAT FINANCIER", [], []),
    ("solde", "VII. RÉSULTAT ORDINAIRE AVANT IMPÔTS (V + VI)", [], []),
    ("charge", "Impôts exigibles sur résultats ordinaires", ["695", "698"], []),
    ("charge", "Impôts différés sur résultats ordinaires", ["692", "693"], []),
    ("solde", "VIII. RÉSULTAT NET DE L'EXERCICE", [], []),
]


def construit_tcr(societe_id: int, date_debut: str, date_fin: str) -> dict:
    soldes = _soldes(societe_id, date_debut, date_fin)

    def montant_produit(prefixes, exclus):
        return -_agrege(soldes, prefixes, exclus, None)

    def montant_charge(prefixes, exclus):
        return _agrege(soldes, prefixes, exclus, None)

    lignes = []
    production = consommation = 0
    valeur_ajoutee = ebe = resultat_operationnel = 0
    produits_financiers = charges_financieres = 0
    resultat_ordinaire = impots = 0

    for genre, libelle, prefixes, exclus in TCR:
        if genre == "produit":
            montant = montant_produit(prefixes, exclus)
            if libelle in ("Chiffre d'affaires",
                           "Variation des stocks produits finis et en cours",
                           "Production immobilisée", "Subventions d'exploitation"):
                production += montant
            elif libelle == "Autres produits opérationnels":
                resultat_operationnel += montant
            elif libelle == "Reprises sur pertes de valeur et provisions":
                resultat_operationnel += montant
            elif libelle == "Produits financiers":
                produits_financiers = montant
            lignes.append({"libelle": libelle, "montant": montant, "genre": "produit"})
        elif genre == "charge":
            montant = montant_charge(prefixes, exclus)
            if libelle in ("Achats consommés",
                           "Services extérieurs et autres consommations"):
                consommation += montant
            elif libelle in ("Charges de personnel",
                             "Impôts, taxes et versements assimilés"):
                ebe -= montant
            elif libelle in ("Autres charges opérationnelles",
                             "Dotations aux amortissements, provisions et pertes de valeur"):
                resultat_operationnel -= montant
            elif libelle == "Charges financières":
                charges_financieres = montant
            elif libelle.startswith("Impôts"):
                impots += montant
            lignes.append({"libelle": libelle, "montant": montant, "genre": "charge"})
        elif genre == "total":
            if libelle.startswith("I."):
                lignes.append({"libelle": libelle, "montant": production, "genre": "total"})
            else:
                lignes.append({"libelle": libelle, "montant": consommation,
                               "genre": "total"})
        else:  # solde
            if libelle.startswith("III."):
                valeur_ajoutee = production - consommation
                valeur = valeur_ajoutee
            elif libelle.startswith("IV."):
                ebe = valeur_ajoutee + ebe
                valeur = ebe
            elif libelle.startswith("V."):
                resultat_operationnel = ebe + resultat_operationnel
                valeur = resultat_operationnel
            elif libelle.startswith("VI."):
                valeur = produits_financiers - charges_financieres
            elif libelle.startswith("VII."):
                resultat_ordinaire = resultat_operationnel + produits_financiers - charges_financieres
                valeur = resultat_ordinaire
            else:
                valeur = resultat_ordinaire - impots
            lignes.append({"libelle": libelle, "montant": valeur, "genre": "solde"})

    return {
        "date_debut": date_debut, "date_fin": date_fin, "lignes": lignes,
        "production": production, "consommation": consommation,
        "valeur_ajoutee": valeur_ajoutee, "ebe": ebe,
        "resultat_operationnel": resultat_operationnel,
        "resultat_financier": produits_financiers - charges_financieres,
        "resultat_net": resultat_ordinaire - impots,
    }


# ---------------------------------------------------------------------------
# Tableau des flux de trésorerie (méthode indirecte)
# ---------------------------------------------------------------------------

# Partition exhaustive et disjointe du plan comptable entre les trois flux.
# Chaque compte appartient à un et un seul groupe : le tableau s'articule alors
# exactement avec la variation de trésorerie, sans écart d'arrondi possible.
FLUX_TRESORERIE = (["5"], ["59"])
FLUX_INVESTISSEMENT = (["20", "21", "22", "23", "24", "25", "26", "27"], [])
FLUX_FINANCEMENT = (["1"], [])
FLUX_EXPLOITATION = (["28", "29", "3", "4", "59", "6", "7"], [])


def construit_flux(societe_id: int, date_debut: str, date_fin: str) -> dict:
    soldes = _soldes(societe_id, date_debut, date_fin)

    def variation(prefixes, exclus=()):
        return _agrege(soldes, list(prefixes), list(exclus), None)

    # Un flux de trésorerie est l'opposé de la variation des comptes concernés.
    exploitation = -variation(*FLUX_EXPLOITATION)
    investissement = -variation(*FLUX_INVESTISSEMENT)
    financement = -variation(*FLUX_FINANCEMENT)
    variation_tresorerie = variation(*FLUX_TRESORERIE)

    # Détail de l'exploitation (la somme des lignes redonne le flux)
    resultat = -variation(["6", "7"])
    dotations_nettes = -variation(["28", "29"])
    var_stocks = -variation(["3"])
    var_fournisseurs = -variation(["40"])
    var_clients = -variation(["41"])
    var_personnel = -variation(["42", "43"])
    var_fiscal = -variation(["44"])
    var_autres_tiers = -variation(["45", "46", "47", "48", "49"])
    var_provisions = -variation(["59"])

    tresorerie_debut = 0
    if date_debut:
        avant = compta.soldes_par_compte(societe_id, "0001-01-01", _veille(date_debut))
        tresorerie_debut = sum(
            r["debit"] - r["credit"] for r in avant
            if r["compte"][0] == "5" and not r["compte"].startswith("59")
        )

    return {
        "resultat_net": resultat,
        "dotations": dotations_nettes,
        "variation_stocks": var_stocks,
        "variation_fournisseurs": var_fournisseurs,
        "variation_clients": var_clients,
        "variation_personnel": var_personnel,
        "variation_fiscal": var_fiscal,
        "variation_autres_tiers": var_autres_tiers,
        "variation_provisions": var_provisions,
        "flux_exploitation": exploitation,
        "acquisitions_immobilisations": -variation(["20", "21", "22", "23"]),
        "immobilisations_financieres": -variation(["24", "25", "26", "27"]),
        "flux_investissement": investissement,
        "variation_capitaux_propres": -variation(["10", "11", "12"]),
        "variation_subventions_provisions": -variation(["13", "14", "15"]),
        "variation_emprunts": -variation(["16", "17", "18", "19"]),
        "flux_financement": financement,
        "variation_tresorerie": variation_tresorerie,
        "tresorerie_ouverture": tresorerie_debut,
        "tresorerie_cloture": tresorerie_debut + variation_tresorerie,
        "controle": (exploitation + investissement + financement
                     - variation_tresorerie),
    }


def _veille(date: str) -> str:
    import datetime
    return (datetime.date.fromisoformat(date[:10]) - datetime.timedelta(days=1)).isoformat()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@route("GET", "/api/etats/bilan")
def api_bilan(ctx):
    societe_id = ctx.arg_int("societe")
    ex = compta.exercice(ctx.arg_int("exercice"))
    du = ctx.arg("du") or ex["date_debut"]
    au = ctx.arg("au") or ex["date_fin"]
    resultat = construit_bilan(societe_id, du, au)
    resultat["societe"] = compta.societe(societe_id)
    resultat["exercice"] = ex
    return resultat


@route("GET", "/api/etats/tcr")
def api_tcr(ctx):
    societe_id = ctx.arg_int("societe")
    ex = compta.exercice(ctx.arg_int("exercice"))
    du = ctx.arg("du") or ex["date_debut"]
    au = ctx.arg("au") or ex["date_fin"]
    resultat = construit_tcr(societe_id, du, au)
    resultat["societe"] = compta.societe(societe_id)
    resultat["exercice"] = ex
    return resultat


@route("GET", "/api/etats/flux")
def api_flux(ctx):
    societe_id = ctx.arg_int("societe")
    ex = compta.exercice(ctx.arg_int("exercice"))
    du = ctx.arg("du") or ex["date_debut"]
    au = ctx.arg("au") or ex["date_fin"]
    resultat = construit_flux(societe_id, du, au)
    resultat["societe"] = compta.societe(societe_id)
    resultat["exercice"] = ex
    return resultat


@route("GET", "/api/etats/comparatif")
def api_comparatif(ctx):
    """Compare les principaux agrégats entre deux exercices."""
    societe_id = ctx.arg_int("societe")
    ex = compta.exercice(ctx.arg_int("exercice"))
    precedent = db.ligne(
        "SELECT * FROM exercices WHERE societe_id = ? AND date_fin < ? "
        "ORDER BY date_fin DESC LIMIT 1", (societe_id, ex["date_debut"])
    )
    courant = construit_tcr(societe_id, ex["date_debut"], ex["date_fin"])
    resultat = {"exercice": ex, "courant": courant}
    if precedent:
        resultat["precedent_exercice"] = precedent
        resultat["precedent"] = construit_tcr(societe_id, precedent["date_debut"],
                                              precedent["date_fin"])
    return resultat


@route("GET", "/api/export/etats-financiers")
def api_export_etats(ctx):
    """Liasse : bilan, TCR et flux de trésorerie dans un même classeur."""
    societe_id = ctx.arg_int("societe")
    ex = compta.exercice(ctx.arg_int("exercice"))
    soc = compta.societe(societe_id)
    du, au = ex["date_debut"], ex["date_fin"]

    bilan = construit_bilan(societe_id, du, au)
    tcr = construit_tcr(societe_id, du, au)
    flux = construit_flux(societe_id, du, au)

    classeur = tableur.Classeur()

    entete = [
        (soc["raison_sociale"], ""),
        (f"NIF : {soc['nif'] or '—'}", f"RC : {soc['rc'] or '—'}"),
        (f"Exercice : {ex['libelle']}",
         f"Du {util.date_fr(du)} au {util.date_fr(au)}"),
    ]

    f = classeur.feuille("Bilan")
    f.titre("BILAN — ACTIF")
    for gauche, droite in entete:
        f.ajoute(tableur.texte(gauche), tableur.texte(droite))
    f.vide()
    f.entetes("Rubrique", "Montant (net)")
    f.largeurs_auto(62, 22)
    for section in bilan["actif"]:
        f.ajoute(tableur.texte(section["titre"], tableur.GRAS))
        for l in section["lignes"]:
            f.ajoute(tableur.texte("   " + l["libelle"]), tableur.monnaie(l["montant"]))
        f.ajoute(tableur.texte("   Total " + section["titre"].lower(), tableur.GRAS),
                 tableur.monnaie(section["total"], gras=True))
    f.ajoute(tableur.texte("TOTAL GÉNÉRAL ACTIF", tableur.GRAS),
             tableur.monnaie(bilan["total_actif"], total=True))
    f.vide(2)
    f.titre("BILAN — PASSIF")
    f.entetes("Rubrique", "Montant")
    for section in bilan["passif"]:
        f.ajoute(tableur.texte(section["titre"], tableur.GRAS))
        for l in section["lignes"]:
            f.ajoute(tableur.texte("   " + l["libelle"]), tableur.monnaie(l["montant"]))
        f.ajoute(tableur.texte("   Total " + section["titre"].lower(), tableur.GRAS),
                 tableur.monnaie(section["total"], gras=True))
    f.ajoute(tableur.texte("TOTAL GÉNÉRAL PASSIF", tableur.GRAS),
             tableur.monnaie(bilan["total_passif"], total=True))
    if not bilan["equilibre"]:
        f.vide()
        f.ajoute(tableur.texte("⚠ ÉCART ACTIF/PASSIF", tableur.GRAS),
                 tableur.monnaie(bilan["ecart"], gras=True))

    f2 = classeur.feuille("Compte de résultat")
    f2.titre("COMPTE DE RÉSULTAT (par nature)")
    for gauche, droite in entete:
        f2.ajoute(tableur.texte(gauche), tableur.texte(droite))
    f2.vide()
    f2.entetes("Libellé", "Montant")
    f2.largeurs_auto(62, 22)
    for l in tcr["lignes"]:
        style = tableur.GRAS if l["genre"] in ("total", "solde") else tableur.NORMAL
        f2.ajoute(tableur.texte(l["libelle"], style),
                  tableur.monnaie(l["montant"], gras=(style == tableur.GRAS)))

    f3 = classeur.feuille("Flux de trésorerie")
    f3.titre("TABLEAU DES FLUX DE TRÉSORERIE (méthode indirecte)")
    f3.vide()
    f3.entetes("Libellé", "Montant")
    f3.largeurs_auto(62, 22)
    for libelle, cle, gras in [
        ("Résultat net de l'exercice", "resultat_net", False),
        ("+ Dotations aux amortissements et pertes de valeur", "dotations", False),
        ("Variation des stocks et en-cours", "variation_stocks", False),
        ("Variation des créances clients", "variation_clients", False),
        ("Variation des dettes fournisseurs", "variation_fournisseurs", False),
        ("Variation des dettes de personnel et sociales", "variation_personnel", False),
        ("Variation des dettes et créances fiscales", "variation_fiscal", False),
        ("Variation des autres comptes de tiers", "variation_autres_tiers", False),
        ("FLUX NET DE TRÉSORERIE DES ACTIVITÉS OPÉRATIONNELLES",
         "flux_exploitation", True),
        ("Acquisitions d'immobilisations", "acquisitions_immobilisations", False),
        ("Immobilisations financières", "immobilisations_financieres", False),
        ("FLUX NET DE TRÉSORERIE DES ACTIVITÉS D'INVESTISSEMENT",
         "flux_investissement", True),
        ("Variation des capitaux propres", "variation_capitaux_propres", False),
        ("Variation des subventions et provisions", "variation_subventions_provisions", False),
        ("Variation des emprunts", "variation_emprunts", False),
        ("FLUX NET DE TRÉSORERIE DES ACTIVITÉS DE FINANCEMENT",
         "flux_financement", True),
        ("VARIATION DE TRÉSORERIE DE LA PÉRIODE", "variation_tresorerie", True),
        ("Trésorerie à l'ouverture", "tresorerie_ouverture", False),
        ("Trésorerie à la clôture", "tresorerie_cloture", True),
    ]:
        f3.ajoute(tableur.texte(libelle, tableur.GRAS if gras else tableur.NORMAL),
                  tableur.monnaie(flux[cle], gras=gras))

    return Reponse(classeur.octets(),
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   f"etats_financiers_{soc['code']}_{ex['libelle']}.xlsx")
