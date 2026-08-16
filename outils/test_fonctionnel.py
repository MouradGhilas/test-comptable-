#!/usr/bin/env python3
"""Test fonctionnel de bout en bout.

Simule une année de travail du comptable sur les deux activités (agence et
promotion) et vérifie que la comptabilité reste équilibrée et cohérente à
chaque étape.

    python3 outils/test_fonctionnel.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

DOSSIER = Path(tempfile.mkdtemp(prefix="cabinet_immo_test_"))

import noyau.config as module_config                                   # noqa: E402
module_config.config = module_config.Configuration({"dossier_donnees": str(DOSSIER)})

from noyau import base as db                                            # noqa: E402
from noyau import util                                                  # noqa: E402
from noyau.serveur import ErreurApplicative, ROUTES                     # noqa: E402

db.initialise()
import modules                                                          # noqa: E402,F401

SUCCES = []
ECHECS = []


class Faux:
    """Contexte d'appel minimal, équivalent d'une requête HTTP."""

    def __init__(self, corps=None, requete=None, params=None, role="admin"):
        self.corps = corps or {}
        self.requete = {c: [str(v)] for c, v in (requete or {}).items()}
        self.params = params or {}
        self.utilisateur = {"id": 1, "identifiant": "test", "role": role,
                            "nom_complet": "Testeur"}
        self.handler = None

    nom_utilisateur = "test"

    def arg(self, nom, defaut=None):
        v = self.requete.get(nom)
        return v[0] if v else defaut

    def arg_int(self, nom, defaut=None):
        v = self.arg(nom)
        try:
            return int(v) if v not in (None, "") else defaut
        except ValueError:
            return defaut

    def champ(self, nom, defaut=None):
        return self.corps.get(nom, defaut)

    def champ_requis(self, nom):
        v = self.corps.get(nom)
        if v in (None, ""):
            raise ErreurApplicative(f"Le champ « {nom} » est obligatoire.")
        return v

    def montant(self, nom, defaut=0):
        return util.centimes(self.corps.get(nom, defaut))

    def taux(self, nom, defaut=0):
        v = self.corps.get(nom)
        return util.vers_taux(v) if v not in (None, "") else defaut

    def entier(self, nom, defaut=None):
        v = self.corps.get(nom)
        try:
            return int(v) if v not in (None, "") else defaut
        except (TypeError, ValueError):
            return defaut

    def booleen(self, nom, defaut=False):
        v = self.corps.get(nom, defaut)
        if isinstance(v, bool):
            return 1 if v else 0
        return 1 if str(v).lower() in {"1", "true", "oui", "vrai", "on"} else 0

    def date(self, nom, defaut=None):
        return util.date_iso(self.corps.get(nom), defaut)

    def exige_role(self, *roles):
        pass

    def interdit_lecture_seule(self):
        pass


def verifie(libelle, condition, detail=""):
    if condition:
        SUCCES.append(libelle)
        print(f"  ✓ {libelle}")
    else:
        ECHECS.append((libelle, detail))
        print(f"  ✗ {libelle}   {detail}")


def titre(texte):
    print(f"\n\033[1m{texte}\033[0m")


def equilibre_general(societe_id):
    r = db.ligne(
        "SELECT COALESCE(SUM(l.debit),0) d, COALESCE(SUM(l.credit),0) c "
        "FROM lignes l JOIN ecritures e ON e.id = l.ecriture_id WHERE e.societe_id = ?",
        (societe_id,))
    return r["d"], r["c"]


# ===========================================================================
def executer():
    from modules import (systeme, comptabilite as compta, tiers as mod_tiers,
                         facturation, agence, promotion, fiscalite, paie,
                         immobilisations, etats, tresorerie)  # noqa: F401

    titre("1. Utilitaires monétaires")
    verifie("Conversion « 1 234,56 » → 123456 centimes",
            util.centimes("1 234,56") == 123456, str(util.centimes("1 234,56")))
    verifie("Conversion 1500.5 → 150050", util.centimes(1500.5) == 150050)
    verifie("TVA 19 % de 100 000,00 DA = 19 000,00 DA",
            util.applique_taux(10000000, 1900) == 1900000)
    verifie("Décomposition TTC 119 000 → HT 100 000 + TVA 19 000",
            util.ht_depuis_ttc(11900000, 1900) == (10000000, 1900000),
            str(util.ht_depuis_ttc(11900000, 1900)))
    verifie("Répartition sans perte de centime",
            sum(util.repartir(100000, [1, 1, 1])) == 100000,
            str(util.repartir(100000, [1, 1, 1])))
    verifie("Montant en lettres",
            "mille" in util.montant_en_lettres(125045).lower(),
            util.montant_en_lettres(125045))

    titre("2. Création du dossier « promotion + agence »")
    ctx = Faux({
        "code": "IMMO", "raison_sociale": "SARL EL BARAKA IMMOBILIER",
        "forme_juridique": "SARL", "activite": "mixte", "adresse": "12 rue Didouche Mourad",
        "commune": "Alger-Centre", "wilaya": "16 Alger", "telephone": "021 00 00 00",
        "nif": "000116001234567", "nis": "0001160012345", "rc": "16/00-1234567 B 09",
        "article_imposition": "16001234567", "capital": "5000000",
        "banque_nom": "BNA agence Didouche", "banque_rib": "001 00123 4567890123 45",
        "annee_exercice": "2026",
    })
    with db.transaction():
        societe_id = systeme._cree_societe(ctx)
    soc = compta.societe(societe_id)
    verifie("Dossier créé", soc["raison_sociale"] == "SARL EL BARAKA IMMOBILIER")
    nb_comptes = db.valeur("SELECT COUNT(*) FROM comptes WHERE societe_id = ?",
                           (societe_id,), 0)
    verifie(f"Plan comptable SCF installé ({nb_comptes} comptes)", nb_comptes > 150,
            str(nb_comptes))
    verifie("Journaux créés",
            db.valeur("SELECT COUNT(*) FROM journaux WHERE societe_id = ?",
                      (societe_id,), 0) == 7)
    exercice = db.ligne("SELECT * FROM exercices WHERE societe_id = ?", (societe_id,))
    verifie("Exercice 2026 ouvert", exercice["libelle"] == "2026")

    banque = db.ligne("SELECT * FROM comptes_tresorerie WHERE societe_id = ? "
                      "AND type = 'banque'", (societe_id,))
    caisse = db.ligne("SELECT * FROM comptes_tresorerie WHERE societe_id = ? "
                      "AND type = 'caisse'", (societe_id,))
    verifie("Comptes de trésorerie créés", banque and caisse)

    titre("3. Contrôles de saisie comptable")
    try:
        with db.transaction():
            compta.enregistre_ecriture(societe_id, "OD", "2026-03-01", "Test déséquilibre", [
                {"compte": "531", "debit": 100000, "credit": 0},
                {"compte": "706", "debit": 0, "credit": 90000},
            ])
        verifie("Écriture déséquilibrée refusée", False, "elle a été acceptée !")
    except ErreurApplicative as err:
        verifie("Écriture déséquilibrée refusée", "déséquilibrée" in str(err))

    try:
        with db.transaction():
            compta.enregistre_ecriture(societe_id, "OD", "2026-03-01", "Compte inconnu", [
                {"compte": "999999", "debit": 100000, "credit": 0},
                {"compte": "531", "debit": 0, "credit": 100000},
            ])
        verifie("Compte inexistant refusé", False, "accepté !")
    except ErreurApplicative as err:
        verifie("Compte inexistant refusé", "n'existe pas" in str(err))

    try:
        with db.transaction():
            compta.enregistre_ecriture(societe_id, "OD", "2025-03-01", "Hors exercice", [
                {"compte": "531", "debit": 100000, "credit": 0},
                {"compte": "706", "debit": 0, "credit": 100000},
            ])
        verifie("Date hors exercice refusée", False, "acceptée !")
    except ErreurApplicative as err:
        verifie("Date hors exercice refusée", "exercice" in str(err).lower())

    titre("4. Apport en capital et alimentation de la banque")
    with db.transaction():
        compta.enregistre_ecriture(
            societe_id, "OD", "2026-01-02", "Constitution du capital social", [
                {"compte": "5121", "debit": 500000000, "credit": 0},
                {"compte": "101", "debit": 0, "credit": 500000000},
            ], utilisateur="test")
    solde_banque = compta.solde_compte(societe_id, "5121", None, "2026-12-31",
                                       prefixe=False)["solde"]
    verifie("Banque créditée de 5 000 000,00 DA", solde_banque == 500000000,
            util.formate_montant(solde_banque))

    titre("5. Agence — propriétaire, bien, mandat, vente et commission")
    with db.transaction():
        proprio_id = mod_tiers.api_cree(Faux({
            "societe_id": societe_id, "type": "mandant", "forme": "physique",
            "nom": "BENALI", "prenom": "Karim", "telephone": "0550 11 22 33",
            "adresse": "Hydra, Alger",
        }))["id"]
        acheteur_id = mod_tiers.api_cree(Faux({
            "societe_id": societe_id, "type": "client", "forme": "physique",
            "nom": "MEZIANE", "prenom": "Sofiane", "telephone": "0661 44 55 66",
        }))["id"]
        locataire_id = mod_tiers.api_cree(Faux({
            "societe_id": societe_id, "type": "client", "forme": "physique",
            "nom": "HADJ", "prenom": "Amina",
        }))["id"]

        bien_id = agence.api_cree_bien(Faux({
            "societe_id": societe_id, "designation": "Appartement F3 Hydra",
            "type_bien": "appartement", "surface": "95", "nb_pieces": "F3",
            "commune": "Hydra", "wilaya": "16 Alger", "proprietaire_id": proprio_id,
            "prix_demande": "25000000", "nature_juridique": "acte_notarie",
        }))["id"]
        bien2_id = agence.api_cree_bien(Faux({
            "societe_id": societe_id, "designation": "Local commercial Bab Ezzouar",
            "type_bien": "local_commercial", "surface": "60",
            "proprietaire_id": proprio_id, "loyer_mensuel": "80000",
        }))["id"]

        mandat_id = agence.api_cree_mandat(Faux({
            "societe_id": societe_id, "bien_id": bien_id, "mandant_id": proprio_id,
            "type_mandat": "vente", "exclusif": True, "date_debut": "2026-02-01",
            "prix_mandat": "25000000", "taux_commission": "2",
            "charge_commission": "vendeur",
        }))["id"]

        transaction = agence.api_cree_transaction(Faux({
            "societe_id": societe_id, "bien_id": bien_id, "mandat_id": mandat_id,
            "vendeur_id": proprio_id, "acquereur_id": acheteur_id,
            "date_compromis": "2026-03-10", "date_acte": "2026-04-15",
            "prix_vente": "25000000", "taux_tva": "19",
        }))
    verifie("Commission calculée à 2 % de 25 000 000 = 500 000,00 DA",
            db.ligne("SELECT commission_ht FROM transactions WHERE id = ?",
                     (transaction["id"],))["commission_ht"] == 50000000,
            util.formate_montant(db.ligne("SELECT commission_ht FROM transactions "
                                          "WHERE id = ?", (transaction["id"],))["commission_ht"]))

    facture = agence.api_facture_commission(Faux({}, params={"id": str(transaction["id"])}))
    f = db.ligne("SELECT * FROM factures WHERE id = ?", (facture["facture_id"],))
    verifie("Facture de commission validée", f["statut"] == "validee")
    verifie("TVA 19 % sur commission = 95 000,00 DA", f["montant_tva"] == 9500000,
            util.formate_montant(f["montant_tva"]))
    ca_commission = compta.solde_compte(societe_id, "7061", "2026-01-01", "2026-12-31")
    verifie("Commission enregistrée en 7061",
            ca_commission["credit"] - ca_commission["debit"] == 50000000)
    verifie("Bien passé au statut « vendu »",
            db.ligne("SELECT statut FROM biens WHERE id = ?", (bien_id,))["statut"] == "vendu")

    with db.transaction():
        facturation.api_cree_reglement(Faux({
            "societe_id": societe_id, "sens": "encaissement", "date": "2026-04-20",
            "tresorerie_id": banque["id"], "facture_id": facture["facture_id"],
            "montant": "595000", "mode": "virement", "reference": "VIR-4587",
        }))
    f = db.ligne("SELECT * FROM factures WHERE id = ?", (facture["facture_id"],))
    verifie("Facture soldée après encaissement", f["statut"] == "payee",
            f["statut"])
    solde_client = compta.solde_compte(societe_id, "411", "2026-01-01", "2026-12-31")
    verifie("Compte client soldé", solde_client["solde"] == 0,
            util.formate_montant(solde_client["solde"]))

    titre("6. Agence — gestion locative (le loyer n'est pas un produit)")
    with db.transaction():
        bail = agence.api_cree_bail(Faux({
            "societe_id": societe_id, "bien_id": bien2_id,
            "proprietaire_id": proprio_id, "locataire_id": locataire_id,
            "usage": "commercial", "date_debut": "2026-01-01", "duree_mois": 24,
            "loyer_mensuel": "80000", "charges_mensuelles": "5000",
            "caution": "160000", "jour_echeance": 5, "taux_gestion": "5",
            "encaisse_par_agence": True,
        }))
    genere = agence.api_genere_quittances(Faux({
        "societe_id": societe_id, "periode": "2026-01"}))
    verifie("Quittance de janvier générée", genere["creees"] == 1, str(genere))

    quittance = db.ligne("SELECT * FROM quittances WHERE bail_id = ?", (bail["id"],))
    verifie("Total quittance = loyer + charges = 85 000,00 DA",
            quittance["total"] == 8500000, util.formate_montant(quittance["total"]))
    verifie("Honoraires de gestion 5 % du loyer = 4 000,00 DA",
            quittance["honoraires_gestion_ht"] == 400000,
            util.formate_montant(quittance["honoraires_gestion_ht"]))

    agence.api_encaisse_quittance(Faux(
        {"tresorerie_id": banque["id"], "date": "2026-01-06"},
        params={"id": str(quittance["id"])}))
    mandant = compta.solde_compte(societe_id, "4671", "2026-01-01", "2026-12-31")
    du_proprio = -mandant["solde"]
    attendu = 8500000 - 400000 - 76000     # total − honoraires HT − TVA sur honoraires
    verifie("Dette envers le propriétaire = net à reverser",
            du_proprio == attendu,
            f"{util.formate_montant(du_proprio)} ≠ {util.formate_montant(attendu)}")

    honoraires = compta.solde_compte(societe_id, "7063", "2026-01-01", "2026-12-31")
    verifie("Seuls les honoraires sont en produits (7063)",
            honoraires["credit"] - honoraires["debit"] == 400000,
            util.formate_montant(honoraires["credit"] - honoraires["debit"]))
    produits_loyers = compta.solde_compte(societe_id, "706", "2026-01-01", "2026-12-31")
    verifie("Le loyer de 85 000 DA n'apparaît pas en chiffre d'affaires",
            (produits_loyers["credit"] - produits_loyers["debit"]) == 50400000,
            util.formate_montant(produits_loyers["credit"] - produits_loyers["debit"]))

    reversement = agence.api_reverse_proprietaire(Faux({
        "societe_id": societe_id, "quittances": [quittance["id"]],
        "tresorerie_id": banque["id"], "date": "2026-01-10",
    }))
    verifie("Reversement au propriétaire du net", reversement["montant"] == attendu,
            util.formate_montant(reversement["montant"]))
    mandant = compta.solde_compte(societe_id, "4671", "2026-01-01", "2026-12-31")
    verifie("Compte mandant soldé après reversement", mandant["solde"] == 0,
            util.formate_montant(mandant["solde"]))

    titre("7. Promotion — programme, lots, contrat VSP")
    with db.transaction():
        programme_id = promotion.api_cree_programme(Faux({
            "societe_id": societe_id, "code": "RES-JASMIN",
            "intitule": "Résidence Les Jasmins", "commune": "Birkhadem",
            "wilaya": "16 Alger", "surface_terrain": "2400", "nb_logements": 24,
            "num_permis_construire": "PC/2025/0142", "date_permis": "2025-11-20",
            "date_debut_travaux": "2026-01-15", "date_fin_prevue": "2028-06-30",
            "budget_terrain": "60000000", "budget_etudes": "8000000",
            "budget_travaux": "180000000", "budget_vrd": "15000000",
            "budget_frais_divers": "7000000", "budget_frais_financiers": "10000000",
            "chiffre_affaires_prevu": "360000000",
            "fait_generateur_tva": "encaissement", "taux_tva": "19",
            "statut": "en_cours", "fgcmpi_taux": "1",
        }))["id"]

        lots = [{"numero": f"A{i:02d}", "type_lot": "logement",
                 "typologie": "F3" if i % 2 else "F4",
                 "batiment": "A", "etage": str((i - 1) // 4 + 1),
                 "surface_habitable": "85" if i % 2 else "105",
                 "prix_m2": "160000"} for i in range(1, 25)]
        promotion.api_genere_lots(Faux({
            "societe_id": societe_id, "programme_id": programme_id, "lots": lots}))

    nb_lots = db.valeur("SELECT COUNT(*) FROM lots WHERE programme_id = ?",
                        (programme_id,), 0)
    verifie("24 lots générés", nb_lots == 24, str(nb_lots))
    lot = db.ligne("SELECT * FROM lots WHERE programme_id = ? AND numero = 'A01'",
                   (programme_id,))
    verifie("Prix du lot A01 = 85 m² × 160 000 = 13 600 000,00 DA",
            lot["prix_vente"] == 1360000000, util.formate_montant(lot["prix_vente"]))

    contrat = promotion.api_cree_contrat(Faux({
        "societe_id": societe_id, "lot_id": lot["id"], "acquereur_id": acheteur_id,
        "type_contrat": "vsp", "date_contrat": "2026-02-20",
        "modele_echeancier": "VSP_STANDARD", "taux_tva": "19",
        "fgcmpi_atteste": True, "fgcmpi_numero": "FG-2026-0142",
        "mode_financement": "credit_bancaire", "banque": "CPA",
    }))
    echeances = db.lignes("SELECT * FROM echeances_vsp WHERE contrat_id = ? ORDER BY ordre",
                          (contrat["id"],))
    verifie("Échéancier VSP en 6 tranches", len(echeances) == 6, str(len(echeances)))
    verifie("Somme des échéances = prix du lot",
            sum(e["montant"] for e in echeances) == lot["prix_vente"],
            util.formate_montant(sum(e["montant"] for e in echeances)))
    verifie("1re tranche = 20 % = 2 720 000,00 DA",
            echeances[0]["montant"] == 272000000,
            util.formate_montant(echeances[0]["montant"]))
    verifie("Lot passé au statut « réservé »",
            db.ligne("SELECT statut FROM lots WHERE id = ?", (lot["id"],))["statut"]
            == "reserve")

    try:
        promotion.api_cree_contrat(Faux({
            "societe_id": societe_id, "lot_id": lot["id"], "acquereur_id": locataire_id,
            "date_contrat": "2026-03-01"}))
        verifie("Double vente du même lot refusée", False, "acceptée !")
    except ErreurApplicative as err:
        verifie("Double vente du même lot refusée", "déjà" in str(err))

    titre("8. Promotion — encaissements VSP (avances, pas de chiffre d'affaires)")
    promotion.api_encaisse_echeance(Faux(
        {"tresorerie_id": banque["id"], "date": "2026-02-25", "mode": "virement",
         "reference": "VIR-1001"},
        params={"id": str(echeances[0]["id"])}))
    avances = compta.solde_compte(societe_id, "4191", "2026-01-01", "2026-12-31")
    tva_vsp = compta.solde_compte(societe_id, "4457", "2026-01-01", "2026-12-31")
    ht_attendu, tva_attendue = util.ht_depuis_ttc(272000000, 1900)
    verifie("Encaissement porté en avances 4191 (et non en produit)",
            -avances["solde"] == ht_attendu,
            f"{util.formate_montant(-avances['solde'])} vs {util.formate_montant(ht_attendu)}")
    ventes_logements = compta.solde_compte(societe_id, "7011", "2026-01-01", "2026-12-31")
    verifie("Aucun produit constaté avant livraison",
            ventes_logements["credit"] == 0)
    verifie("TVA collectée à l'encaissement",
            tva_attendue > 0 and -tva_vsp["solde"] >= tva_attendue)

    promotion.api_avancement(Faux({"avancement": "60"},
                                  params={"id": str(programme_id)}))
    exigibles = db.lignes(
        "SELECT * FROM echeances_vsp WHERE contrat_id = ? AND statut = 'exigible'",
        (contrat["id"],))
    verifie("L'avancement à 60 % rend exigibles les tranches jusqu'au gros œuvre",
            len(exigibles) >= 2, f"{len(exigibles)} exigibles")

    for ech in echeances[1:3]:
        promotion.api_encaisse_echeance(Faux(
            {"tresorerie_id": banque["id"], "date": "2026-06-15"},
            params={"id": str(ech["id"])}))
    contrat_maj = db.ligne("SELECT * FROM contrats_vsp WHERE id = ?", (contrat["id"],))
    attendu_encaisse = sum(e["montant"] for e in echeances[:3])
    verifie("Cumul encaissé conforme à l'échéancier",
            contrat_maj["montant_encaisse"] == attendu_encaisse,
            util.formate_montant(contrat_maj["montant_encaisse"]))

    titre("9. Promotion — dépenses de chantier et coût de revient")
    with db.transaction():
        entreprise_id = mod_tiers.api_cree(Faux({
            "societe_id": societe_id, "type": "fournisseur", "forme": "morale",
            "raison_sociale": "ETP EL AMEL", "nif": "000116009876543",
        }))["id"]
        promotion.api_cree_situation(Faux({
            "societe_id": societe_id, "programme_id": programme_id,
            "entreprise_id": entreprise_id, "date": "2026-05-31",
            "lot_travaux": "Gros œuvre", "montant_marche": "120000000",
            "avancement": "40", "montant_ht": "48000000", "taux_tva": "19",
            "taux_retenue": "5", "compte": "6051", "poste_budget": "gros_oeuvre",
        }))
        compta.enregistre_ecriture(
            societe_id, "AC", "2026-03-05", "Acquisition du terrain — Les Jasmins", [
                {"compte": "6054", "debit": 6000000000, "credit": 0,
                 "programme_id": programme_id, "poste_budget": "terrain"},
                {"compte": "404", "debit": 0, "credit": 6000000000,
                 "tiers_id": entreprise_id},
            ], utilisateur="test")

    cout = promotion._cout_engage(societe_id, programme_id)
    verifie("Coût engagé sur le programme = terrain + travaux",
            cout == 6000000000 + 4800000000, util.formate_montant(cout))

    repartition = promotion.api_repartit_cout(Faux(
        {"base": "budget", "cle": "surface"}, params={"id": str(programme_id)}))
    total_reparti = db.valeur(
        "SELECT COALESCE(SUM(cout_revient),0) FROM lots WHERE programme_id = ?",
        (programme_id,), 0)
    verifie("Répartition du budget sur les lots sans perte de centime",
            total_reparti == repartition["total_reparti"],
            f"{util.formate_montant(total_reparti)} vs "
            f"{util.formate_montant(repartition['total_reparti'])}")

    stock = promotion.api_stock_encours(Faux({"date": "2026-06-30"},
                                             params={"id": str(programme_id)}))
    encours = compta.solde_compte(societe_id, "332", "2026-01-01", "2026-12-31")
    verifie("Travaux en cours portés au stock (332 / 723)",
            encours["solde"] == cout, util.formate_montant(encours["solde"]))

    titre("10. Livraison d'un lot — constatation du chiffre d'affaires")
    for ech in echeances[3:]:
        promotion.api_encaisse_echeance(Faux(
            {"tresorerie_id": banque["id"], "date": "2026-09-30"},
            params={"id": str(ech["id"])}))
    livraison = promotion.api_livre_lot(Faux(
        {"date": "2026-10-15", "destocker": True}, params={"id": str(contrat["id"])}))
    ventes = compta.solde_compte(societe_id, "7011", "2026-01-01", "2026-12-31")
    ht_total, _ = util.ht_depuis_ttc(lot["prix_vente"], 1900)
    verifie("Chiffre d'affaires constaté à la livraison",
            ventes["credit"] - ventes["debit"] == ht_total,
            f"{util.formate_montant(ventes['credit'] - ventes['debit'])} vs "
            f"{util.formate_montant(ht_total)}")
    avances = compta.solde_compte(societe_id, "4191", "2026-01-01", "2026-12-31")
    verifie("Compte d'avances soldé pour ce lot", avances["solde"] == 0,
            util.formate_montant(avances["solde"]))
    verifie("Lot marqué livré",
            db.ligne("SELECT statut FROM lots WHERE id = ?", (lot["id"],))["statut"]
            == "livre")

    titre("11. Paie — CNAS et IRG")
    with db.transaction():
        salarie = paie.api_cree_salarie(Faux({
            "societe_id": societe_id, "nom": "SAADI", "prenom": "Yacine",
            "poste": "Comptable", "date_embauche": "2024-03-01",
            "num_secu": "1234567890123", "salaire_base": "60000",
            "primes": [{"libelle": "Prime de rendement", "montant": 10000,
                        "soumis_cnas": True, "soumis_irg": True},
                       {"libelle": "Panier et transport", "montant": 6000,
                        "soumis_cnas": False, "soumis_irg": False}],
        }))
    salarie_db = db.ligne("SELECT * FROM salaries WHERE id = ?", (salarie["id"],))
    calcul = paie.calcule_bulletin(societe_id, salarie_db, "2026-01")
    verifie("Salaire brut = 76 000,00 DA", calcul["salaire_brut"] == 7600000,
            util.formate_montant(calcul["salaire_brut"]))
    verifie("Base CNAS = 70 000,00 DA (hors panier/transport)",
            calcul["base_cnas"] == 7000000, util.formate_montant(calcul["base_cnas"]))
    verifie("CNAS salarié 9 % = 6 300,00 DA", calcul["cnas_salarie"] == 630000,
            util.formate_montant(calcul["cnas_salarie"]))
    verifie("CNAS patronale 26 % = 18 200,00 DA",
            calcul["cnas_patronale"] == 1820000,
            util.formate_montant(calcul["cnas_patronale"]))
    verifie("IRG calculé et positif", calcul["irg"] > 0,
            util.formate_montant(calcul["irg"]))
    verifie("Net à payer cohérent",
            calcul["net_a_payer"] == calcul["salaire_brut"] - calcul["cnas_salarie"]
            - calcul["irg"] - calcul["autres_retenues"])

    paie.api_genere_bulletins(Faux({"societe_id": societe_id, "periode": "2026-01"}))
    resultat_paie = paie.api_comptabilise_paie(Faux({
        "societe_id": societe_id, "periode": "2026-01", "date": "2026-01-31"}))
    verifie("Écriture de paie générée", resultat_paie["ecriture_id"] > 0)
    dette_cnas = compta.solde_compte(societe_id, "431", "2026-01-01", "2026-12-31")
    verifie("Dette CNAS = part salariale + patronale",
            -dette_cnas["solde"] == calcul["cnas_salarie"] + calcul["cnas_patronale"],
            util.formate_montant(-dette_cnas["solde"]))

    titre("12. Immobilisations et amortissements")
    with db.transaction():
        immo = immobilisations.api_cree(Faux({
            "societe_id": societe_id, "designation": "Véhicule de service Dacia",
            "compte": "2182", "date_acquisition": "2026-01-10",
            "date_mise_service": "2026-01-10", "valeur_acquisition": "2400000",
            "duree_mois": 60, "mode": "lineaire",
        }))
    immo_db = db.ligne("SELECT * FROM immobilisations WHERE id = ?", (immo["id"],))
    plan = immobilisations.plan_amortissement(immo_db)
    verifie("Plan sur 5 ans", len(plan) >= 5, str(len(plan)))
    verifie("Cumul final = valeur d'acquisition",
            plan[-1]["cumul"] == 240000000, util.formate_montant(plan[-1]["cumul"]))
    dotation = immobilisations.api_dotations(Faux({
        "societe_id": societe_id, "exercice_id": exercice["id"]}))
    verifie("Dotation comptabilisée", dotation.get("dotations", 0) == 1, str(dotation))

    titre("13. Fiscalité — G50")
    g50 = fiscalite.calcule_g50(societe_id, "2026-01")
    verifie("TVA collectée reprise du grand livre", g50["tva_collectee"] > 0,
            util.formate_montant(g50["tva_collectee"]))
    verifie("IRG salaires repris du compte 4421", g50["irg_salaires"] == calcul["irg"],
            util.formate_montant(g50["irg_salaires"]))
    verifie("Date limite = 20 du mois suivant", g50["date_limite"] == "2026-02-20",
            g50["date_limite"])
    fiscalite.api_enregistre_g50(Faux({
        "societe_id": societe_id, "periode": "2026-01", "statut": "calculee"}))
    liquidation = fiscalite.api_comptabilise_g50(Faux({
        "societe_id": societe_id, "periode": "2026-01", "date": "2026-01-31"}))
    verifie("Écriture de liquidation de TVA générée", liquidation["ecriture_id"] > 0)
    tva_apres = compta.solde_compte(societe_id, "4457", "2026-01-01", "2026-01-31")
    verifie("Compte 4457 soldé après liquidation de janvier",
            tva_apres["solde"] == 0, util.formate_montant(tva_apres["solde"]))

    titre("14. États financiers")
    bilan = etats.construit_bilan(societe_id, "2026-01-01", "2026-12-31")
    verifie("Bilan équilibré (actif = passif)", bilan["equilibre"],
            f"écart de {util.formate_montant(bilan['ecart'])}")
    tcr = etats.construit_tcr(societe_id, "2026-01-01", "2026-12-31")
    verifie("Résultat du TCR = produits − charges",
            tcr["resultat_net"] == bilan["resultat"],
            f"{util.formate_montant(tcr['resultat_net'])} vs "
            f"{util.formate_montant(bilan['resultat'])}")
    flux = etats.construit_flux(societe_id, "2026-01-01", "2026-12-31")
    verifie("Tableau des flux cohérent", flux["controle"] == 0,
            util.formate_montant(flux["controle"]))

    titre("15. Équilibre général et contrôles")
    debit, credit = equilibre_general(societe_id)
    verifie("Comptabilité globalement équilibrée", debit == credit,
            f"{util.formate_montant(debit)} vs {util.formate_montant(credit)}")
    controles = compta.api_controles(Faux({}, params={"id": str(exercice["id"])}))
    verifie("Aucune anomalie bloquante", controles["bloquants"] == 0,
            str([a["message"] for a in controles["anomalies"]
                 if a["gravite"] == "bloquant"]))

    titre("16. Exports et documents")
    from modules import documents
    facture_detail = facturation.api_detail(Faux({}, params={"id": str(facture["facture_id"])}))
    html = documents.facture_html(facture_detail)
    verifie("Facture imprimable générée", "NET À PAYER" in html and "NIF" in html)
    verifie("Montant en toutes lettres présent sur la facture",
            "Arrêtée la présente facture" in html)

    export = compta.api_export_balance(Faux({}, requete={
        "societe": societe_id, "exercice": exercice["id"]}))
    verifie("Export Excel de la balance produit un fichier xlsx valide",
            export.contenu[:2] == b"PK" and len(export.contenu) > 2000,
            f"{len(export.contenu)} octets")

    export_prog = promotion.api_export_programme(Faux({}, requete={
        "societe": societe_id, "programme": programme_id}))
    verifie("Export Excel du programme immobilier",
            export_prog.contenu[:2] == b"PK" and len(export_prog.contenu) > 2000)

    titre("17. Clôture de l'exercice")
    with db.transaction():
        exercice_2027 = db.insere("exercices", {
            "societe_id": societe_id, "libelle": "2027",
            "date_debut": "2027-01-01", "date_fin": "2027-12-31", "cloture": 0})
    resultat_cloture = compta.api_cloture(Faux(
        {"exercice_suivant": exercice_2027}, params={"id": str(exercice["id"])}))
    verifie("Exercice clôturé avec report du résultat",
            resultat_cloture["a_nouveaux"] > 0, str(resultat_cloture))
    charges_apres = compta.solde_compte(societe_id, "6", "2026-01-01", "2026-12-31")
    verifie("Comptes de charges soldés à la clôture",
            charges_apres["debit"] - charges_apres["credit"] == 0,
            util.formate_montant(charges_apres["debit"] - charges_apres["credit"]))
    an = compta.solde_compte(societe_id, "1", "2027-01-01", "2027-12-31")
    verifie("À-nouveaux repris sur 2027", an["debit"] + an["credit"] > 0)
    debit27, credit27 = db.ligne(
        "SELECT COALESCE(SUM(l.debit),0) d, COALESCE(SUM(l.credit),0) c "
        "FROM lignes l JOIN ecritures e ON e.id = l.ecriture_id "
        "WHERE e.exercice_id = ?", (exercice_2027,)).values()
    verifie("À-nouveaux équilibrés", debit27 == credit27,
            f"{util.formate_montant(debit27)} vs {util.formate_montant(credit27)}")

    try:
        with db.transaction():
            compta.enregistre_ecriture(societe_id, "OD", "2026-12-01",
                                       "Après clôture", [
                                           {"compte": "531", "debit": 1000, "credit": 0},
                                           {"compte": "706", "debit": 0, "credit": 1000},
                                       ])
        verifie("Écriture refusée sur exercice clôturé", False, "acceptée !")
    except ErreurApplicative as err:
        verifie("Écriture refusée sur exercice clôturé", "clôturé" in str(err))

    titre("18. Déclaré / hors déclaration")
    # On repart d'un exercice ouvert : 2027, créé à la clôture ci-dessus.
    with db.transaction():
        compta.enregistre_ecriture(
            societe_id, "VE", "2027-02-10", "Commission encaissée — déclarée", [
                {"compte": "4112", "debit": 11900000, "credit": 0, "tiers_id": acheteur_id},
                {"compte": "7061", "debit": 0, "credit": 10000000},
                {"compte": "4457", "debit": 0, "credit": 1900000},
            ], utilisateur="test", perimetre="declare")
        compta.enregistre_ecriture(
            societe_id, "CA", "2027-02-12", "Commission encaissée — hors déclaration", [
                {"compte": "531", "debit": 5000000, "credit": 0},
                {"compte": "7061", "debit": 0, "credit": 5000000},
            ], utilisateur="test", perimetre="hors_declaration")

    declare = compta.solde_compte(societe_id, "7061", "2027-01-01", "2027-12-31",
                                  perimetre="declare")
    hors = compta.solde_compte(societe_id, "7061", "2027-01-01", "2027-12-31",
                               perimetre="hors_declaration")
    tous = compta.solde_compte(societe_id, "7061", "2027-01-01", "2027-12-31")
    verifie("Produits déclarés isolés", declare["credit"] == 10000000,
            util.formate_montant(declare["credit"]))
    verifie("Produits hors déclaration isolés", hors["credit"] == 5000000,
            util.formate_montant(hors["credit"]))
    verifie("Vue réelle = somme des deux", tous["credit"] == 15000000,
            util.formate_montant(tous["credit"]))

    g50_2027 = fiscalite.calcule_g50(societe_id, "2027-02")
    verifie("La G50 ne retient que la TVA déclarée",
            g50_2027["tva_collectee"] == 1900000,
            util.formate_montant(g50_2027["tva_collectee"]))
    verifie("La G50 signale ce qui en est exclu",
            g50_2027["hors_declaration"]["nb_ecritures"] == 1
            and g50_2027["hors_declaration"]["produits"] == 5000000,
            str(g50_2027["hors_declaration"]))
    verifie("La G50 déclare son périmètre", g50_2027["perimetre"] == "declare")

    bilan_declare = etats.construit_bilan(societe_id, "2027-01-01", "2027-12-31",
                                          perimetre="declare")
    bilan_reel = etats.construit_bilan(societe_id, "2027-01-01", "2027-12-31")
    verifie("Bilan déclaré équilibré", bilan_declare["equilibre"],
            util.formate_montant(bilan_declare["ecart"]))
    verifie("Bilan réel équilibré", bilan_reel["equilibre"],
            util.formate_montant(bilan_reel["ecart"]))
    verifie("Le résultat réel dépasse le résultat déclaré",
            bilan_reel["resultat"] > bilan_declare["resultat"],
            f"{util.formate_montant(bilan_reel['resultat'])} vs "
            f"{util.formate_montant(bilan_declare['resultat'])}")

    titre("19. Résumé envoyé au dirigeant")
    from modules import rapports
    resume = rapports.construit_resume(societe_id)
    verifie("Résumé calculé", resume["societe"] and "tresorerie" in resume)
    texte = rapports.resume_en_texte(resume, False)
    verifie("Résumé lisible sur téléphone",
            "TRÉSORERIE" in texte and "DA" in texte and len(texte) < 4000,
            f"{len(texte)} caractères")
    verifie("Pas de devise en double dans le résumé", "DA DA" not in texte)
    resume_reel = rapports.construit_resume(societe_id, None, jour="2027-02-15")
    resume_declare = rapports.construit_resume(societe_id, "declare", jour="2027-02-15")
    verifie("Le résumé respecte le périmètre demandé",
            resume_declare["chiffre_affaires"] == 10000000
            and resume_reel["chiffre_affaires"] == 15000000,
            f"déclaré {resume_declare['chiffre_affaires']} / "
            f"réel {resume_reel['chiffre_affaires']}")

    titre("20. Migration de schéma")
    verifie("Base au dernier schéma", db.version_schema() == db.VERSION_SCHEMA,
            f"v{db.version_schema()} / v{db.VERSION_SCHEMA}")
    rapport = db.initialise()
    verifie("Réinitialisation sans effet (idempotence)", rapport["migrations"] == [],
            str(rapport["migrations"]))
    verifie("Ajout de colonne idempotent",
            db.ajoute_colonne("ecritures", "perimetre", "TEXT") is False)

    titre("21. Sauvegarde et intégrité")
    from modules.fichiers import cree_sauvegarde
    archive = cree_sauvegarde("test")
    verifie("Archive de sauvegarde créée", archive.exists() and archive.stat().st_size > 1000,
            f"{archive.stat().st_size} octets")
    verifie("Intégrité SQLite", db.valeur("PRAGMA integrity_check", (), "?") == "ok")


# ===========================================================================
if __name__ == "__main__":
    print("\n\033[1m═══ TEST FONCTIONNEL — CABINET IMMO ═══\033[0m")
    print(f"Dossier temporaire : {DOSSIER}")
    code = 0
    try:
        executer()
    except Exception:                                        # noqa: BLE001
        import traceback
        traceback.print_exc()
        ECHECS.append(("Exception non rattrapée", "voir la trace ci-dessus"))
    finally:
        print("\n" + "═" * 72)
        print(f"\033[1mRÉSULTAT : {len(SUCCES)} réussite(s), {len(ECHECS)} échec(s)\033[0m")
        if ECHECS:
            code = 1
            print("\nÉchecs :")
            for libelle, detail in ECHECS:
                print(f"  ✗ {libelle}  —  {detail}")
        print("═" * 72)
        db.ferme()
        shutil.rmtree(DOSSIER, ignore_errors=True)
    raise SystemExit(code)
