#!/usr/bin/env python3
"""Crée un dossier de démonstration complet, pour découvrir l'application.

Génère une année d'activité réaliste : agence (mandats, ventes, baux, loyers)
et promotion (programme de 24 logements, contrats VSP, chantier), avec la
comptabilité correspondante.

    python3 outils/donnees_demonstration.py                  # dossier par défaut
    python3 outils/donnees_demonstration.py --donnees /chemin

⚠️ Ces données sont fictives. Créez un dossier séparé pour votre comptabilité réelle.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

#: Lancé directement, le script accepte --donnees et ouvre lui-même la base.
#: Importé par l'application — pour créer le jeu d'essai depuis l'interface —
#: il ne touche ni aux arguments de la ligne de commande, qui sont ceux du
#: serveur, ni à la base, déjà ouverte.
AUTONOME = __name__ == "__main__"

import noyau.config as module_config                                    # noqa: E402
if AUTONOME:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("--donnees", help="dossier de données")
    arguments = analyseur.parse_args()
    if arguments.donnees:
        module_config.config = module_config.Configuration(
            {"dossier_donnees": arguments.donnees})

from noyau import base as db                                            # noqa: E402
from noyau import util                                                  # noqa: E402
from noyau.serveur import hache_mot_de_passe                            # noqa: E402

if AUTONOME:
    db.initialise()

from modules import systeme, comptabilite as compta, promotion, agence  # noqa: E402
from modules import tiers as mod_tiers, facturation, paie, immobilisations  # noqa: E402
from modules import fiscalite                                           # noqa: E402

ANNEE = int(util.aujourdhui()[:4])


class Ctx:
    """Contexte d'appel minimal, équivalent d'une requête authentifiée."""

    def __init__(self, corps=None, requete=None, params=None):
        self.corps = corps or {}
        self.requete = {c: [str(v)] for c, v in (requete or {}).items()}
        self.params = params or {}
        self.utilisateur = {"id": 1, "identifiant": "demo", "role": "admin"}

    nom_utilisateur = "demo"

    def arg(self, n, d=None):
        v = self.requete.get(n)
        return v[0] if v else d

    def arg_int(self, n, d=None):
        v = self.arg(n)
        return int(v) if v not in (None, "") else d

    def champ(self, n, d=None):
        return self.corps.get(n, d)

    def champ_requis(self, n):
        return self.corps[n]

    def montant(self, n, d=0):
        return util.centimes(self.corps.get(n, d))

    def taux(self, n, d=0):
        v = self.corps.get(n)
        return util.vers_taux(v) if v not in (None, "") else d

    def entier(self, n, d=None):
        v = self.corps.get(n)
        return int(v) if v not in (None, "") else d

    def booleen(self, n, d=False):
        v = self.corps.get(n, d)
        return 1 if (v is True or str(v).lower() in {"1", "true", "oui"}) else 0

    def date(self, n, d=None):
        return util.date_iso(self.corps.get(n), d)

    def exige_role(self, *r):
        pass

    def interdit_lecture_seule(self):
        pass


def etape(texte):
    print(f"  → {texte}")


def construire():
    existant = db.ligne("SELECT id FROM societes WHERE code = 'DEMO'")
    if existant:
        print("Le dossier de démonstration existe déjà. Rien à faire.")
        return existant["id"]

    if not db.valeur("SELECT COUNT(*) FROM utilisateurs", (), 0):
        with db.transaction():
            db.insere("utilisateurs", {
                "identifiant": "demo", "nom_complet": "Comptable (démonstration)",
                "mot_de_passe": hache_mot_de_passe("demo1234"), "role": "admin",
                "actif": 1, "cree_le": util.maintenant(),
            })
        print("  Compte créé : identifiant « demo », mot de passe « demo1234 »")

    etape("Création du dossier « SARL EL BARAKA IMMOBILIER »")
    with db.transaction():
        societe_id = systeme._cree_societe(Ctx({
            "code": "DEMO", "raison_sociale": "SARL EL BARAKA IMMOBILIER (démonstration)",
            "forme_juridique": "SARL", "activite": "mixte",
            "adresse": "12 rue Didouche Mourad", "commune": "Alger-Centre",
            "wilaya": "16 Alger", "telephone": "021 63 45 78",
            "email": "contact@elbaraka-immo.dz",
            "nif": "000116001234567", "nis": "0001160012345",
            "rc": "16/00-1234567 B 09", "article_imposition": "16001234567",
            "capital": "5000000", "banque_nom": "BNA — agence Didouche Mourad",
            "banque_rib": "001 00123 4567890123 45", "annee_exercice": ANNEE,
        }))
    exercice = db.ligne("SELECT * FROM exercices WHERE societe_id = ?", (societe_id,))
    banque = db.ligne("SELECT * FROM comptes_tresorerie WHERE societe_id = ? AND type='banque'",
                      (societe_id,))
    caisse = db.ligne("SELECT * FROM comptes_tresorerie WHERE societe_id = ? AND type='caisse'",
                      (societe_id,))

    etape("Constitution du capital et compte séquestre")
    with db.transaction():
        compta.enregistre_ecriture(
            societe_id, "OD", f"{ANNEE}-01-02", "Constitution du capital social", [
                {"compte": "5121", "debit": 500000000, "credit": 0},
                {"compte": "101", "debit": 0, "credit": 500000000},
            ], utilisateur="demo")
        db.insere("comptes_tresorerie", {
            "societe_id": societe_id, "code": "SEQUESTRE",
            "libelle": "Compte spécial promotion (fonds VSP)", "type": "banque",
            "compte": "5122", "banque": "CPA", "devise": "DZD",
            "est_sequestre": 1, "actif": 1,
        })

    etape("Tiers : propriétaires, clients, fournisseurs, notaire")
    with db.transaction():
        proprios = [mod_tiers.api_cree(Ctx({
            "societe_id": societe_id, "type": "mandant", "forme": "physique",
            "nom": nom, "prenom": prenom, "telephone": tel, "adresse": adr,
            "banque_rib": rib,
        }))["id"] for nom, prenom, tel, adr, rib in [
            ("BENALI", "Karim", "0550 11 22 33", "Hydra, Alger", "002 00456 1122334455 66"),
            ("MEZIANE", "Farida", "0661 44 55 66", "Kouba, Alger", "003 00789 9988776655 44"),
            ("HADDAD", "Rachid", "0770 77 88 99", "Bab Ezzouar, Alger", ""),
        ]]
        clients = [mod_tiers.api_cree(Ctx({
            "societe_id": societe_id, "type": "client", "forme": "physique",
            "nom": nom, "prenom": prenom, "telephone": tel,
            "piece_identite": piece,
        }))["id"] for nom, prenom, tel, piece in [
            ("SAADI", "Yacine", "0550 12 34 56", "CNI 1234567890"),
            ("BOUMEDIENE", "Amina", "0661 23 45 67", "CNI 2345678901"),
            ("CHERIF", "Sofiane", "0770 34 56 78", "CNI 3456789012"),
            ("LAKHDARI", "Nadia", "0555 45 67 89", "CNI 4567890123"),
            ("ZEROUAL", "Mourad", "0666 56 78 90", "CNI 5678901234"),
        ]]
        entreprise = mod_tiers.api_cree(Ctx({
            "societe_id": societe_id, "type": "fournisseur", "forme": "morale",
            "raison_sociale": "ETP EL AMEL", "nif": "000116009876543",
            "rc": "16/00-9876543 B 12", "telephone": "021 55 66 77",
        }))["id"]
        bureau_etudes = mod_tiers.api_cree(Ctx({
            "societe_id": societe_id, "type": "fournisseur", "forme": "morale",
            "raison_sociale": "BET ARCHI CONCEPT", "nif": "000116005555555",
        }))["id"]
        notaire = mod_tiers.api_cree(Ctx({
            "societe_id": societe_id, "type": "notaire", "forme": "physique",
            "raison_sociale": "Maître AMRANI", "telephone": "021 74 85 96",
        }))["id"]

    etape("Agence : biens, mandats, vente et commission")
    with db.transaction():
        bien_vente = agence.api_cree_bien(Ctx({
            "societe_id": societe_id, "designation": "Appartement F3 — résidence Les Oliviers",
            "type_bien": "appartement", "surface": "95", "nb_pieces": "F3", "etage": "4",
            "commune": "Hydra", "wilaya": "16 Alger", "proprietaire_id": proprios[0],
            "prix_demande": "25000000", "nature_juridique": "acte_notarie",
            "num_acte": "AN/2019/1245",
        }))["id"]
        local = agence.api_cree_bien(Ctx({
            "societe_id": societe_id, "designation": "Local commercial 60 m² — Bab Ezzouar",
            "type_bien": "local_commercial", "surface": "60", "commune": "Bab Ezzouar",
            "wilaya": "16 Alger", "proprietaire_id": proprios[1], "loyer_mensuel": "80000",
        }))["id"]
        appart_loue = agence.api_cree_bien(Ctx({
            "societe_id": societe_id, "designation": "Appartement F2 — Kouba",
            "type_bien": "appartement", "surface": "62", "nb_pieces": "F2",
            "commune": "Kouba", "wilaya": "16 Alger", "proprietaire_id": proprios[2],
            "loyer_mensuel": "45000",
        }))["id"]
        agence.api_cree_bien(Ctx({
            "societe_id": societe_id, "designation": "Villa 250 m² avec jardin — Dely Ibrahim",
            "type_bien": "villa", "surface": "250", "commune": "Dely Ibrahim",
            "wilaya": "16 Alger", "proprietaire_id": proprios[0], "prix_demande": "78000000",
        }))

        mandat = agence.api_cree_mandat(Ctx({
            "societe_id": societe_id, "bien_id": bien_vente, "mandant_id": proprios[0],
            "type_mandat": "vente", "exclusif": True, "date_debut": f"{ANNEE}-02-01",
            "date_fin": f"{ANNEE}-08-01", "prix_mandat": "25000000",
            "taux_commission": "2", "charge_commission": "vendeur",
        }))["id"]
        transaction = agence.api_cree_transaction(Ctx({
            "societe_id": societe_id, "bien_id": bien_vente, "mandat_id": mandat,
            "vendeur_id": proprios[0], "acquereur_id": clients[0], "notaire_id": notaire,
            "date_compromis": f"{ANNEE}-03-10", "date_acte": f"{ANNEE}-04-15",
            "prix_vente": "25000000", "taux_tva": "19",
        }))
    facture = agence.api_facture_commission(Ctx({"date": f"{ANNEE}-04-15"},
                                                params={"id": str(transaction["id"])}))
    with db.transaction():
        facturation.api_cree_reglement(Ctx({
            "societe_id": societe_id, "sens": "encaissement", "date": f"{ANNEE}-04-22",
            "tresorerie_id": banque["id"], "facture_id": facture["facture_id"],
            "montant": "595000", "mode": "virement", "reference": "VIR-2024-0458",
        }))

    etape("Agence : baux et gestion locative sur 6 mois")
    with db.transaction():
        bail_local = agence.api_cree_bail(Ctx({
            "societe_id": societe_id, "bien_id": local, "proprietaire_id": proprios[1],
            "locataire_id": clients[1], "usage": "commercial",
            "date_debut": f"{ANNEE}-01-01", "duree_mois": 24, "loyer_mensuel": "80000",
            "charges_mensuelles": "5000", "caution": "160000", "jour_echeance": 5,
            "taux_gestion": "5", "encaisse_par_agence": True, "enregistre": True,
            "date_enregistrement": f"{ANNEE}-01-08",
        }))["id"]
        agence.api_cree_bail(Ctx({
            "societe_id": societe_id, "bien_id": appart_loue, "proprietaire_id": proprios[2],
            "locataire_id": clients[2], "usage": "habitation",
            "date_debut": f"{ANNEE}-01-01", "duree_mois": 12, "loyer_mensuel": "45000",
            "caution": "90000", "jour_echeance": 5, "taux_gestion": "5",
            "encaisse_par_agence": True,
        }))
    agence.api_encaisse_caution(Ctx({"tresorerie_id": banque["id"],
                                     "date": f"{ANNEE}-01-03"},
                                    params={"id": str(bail_local)}))

    for mois in range(1, 7):
        periode = f"{ANNEE}-{mois:02d}"
        agence.api_genere_quittances(Ctx({"societe_id": societe_id, "periode": periode}))
        quittances = db.lignes(
            "SELECT * FROM quittances WHERE societe_id = ? AND periode = ?",
            (societe_id, periode))
        for q in quittances:
            # On laisse volontairement un impayé en juin, pour illustrer les relances
            if mois == 6 and q["loyer"] == 4500000:
                continue
            agence.api_encaisse_quittance(Ctx(
                {"tresorerie_id": banque["id"], "date": util.jour_du_mois(periode, 7)},
                params={"id": str(q["id"])}))
        a_reverser = [q for q in db.lignes(
            "SELECT q.*, b.proprietaire_id FROM quittances q JOIN baux b ON b.id = q.bail_id "
            "WHERE q.societe_id = ? AND q.periode = ? AND q.montant_encaisse > 0",
            (societe_id, periode))]
        par_proprio: dict[int, list] = {}
        for q in a_reverser:
            par_proprio.setdefault(q["proprietaire_id"], []).append(q["id"])
        for proprietaire, ids in par_proprio.items():
            agence.api_reverse_proprietaire(Ctx({
                "societe_id": societe_id, "quittances": ids,
                "tresorerie_id": banque["id"],
                "date": util.jour_du_mois(periode, 12),
            }))

    etape("Promotion : programme « Résidence Les Jasmins » (24 logements)")
    with db.transaction():
        programme = promotion.api_cree_programme(Ctx({
            "societe_id": societe_id, "code": "RES-JASMIN",
            "intitule": "Résidence Les Jasmins", "adresse": "Route de Birkhadem",
            "commune": "Birkhadem", "wilaya": "16 Alger",
            "surface_terrain": "2400", "surface_batie": "3800", "nb_logements": 24,
            "num_permis_construire": f"PC/{ANNEE - 1}/0142",
            "date_permis": f"{ANNEE - 1}-11-20",
            "num_acte_terrain": f"AN/{ANNEE - 1}/8874",
            "date_acte_terrain": f"{ANNEE - 1}-09-15",
            "date_debut_travaux": f"{ANNEE}-01-15", "date_fin_prevue": f"{ANNEE + 2}-06-30",
            "budget_terrain": "60000000", "budget_etudes": "8000000",
            "budget_travaux": "180000000", "budget_vrd": "15000000",
            "budget_frais_divers": "7000000", "budget_frais_financiers": "10000000",
            "chiffre_affaires_prevu": "360000000",
            "methode_produit": "achevement", "fait_generateur_tva": "encaissement",
            "taux_tva": "19", "statut": "en_cours", "fgcmpi_taux": "1",
            "fgcmpi_police": "FG-POL-2024-0088",
        }))["id"]
        lots = []
        for i in range(1, 25):
            f3 = i % 2 == 1
            lots.append({
                "numero": f"A{i:02d}", "type_lot": "logement",
                "typologie": "F3" if f3 else "F4", "batiment": "A",
                "etage": str((i - 1) // 4 + 1),
                "surface_habitable": "85" if f3 else "105",
                "prix_m2": "160000",
            })
        promotion.api_genere_lots(Ctx({"societe_id": societe_id,
                                       "programme_id": programme, "lots": lots}))
        # Quelques parkings
        promotion.api_genere_lots(Ctx({
            "societe_id": societe_id, "programme_id": programme,
            "lots": [{"numero": f"P{i:02d}", "type_lot": "parking",
                      "surface_habitable": "12", "prix_vente": "800000"}
                     for i in range(1, 9)],
        }))

    etape("Promotion : acquisition du terrain, études et travaux")
    with db.transaction():
        compta.enregistre_ecriture(
            societe_id, "AC", f"{ANNEE}-01-10",
            "Acquisition du terrain — Résidence Les Jasmins", [
                {"compte": "6054", "debit": 6000000000, "credit": 0,
                 "programme_id": programme, "poste_budget": "terrain"},
                {"compte": "404", "debit": 0, "credit": 6000000000, "tiers_id": notaire},
            ], piece="ACTE-8874", utilisateur="demo")
        compta.enregistre_ecriture(
            societe_id, "AC", f"{ANNEE}-01-20", "Études architecturales et bureau de contrôle", [
                {"compte": "6041", "debit": 600000000, "credit": 0,
                 "programme_id": programme, "poste_budget": "etudes"},
                {"compte": "44566", "debit": 114000000, "credit": 0},
                {"compte": "401", "debit": 0, "credit": 714000000, "tiers_id": bureau_etudes},
            ], utilisateur="demo")
        for numero, date, montant, avancement in [
            ("ST-01", f"{ANNEE}-03-31", "32000000", "15"),
            ("ST-02", f"{ANNEE}-05-31", "48000000", "40"),
        ]:
            promotion.api_cree_situation(Ctx({
                "societe_id": societe_id, "programme_id": programme,
                "entreprise_id": entreprise, "numero": numero, "date": date,
                "lot_travaux": "Gros œuvre", "montant_marche": "120000000",
                "avancement": avancement, "montant_ht": montant, "taux_tva": "19",
                "taux_retenue": "5", "compte": "6051", "poste_budget": "gros_oeuvre",
            }))

    etape("Promotion : contrats de vente sur plan et encaissements")
    lots_db = db.lignes(
        "SELECT * FROM lots WHERE programme_id = ? AND type_lot='logement' ORDER BY numero",
        (programme,))
    contrats = []
    for index, (lot, acquereur) in enumerate(zip(lots_db[:5], clients)):
        contrat = promotion.api_cree_contrat(Ctx({
            "societe_id": societe_id, "lot_id": lot["id"], "acquereur_id": acquereur,
            "type_contrat": "vsp", "date_contrat": f"{ANNEE}-{2 + index:02d}-15",
            "notaire_id": notaire, "num_acte_notarie": f"VSP/{ANNEE}/{100 + index}",
            "modele_echeancier": "VSP_STANDARD", "taux_tva": "19",
            "fgcmpi_atteste": True, "fgcmpi_numero": f"FG-{ANNEE}-{200 + index}",
            "mode_financement": "credit_bancaire" if index % 2 else "fonds_propres",
            "banque": "CPA" if index % 2 else "",
        }))
        contrats.append(contrat["id"])

    promotion.api_avancement(Ctx({"avancement": "40"}, params={"id": str(programme)}))
    sequestre = db.ligne("SELECT * FROM comptes_tresorerie WHERE societe_id = ? "
                         "AND code = 'SEQUESTRE'", (societe_id,))
    for index, contrat_id in enumerate(contrats):
        echeances = db.lignes(
            "SELECT * FROM echeances_vsp WHERE contrat_id = ? ORDER BY ordre", (contrat_id,))
        # Les premiers acquéreurs ont réglé davantage de tranches
        nb = max(1, 3 - index // 2)
        for e in echeances[:nb]:
            promotion.api_encaisse_echeance(Ctx(
                {
                    "tresorerie_id": sequestre["id"],
                    "date": util.ajoute_mois(f"{ANNEE}-{2 + index:02d}-20", e["ordre"] * 2),
                    "mode": "virement", "reference": f"VIR-VSP-{index}{e['ordre']}",
                },
                params={"id": str(e["id"])},
            ))

    with db.transaction():
        promotion.api_stock_encours(Ctx({"date": f"{ANNEE}-06-30"},
                                        params={"id": str(programme)}))
    promotion.api_repartit_cout(Ctx({"base": "budget", "cle": "surface"},
                                    params={"id": str(programme)}))

    etape("Personnel : 3 salariés et 6 mois de paie")
    with db.transaction():
        for matricule, nom, prenom, poste, salaire, primes in [
            ("S0001", "SAADI", "Yacine", "Comptable", "60000",
             [{"libelle": "Prime de rendement", "montant": 10000, "soumis_cnas": True, "soumis_irg": True},
              {"libelle": "Panier et transport", "montant": 6000, "soumis_cnas": False, "soumis_irg": False}]),
            ("S0002", "BELKACEM", "Lila", "Négociatrice", "45000",
             [{"libelle": "Commission", "montant": 15000, "soumis_cnas": True, "soumis_irg": True}]),
            ("S0003", "TOUATI", "Omar", "Conducteur de travaux", "80000",
             [{"libelle": "Indemnité de chantier", "montant": 12000, "soumis_cnas": True, "soumis_irg": True}]),
        ]:
            paie.api_cree_salarie(Ctx({
                "societe_id": societe_id, "matricule": matricule, "nom": nom,
                "prenom": prenom, "poste": poste, "salaire_base": salaire,
                "primes": primes, "date_embauche": f"{ANNEE - 2}-03-01",
                "num_secu": f"12345678901{matricule[-1]}", "type_contrat": "CDI",
            }))
    for mois in range(1, 7):
        periode = f"{ANNEE}-{mois:02d}"
        paie.api_genere_bulletins(Ctx({"societe_id": societe_id, "periode": periode}))
        paie.api_comptabilise_paie(Ctx({
            "societe_id": societe_id, "periode": periode,
            "date": util.fin_de_mois(periode)}))
        paie.api_paye_salaires(Ctx({
            "societe_id": societe_id, "periode": periode,
            "tresorerie_id": banque["id"],
            "date": util.jour_du_mois(util.mois_suivant(periode), 3)}))

    etape("Immobilisations et charges courantes")
    with db.transaction():
        immobilisations.api_cree(Ctx({
            "societe_id": societe_id, "designation": "Véhicule de service Dacia Logan",
            "compte": "2182", "date_acquisition": f"{ANNEE}-01-10",
            "valeur_acquisition": "2400000", "duree_mois": 60, "mode": "lineaire",
            "comptabiliser": True, "fournisseur_id": entreprise, "taux_tva": "19",
        }))
        immobilisations.api_cree(Ctx({
            "societe_id": societe_id, "designation": "Mobilier et matériel de bureau",
            "compte": "2184", "date_acquisition": f"{ANNEE}-01-15",
            "valeur_acquisition": "850000", "duree_mois": 120, "mode": "lineaire",
            "comptabiliser": True, "fournisseur_id": entreprise, "taux_tva": "19",
        }))
        for mois in range(1, 7):
            periode = f"{ANNEE}-{mois:02d}"
            compta.enregistre_ecriture(
                societe_id, "BQ", util.jour_du_mois(periode, 25),
                f"Loyer du local de l'agence — {util.libelle_periode(periode)}", [
                    {"compte": "6131", "debit": 6000000, "credit": 0},
                    {"compte": "5121", "debit": 0, "credit": 6000000},
                ], utilisateur="demo")
            compta.enregistre_ecriture(
                societe_id, "CA", util.jour_du_mois(periode, 20),
                f"Fournitures, carburant et frais divers — {util.libelle_periode(periode)}", [
                    {"compte": "6073", "debit": 1200000, "credit": 0},
                    {"compte": "6072", "debit": 1800000, "credit": 0},
                    {"compte": "531", "debit": 0, "credit": 3000000},
                ], utilisateur="demo")

    etape("Amortissements de l'exercice")
    immobilisations.api_dotations(Ctx({
        "societe_id": societe_id, "exercice_id": exercice["id"]}))

    etape("Fiscalité : calendrier des obligations et déclarations G50")
    fiscalite.api_genere_obligations(Ctx({"societe_id": societe_id, "annee": ANNEE}))
    for mois in range(1, 6):
        periode = f"{ANNEE}-{mois:02d}"
        fiscalite.api_enregistre_g50(Ctx({
            "societe_id": societe_id, "periode": periode, "statut": "calculee"}))
        fiscalite.api_comptabilise_g50(Ctx({
            "societe_id": societe_id, "periode": periode,
            "date": util.fin_de_mois(periode)}))

    # Alimentation de la caisse pour éviter un solde négatif
    with db.transaction():
        compta.enregistre_ecriture(
            societe_id, "OD", f"{ANNEE}-01-05", "Alimentation de la caisse", [
                {"compte": "531", "debit": 30000000, "credit": 0},
                {"compte": "5121", "debit": 0, "credit": 30000000},
            ], utilisateur="demo")

    debit, credit = db.ligne(
        "SELECT COALESCE(SUM(l.debit),0) d, COALESCE(SUM(l.credit),0) c FROM lignes l "
        "JOIN ecritures e ON e.id = l.ecriture_id WHERE e.societe_id = ?",
        (societe_id,)).values()

    print()
    print("=" * 68)
    print("  Dossier de démonstration créé.")
    print(f"  Écritures        : {db.valeur('SELECT COUNT(*) FROM ecritures WHERE societe_id = ?', (societe_id,), 0)}")
    print(f"  Total débit      : {util.formate_montant(debit)}")
    print(f"  Total crédit     : {util.formate_montant(credit)}")
    print(f"  Équilibre        : {'OK' if debit == credit else 'ANOMALIE'}")
    print(f"  Dossier données  : {module_config.config.dossier_donnees}")
    print()
    print("  Lancez l'application :  python3 app.py")
    print("=" * 68)
    return societe_id


if __name__ == "__main__":
    construire()
    db.ferme()
