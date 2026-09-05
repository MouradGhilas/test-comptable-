"""Reprise des données existantes depuis Excel.

Le principe demandé : l'application fournit les en-têtes, le comptable remplit
le fichier avec ses propres données, puis le réintègre. Il n'a donc jamais à
deviner un format.

L'import se fait toujours en deux temps :

  1. **Contrôle** — le fichier est lu et vérifié ligne par ligne, sans rien
     écrire. Chaque anomalie est rapportée avec son numéro de ligne.
  2. **Validation** — seules les lignes saines sont enregistrées, par le même
     chemin que la saisie manuelle (`comptabilite.enregistre_ecriture`,
     `facturation.cree_facture`), donc avec les mêmes contrôles.

Formats acceptés : .xlsx et .csv (séparateur « ; », encodage Excel français).

Règle d'ensemble : **l'import reprend l'existant, il ne recomptabilise pas le
passé.** Les baux, lots, contrats et immobilisations repris décrivent une
situation ; ce sont la balance d'ouverture ou les écritures importées qui
portent la comptabilité. Sans cela, tout serait compté deux fois.
"""

from __future__ import annotations

import base64
import json
import sqlite3
import unicodedata

from noyau import base as db
from noyau import tableur
from noyau import util
from noyau.serveur import ErreurApplicative, route, Reponse
from modules import comptabilite as compta

TAILLE_MAX = 16 * 1024 * 1024


# ---------------------------------------------------------------------------
# Description d'une colonne
# ---------------------------------------------------------------------------

class Colonne:
    """Une colonne du modèle : son en-tête, ce qu'elle attend, son exemple.

    `champ` nomme la colonne SQL visée (par défaut, aucune : la colonne est
    alors exploitée par un traitement particulier). `type` pilote la
    conversion, `reference` la résolution d'un identifiant, `valeurs`
    l'ensemble fermé des réponses acceptées.
    """

    def __init__(self, nom, aide, exemple="", requis=False, synonymes=(),
                 champ=None, type="texte", reference=None, parent=None,
                 valeurs=None):
        self.nom = nom
        self.aide = aide
        self.exemple = exemple
        self.requis = requis
        self.synonymes = synonymes
        self.champ = champ
        self.type = type
        self.reference = reference        # table visée : tiers, compte, bien…
        self.parent = parent              # colonne qui restreint la recherche
        self.valeurs = set(valeurs) if valeurs else None


def _sans_accent(texte: str) -> str:
    decompose = unicodedata.normalize("NFD", str(texte or ""))
    return "".join(c for c in decompose if unicodedata.category(c) != "Mn").lower()


def _date(valeur: str) -> str | None:
    """Accepte JJ/MM/AAAA, AAAA-MM-JJ, et le format renvoyé par Excel."""
    valeur = (valeur or "").strip()
    if not valeur:
        return None
    if "/" in valeur:
        morceaux = valeur.split("/")
        if len(morceaux) == 3 and len(morceaux[2]) == 4:
            valeur = f"{morceaux[2]}-{morceaux[1].zfill(2)}-{morceaux[0].zfill(2)}"
    return util.date_iso(valeur)


def _oui_non(valeur: str) -> int:
    return 1 if _sans_accent(valeur).startswith(("o", "y", "1", "v", "true")) else 0


#: Conversion d'une valeur du fichier vers ce qui est stocké en base.
CONVERTISSEURS = {
    "texte": lambda v: v or None,
    "montant": lambda v: util.centimes(v) if v else 0,
    "surface": lambda v: util.centimes(v) if v else 0,   # m² × 100
    "quantite": lambda v: int(round(float(str(v).replace(",", ".")) * 1000)) if v else 0,
    "date": _date,
    "entier": lambda v: int(float(str(v).replace(",", "."))) if v else None,
    "taux": lambda v: util.vers_taux(v) if v else 0,
    "oui_non": _oui_non,
    "minuscule": lambda v: _sans_accent(v) or None,
}


# ---------------------------------------------------------------------------
# Résolution des références
# ---------------------------------------------------------------------------

def _cherche(sql: str, params) -> int | None:
    trouve = db.ligne(sql, params)
    return trouve["id"] if trouve else None


def resout_reference(table: str, societe_id: int, valeur: str,
                     parent_id=None) -> int | None:
    """Retrouve l'identifiant d'un élément désigné par son nom ou son code."""
    if not valeur:
        return None
    if table == "tiers":
        return _cherche(
            "SELECT id FROM tiers WHERE societe_id = ? AND "
            "(raison_sociale = ? COLLATE NOCASE OR code = ? COLLATE NOCASE)",
            (societe_id, valeur, valeur))
    if table == "bien":
        return _cherche(
            "SELECT id FROM biens WHERE societe_id = ? AND "
            "(reference = ? COLLATE NOCASE OR designation = ? COLLATE NOCASE)",
            (societe_id, valeur, valeur))
    if table == "programme":
        return _cherche(
            "SELECT id FROM programmes WHERE societe_id = ? AND "
            "(code = ? COLLATE NOCASE OR intitule = ? COLLATE NOCASE)",
            (societe_id, valeur, valeur))
    if table == "lot":
        if parent_id:
            return _cherche(
                "SELECT id FROM lots WHERE societe_id = ? AND programme_id = ? "
                "AND numero = ? COLLATE NOCASE", (societe_id, parent_id, valeur))
        return _cherche("SELECT id FROM lots WHERE societe_id = ? AND "
                        "numero = ? COLLATE NOCASE", (societe_id, valeur))
    if table == "bail":
        return _cherche("SELECT id FROM baux WHERE societe_id = ? AND "
                        "numero = ? COLLATE NOCASE", (societe_id, valeur))
    if table == "tresorerie":
        return _cherche(
            "SELECT id FROM comptes_tresorerie WHERE societe_id = ? AND "
            "(code = ? COLLATE NOCASE OR libelle = ? COLLATE NOCASE)",
            (societe_id, valeur, valeur))
    if table == "contrat_vsp":
        return _cherche("SELECT id FROM contrats_vsp WHERE societe_id = ? AND "
                        "numero = ? COLLATE NOCASE", (societe_id, valeur))
    if table == "compte":
        trouve = db.ligne("SELECT numero FROM comptes WHERE societe_id = ? AND "
                          "numero = ?", (societe_id, valeur))
        return trouve["numero"] if trouve else None
    raise ValueError(f"référence inconnue : {table}")


#: Nom lisible de ce qui est recherché, pour les messages d'anomalie.
LIBELLES_REFERENCE = {
    "tiers": "tiers", "bien": "bien", "programme": "programme", "lot": "lot",
    "bail": "bail", "tresorerie": "compte de trésorerie",
    "contrat_vsp": "contrat VSP", "compte": "compte",
}

#: Ce qu'un import crée de lui-même quand le fichier le désigne sans qu'il
#: existe : tout ce dont la référence **est** l'identité. Un client, un
#: compte, un journal, un bien, un programme, un lot ne sont, vus d'un
#: fichier qui les cite, qu'un nom ou un numéro. La fiche naît donc avec ce
#: nom, marquée « à compléter », et le fichier qui la décrit vraiment la
#: remplira plus tard — dans n'importe quel ordre.
#:
#: Quatre renvois n'y sont pas, et ce n'est pas un ordre imposé mais ce que
#: ces objets sont : un règlement sans sa facture ne règle rien, une
#: quittance sans son bail ne quitte rien, une échéance sans son contrat
#: n'échoit de rien, et un mouvement sans son compte de trésorerie irait se
#: poser sur un compte comptable choisi au hasard.
CREABLES = {"tiers", "compte", "bien", "programme", "lot", "tresorerie"}

#: Comment fabriquer la fiche minimale d'une référence : la table, la colonne
#: qui porte l'identité, et le champ où recopier ce nom faute de mieux.
FICHES_MINIMALES = {
    "bien": {"table": "biens", "cle": "reference", "recopie": "designation",
             "defauts": {"type_bien": "appartement", "statut": "disponible"}},
    "programme": {"table": "programmes", "cle": "code", "recopie": "intitule",
                  "defauts": {"statut": "etude"}},
    # Un lot n'existe que dans un programme : sans lui, la fiche n'aurait
    # nulle part où se ranger. C'est le seul de la liste qui peut échouer.
    "lot": {"table": "lots", "cle": "numero", "recopie": None,
            "defauts": {"type_lot": "logement", "statut": "disponible"},
            "parent": "programme"},
    # Le compte comptable est un choix, pas une évidence : 512 est le cas
    # courant, la fiche reste marquée « à compléter » pour qu'il le corrige
    # si c'est une caisse ou un CCP.
    "tresorerie": {"table": "comptes_tresorerie", "cle": "code",
                   "recopie": "libelle",
                   "defauts": {"type": "banque", "compte": "512", "actif": 1}},
}


# ---------------------------------------------------------------------------
# Modèles
# ---------------------------------------------------------------------------

_NOTICE_FACTURES = [
    "Une ligne du fichier = une ligne de facture (une prestation, un article).",
    "Les lignes qui portent le même « N° facture » forment une seule facture.",
    "",
    "Le tiers est retrouvé par sa raison sociale ou son code : importez donc",
    "vos tiers avant vos factures. Un tiers inconnu est signalé, jamais créé",
    "au hasard.",
    "",
    "Le prix unitaire s'entend hors taxes. Le taux de TVA s'écrit 19 ou 9 ;",
    "laissé vide, il vaut 19.",
    "",
    "« Périmètre » accepte Déclaré ou Non déclaré : un même fichier peut donc",
    "contenir les deux.",
    "",
    "Les factures sont créées en brouillon. Elles ne produisent leur écriture",
    "comptable qu'une fois validées dans l'application, après relecture.",
]

_COLONNES_FACTURES = [
    Colonne("N° facture", "Regroupe les lignes d'une même facture", "FA-2026-014",
            requis=True, synonymes=("numero", "n° facture", "facture", "piece")),
    Colonne("Date", "Date de la facture", "15/03/2026", requis=True),
    Colonne("Tiers", "Client ou fournisseur, tel qu'enregistré", "BENALI Karim",
            requis=True, synonymes=("client", "fournisseur", "raison sociale")),
    Colonne("Désignation", "Libellé de la ligne", "Commission de transaction",
            requis=True, synonymes=("designation", "libelle", "intitule",
                                    "description")),
    Colonne("Quantité", "Nombre d'unités (1 par défaut)", "1",
            synonymes=("quantite", "qte")),
    Colonne("Unité", "Unité de mesure", "", synonymes=("unite",)),
    Colonne("Prix unitaire", "Prix hors taxes d'une unité", "500000",
            synonymes=("prix", "pu", "prix unitaire ht")),
    # « Montant HT » était un synonyme de « Prix unitaire ». Un fichier qui
    # donne le total d'une ligne **et** une quantité voyait donc sa somme
    # multipliée : 100 × 4 954 100 au lieu de 4 954 100. Les deux colonnes
    # sont désormais distinctes, et le montant l'emporte quand il est là.
    Colonne("Montant HT", "Montant de la ligne, taxes non comprises "
                          "(l'emporte sur le prix unitaire)", "500000",
            synonymes=("montant ht", "montant", "total ht", "montant hors taxes")),
    Colonne("Remise %", "Remise en pourcentage", "", synonymes=("remise",)),
    Colonne("Taux TVA", "19, 9 ou 0", "19", synonymes=("tva", "taux tva %")),
    Colonne("Compte", "Compte de produit ou de charge (facultatif)", "7061"),
    Colonne("Objet", "Objet de la facture", "Vente appartement Hydra"),
    Colonne("Échéance", "Date d'échéance de règlement", "",
            synonymes=("date echeance", "echeance")),
    Colonne("Mode de règlement", "espece, cheque, virement ou traite", "",
            synonymes=("mode reglement", "reglement", "mode")),
    Colonne("Périmètre", "Déclaré ou Non déclaré", "Déclaré",
            synonymes=("perimetre",)),
]

TYPES_TIERS = {"client", "fournisseur", "mandant", "locataire", "acquereur",
               "salarie", "autre"}
MODES_REGLEMENT = {"espece", "cheque", "virement", "traite"}


MODELES = {
    # -- Comptabilité ------------------------------------------------------
    "balance_ouverture": {
        "libelle": "Balance d'ouverture (reprise en cours d'année)",
        "groupe": "Comptabilité",
        "notice": [
            "C'est par ce fichier qu'on reprend un dossier déjà tenu ailleurs.",
            "",
            "Indiquez, pour chaque compte, son solde à la date de reprise :",
            "soit dans la colonne Débit, soit dans la colonne Crédit, jamais",
            "les deux. Le total des débits doit égaler le total des crédits.",
            "",
            "Une seule écriture d'à-nouveaux est produite, dans le journal AN,",
            "à la date choisie. Elle porte l'ensemble des soldes repris.",
            "",
            "Ne reprenez pas ici les comptes de charges et de produits",
            "(classes 6 et 7) si vous importez par ailleurs le détail des",
            "écritures de l'exercice : ils seraient comptés deux fois.",
            "",
            "Les comptes absents du plan comptable sont créés avec la balance,",
            "d'après leur compte de rattachement, et marqués « à compléter ».",
        ],
        "colonnes": [
            Colonne("Compte", "Numéro du compte", "411", requis=True,
                    synonymes=("numero", "n° compte", "compte general")),
            Colonne("Intitulé", "Rappel du libellé (facultatif)", "Clients",
                    synonymes=("intitule", "libelle")),
            Colonne("Tiers", "Pour un compte de tiers (facultatif)", ""),
            Colonne("Débit", "Solde débiteur", "1250000", synonymes=("debit",)),
            Colonne("Crédit", "Solde créditeur", "", synonymes=("credit",)),
        ],
    },
    "ecritures": {
        "libelle": "Écritures comptables",
        "groupe": "Comptabilité",
        "notice": [
            "Une ligne du fichier = une ligne d'écriture (un compte, un montant).",
            "Les lignes qui portent le même « N° écriture » forment une seule",
            "écriture : elles doivent s'équilibrer entre elles (total des débits",
            "égal au total des crédits).",
            "",
            "Tenez votre fichier comme un journal : une case laissée vide reprend",
            "la valeur de la ligne du dessus. Vous n'écrivez donc la date, le",
            "journal et le numéro qu'une seule fois par écriture.",
            "",
            "Le journal s'écrit par son code (CA) ou par son nom (Caisse).",
            "",
            "Une ligne de totaux en bas du tableau est ignorée d'elle-même.",
            "",
            "La colonne « Périmètre » accepte : Déclaré ou Non déclaré. Laissée",
            "vide, elle prend la valeur par défaut du dossier. Un même fichier",
            "peut donc contenir les deux.",
            "",
            "Les montants s'écrivent sans symbole : 16000000 ou 16 000 000,00.",
            "Les dates s'écrivent JJ/MM/AAAA ou AAAA-MM-JJ.",
        ],
        "colonnes": [
            # Facultative : à défaut, les lignes d'une même écriture sont
            # reconnues par leur date, leur journal et leur libellé.
            # « piece » n'est pas un synonyme ici : il désigne la colonne
            # « N° de pièce » plus bas.
            Colonne("N° écriture", "Regroupe les lignes d'une même écriture",
                    "1", synonymes=("n° ecriture", "numero", "n°", "n° ecr")),
            Colonne("Date", "Date de l'opération", "15/03/2026", requis=True),
            Colonne("Journal", "Code du journal (OD, VE, AC, BQ, CA…)", "VE",
                    requis=True),
            Colonne("Libellé", "Intitulé de l'écriture", "Vente lot A05",
                    requis=True, synonymes=("libelle", "intitule")),
            Colonne("Compte", "Numéro de compte du plan comptable", "411",
                    requis=True, synonymes=("compte general", "n° compte")),
            Colonne("Tiers", "Nom ou code du tiers (facultatif)", "BENALI Karim"),
            Colonne("Débit", "Montant au débit", "16000000", synonymes=("debit",)),
            Colonne("Crédit", "Montant au crédit", "", synonymes=("credit",)),
            Colonne("Périmètre", "Déclaré ou Non déclaré", "Déclaré",
                    synonymes=("perimetre",)),
            Colonne("N° de pièce", "Référence du justificatif", "FA-2026-014",
                    synonymes=("piece", "n° piece", "justificatif")),
        ],
    },
    "factures_vente": {
        "libelle": "Factures de vente", "groupe": "Comptabilité",
        "sens": "vente", "notice": _NOTICE_FACTURES,
        "colonnes": _COLONNES_FACTURES,
    },
    "factures_achat": {
        "libelle": "Factures d'achat", "groupe": "Comptabilité",
        "sens": "achat", "notice": _NOTICE_FACTURES,
        "colonnes": _COLONNES_FACTURES,
    },
    "reglements": {
        "libelle": "Règlements (encaissements et décaissements)",
        "groupe": "Comptabilité",
        "notice": [
            "Rattache un paiement à une facture déjà enregistrée.",
            "",
            "« Sens » vaut encaissement (client) ou decaissement (fournisseur).",
            "",
            "Le règlement est enregistré sans écriture comptable : la balance",
            "d'ouverture, ou les écritures importées, portent déjà la",
            "trésorerie à la date de reprise. La facture est simplement",
            "marquée réglée à hauteur du montant.",
        ],
        "colonnes": [
            Colonne("N° facture", "Facture réglée, telle qu'importée",
                    "FA-2026-014", requis=True,
                    synonymes=("facture", "numero facture")),
            Colonne("Date", "Date du règlement", "20/03/2026", requis=True),
            Colonne("Montant", "Montant réglé", "654500", requis=True),
            Colonne("Sens", "encaissement ou decaissement", "encaissement",
                    requis=True),
            Colonne("Mode", "espece, cheque, virement ou traite", "virement"),
            Colonne("Compte de trésorerie", "Code du compte encaisseur", "BNA",
                    synonymes=("tresorerie", "banque", "caisse")),
            Colonne("Référence", "N° de chèque, référence de virement", ""),
        ],
    },
    "comptes": {
        "libelle": "Plan comptable (comptes supplémentaires)",
        "groupe": "Comptabilité",
        "table": "comptes", "cle_unique": "numero",
        "defauts": {"actif": 1},
        "notice": [
            "N'indiquez ici que les comptes qui manquent au plan SCF livré avec",
            "l'application : les comptes existants ne sont pas modifiés.",
            "",
            "La classe est déduite du premier chiffre du numéro.",
        ],
        "colonnes": [
            Colonne("Compte", "Numéro du compte", "4011", requis=True,
                    champ="numero", synonymes=("numero", "n° compte")),
            Colonne("Intitulé", "Libellé du compte", "Fournisseurs de travaux",
                    requis=True, champ="intitule", synonymes=("intitule", "libelle")),
            Colonne("Lettrable", "oui / non — pour les comptes de tiers", "oui",
                    champ="lettrable", type="oui_non"),
        ],
    },
    "tresorerie": {
        "libelle": "Comptes de trésorerie (banques et caisses)",
        "groupe": "Comptabilité",
        "table": "comptes_tresorerie", "cle_unique": "code",
        "defauts": {"actif": 1, "devise": "DZD"},
        "notice": [
            "Un compte par banque et par caisse.",
            "",
            "« Compte » est le compte du plan comptable rattaché : 5121 pour",
            "une banque, 53 pour une caisse.",
            "",
            "Un compte séquestre reçoit les fonds des acquéreurs en VSP ;",
            "rattachez-le à son programme.",
        ],
        "colonnes": [
            Colonne("Code", "Identifiant court", "BNA", requis=True, champ="code"),
            Colonne("Libellé", "Nom du compte", "BNA agence Didouche",
                    requis=True, champ="libelle", synonymes=("libelle", "nom")),
            Colonne("Type", "banque ou caisse", "banque", champ="type",
                    type="minuscule", valeurs={"banque", "caisse"}),
            Colonne("Compte", "Compte comptable rattaché", "5121", requis=True,
                    champ="compte", reference="compte"),
            Colonne("Banque", "Nom de l'établissement", "BNA", champ="banque"),
            Colonne("Agence", "Agence bancaire", "Didouche Mourad", champ="agence"),
            Colonne("RIB", "Relevé d'identité bancaire", "", champ="rib"),
            Colonne("Séquestre", "oui si compte séquestre VSP", "non",
                    champ="est_sequestre", type="oui_non"),
            Colonne("Programme", "Programme du séquestre (facultatif)", "",
                    champ="programme_id", reference="programme"),
        ],
    },
    "immobilisations": {
        "libelle": "Immobilisations",
        "groupe": "Comptabilité",
        "table": "immobilisations", "cle_unique": "code",
        "defauts": {"statut": "en_service", "mode": "lineaire"},
        "notice": [
            "Reprise du parc existant : aucune écriture d'acquisition n'est",
            "générée, la balance d'ouverture porte déjà la valeur et les",
            "amortissements cumulés.",
            "",
            "« Durée » s'exprime en mois (5 ans = 60).",
            "",
            "Comptes usuels : 213 constructions, 218 autres immobilisations,",
            "2182 matériel de transport.",
            "",
            "Laissez « Compte amortissement » et « Compte dotation » vides :",
            "l'application les déduit du compte d'immobilisation.",
        ],
        "colonnes": [
            Colonne("Code", "Identifiant interne", "IMMO-001", requis=True,
                    champ="code"),
            Colonne("Désignation", "Nature du bien", "Véhicule utilitaire",
                    requis=True, champ="designation",
                    synonymes=("designation", "libelle")),
            Colonne("Compte", "Compte d'immobilisation", "2182", requis=True,
                    champ="compte", reference="compte"),
            Colonne("Compte amortissement", "Déduit du compte si laissé vide",
                    "", champ="compte_amort", reference="compte",
                    synonymes=("compte amort", "amortissement")),
            Colonne("Compte dotation", "Déduit si laissé vide", "",
                    champ="compte_dotation", reference="compte"),
            Colonne("Date d'acquisition", "Date d'achat", "01/02/2024",
                    requis=True, champ="date_acquisition", type="date",
                    synonymes=("date acquisition", "acquisition")),
            Colonne("Date de mise en service", "Départ de l'amortissement",
                    "01/02/2024", champ="date_mise_service", type="date",
                    synonymes=("mise en service",)),
            Colonne("Valeur d'acquisition", "Coût d'achat hors taxes", "2400000",
                    champ="valeur_acquisition", type="montant",
                    synonymes=("valeur", "valeur acquisition", "montant")),
            Colonne("Valeur résiduelle", "Valeur en fin de vie", "",
                    champ="valeur_residuelle", type="montant"),
            Colonne("Durée (mois)", "Durée d'amortissement en mois", "60",
                    champ="duree_mois", type="entier",
                    synonymes=("duree", "duree mois")),
        ],
    },
    # -- Tiers -------------------------------------------------------------
    "tiers": {
        "libelle": "Tiers (clients, fournisseurs, propriétaires, locataires)",
        "groupe": "Tiers",
        "table": "tiers", "cle_unique": "raison_sociale",
        "defauts": {"actif": 1, "cree_le": util.maintenant,
                    "code": lambda societe_id, v: db.numero_suivant(societe_id, "tiers")},
        "notice": [
            "La colonne « Type » accepte : client, fournisseur, mandant,",
            "locataire, acquereur, salarie, autre.",
            "",
            "« mandant » désigne le propriétaire pour lequel l'agence gère un",
            "bien ; « acquereur » l'acheteur d'un lot en promotion.",
        ],
        "colonnes": [
            Colonne("Type", "client, fournisseur, mandant, locataire, acquereur",
                    "client", requis=True, champ="type", type="minuscule",
                    valeurs=TYPES_TIERS),
            Colonne("Raison sociale", "Nom de la personne ou de l'entreprise",
                    "BENALI Karim", requis=True, champ="raison_sociale",
                    synonymes=("nom", "raison_sociale", "denomination")),
            Colonne("NIF", "Numéro d'identification fiscale", "000116001234567",
                    champ="nif"),
            Colonne("NIS", "Numéro d'identification statistique", "", champ="nis"),
            Colonne("RC", "Registre de commerce", "", champ="rc"),
            Colonne("Article", "Article d'imposition", "",
                    champ="article_imposition",
                    synonymes=("article imposition", "article_imposition")),
            Colonne("Adresse", "Adresse postale", "12 rue Didouche Mourad",
                    champ="adresse"),
            Colonne("Commune", "Commune", "Alger-Centre", champ="commune"),
            Colonne("Wilaya", "Wilaya", "16 Alger", champ="wilaya"),
            Colonne("Téléphone", "Numéro de téléphone", "0550112233",
                    champ="telephone", synonymes=("telephone", "tel")),
            Colonne("Courriel", "Adresse e-mail", "", champ="email",
                    synonymes=("email", "mail")),
        ],
    },
    "salaries": {
        "libelle": "Salariés", "groupe": "Tiers",
        "table": "salaries", "cle_unique": "matricule",
        "defauts": {"actif": 1},
        "notice": [
            "Le salaire de base s'entend brut mensuel, en dinars.",
            "",
            "La date d'embauche sert au calcul de l'ancienneté.",
        ],
        "colonnes": [
            Colonne("Matricule", "Identifiant interne", "S001", requis=True,
                    champ="matricule"),
            Colonne("Nom", "Nom de famille", "SAADI", requis=True, champ="nom"),
            Colonne("Prénom", "Prénom", "Yacine", requis=True, champ="prenom",
                    synonymes=("prenom",)),
            Colonne("Poste", "Fonction occupée", "Comptable", champ="poste"),
            Colonne("Catégorie", "Catégorie socioprofessionnelle", "",
                    champ="categorie"),
            Colonne("Date d'embauche", "Date d'entrée", "01/02/2024",
                    champ="date_embauche", type="date",
                    synonymes=("date embauche", "embauche")),
            Colonne("Type de contrat", "CDI, CDD…", "CDI", champ="type_contrat",
                    synonymes=("contrat", "type contrat")),
            Colonne("Salaire de base", "Brut mensuel", "60000",
                    champ="salaire_base", type="montant",
                    synonymes=("salaire", "salaire base")),
            Colonne("Primes", "Primes mensuelles", "", champ="primes",
                    type="montant"),
            Colonne("Nombre d'enfants", "Pour l'IRG", "", champ="nb_enfants",
                    type="entier", synonymes=("enfants", "nb enfants")),
            Colonne("N° sécurité sociale", "Numéro CNAS", "", champ="num_secu",
                    synonymes=("cnas", "securite sociale", "n° cnas")),
            Colonne("RIB", "Compte bancaire du salarié", "", champ="rib"),
        ],
    },
    # -- Agence immobilière ------------------------------------------------
    "biens": {
        "libelle": "Biens en portefeuille", "groupe": "Agence immobilière",
        "table": "biens", "cle_unique": "reference",
        "defauts": {"statut": "disponible", "cree_le": util.maintenant},
        "notice": [
            "La colonne « Type » accepte : appartement, villa, local, terrain,",
            "bureau, hangar, autre.",
            "",
            "Renseignez « Loyer mensuel » pour un bien en location, « Prix de",
            "vente » pour un bien à vendre.",
            "",
            "Le propriétaire n'a pas besoin d'exister : s'il est inconnu, il",
            "est créé avec son nom, à compléter ensuite.",
        ],
        "colonnes": [
            Colonne("Référence", "Référence interne du bien", "APT-001",
                    requis=True, champ="reference", synonymes=("reference", "ref")),
            Colonne("Désignation", "Description du bien", "F3 à Hydra, 95 m²",
                    requis=True, champ="designation",
                    synonymes=("designation", "libelle", "intitule")),
            Colonne("Type", "appartement, villa, local, terrain…", "appartement",
                    champ="type_bien", type="minuscule",
                    synonymes=("type bien", "nature")),
            Colonne("Surface", "Surface en m²", "95", champ="surface",
                    type="surface"),
            Colonne("Nombre de pièces", "F3 => 3", "3", champ="nb_pieces",
                    type="entier", synonymes=("pieces", "nb pieces")),
            Colonne("Étage", "Étage", "2", champ="etage", type="entier"),
            Colonne("Adresse", "Adresse du bien", "14 rue des Frères Aïssou",
                    champ="adresse"),
            Colonne("Commune", "Commune", "Hydra", champ="commune"),
            Colonne("Wilaya", "Wilaya", "16 Alger", champ="wilaya"),
            Colonne("Loyer mensuel", "Pour un bien en location", "45000",
                    champ="loyer_mensuel", type="montant",
                    synonymes=("loyer", "loyer mensuel")),
            Colonne("Prix de vente", "Pour un bien à vendre", "",
                    champ="prix_demande", type="montant",
                    synonymes=("prix", "prix demande", "prix vente")),
            Colonne("Propriétaire", "Nom du mandant (tiers existant)",
                    "BENALI Karim", champ="proprietaire_id", reference="tiers",
                    synonymes=("proprietaire", "mandant")),
        ],
    },
    "mandats": {
        "libelle": "Mandats de vente et de gestion",
        "groupe": "Agence immobilière",
        "table": "mandats", "cle_unique": "numero",
        "defauts": {"statut": "actif", "cree_le": util.maintenant},
        "notice": [
            "« Type » accepte : vente, location, gestion.",
            "",
            "La commission s'exprime soit en taux (5 pour 5 %), soit en montant",
            "forfaitaire. Renseignez l'une ou l'autre.",
            "",
            "Le bien et le mandant n'ont pas besoin d'exister : inconnus, ils",
            "sont créés avec leur référence, à compléter ensuite.",
        ],
        "colonnes": [
            Colonne("N° mandat", "Référence du mandat", "MD-2026-001",
                    requis=True, champ="numero", synonymes=("numero", "mandat")),
            Colonne("Bien", "Référence du bien", "APT-001", requis=True,
                    champ="bien_id", reference="bien"),
            Colonne("Mandant", "Propriétaire", "BENALI Karim",
                    champ="mandant_id", reference="tiers",
                    synonymes=("proprietaire",)),
            Colonne("Type", "vente, location ou gestion", "gestion",
                    champ="type_mandat", type="minuscule",
                    valeurs={"vente", "location", "gestion"},
                    synonymes=("type mandat",)),
            Colonne("Exclusif", "oui / non", "non", champ="exclusif",
                    type="oui_non"),
            Colonne("Date de début", "Prise d'effet", "01/01/2026", requis=True,
                    champ="date_debut", type="date", synonymes=("date debut", "debut")),
            Colonne("Date de fin", "Échéance du mandat", "31/12/2026",
                    champ="date_fin", type="date", synonymes=("date fin", "fin")),
            Colonne("Prix mandat", "Prix convenu", "", champ="prix_mandat",
                    type="montant"),
            Colonne("Taux commission", "En pourcentage", "5",
                    champ="taux_commission", type="taux",
                    synonymes=("commission", "taux")),
            Colonne("Commission forfaitaire", "Montant fixe", "",
                    champ="commission_forfait", type="montant"),
        ],
    },
    "baux": {
        "libelle": "Baux de location", "groupe": "Agence immobilière",
        "table": "baux", "cle_unique": "numero",
        "defauts": {"statut": "actif", "cree_le": util.maintenant,
                    "periodicite_mois": 1},
        "notice": [
            "Le bien, le propriétaire et le locataire sont créés s'ils sont",
            "inconnus : aucun fichier n'est à passer avant celui-ci.",
            "",
            "« Jour d'échéance » est le jour du mois où le loyer est dû.",
            "",
            "« Taux de gestion » est la part revenant à l'agence, en",
            "pourcentage du loyer encaissé.",
            "",
            "Aucun loyer n'est généré à l'import : reprenez les quittances déjà",
            "émises par le modèle « Loyers et quittances ».",
        ],
        "colonnes": [
            Colonne("N° bail", "Référence du bail", "BX-2026-001", requis=True,
                    champ="numero", synonymes=("numero", "bail")),
            Colonne("Bien", "Référence du bien loué", "APT-001", requis=True,
                    champ="bien_id", reference="bien"),
            Colonne("Propriétaire", "Mandant", "BENALI Karim",
                    champ="proprietaire_id", reference="tiers",
                    synonymes=("mandant", "bailleur")),
            Colonne("Locataire", "Preneur", "CHERIF Sofiane", requis=True,
                    champ="locataire_id", reference="tiers"),
            Colonne("Usage", "habitation ou professionnel", "habitation",
                    champ="usage", type="minuscule"),
            Colonne("Date de début", "Prise d'effet", "01/01/2026", requis=True,
                    champ="date_debut", type="date", synonymes=("date debut", "debut")),
            Colonne("Date de fin", "Fin du bail", "31/12/2026", champ="date_fin",
                    type="date", synonymes=("date fin", "fin")),
            Colonne("Durée (mois)", "Durée en mois", "12", champ="duree_mois",
                    type="entier", synonymes=("duree",)),
            Colonne("Loyer mensuel", "Hors charges", "45000", requis=True,
                    champ="loyer_mensuel", type="montant", synonymes=("loyer",)),
            Colonne("Charges mensuelles", "Provisions pour charges", "",
                    champ="charges_mensuelles", type="montant",
                    synonymes=("charges",)),
            Colonne("Caution", "Dépôt de garantie", "90000", champ="caution",
                    type="montant"),
            Colonne("Jour d'échéance", "Jour du mois", "5",
                    champ="jour_echeance", type="entier",
                    synonymes=("jour echeance", "echeance")),
            Colonne("Taux de gestion", "Part de l'agence, en %", "5",
                    champ="taux_gestion", type="taux",
                    synonymes=("taux gestion", "gestion")),
            Colonne("Encaissé par l'agence", "oui si l'agence encaisse", "oui",
                    champ="encaisse_par_agence", type="oui_non",
                    synonymes=("encaisse par agence", "encaissement agence")),
        ],
    },
    "quittances": {
        "libelle": "Loyers et quittances déjà émis",
        "groupe": "Agence immobilière",
        "table": "quittances", "cle_unique": "numero",
        "defauts": {"cree_le": util.maintenant},
        "notice": [
            "Reprise de l'historique des loyers : aucune écriture comptable",
            "n'est générée, la balance d'ouverture porte déjà les créances et",
            "les sommes dues aux propriétaires.",
            "",
            "« Période » s'écrit AAAA-MM (2026-03) ou 03/2026.",
            "",
            "« Statut » accepte : emise, encaissee, reversee, impayee.",
            "Laissez « Montant encaissé » vide pour un loyer impayé.",
        ],
        "colonnes": [
            Colonne("N° quittance", "Référence", "QT-2026-0031", requis=True,
                    champ="numero", synonymes=("numero", "quittance")),
            Colonne("Bail", "N° du bail", "BX-2026-001", requis=True,
                    champ="bail_id", reference="bail"),
            Colonne("Période", "Mois concerné", "2026-03", requis=True,
                    champ="periode", synonymes=("periode", "mois")),
            Colonne("Date d'échéance", "Date d'exigibilité", "05/03/2026",
                    requis=True, champ="date_echeance", type="date",
                    synonymes=("date echeance", "echeance")),
            Colonne("Loyer", "Loyer hors charges", "45000", champ="loyer",
                    type="montant"),
            Colonne("Charges", "Charges de la période", "", champ="charges",
                    type="montant"),
            Colonne("Total", "Loyer + charges", "45000", champ="total",
                    type="montant"),
            Colonne("Honoraires HT", "Part de l'agence", "2250",
                    champ="honoraires_gestion_ht", type="montant",
                    synonymes=("honoraires", "honoraires ht")),
            Colonne("Net propriétaire", "Somme due au mandant", "42322",
                    champ="net_proprietaire", type="montant",
                    synonymes=("net proprietaire", "net")),
            Colonne("Montant encaissé", "Ce qui a été perçu", "45000",
                    champ="montant_encaisse", type="montant",
                    synonymes=("encaisse", "montant encaisse")),
            Colonne("Date d'encaissement", "Date de perception", "05/03/2026",
                    champ="date_encaissement", type="date",
                    synonymes=("date encaissement",)),
            Colonne("Statut", "emise, encaissee, reversee, impayee", "encaissee",
                    champ="statut", type="minuscule",
                    valeurs={"emise", "encaissee", "reversee", "impayee"}),
            Colonne("Périmètre", "Déclaré ou Non déclaré", "Déclaré",
                    champ="perimetre", synonymes=("perimetre",)),
        ],
    },
    # -- Promotion immobilière ---------------------------------------------
    "programmes": {
        "libelle": "Programmes immobiliers", "groupe": "Promotion immobilière",
        "table": "programmes", "cle_unique": "code",
        "defauts": {"statut": "en_cours", "cree_le": util.maintenant},
        "notice": [
            "Un programme = une opération de promotion (une résidence).",
            "",
            "Les budgets servent au suivi du coût de revient : ils peuvent être",
            "complétés plus tard dans l'application.",
            "",
            "« Avancement » s'exprime en pourcentage (40 pour 40 %).",
        ],
        "colonnes": [
            Colonne("Code", "Identifiant du programme", "JASMINS", requis=True,
                    champ="code"),
            Colonne("Intitulé", "Nom du programme", "Résidence Les Jasmins",
                    requis=True, champ="intitule", synonymes=("intitule", "nom")),
            Colonne("Adresse", "Adresse du chantier", "Route de Baba Hassen",
                    champ="adresse"),
            Colonne("Commune", "Commune", "Draria", champ="commune"),
            Colonne("Wilaya", "Wilaya", "16 Alger", champ="wilaya"),
            Colonne("Surface terrain", "En m²", "3200", champ="surface_terrain",
                    type="surface", synonymes=("surface terrain", "terrain")),
            Colonne("Surface bâtie", "En m²", "5400", champ="surface_batie",
                    type="surface", synonymes=("surface batie",)),
            Colonne("Nombre de logements", "Lots d'habitation", "48",
                    champ="nb_logements", type="entier",
                    synonymes=("logements", "nb logements")),
            Colonne("Nombre de locaux", "Locaux commerciaux", "4",
                    champ="nb_locaux", type="entier", synonymes=("locaux",)),
            Colonne("N° permis de construire", "Référence du permis", "",
                    champ="num_permis_construire",
                    synonymes=("permis", "permis de construire")),
            Colonne("Date du permis", "Date de délivrance", "",
                    champ="date_permis", type="date"),
            Colonne("Date début travaux", "Ouverture du chantier", "01/03/2025",
                    champ="date_debut_travaux", type="date",
                    synonymes=("debut travaux",)),
            Colonne("Date de livraison prévue", "Échéance", "31/12/2027",
                    champ="date_fin_prevue", type="date",
                    synonymes=("date fin prevue", "livraison prevue")),
            Colonne("Budget terrain", "Coût du terrain", "",
                    champ="budget_terrain", type="montant"),
            Colonne("Budget travaux", "Coût des travaux", "",
                    champ="budget_travaux", type="montant"),
            Colonne("Avancement", "En pourcentage", "40", champ="avancement",
                    type="taux"),
        ],
    },
    "lots": {
        "libelle": "Lots des programmes", "groupe": "Promotion immobilière",
        "table": "lots", "cle_unique": None,
        "defauts": {"statut": "libre"},
        "notice": [
            "Un lot = un logement ou un local à vendre.",
            "",
            "Le programme est créé s'il est inconnu, avec son seul code : le",
            "fichier des programmes le complétera, avant ou après celui-ci.",
            "",
            "« Statut » accepte : libre, reserve, vendu, livre.",
            "",
            "Le numéro doit être unique à l'intérieur d'un programme.",
        ],
        "colonnes": [
            Colonne("Programme", "Code du programme", "JASMINS", requis=True,
                    champ="programme_id", reference="programme"),
            Colonne("N° lot", "Numéro du lot", "A05", requis=True,
                    champ="numero", synonymes=("numero", "lot")),
            Colonne("Type", "logement, local, parking, cave", "logement",
                    champ="type_lot", type="minuscule",
                    synonymes=("type lot", "nature")),
            Colonne("Typologie", "F2, F3, F4…", "F3", champ="typologie"),
            Colonne("Bâtiment", "Bâtiment", "A", champ="batiment"),
            Colonne("Étage", "Étage", "2", champ="etage", type="entier"),
            Colonne("Surface habitable", "En m²", "95",
                    champ="surface_habitable", type="surface",
                    synonymes=("surface", "surface habitable")),
            Colonne("Surface utile", "En m²", "", champ="surface_utile",
                    type="surface"),
            Colonne("Prix de vente", "Prix du lot", "8500000",
                    champ="prix_vente", type="montant",
                    synonymes=("prix", "prix vente")),
            Colonne("Statut", "libre, reserve, vendu, livre", "libre",
                    champ="statut", type="minuscule",
                    valeurs={"libre", "reserve", "vendu", "livre"}),
        ],
    },
    "contrats_vsp": {
        "libelle": "Contrats de vente sur plan (VSP)",
        "groupe": "Promotion immobilière",
        "table": "contrats_vsp", "cle_unique": "numero",
        "defauts": {"statut": "en_cours", "cree_le": util.maintenant},
        "notice": [
            "Le programme, le lot et l'acquéreur sont créés s'ils sont inconnus,",
            "avec leur seul nom, à compléter ensuite. Un lot demande toutefois",
            "que sa colonne « Programme » soit renseignée : sans elle, on ne",
            "sait pas dans quel programme le ranger.",
            "",
            "« Montant encaissé » reprend le cumul déjà perçu à la date de",
            "reprise. Aucune écriture n'est générée : la balance d'ouverture",
            "porte déjà les avances reçues au compte 4191.",
            "",
            "L'échéancier se reprend séparément, par le modèle « Échéanciers",
            "VSP ».",
        ],
        "colonnes": [
            Colonne("N° contrat", "Référence du contrat", "VSP-2026-007",
                    requis=True, champ="numero", synonymes=("numero", "contrat")),
            Colonne("Programme", "Code du programme", "JASMINS", requis=True,
                    champ="programme_id", reference="programme"),
            Colonne("N° lot", "Lot vendu", "A05", requis=True, champ="lot_id",
                    reference="lot", parent="Programme", synonymes=("lot",)),
            Colonne("Acquéreur", "Acheteur", "ZEROUAL Mourad", requis=True,
                    champ="acquereur_id", reference="tiers",
                    synonymes=("acquereur", "client")),
            Colonne("Type", "reservation ou vente", "vente",
                    champ="type_contrat", type="minuscule",
                    synonymes=("type contrat",)),
            Colonne("Date de réservation", "Date de la réservation", "",
                    champ="date_reservation", type="date",
                    synonymes=("date reservation", "reservation")),
            Colonne("Date du contrat", "Date de signature", "10/02/2026",
                    champ="date_contrat", type="date",
                    synonymes=("date contrat", "date")),
            Colonne("N° acte notarié", "Référence de l'acte", "",
                    champ="num_acte_notarie", synonymes=("acte", "acte notarie")),
            Colonne("Prix total", "Prix de vente TTC", "8500000", requis=True,
                    champ="prix_total", type="montant", synonymes=("prix",)),
            Colonne("Taux TVA", "Taux applicable", "19", champ="taux_tva",
                    type="taux"),
            Colonne("Montant encaissé", "Cumul déjà perçu", "3400000",
                    champ="montant_encaisse", type="montant",
                    synonymes=("encaisse", "montant encaisse")),
            Colonne("Statut", "en_cours, livre, resilie", "en_cours",
                    champ="statut", type="minuscule"),
        ],
    },
    "echeances_vsp": {
        "libelle": "Échéanciers VSP", "groupe": "Promotion immobilière",
        "table": "echeances_vsp", "cle_unique": None,
        "defauts": {"statut": "a_venir"},
        "sans_societe": True,
        "notice": [
            "Une ligne = une tranche de l'échéancier d'un contrat.",
            "",
            "Le contrat, lui, doit exister : une échéance appartient à un",
            "contrat, avec son prix et son plan de paiement. Passez le fichier",
            "des contrats — avant ou après le reste, peu importe.",
            "",
            "Renseignez soit le pourcentage du prix, soit le montant.",
            "",
            "« Statut » accepte : a_venir, appelee, reglee.",
        ],
        "colonnes": [
            Colonne("N° contrat", "Contrat concerné", "VSP-2026-007",
                    requis=True, champ="contrat_id", reference="contrat_vsp",
                    synonymes=("contrat",)),
            Colonne("Ordre", "Rang de la tranche", "1", champ="ordre",
                    type="entier", synonymes=("rang", "n°")),
            Colonne("Libellé", "Intitulé de la tranche", "Achèvement fondations",
                    requis=True, champ="libelle", synonymes=("libelle", "tranche")),
            Colonne("Pourcentage", "Part du prix, en %", "20",
                    champ="pourcentage", type="taux", synonymes=("pourcentage", "%")),
            Colonne("Montant", "Montant de la tranche", "1700000",
                    champ="montant", type="montant"),
            Colonne("Date prévue", "Date d'exigibilité", "30/06/2026",
                    champ="date_prevue", type="date",
                    synonymes=("date prevue", "echeance")),
            Colonne("Montant réglé", "Déjà encaissé sur la tranche", "",
                    champ="montant_regle", type="montant",
                    synonymes=("regle", "montant regle")),
            Colonne("Statut", "a_venir, appelee, reglee", "a_venir",
                    champ="statut", type="minuscule"),
        ],
    },
}

#: Ordre d'affichage des modèles à l'écran — un rangement, pas une marche à
#: suivre. Les fichiers se déposent dans l'ordre qui arrange celui qui les a :
#: ce qu'un fichier cite et qui n'existe pas encore est créé avec lui, puis
#: complété par le fichier qui le décrit, qu'il arrive avant ou après.
ORDRE_AFFICHAGE = [
    "comptes", "tiers", "tresorerie", "balance_ouverture", "biens", "mandats",
    "baux", "quittances", "programmes", "lots", "contrats_vsp", "echeances_vsp",
    "immobilisations", "salaries", "factures_vente", "factures_achat",
    "reglements", "ecritures",
]

GROUPES = ["Comptabilité", "Tiers", "Agence immobilière", "Promotion immobilière"]


# ---------------------------------------------------------------------------
# Fabrication des modèles vierges
# ---------------------------------------------------------------------------

def construit_modele(cle: str) -> bytes:
    modele = MODELES[cle]
    classeur = tableur.Classeur()

    feuille = classeur.feuille("Données")
    feuille.entetes(*[c.nom for c in modele["colonnes"]])
    feuille.ajoute(*[tableur.texte(c.exemple) for c in modele["colonnes"]])
    feuille.largeurs_auto(*[max(12, min(34, len(c.nom) + 6))
                            for c in modele["colonnes"]])

    notice = classeur.feuille("Notice")
    notice.titre(f"Import — {modele['libelle']}")
    notice.vide()
    notice.ajoute(tableur.texte("Comment procéder", tableur.GRAS))
    for ligne in [
        "1. Remplissez la feuille « Données » en gardant la ligne d'en-têtes.",
        "2. Effacez la ligne d'exemple.",
        "3. Enregistrez, puis déposez le fichier dans l'application :",
        "   Paramètres > Import de données.",
        "4. L'application contrôle tout avant d'écrire quoi que ce soit et",
        "   affiche les anomalies avec leur numéro de ligne.",
    ]:
        notice.ajoute(tableur.texte(ligne))
    notice.vide()
    for ligne in modele["notice"]:
        notice.ajoute(tableur.texte(ligne))
    notice.vide()
    notice.ajoute(tableur.texte("Colonnes", tableur.GRAS))
    notice.entetes("Colonne", "Obligatoire", "Contenu attendu")
    for colonne in modele["colonnes"]:
        notice.ajoute(tableur.texte(colonne.nom),
                      tableur.texte("oui" if colonne.requis else ""),
                      tableur.texte(colonne.aide))
    notice.largeurs_auto(26, 13, 60)
    return classeur.octets()


@route("GET", "/api/import/modeles")
def api_modeles(ctx):
    return {
        "groupes": GROUPES,
        # Ce que l'import crée de lui-même, et les quelques renvois qui
        # restent exigés — pour que l'écran le dise sans les énumérer à la main.
        "creables": sorted(LIBELLES_REFERENCE[r] for r in CREABLES),
        "exiges": [{"libelle": LIBELLES_REFERENCE[r], "pourquoi": p.lstrip(" —")}
                   for r, p in POURQUOI_EXIGE.items()],
        "modeles": [
            {"cle": cle, "libelle": MODELES[cle]["libelle"],
             "groupe": MODELES[cle].get("groupe", "Comptabilité"),
             "colonnes": [{"nom": c.nom, "requis": c.requis, "aide": c.aide}
                          for c in MODELES[cle]["colonnes"]]}
            for cle in sorted(MODELES,
                              key=lambda c: ORDRE_AFFICHAGE.index(c)
                              if c in ORDRE_AFFICHAGE else 99)
        ],
    }


@route("GET", "/api/import/modele/<cle>")
def api_telecharge_modele(ctx):
    cle = ctx.params["cle"]
    if cle not in MODELES:
        raise ErreurApplicative("Modèle inconnu.", 404)
    return Reponse(
        construit_modele(cle),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        nom_fichier=f"modele-{cle}.xlsx")


# ---------------------------------------------------------------------------
# Lecture d'un fichier déposé
# ---------------------------------------------------------------------------

def _normalise_entete(texte: str) -> str:
    propre = _sans_accent(texte).replace("_", " ").replace(".", " ")
    return " ".join(propre.split())


def associe_colonnes(entetes: list[str], modele: dict) -> dict[str, int]:
    """Fait correspondre les en-têtes du fichier aux colonnes attendues.

    Tolérant : accents, majuscules, espaces et quelques synonymes usuels.
    """
    presents = {_normalise_entete(e): i for i, e in enumerate(entetes)}
    association = {}
    for colonne in modele["colonnes"]:
        for candidat in (colonne.nom, *colonne.synonymes):
            index = presents.get(_normalise_entete(candidat))
            if index is not None:
                association[colonne.nom] = index
                break
    return association


def _decode_fichier(ctx) -> bytes:
    contenu = ctx.champ_requis("contenu")
    if contenu.startswith("data:") and "," in contenu[:120]:
        contenu = contenu.split(",", 1)[1]
    try:
        octets = base64.b64decode(contenu, validate=True)
    except Exception as err:                                   # noqa: BLE001
        raise ErreurApplicative(f"Fichier illisible : {err}") from err
    if len(octets) > TAILLE_MAX:
        raise ErreurApplicative("Fichier trop volumineux (16 Mio maximum).", 413)
    return octets


def _valeur(rang: list, association: dict, nom: str) -> str:
    index = association.get(nom)
    if index is None or index >= len(rang):
        return ""
    valeur = rang[index]
    return "" if valeur is None else str(valeur).strip()


def _perimetre(valeur: str, defaut: str) -> str:
    propre = _sans_accent(valeur)
    if not propre:
        return defaut
    if propre.startswith("non") or "hors" in propre:
        return "hors_declaration"
    return "declare"


def _tiers_id(societe_id: int, nom: str):
    return resout_reference("tiers", societe_id, nom)


# ---------------------------------------------------------------------------
# Ce dont l'import a besoin, il le crée
# ---------------------------------------------------------------------------
#
# Exiger que le plan comptable, les tiers et les journaux existent avant
# d'importer un journal d'écritures, c'est demander de reprendre son dossier
# trois fois, dans le bon ordre, en corrigeant à chaque tour. Ce qui manque
# et qui n'est qu'un nom se crée donc tout seul.
#
# Deux garde-fous, parce que créer à l'aveugle serait pire que refuser :
#
#   * seuls les éléments qui ne portent aucune décision sont créés — un
#     compte, un tiers, un journal. Un programme immobilier, un bail, un lot
#     engagent une structure : ceux-là restent à créer sciemment ;
#   * tout ce qui est créé est annoncé AVANT, listé APRÈS, et rattaché à
#     l'import — « Annuler cette reprise » les emporte avec le reste.

#: Compte collectif à donner au tiers créé, selon sa nature.
COMPTES_PAR_TYPE = {"client": "411", "fournisseur": "401",
                    "mandant": "4671", "salarie": "421", "autre": "411"}

#: Compte collectif -> nature du tiers qui s'y rattache.
TYPES_PAR_COLLECTIF = (
    ("467", "mandant"), ("411", "client"), ("41", "client"),
    ("401", "fournisseur"), ("40", "fournisseur"), ("42", "salarie"),
)

#: Code de journal -> son type, quand il se devine.
TYPES_JOURNAL = {"VE": "ventes", "AC": "achats", "BQ": "banque", "CA": "caisse",
                 "PA": "paie", "AN": "anouveaux", "OD": "od"}


def type_de_tiers(compte: str) -> str:
    for prefixe, type_tiers in TYPES_PAR_COLLECTIF:
        if str(compte or "").startswith(prefixe):
            return type_tiers
    return "autre"


def _compte_parent(societe_id: int, numero: str) -> dict | None:
    """Le compte existant le plus proche au-dessus : 4011 -> 401 -> 40.

    Un sous-compte hérite des caractéristiques du sien : sa nature, sa
    rubrique de bilan, son collectif. C'est ainsi qu'un plan comptable se
    détaille, et cela évite de demander ce que l'on sait déjà.
    """
    for longueur in range(len(numero) - 1, 0, -1):
        parent = db.ligne(
            "SELECT * FROM comptes WHERE numero = ? "
            "AND (societe_id = ? OR societe_id IS NULL) LIMIT 1",
            (numero[:longueur], societe_id))
        if parent:
            return parent
    return None


def compte_a_creer(societe_id: int, numero: str) -> dict:
    """Ce qu'on écrirait dans le plan pour ce compte-là."""
    parent = _compte_parent(societe_id, numero)
    return {
        "numero": numero,
        "intitule": (parent["intitule"] if parent else f"Compte {numero}"),
        "classe": int(numero[0]),
        "nature": parent["nature"] if parent else "mixte",
        "rubrique": parent["rubrique"] if parent else None,
        "collectif": parent["collectif"] if parent else None,
        "lettrable": parent["lettrable"] if parent else 0,
        "actif": 1,
        "parent": parent["numero"] if parent else None,
    }


class Manquants:
    """Ce que le fichier désigne et que le dossier ne connaît pas encore.

    Recense pendant l'analyse, crée à la validation. Les deux moments sont
    séparés à dessein : on montre d'abord, on écrit ensuite.
    """

    def __init__(self, societe_id: int):
        self.societe_id = societe_id
        self.comptes: dict = {}
        self.tiers: dict = {}
        self.journaux: dict = {}
        #: {(reference, valeur, parent) : {...}} — biens, programmes, lots.
        self.fiches: dict = {}

    def compte(self, numero: str) -> None:
        if numero and numero not in self.comptes:
            self.comptes[numero] = compte_a_creer(self.societe_id, numero)

    def tiers_nomme(self, nom: str, compte: str = "") -> None:
        cle = str(nom or "").strip().lower()
        if cle and cle not in self.tiers:
            self.tiers[cle] = {"raison_sociale": str(nom).strip(),
                               "type": type_de_tiers(compte)}

    def journal(self, code: str) -> None:
        propre = str(code or "").strip().upper()
        if propre and propre not in self.journaux:
            self.journaux[propre] = {
                "code": propre,
                "libelle": {"VE": "Ventes", "AC": "Achats", "BQ": "Banque",
                            "CA": "Caisse", "PA": "Paie",
                            "AN": "À-nouveaux"}.get(propre, str(code).strip()),
                "type": TYPES_JOURNAL.get(propre, "od"),
            }

    def fiche(self, reference: str, valeur: str, parent: str = "") -> None:
        """Une fiche qui n'a encore que son nom : bien, programme, lot."""
        cle = (reference, str(valeur).strip().lower(), str(parent or "").lower())
        if valeur and cle not in self.fiches:
            self.fiches[cle] = {"reference": reference,
                                "valeur": str(valeur).strip(),
                                "parent": str(parent or "").strip(),
                                "libelle": LIBELLES_REFERENCE.get(reference,
                                                                  reference)}

    def resume(self) -> dict:
        return {"comptes": list(self.comptes.values()),
                "tiers": list(self.tiers.values()),
                "journaux": list(self.journaux.values()),
                "fiches": list(self.fiches.values())}

    def __bool__(self) -> bool:
        return bool(self.comptes or self.tiers or self.journaux or self.fiches)


def cree_manquants(societe_id: int, a_creer: dict, utilisateur=None) -> dict:
    """Crée ce qui manquait. À appeler dans une transaction.

    Renvoie les identifiants créés, table par table, pour que l'annulation
    de l'import sache quoi reprendre.
    """
    crees: dict = {}
    for compte in (a_creer or {}).get("comptes", []):
        if db.ligne("SELECT id FROM comptes WHERE societe_id = ? AND numero = ?",
                    (societe_id, compte["numero"])):
            continue
        donnees = {c: v for c, v in compte.items() if c != "parent"}
        donnees["societe_id"] = societe_id
        donnees["incomplet"] = 1
        crees.setdefault("comptes", []).append(db.insere("comptes", donnees))

    for tiers in (a_creer or {}).get("tiers", []):
        if resout_reference("tiers", societe_id, tiers["raison_sociale"]):
            continue
        cle = f"tiers_{tiers['type']}"
        code = db.numero_suivant(
            societe_id, cle if cle in db.FORMATS_DEFAUT else "tiers_autre")
        crees.setdefault("tiers", []).append(db.insere("tiers", {
            "societe_id": societe_id, "code": code, "type": tiers["type"],
            "raison_sociale": tiers["raison_sociale"],
            # Le compte collectif suit le type : c'est là que ses écritures
            # iront se ranger.
            "compte_comptable": COMPTES_PAR_TYPE.get(tiers["type"], "411"),
            "actif": 1, "incomplet": 1, "cree_le": util.maintenant(),
        }))

    for journal in (a_creer or {}).get("journaux", []):
        if db.ligne("SELECT id FROM journaux WHERE societe_id = ? AND code = ?",
                    (societe_id, journal["code"])):
            continue
        crees.setdefault("journaux", []).append(db.insere("journaux", {
            "societe_id": societe_id, "code": journal["code"],
            "libelle": journal["libelle"], "type": journal["type"],
            "actif": 1, "incomplet": 1,
        }))

    # Les programmes d'abord : un lot a besoin du sien, et il vient peut-être
    # d'être créé à la ligne du dessus.
    fiches = (a_creer or {}).get("fiches", [])
    ordre = {"programme": 0, "bien": 1, "lot": 2}
    for fiche in sorted(fiches, key=lambda f: ordre.get(f["reference"], 9)):
        forme = FICHES_MINIMALES.get(fiche["reference"])
        if not forme or resout_reference(fiche["reference"], societe_id,
                                         fiche["valeur"]):
            continue
        donnees = {"societe_id": societe_id, "incomplet": 1,
                   forme["cle"]: fiche["valeur"], **forme["defauts"]}
        if forme.get("recopie"):
            donnees[forme["recopie"]] = fiche["valeur"]
        if forme.get("parent"):
            parent_id = resout_reference(forme["parent"], societe_id,
                                         fiche.get("parent"))
            if not parent_id:
                continue          # signalé à l'analyse, pas créé en silence
            donnees[f"{forme['parent']}_id"] = parent_id
        if "cree_le" in db.colonnes(forme["table"]):
            donnees["cree_le"] = util.maintenant()
        crees.setdefault(forme["table"], []).append(
            db.insere(forme["table"], donnees))
    if crees and utilisateur is not None:
        db.trace("creation_import", "reprise", None,
                 {t: len(i) for t, i in crees.items()}, utilisateur)
    return crees


# ---------------------------------------------------------------------------
# Contrôle générique d'une table
# ---------------------------------------------------------------------------

def analyse_generique(societe_id, rangs, association, modele, cle_modele):
    """Contrôle et prépare les lignes d'une table décrite de façon déclarative."""
    prets, anomalies, apercu, ignorees = [], [], [], []
    cle_unique = modele.get("cle_unique")
    table = modele["table"]
    # Deux situations que l'on confondait, et qui n'appellent pas la même
    # réponse : l'élément est déjà enregistré — il n'y a rien à faire, ce
    # n'est pas une erreur — ou il figure deux fois dans le fichier, et là
    # il faut le corriger. On garde la ligne du premier passage pour le dire.
    # {clé : (id, à compléter ?)} — une fiche née d'une simple mention dans
    # un autre fichier n'a que son nom. Quand le fichier qui la décrit
    # arrive, il doit la remplir, pas passer son chemin : c'est ce qui rend
    # l'ordre des imports indifférent.
    deja_en_base: dict = {}
    if cle_unique:
        a_completer = "incomplet" in db.colonnes(table)
        for r in db.lignes(
                f"SELECT id, {cle_unique}"
                + (", incomplet" if a_completer else "")
                + f" FROM {table} WHERE societe_id = ?", (societe_id,)):
            if r[cle_unique] is None:
                continue
            deja_en_base[str(r[cle_unique]).lower()] = (
                r["id"], bool(r["incomplet"]) if a_completer else False)
    vus_dans_le_fichier: dict = {}
    manquants = Manquants(societe_id)
    completes = 0

    for decalage, rang in enumerate(rangs):
        numero_ligne = decalage + 2          # +1 en-tête, +1 pour compter de 1
        if not any(str(c).strip() for c in rang):
            continue
        brut = {c.nom: _valeur(rang, association, c.nom)
                for c in modele["colonnes"]}
        erreurs = []
        enregistrement = {}
        resolus = {}

        for colonne in modele["colonnes"]:
            valeur = brut[colonne.nom]
            if colonne.requis and not valeur:
                erreurs.append(f"« {colonne.nom} » est obligatoire")
                continue
            if not colonne.champ:
                continue
            if colonne.valeurs and valeur:
                propre = _sans_accent(valeur)
                if propre not in colonne.valeurs:
                    erreurs.append(
                        f"{colonne.nom.lower()} « {valeur} » inconnu "
                        f"({', '.join(sorted(colonne.valeurs))})")
                    continue
            if colonne.reference:
                if not valeur:
                    continue
                parent_id = resolus.get(colonne.parent)
                identifiant = resout_reference(colonne.reference, societe_id,
                                               valeur, parent_id)
                if identifiant is None and colonne.reference in CREABLES:
                    # La référence est l'identité : la fiche naît avec ce
                    # nom, marquée « à compléter ». Aucun ordre à respecter,
                    # donc — le fichier qui la décrit vraiment la remplira,
                    # qu'il passe avant ou après.
                    manque = _reclame(manquants, colonne, valeur,
                                      brut.get(colonne.parent or "", ""))
                    if manque:
                        erreurs.append(manque)
                    elif colonne.reference == "compte":
                        enregistrement[colonne.champ] = str(valeur).strip()
                    continue
                if identifiant is None:
                    libelle = LIBELLES_REFERENCE[colonne.reference]
                    erreurs.append(f"{libelle} « {valeur} » introuvable"
                                   + _pourquoi_exige(colonne.reference))
                    continue
                resolus[colonne.nom] = identifiant
                enregistrement[colonne.champ] = identifiant
                continue
            try:
                enregistrement[colonne.champ] = CONVERTISSEURS[colonne.type](valeur)
            except (ValueError, TypeError):
                erreurs.append(f"« {colonne.nom} » : valeur « {valeur} » "
                               "incompréhensible")

        reference = (str(enregistrement.get(cle_unique, "")).lower()
                     if cle_unique and not erreurs else "")
        affichee = (brut.get(_nom_de_champ(modele, cle_unique))
                    if cle_unique else "")
        if reference and reference in deja_en_base:
            identifiant, a_remplir = deja_en_base[reference]
            if a_remplir:
                # Elle existe parce qu'un autre fichier l'a citée, et n'a que
                # son nom. Cette ligne-ci la décrit : on la remplit.
                enregistrement["_completer"] = identifiant
                erreurs += _controles_specifiques(societe_id, cle_modele, brut,
                                                  enregistrement)
                for message in erreurs:
                    anomalies.append({"ligne": numero_ligne, "message": message})
                apercu.append({"ligne": numero_ligne, "valeurs": brut,
                               "erreurs": erreurs, "complete": True})
                if not erreurs:
                    prets.append(enregistrement)
                    completes += 1
                continue
            # Rien à faire n'est pas une erreur : l'import reprend l'existant,
            # il ne le réécrit pas. Bloquer tout le fichier pour cela serait
            # absurde — un plan comptable repris est déjà là aux neuf dixièmes.
            ignorees.append({
                "ligne": numero_ligne,
                "message": f"« {affichee} » est déjà enregistré : rien à faire"})
            apercu.append({"ligne": numero_ligne, "valeurs": brut, "erreurs": []})
            continue
        if reference and reference in vus_dans_le_fichier:
            erreurs.append(f"« {affichee} » apparaît déjà à la ligne "
                           f"{vus_dans_le_fichier[reference]} de ce fichier")
        elif reference:
            vus_dans_le_fichier[reference] = numero_ligne

        erreurs += _controles_specifiques(societe_id, cle_modele, brut,
                                          enregistrement)

        for message in erreurs:
            anomalies.append({"ligne": numero_ligne, "message": message})
        apercu.append({"ligne": numero_ligne, "valeurs": brut, "erreurs": erreurs})
        if not erreurs:
            prets.append(enregistrement)

    resultat = {"prets": prets, "anomalies": anomalies, "apercu": apercu,
                "ignorees": ignorees, "nb_ignorees": len(ignorees),
                "nb_valides": len(prets), "a_creer": manquants.resume(),
                "nb_completes": completes,
                "nb_rejetes": len(apercu) - len(prets) - len(ignorees)}
    diagnostic = _fichier_suspect(modele, cle_unique, vus_dans_le_fichier,
                                  ignorees, len(apercu))
    if diagnostic:
        resultat["avertissement"] = diagnostic
    return resultat


def _reclame(manquants, colonne, valeur, parent) -> str | None:
    """Inscrit la fiche à créer. Renvoie un message si elle ne peut pas l'être."""
    if colonne.reference == "tiers":
        manquants.tiers_nomme(valeur)
        return None
    if colonne.reference == "compte":
        manquants.compte(str(valeur).strip())
        return None
    forme = FICHES_MINIMALES.get(colonne.reference, {})
    if forme.get("parent") and not parent:
        # Le seul cas où la fiche minimale ne suffit pas : un lot sans son
        # programme n'a nulle part où se ranger.
        return (f"le lot « {valeur} » est inconnu, et la colonne "
                f"« Programme » n'est pas renseignée : sans elle, impossible "
                f"de savoir dans quel programme le créer")
    manquants.fiche(colonne.reference, valeur, parent)
    return None


#: Ce qui reste sans réponse ne fait plus l'objet d'un cours : la ligne est
#: mise de côté, avec la raison en une phrase, et rejouée d'elle-même dès que
#: ce qui lui manquait existe.
POURQUOI_EXIGE: dict = {}


def _pourquoi_exige(reference: str) -> str:
    return POURQUOI_EXIGE.get(reference, "")


def _fichier_suspect(modele, cle_unique, vus, ignorees, nb_lignes) -> str | None:
    """Le fichier ressemble-t-il à ce que ce modèle attend ?

    Une colonne d'identifiant qui porte la même valeur sur toutes les lignes
    ne peut pas être un identifiant : c'est presque toujours le signe qu'on
    s'est trompé de type de données. Le dire vaut mieux que d'aligner cent
    fois la même anomalie.
    """
    if not cle_unique or nb_lignes < 3:
        return None
    distinctes = len(vus) + len({i["message"] for i in ignorees})
    if distinctes > 1:
        return None
    colonne = _nom_de_champ_lisible(modele, cle_unique)
    return (f"La colonne « {colonne} » porte la même valeur sur les "
            f"{nb_lignes} lignes. Ce fichier n'est probablement pas un(e) "
            f"« {modele['libelle']} » : vérifiez le type de données choisi "
            f"en haut de l'écran. Une liste de clients ou de fournisseurs, "
            f"par exemple, s'importe par le modèle « Tiers ».")


def _nom_de_champ_lisible(modele: dict, champ: str) -> str:
    for colonne in modele["colonnes"]:
        if colonne.champ == champ:
            return colonne.nom
    return champ


def _nom_de_champ(modele: dict, champ: str) -> str:
    for colonne in modele["colonnes"]:
        if colonne.champ == champ:
            return colonne.nom
    return champ


def _controles_specifiques(societe_id, cle_modele, brut, enregistrement) -> list[str]:
    """Les quelques règles qui ne se déduisent pas de la description."""
    erreurs = []
    if cle_modele == "comptes":
        numero = brut["Compte"]
        if numero and not numero.isdigit():
            erreurs.append(f"le numéro de compte « {numero} » "
                           "doit être composé de chiffres")
    elif cle_modele == "lots":
        # Le numéro d'un lot n'est unique qu'à l'intérieur de son programme.
        programme_id = enregistrement.get("programme_id")
        numero = enregistrement.get("numero")
        if programme_id and numero and db.ligne(
                "SELECT id FROM lots WHERE societe_id = ? AND programme_id = ? "
                "AND numero = ? COLLATE NOCASE",
                (societe_id, programme_id, numero)):
            erreurs.append(f"le lot {numero} existe déjà dans ce programme")
    elif cle_modele == "salaries":
        # La colonne « Primes » du fichier est un simple montant ; la fiche du
        # salarié, elle, porte une liste détaillée (libellé, soumis CNAS,
        # soumis IRG). Sans cette mise en forme, l'import déposait un nombre
        # là où le reste de l'application attend du JSON.
        montant = enregistrement.pop("primes", None)
        if montant:
            enregistrement["primes"] = json.dumps(
                [{"libelle": "Primes", "montant": int(montant),
                  "soumis_cnas": True, "soumis_irg": True}], ensure_ascii=False)
        else:
            enregistrement["primes"] = json.dumps([])
    elif cle_modele == "quittances":
        # Un total absent se déduit du loyer et des charges.
        if not enregistrement.get("total"):
            enregistrement["total"] = (enregistrement.get("loyer", 0)
                                       + enregistrement.get("charges", 0))
        enregistrement["perimetre"] = _perimetre(
            brut.get("Périmètre", ""),
            db.valeur("SELECT perimetre_defaut FROM societes WHERE id = ?",
                      (societe_id,), "declare"))
    elif cle_modele == "immobilisations":
        if not enregistrement.get("date_mise_service"):
            enregistrement["date_mise_service"] = enregistrement.get(
                "date_acquisition")
        # Les comptes d'amortissement et de dotation se déduisent du compte
        # d'immobilisation : inutile de les faire saisir.
        from modules import immobilisations as mod_immo
        if not enregistrement.get("compte_amort") and enregistrement.get("compte"):
            enregistrement["compte_amort"] = mod_immo.compte_amortissement(
                enregistrement["compte"])
        enregistrement.setdefault("compte_dotation", None)
        if not enregistrement["compte_dotation"]:
            enregistrement["compte_dotation"] = "68112"
        for champ, libelle in (("compte_amort", "compte d'amortissement"),
                               ("compte_dotation", "compte de dotation")):
            valeur = enregistrement.get(champ)
            if valeur and not db.ligne(
                    "SELECT id FROM comptes WHERE societe_id = ? AND numero = ?",
                    (societe_id, valeur)):
                erreurs.append(f"{libelle} « {valeur} » absent du plan comptable")
    return erreurs


def _valeur_defaut(defaut, societe_id, enregistrement):
    """Un défaut peut être une valeur, ou une fonction qui la calcule."""
    if not callable(defaut):
        return defaut
    try:
        return defaut(societe_id, enregistrement)
    except TypeError:
        return defaut()


def _importe_generique(societe_id, modele, rangs) -> dict:
    identifiants, completes = [], []
    for enregistrement in rangs:
        # Une fiche qui n'avait que son nom : cette ligne la décrit enfin.
        # Elle est remplie, pas dupliquée — et elle n'appartient pas à cet
        # import, qui ne l'a pas créée : l'annuler ne doit pas l'emporter.
        a_completer = enregistrement.pop("_completer", None)
        if a_completer:
            donnees = {c: v for c, v in enregistrement.items() if v is not None}
            donnees["incomplet"] = 0
            db.modifie(modele["table"], a_completer, donnees)
            completes.append(a_completer)
            continue
        if not modele.get("sans_societe"):
            enregistrement["societe_id"] = societe_id
        for champ, defaut in modele.get("defauts", {}).items():
            if enregistrement.get(champ) in (None, ""):
                enregistrement[champ] = _valeur_defaut(defaut, societe_id,
                                                       enregistrement)
        if modele["table"] == "comptes":
            enregistrement["classe"] = int(str(enregistrement["numero"])[0])
        # Les champs restés vides sont omis : la valeur par défaut du schéma
        # s'applique alors, plutôt qu'un NULL sur une colonne NOT NULL.
        identifiants.append(
            db.insere(modele["table"], {c: v for c, v in enregistrement.items()
                                        if v is not None}))
    return {"nb": len(rangs), "objets": {modele["table"]: identifiants},
            "completes": {modele["table"]: completes} if completes else {}}


# ---------------------------------------------------------------------------
# Contrôles particuliers : écritures, factures, balance, règlements
# ---------------------------------------------------------------------------

def resout_journal(societe_id: int, saisi: str) -> tuple[str | None, str | None]:
    """Retrouve un journal par son code ou par son intitulé.

    Un comptable écrit « CAISSE » ou « Journal de caisse » là où le logiciel
    attend « CA » : refuser cela n'apprendrait rien à personne.
    Renvoie (code, message d'anomalie).
    """
    journaux = db.lignes("SELECT code, libelle FROM journaux WHERE societe_id = ?",
                         (societe_id,))
    codes = ", ".join(sorted(j["code"] for j in journaux))
    if not saisi:
        return None, None
    cherche = _sans_accent(saisi)
    for j in journaux:
        if _sans_accent(j["code"]) == cherche:
            return j["code"], None
    # Puis par intitulé : « caisse » retrouve « Journal de caisse ».
    proches = [j for j in journaux
               if cherche in _sans_accent(j["libelle"])
               or _sans_accent(j["libelle"]) in cherche]
    if len(proches) == 1:
        return proches[0]["code"], None
    if len(proches) > 1:
        return None, (f"le journal « {saisi} » correspond à plusieurs journaux "
                      f"({', '.join(p['code'] for p in proches)}) : indiquez son code")
    return None, (f"le journal « {saisi} » n'existe pas — journaux disponibles : "
                  f"{codes}")


def comptes_proches(comptes_connus: set[str], numero: str, combien: int = 3) -> list[str]:
    """Les comptes existants qui ressemblent le plus au numéro saisi."""
    if not numero:
        return []
    meilleurs: list[tuple[int, str]] = []
    for candidat in comptes_connus:
        commun = 0
        for a, b in zip(numero, candidat):
            if a != b:
                break
            commun += 1
        if commun >= 2:
            meilleurs.append((commun, candidat))
    meilleurs.sort(key=lambda x: (-x[0], len(x[1]), x[1]))
    return [c for _, c in meilleurs[:combien]]


def _est_ligne_de_total(libelle: str, compte: str, debit: int, credit: int) -> bool:
    """Reconnaît la ligne de totaux que l'on met au bas d'un tableau Excel."""
    if compte:
        return False
    if "total" in _sans_accent(libelle):
        return True
    return bool(debit and credit)


def analyse_ecritures(societe_id, rangs, association, defaut_perimetre):
    """Regroupe les lignes par numéro d'écriture et contrôle chaque groupe.

    Le fichier est lu comme un journal se lit : une case laissée vide reprend
    la valeur de la ligne précédente. C'est ainsi qu'on tient un journal, sur
    papier comme dans un tableur — la date, le journal et le numéro ne sont
    écrits qu'une fois par écriture.
    """
    groupes: dict[str, dict] = {}
    ordre: list[str] = []
    anomalies = []
    ignorees = []

    comptes_connus = {str(c["numero"]) for c in db.lignes(
        "SELECT numero FROM comptes WHERE societe_id = ?", (societe_id,))}
    journaux_resolus: dict[str, tuple[str | None, str | None]] = {}
    manquants = Manquants(societe_id)

    # Dernières valeurs rencontrées, reprises quand la cellule est vide.
    reprise = {"cle": "", "date": "", "journal": "", "libelle": "", "piece": "",
               "perimetre": ""}

    for decalage, rang in enumerate(rangs):
        numero_ligne = decalage + 2
        if not any(str(c).strip() for c in rang):
            continue
        compte = _valeur(rang, association, "Compte")
        debit = _valeur(rang, association, "Débit")
        credit = _valeur(rang, association, "Crédit")
        montant_debit = util.centimes(debit) if debit else 0
        montant_credit = util.centimes(credit) if credit else 0
        libelle_brut = _valeur(rang, association, "Libellé")

        if _est_ligne_de_total(libelle_brut, compte, montant_debit, montant_credit):
            ignorees.append(numero_ligne)
            continue

        # Une cellule vide continue l'écriture précédente.
        cle = _valeur(rang, association, "N° écriture") or reprise["cle"]
        date = _valeur(rang, association, "Date") or reprise["date"]
        journal_saisi = _valeur(rang, association, "Journal") or reprise["journal"]
        libelle = libelle_brut or reprise["libelle"]
        piece = _valeur(rang, association, "N° de pièce") or reprise["piece"]
        perimetre = _valeur(rang, association, "Périmètre") or reprise["perimetre"]
        reprise.update({"cle": cle, "date": date, "journal": journal_saisi,
                        "libelle": libelle, "piece": piece, "perimetre": perimetre})

        if journal_saisi not in journaux_resolus:
            journaux_resolus[journal_saisi] = resout_journal(societe_id, journal_saisi)
        journal, erreur_journal = journaux_resolus[journal_saisi]

        erreurs = []
        if not cle:
            cle = f"auto-{date}-{libelle}-{journal_saisi}"
        if not compte:
            erreurs.append("compte manquant")
        elif not compte.isdigit():
            # Un numéro de compte est fait de chiffres : là, c'est la colonne
            # qui est mal lue, pas le plan qui est incomplet.
            erreurs.append(f"« {compte} » n'est pas un numéro de compte")
        elif compte not in comptes_connus:
            # Le plan comptable se complète tout seul : refuser une écriture
            # parce qu'il manque un sous-compte obligerait à reprendre le
            # dossier deux fois.
            manquants.compte(compte)
            comptes_connus.add(compte)
        if erreur_journal:
            if "n'existe pas" in erreur_journal and journal_saisi:
                manquants.journal(journal_saisi)
                journal = journal_saisi.strip().upper()
                journaux_resolus[journal_saisi] = (journal, None)
            else:
                erreurs.append(erreur_journal)
        if montant_debit and montant_credit:
            erreurs.append("débit et crédit renseignés sur la même ligne")
        if not montant_debit and not montant_credit:
            erreurs.append("aucun montant")

        groupe = groupes.get(cle)
        if groupe is None:
            iso = _date(date)
            if not iso:
                erreurs.append(
                    f"date « {date} » incompréhensible" if date
                    else "date manquante, et aucune date à reprendre plus haut")
            if not journal_saisi:
                erreurs.append("journal manquant")
            if not libelle:
                erreurs.append("libellé manquant")
            groupe = groupes[cle] = {
                "cle": cle, "date": iso, "journal": journal, "libelle": libelle,
                "piece": piece,
                "perimetre": _perimetre(perimetre, defaut_perimetre),
                "lignes": [], "lignes_fichier": [], "erreurs": [],
                "debit": 0, "credit": 0,
            }
            ordre.append(cle)

        groupe["lignes_fichier"].append(numero_ligne)
        if erreurs:
            for message in erreurs:
                anomalies.append({"ligne": numero_ligne, "message": message})
            groupe["erreurs"].extend(erreurs)
            continue

        groupe["debit"] += montant_debit
        groupe["credit"] += montant_credit
        groupe["lignes"].append({
            "compte": compte,
            "libelle": libelle,
            "debit": montant_debit,
            "credit": montant_credit,
            "tiers_id": _tiers_id(societe_id, _valeur(rang, association, "Tiers")),
            "tiers_nom": _valeur(rang, association, "Tiers"),
        })
        nom_tiers = _valeur(rang, association, "Tiers")
        if nom_tiers and not _tiers_id(societe_id, nom_tiers):
            manquants.tiers_nomme(nom_tiers, compte)

    prets = []
    for cle in ordre:
        groupe = groupes[cle]
        if groupe["erreurs"]:
            # Une ligne déjà refusée fausse forcément le total : inutile
            # d'ajouter un déséquilibre qui n'est qu'une conséquence.
            continue
        if groupe["debit"] != groupe["credit"]:
            message = (f"écriture déséquilibrée : débit "
                       f"{util.formate_montant(groupe['debit'])} ≠ crédit "
                       f"{util.formate_montant(groupe['credit'])}")
            groupe["erreurs"].append(message)
            anomalies.append({"ligne": groupe["lignes_fichier"][0],
                              "message": message})
        elif len(groupe["lignes"]) < 2:
            message = "une écriture comporte au moins deux lignes"
            groupe["erreurs"].append(message)
            anomalies.append({"ligne": groupe["lignes_fichier"][0],
                              "message": message})
        if not groupe["erreurs"]:
            prets.append(groupe)

    apercu = [{
        "reference": g["cle"], "date": g["date"], "journal": g["journal"],
        "libelle": g["libelle"], "montant": g["debit"],
        "perimetre": g["perimetre"], "nb_lignes": len(g["lignes"]),
        "lignes_fichier": g["lignes_fichier"], "erreurs": g["erreurs"],
    } for g in (groupes[c] for c in ordre)]

    return {"prets": prets, "anomalies": anomalies, "apercu": apercu,
            "nb_valides": len(prets), "nb_rejetes": len(ordre) - len(prets),
            "lignes_ignorees": ignorees, "a_creer": manquants.resume()}


def analyse_balance(societe_id, rangs, association, date_reprise):
    """Contrôle une balance de reprise : totaux égaux, comptes complétés.

    Le plan comptable se complète tout seul : une balance reprise d'un autre
    logiciel porte forcément des sous-comptes que le plan livré n'a pas."""
    anomalies, lignes, apercu, ignorees = [], [], [], []
    comptes_connus = {str(c["numero"]) for c in db.lignes(
        "SELECT numero FROM comptes WHERE societe_id = ?", (societe_id,))}
    manquants = Manquants(societe_id)
    total_debit = total_credit = 0
    vus = set()

    for decalage, rang in enumerate(rangs):
        numero_ligne = decalage + 2
        if not any(str(c).strip() for c in rang):
            continue
        compte = _valeur(rang, association, "Compte")
        debit = _valeur(rang, association, "Débit")
        credit = _valeur(rang, association, "Crédit")
        montant_debit_brut = util.centimes(debit) if debit else 0
        montant_credit_brut = util.centimes(credit) if credit else 0
        if _est_ligne_de_total(_valeur(rang, association, "Intitulé"), compte,
                               montant_debit_brut, montant_credit_brut):
            ignorees.append(numero_ligne)
            continue
        erreurs = []
        if not compte:
            erreurs.append("compte manquant")
        elif not str(compte).isdigit():
            erreurs.append(f"« {compte} » n'est pas un numéro de compte")
        elif compte not in comptes_connus:
            # Une balance reprise d'un autre logiciel porte forcément des
            # sous-comptes que le plan livré n'a pas. Les réclamer un par un
            # revenait à faire reprendre le dossier deux fois.
            manquants.compte(compte)
            comptes_connus.add(compte)
            vus.add(compte)
        elif compte in vus:
            erreurs.append(f"le compte {compte} apparaît deux fois")
        else:
            vus.add(compte)
        montant_debit = util.centimes(debit) if debit else 0
        montant_credit = util.centimes(credit) if credit else 0
        if montant_debit and montant_credit:
            erreurs.append("un compte porte un solde débiteur ou créditeur, "
                           "pas les deux")
        if not montant_debit and not montant_credit:
            erreurs.append("aucun solde")

        for message in erreurs:
            anomalies.append({"ligne": numero_ligne, "message": message})
        apercu.append({"ligne": numero_ligne, "compte": compte,
                       "debit": montant_debit, "credit": montant_credit,
                       "erreurs": erreurs})
        if erreurs:
            continue
        total_debit += montant_debit
        total_credit += montant_credit
        lignes.append({
            "compte": compte, "debit": montant_debit, "credit": montant_credit,
            "libelle": _valeur(rang, association, "Intitulé") or "Report à nouveau",
            "tiers_id": _tiers_id(societe_id, _valeur(rang, association, "Tiers")),
        })
        nom_tiers = _valeur(rang, association, "Tiers")
        if nom_tiers and not _tiers_id(societe_id, nom_tiers):
            manquants.tiers_nomme(nom_tiers, compte)

    if lignes and total_debit != total_credit:
        message = (f"balance déséquilibrée : total débit "
                   f"{util.formate_montant(total_debit)} ≠ total crédit "
                   f"{util.formate_montant(total_credit)} — écart de "
                   f"{util.formate_montant(abs(total_debit - total_credit))}")
        anomalies.append({"ligne": 0, "message": message})
        lignes = []

    prets = [{"date": date_reprise, "lignes": lignes,
              "total": total_debit}] if lignes else []
    return {"prets": prets, "anomalies": anomalies, "apercu": apercu,
            "nb_valides": len(lignes), "total": total_debit,
            "nb_rejetes": len([a for a in apercu if a["erreurs"]]),
            "lignes_ignorees": ignorees, "a_creer": manquants.resume()}


def analyse_factures(societe_id, rangs, association, defaut_perimetre, sens):
    """Regroupe les lignes par numéro de facture et contrôle chaque facture."""
    groupes: dict[str, dict] = {}
    ordre: list[str] = []
    anomalies = []
    manquants = Manquants(societe_id)
    existantes = {str(f["numero"]) for f in db.lignes(
        "SELECT numero FROM factures WHERE societe_id = ? AND sens = ?",
        (societe_id, sens))}

    for decalage, rang in enumerate(rangs):
        numero_ligne = decalage + 2
        if not any(str(c).strip() for c in rang):
            continue
        numero = _valeur(rang, association, "N° facture")
        date = _valeur(rang, association, "Date")
        tiers = _valeur(rang, association, "Tiers")
        designation = _valeur(rang, association, "Désignation")
        prix = _valeur(rang, association, "Prix unitaire")

        montant_ligne = _valeur(rang, association, "Montant HT")

        erreurs = []
        if not designation:
            erreurs.append("désignation manquante")
        if not prix and not montant_ligne:
            erreurs.append("ni montant HT ni prix unitaire")

        groupe = groupes.get(numero or f"auto-{numero_ligne}")
        if groupe is None:
            cle = numero or f"auto-{numero_ligne}"
            iso = _date(date)
            tiers_id = _tiers_id(societe_id, tiers)
            if not numero:
                erreurs.append("numéro de facture manquant")
            elif numero in existantes:
                erreurs.append(f"la facture n° {numero} existe déjà")
            if not iso:
                erreurs.append(f"date « {date} » incompréhensible")
            if not tiers:
                erreurs.append("tiers manquant")
            elif tiers_id is None:
                # Un client qu'on facture est un client : le fichier le dit,
                # inutile de le faire saisir ailleurs d'abord.
                manquants.tiers_nomme(
                    tiers, "411" if sens == "vente" else "401")
            mode = _sans_accent(_valeur(rang, association, "Mode de règlement"))
            if mode and mode not in MODES_REGLEMENT:
                erreurs.append(f"mode de règlement « {mode} » inconnu "
                               f"({', '.join(sorted(MODES_REGLEMENT))})")
            groupe = groupes[cle] = {
                "cle": cle, "numero": numero, "date": iso, "sens": sens,
                "tiers_id": tiers_id, "tiers": tiers,
                "objet": _valeur(rang, association, "Objet"),
                "echeance": _date(_valeur(rang, association, "Échéance")),
                "mode_reglement": mode or None,
                "perimetre": _perimetre(_valeur(rang, association, "Périmètre"),
                                        defaut_perimetre),
                "lignes": [], "lignes_fichier": [], "erreurs": [],
            }
            ordre.append(cle)
            existantes.add(numero)          # évite un doublon dans le fichier

        groupe["lignes_fichier"].append(numero_ligne)
        if erreurs:
            for message in erreurs:
                anomalies.append({"ligne": numero_ligne, "message": message})
            groupe["erreurs"].extend(erreurs)
            continue

        groupe["lignes"].append({
            "designation": designation,
            "quantite": _valeur(rang, association, "Quantité") or 1,
            "unite": _valeur(rang, association, "Unité") or None,
            "prix_unitaire": prix,
            "montant_ht": montant_ligne or None,
            "remise_taux": _valeur(rang, association, "Remise %") or 0,
            "taux_tva": _valeur(rang, association, "Taux TVA") or 19,
            "compte": _valeur(rang, association, "Compte") or None,
        })

    prets = []
    for cle in ordre:
        groupe = groupes[cle]
        if not groupe["erreurs"] and not groupe["lignes"]:
            message = "facture sans aucune ligne exploitable"
            groupe["erreurs"].append(message)
            anomalies.append({"ligne": groupe["lignes_fichier"][0],
                              "message": message})
        if not groupe["erreurs"]:
            prets.append(groupe)

    apercu = [{
        "reference": g["numero"], "date": g["date"], "tiers": g["tiers"],
        "libelle": g["objet"], "perimetre": g["perimetre"],
        "nb_lignes": len(g["lignes"]),
        # Un aperçu qui annonce « 1 ligne sera écrite » sans dire combien
        # laisse valider à l'aveugle : c'est ainsi qu'une somme multipliée
        # par cent est passée inaperçue jusqu'au total de l'écran.
        "montant": _montant_apercu(g["lignes"]),
        "lignes_fichier": g["lignes_fichier"],
        "erreurs": g["erreurs"],
    } for g in (groupes[c] for c in ordre)]

    return {"prets": prets, "anomalies": anomalies, "apercu": apercu,
            "nb_valides": len(prets), "nb_rejetes": len(ordre) - len(prets),
            "a_creer": manquants.resume()}


def _montant_apercu(lignes: list[dict]) -> int:
    """Le total hors taxes d'une facture telle qu'elle sera écrite."""
    from modules.facturation import calcule_lignes
    if not lignes:
        return 0
    try:
        _, total_ht, _ = calcule_lignes(lignes)
    except Exception:                                          # noqa: BLE001
        return 0
    return total_ht


SENS_REGLEMENT = {"encaissement", "decaissement"}


def analyse_reglements(societe_id, rangs, association):
    """Rattache chaque règlement à sa facture, ou l'encaisse sans l'affecter.

    Un règlement dont la facture n'est pas encore enregistrée n'est pas une
    anomalie : l'argent est bien entré. Il est repris non affecté, avec le
    numéro qu'il cite, et se rattachera de lui-même quand la facture
    arrivera — que ce soit dans dix minutes ou le mois prochain.
    """
    prets, anomalies, apercu = [], [], []
    manquants = Manquants(societe_id)
    cumul: dict[int, int] = {}

    for decalage, rang in enumerate(rangs):
        numero_ligne = decalage + 2
        if not any(str(c).strip() for c in rang):
            continue
        numero = _valeur(rang, association, "N° facture")
        date = _date(_valeur(rang, association, "Date"))
        montant = util.centimes(_valeur(rang, association, "Montant") or 0)
        sens = _sans_accent(_valeur(rang, association, "Sens"))
        mode = _sans_accent(_valeur(rang, association, "Mode"))
        tresorerie = _valeur(rang, association, "Compte de trésorerie")

        erreurs = []
        facture = db.ligne(
            "SELECT * FROM factures WHERE societe_id = ? AND numero = ? "
            "COLLATE NOCASE", (societe_id, numero)) if numero else None
        if not numero:
            erreurs.append("« N° facture » est obligatoire")
        if not date:
            erreurs.append("date de règlement incompréhensible")
        if montant <= 0:
            erreurs.append("montant absent ou nul")
        if sens and sens not in SENS_REGLEMENT:
            erreurs.append(f"sens « {sens} » inconnu "
                           f"({', '.join(sorted(SENS_REGLEMENT))})")
        if mode and mode not in MODES_REGLEMENT:
            erreurs.append(f"mode « {mode} » inconnu "
                           f"({', '.join(sorted(MODES_REGLEMENT))})")
        tresorerie_id = resout_reference("tresorerie", societe_id, tresorerie)
        if tresorerie and tresorerie_id is None:
            manquants.fiche("tresorerie", tresorerie)

        if facture and not erreurs:
            deja = facture["montant_regle"] + cumul.get(facture["id"], 0)
            if deja + montant > facture["net_a_payer"]:
                erreurs.append(
                    f"le total réglé dépasserait le net à payer de la facture "
                    f"{numero} ({util.formate_montant(facture['net_a_payer'])})")
            else:
                cumul[facture["id"]] = deja + montant - facture["montant_regle"]

        for message in erreurs:
            anomalies.append({"ligne": numero_ligne, "message": message})
        apercu.append({"ligne": numero_ligne, "facture": numero,
                       "montant": montant, "erreurs": erreurs})
        if erreurs:
            continue
        prets.append({
            "facture": facture,
            # Ce que le fichier disait, gardé même sans facture en face :
            # c'est par ce numéro que le rattachement se fera plus tard.
            "reference_facture": numero,
            "tresorerie": tresorerie,
            "date": date, "montant": montant,
            "sens": sens or ("encaissement" if facture and facture["sens"] == "vente"
                             else ("decaissement" if facture else "encaissement")),
            "mode": mode or None, "tresorerie_id": tresorerie_id,
            "reference": _valeur(rang, association, "Référence") or None,
        })

    non_affectes = len([p for p in prets if not p["facture"]])
    return {"prets": prets, "anomalies": anomalies, "apercu": apercu,
            "nb_valides": len(prets), "a_creer": manquants.resume(),
            "nb_non_affectes": non_affectes,
            "nb_rejetes": len([a for a in apercu if a["erreurs"]])}


# ---------------------------------------------------------------------------
# Aiguillage
# ---------------------------------------------------------------------------

def _analyse(ctx, octets: bytes, cle_modele: str) -> dict:
    modele = MODELES[cle_modele]
    societe_id = ctx.entier("societe_id") or ctx.arg_int("societe")
    if not societe_id:
        raise ErreurApplicative("Aucun dossier sélectionné.")
    try:
        entetes, rangs = tableur.lit_tableau(octets)
    except Exception as err:                                   # noqa: BLE001
        raise ErreurApplicative(
            "Fichier illisible. Attendu : un classeur Excel (.xlsx) ou un "
            f"fichier CSV. Détail : {err}") from err

    association = associe_colonnes(entetes, modele)
    manquantes = [c.nom for c in modele["colonnes"]
                  if c.requis and c.nom not in association]
    if manquantes:
        raise ErreurApplicative(
            "Colonnes obligatoires absentes du fichier : "
            + ", ".join(manquantes)
            + ". Téléchargez le modèle et conservez sa ligne d'en-têtes.")

    defaut = db.valeur("SELECT perimetre_defaut FROM societes WHERE id = ?",
                       (societe_id,), "declare")
    if cle_modele == "ecritures":
        resultat = analyse_ecritures(societe_id, rangs, association, defaut)
    elif cle_modele == "balance_ouverture":
        resultat = analyse_balance(societe_id, rangs, association,
                                   ctx.champ("date_reprise"))
    elif cle_modele == "reglements":
        resultat = analyse_reglements(societe_id, rangs, association)
    elif "sens" in modele:
        resultat = analyse_factures(societe_id, rangs, association, defaut,
                                    modele["sens"])
    else:
        resultat = analyse_generique(societe_id, rangs, association, modele,
                                     cle_modele)
    resultat.update({
        "modele": cle_modele,
        "libelle": modele["libelle"],
        # Le fichier tel qu'il est arrivé. Sert à mettre de côté, telles
        # quelles, les lignes que l'application n'a pas su écrire : elles se
        # corrigent ensuite dans l'application, sans repasser par le tableur.
        "_entetes": [str(e).strip() for e in entetes],
        "_rangs": rangs,
        # Non pas la liste des colonnes reconnues, mais la façon dont le
        # fichier a été lu : c'est souvent la réponse à « pourquoi ça ne
        # marche pas ». Une colonne lue de travers se voit immédiatement.
        "colonnes_reconnues": [
            {"attendu": nom, "trouve": str(entetes[index]).strip()}
            for nom, index in sorted(association.items())
            if index < len(entetes)],
        "colonnes_ignorees": [e for i, e in enumerate(entetes)
                              if i not in set(association.values()) and str(e).strip()],
        "societe_id": societe_id,
    })
    return resultat


@route("POST", "/api/import/analyse")
def api_analyse(ctx):
    ctx.interdit_lecture_seule()
    cle = ctx.champ_requis("modele")
    if cle not in MODELES:
        raise ErreurApplicative("Modèle inconnu.", 404)
    resultat = _analyse(ctx, _decode_fichier(ctx), cle)
    for interne in ("prets", "_rangs", "_entetes"):
        resultat.pop(interne, None)      # inutile au navigateur, volumineux
    return resultat


# ---------------------------------------------------------------------------
# Ce qui n'a pas pu être écrit : mis de côté, pas refusé
# ---------------------------------------------------------------------------
#
# Une ligne que l'application ne sait pas écrire tout de suite n'est ni
# refusée ni perdue. Elle attend, avec ses valeurs telles qu'elles étaient
# dans le fichier. Elle se corrige dans l'application — pas dans le tableur,
# pas en refaisant l'import — et surtout : elle est rejouée d'elle-même après
# chaque import suivant. Reprendre les règlements avant les factures marche
# donc, sans que personne n'ait à y penser.

#: Les champs de la requête d'import à conserver avec une ligne mise de
#: côté : sans eux, la rejouer plus tard n'aurait pas le même sens.
CHAMPS_CONSERVES = ("date_reprise", "perimetre", "journal")


def _lignes_rejetees(resultat: dict) -> dict:
    """{numéro de ligne du fichier : raison} — pour tous les modèles.

    Les modèles qui groupent (factures, écritures) rejettent un groupe
    entier : toutes ses lignes partent ensemble, sinon on en perdrait la
    moitié en chemin.
    """
    rejetees: dict = {}
    for vue in resultat.get("apercu") or []:
        erreurs = vue.get("erreurs") or []
        if not erreurs:
            continue
        raison = " ; ".join(erreurs)
        for numero in (vue.get("lignes_fichier") or
                       ([vue["ligne"]] if vue.get("ligne") else [])):
            rejetees[numero] = raison
    for anomalie in resultat.get("anomalies") or []:
        numero = anomalie.get("ligne")
        if numero and numero not in rejetees:
            rejetees[numero] = anomalie.get("message", "")
    return rejetees


def met_de_cote(ctx, societe_id, cle, resultat, import_id) -> int:
    """Range les lignes non écrites, avec le fichier dont elles viennent."""
    rejetees = _lignes_rejetees(resultat)
    if not rejetees:
        return 0
    entetes = json.dumps(resultat.get("_entetes") or [], ensure_ascii=False)
    rangs = resultat.get("_rangs") or []
    fichier = util.nettoie(ctx.champ("fichier")) or None
    # Ce que la requête portait en plus du fichier : sans la date de reprise,
    # une ligne de balance rejouée plus tard n'aurait plus de repère.
    contexte = json.dumps({c: ctx.champ(c) for c in CHAMPS_CONSERVES
                           if ctx.champ(c)}, ensure_ascii=False)
    posees = 0
    for numero, raison in sorted(rejetees.items()):
        index = numero - 2                    # +1 en-tête, +1 pour compter de 1
        if index < 0 or index >= len(rangs):
            continue
        db.insere("lignes_attente", {
            "societe_id": societe_id, "import_id": import_id, "modele": cle,
            "fichier": fichier, "ligne": numero, "entetes": entetes,
            "valeurs": json.dumps([str(c) if c is not None else ""
                                   for c in rangs[index]], ensure_ascii=False),
            "raison": raison, "contexte": contexte,
            "cree_le": util.maintenant(),
            "cree_par": ctx.nom_utilisateur,
        })
        posees += 1
    return posees


# ---------------------------------------------------------------------------
# Écriture
# ---------------------------------------------------------------------------

@route("POST", "/api/import/valider")
def api_valide(ctx):
    ctx.interdit_lecture_seule()
    ctx.exige_role("admin", "comptable")
    cle = ctx.champ_requis("modele")
    if cle not in MODELES:
        raise ErreurApplicative("Modèle inconnu.", 404)
    return importe(ctx, cle, _decode_fichier(ctx))


def importe(ctx, cle, octets, rejouer=True) -> dict:
    """Écrit ce qui est écrivable, range le reste, rejoue ce qui attendait."""
    resultat = _analyse(ctx, octets, cle)

    # Un fichier n'est plus refusé en bloc parce que neuf lignes sur quatre
    # cents posent question. Ce qui est écrivable est écrit, le reste est mis
    # de côté — corrigeable dans l'application, et rejoué tout seul ensuite.
    societe_id = resultat["societe_id"]
    a_creer = resultat.get("a_creer") or {}
    prets = resultat["prets"]
    if not prets and not _quelque_chose_a_creer(a_creer) \
            and not resultat["anomalies"]:
        if resultat.get("nb_ignorees"):
            raise ErreurApplicative(
                f"{resultat['nb_ignorees']} ligne(s) sur {resultat['nb_ignorees']} "
                "étaient déjà enregistrées : il n'y avait rien à reprendre. "
                "Rien n'a été modifié.")
        raise ErreurApplicative("Aucune ligne exploitable dans ce fichier.")

    # Un seul bloc : ou tout passe, ou rien n'est écrit.
    with db.transaction():
        # La ligne d'import est ouverte d'abord : c'est elle qui donnera son
        # identifiant à tout ce qui va être créé, et qui permettra plus tard
        # de défaire la reprise sans avoir à la reconstituer.
        import_id = db.insere("imports", {
            "societe_id": societe_id,
            "modele": cle,
            "libelle": resultat["libelle"],
            "fichier": util.nettoie(ctx.champ("fichier")) or None,
            "nb_rejetes": resultat["nb_rejetes"],
            "cree_le": util.maintenant(),
            "cree_par": ctx.nom_utilisateur,
        })
        compteurs_avant = _photo_compteurs(societe_id)

        # Ce que le fichier désigne et que le dossier ne connaît pas encore
        # est créé ici, avant le reste. Puis le fichier est relu : les
        # renvois qui pendaient — un compte, un tiers, un journal — trouvent
        # cette fois leur destinataire.
        prealables = cree_manquants(societe_id, a_creer, ctx.nom_utilisateur)
        if prealables:
            resultat = _analyse(ctx, octets, cle)
            prets = resultat["prets"]
            if _quelque_chose_a_creer(resultat.get("a_creer")):
                raise ErreurApplicative(
                    "Certains éléments désignés par le fichier n'ont pas pu "
                    "être créés. Rien n'a été importé.")

        if not prets:
            bilan = {"nb": 0, "objets": {}}
        elif cle == "ecritures":
            bilan = _importe_ecritures(ctx, societe_id, prets)
        elif cle == "balance_ouverture":
            bilan = _importe_balance(ctx, societe_id, prets[0])
        elif cle == "reglements":
            bilan = _importe_reglements(ctx, societe_id, prets)
        elif cle.startswith("factures_"):
            bilan = _importe_factures(ctx, societe_id, prets)
        else:
            bilan = _importe_generique(societe_id, MODELES[cle], prets)

        # Ce qui n'a pas pu être écrit attend dans l'application, avec ses
        # valeurs d'origine. Rien ne se perd, rien n'est à ressaisir.
        en_attente = met_de_cote(ctx, societe_id, cle, resultat, import_id)

        crees = bilan["nb"]
        # Les éléments créés en préalable appartiennent à cet import : annuler
        # la reprise doit les reprendre eux aussi, sans quoi le dossier
        # garderait des comptes et des tiers dont plus rien ne dit d'où ils
        # viennent.
        for table, identifiants in prealables.items():
            bilan.setdefault("objets", {}).setdefault(table, []).extend(identifiants)
        _rattache_a_import(import_id, bilan)
        db.modifie("imports", import_id, {
            "nb_crees": crees,
            "objets": json.dumps({
                "tables": bilan.get("objets", {}),
                # Complétées, pas créées : annuler l'import ne les emporte pas,
                # elles existaient avant lui.
                "completes": bilan.get("completes", {}),
                "compteurs": _compteurs_consommes(
                    compteurs_avant, _photo_compteurs(societe_id)),
                "factures_reglees": bilan.get("factures_reglees", []),
            }, ensure_ascii=False),
        })
        db.trace("import", cle, import_id,
                 {"crees": crees, "rejetes": resultat["nb_rejetes"]},
                 ctx.nom_utilisateur)

    # Hors transaction : ce qui attendait peut maintenant passer. Les
    # règlements déposés avant leurs factures se rattachent ici, sans que
    # personne n'ait eu à y penser.
    repris = (rejoue_attente(ctx, societe_id) if rejouer and crees else {})
    rattaches = rattache_reglements(societe_id) if crees else 0

    return {"crees": crees, "rejetes": resultat["nb_rejetes"],
            # Une facture ecrite n'est pas une facture comptabilisee : le
            # compte rendu doit distinguer les deux, sans quoi on croit avoir
            # repris une comptabilite qui n'est nulle part.
            "comptabilisees": bilan.get("comptabilisees", 0),
            "non_comptabilisees": bilan.get("non_comptabilisees", []),
            "ignorees": resultat.get("nb_ignorees", 0),
            "completes": resultat.get("nb_completes", 0),
            "en_attente": en_attente,
            "non_affectes": resultat.get("nb_non_affectes", 0),
            "repris": repris.get("repris", 0),
            "rattaches": rattaches,
            "import_id": import_id, "anomalies": resultat["anomalies"],
            "prealables": {t: len(i) for t, i in prealables.items()},
            "libelle": resultat["libelle"]}


def _quelque_chose_a_creer(a_creer) -> bool:
    return any((a_creer or {}).get(quoi) for quoi in
               ("comptes", "tiers", "journaux", "fiches"))


class _Rejeu:
    """Un contexte d'appel minimal, pour rejouer une ligne mise de côté.

    Le chemin d'import demande un contexte de requête ; ici il n'y a pas de
    requête, seulement des valeurs conservées. Plutôt qu'un second chemin
    d'écriture — qui divergerait du premier au bout de deux versions — on
    fabrique le contexte qui manque.
    """

    def __init__(self, societe_id, nom_utilisateur, valeurs=None):
        self.societe_id = societe_id
        self.nom_utilisateur = nom_utilisateur
        self._valeurs = dict(valeurs or {})
        self._valeurs["societe_id"] = societe_id

    def champ(self, nom, defaut=None):
        valeur = self._valeurs.get(nom)
        return defaut if valeur in (None, "") else valeur

    def champ_requis(self, nom):
        valeur = self.champ(nom)
        if valeur in (None, ""):
            raise ErreurApplicative(f"« {nom} » est obligatoire.")
        return valeur

    def entier(self, nom, defaut=None):
        try:
            return int(self._valeurs.get(nom))
        except (TypeError, ValueError):
            return defaut

    def arg_int(self, nom, defaut=None):
        return self.entier(nom, defaut)

    def booleen(self, nom):
        return bool(self._valeurs.get(nom))

    def interdit_lecture_seule(self):
        return None

    def exige_role(self, *roles):
        return None


def _en_csv(entetes: list, rangs: list) -> bytes:
    """Refabrique un fichier à partir de valeurs conservées."""
    import csv
    import io
    tampon = io.StringIO()
    graveur = csv.writer(tampon, delimiter=";", lineterminator="\n")
    graveur.writerow([str(e) for e in entetes])
    for rang in rangs:
        graveur.writerow(["" if c is None else str(c) for c in rang])
    return tampon.getvalue().encode("utf-8-sig")


def lignes_en_attente(societe_id: int, modele: str | None = None) -> list:
    return db.lignes(
        "SELECT * FROM lignes_attente WHERE societe_id = ?"
        + (" AND modele = ?" if modele else "")
        + " ORDER BY modele, ligne",
        (societe_id, modele) if modele else (societe_id,))


def rejoue_attente(ctx, societe_id: int, modele: str | None = None) -> dict:
    """Reprend ce qui attendait et qui passe maintenant.

    Appelée après chaque import : déposer les règlements avant les factures
    marche alors sans que personne n'ait à y penser. Ce qui ne passe toujours
    pas reste en attente, avec la raison mise à jour — jamais perdu, jamais
    réécrit deux fois.
    """
    repris, restants = 0, 0
    for cle in {l["modele"] for l in lignes_en_attente(societe_id, modele)}:
        if cle not in MODELES:
            continue
        lot = lignes_en_attente(societe_id, cle)
        entetes = json.loads(lot[0]["entetes"] or "[]")
        rangs = [json.loads(l["valeurs"] or "[]") for l in lot]
        garde = {}
        try:
            garde = json.loads(lot[0]["contexte"] or "{}")
        except ValueError:
            pass
        contexte = _Rejeu(societe_id, getattr(ctx, "nom_utilisateur", None),
                          {**garde, "modele": cle,
                           "fichier": lot[0]["fichier"]})
        try:
            essai = _analyse(contexte, _en_csv(entetes, rangs), cle)
        except ErreurApplicative:
            continue                    # le fichier n'est plus lisible tel quel
        rejetees = _lignes_rejetees(essai)
        passent = [i for i in range(len(rangs)) if (i + 2) not in rejetees]
        if not passent:
            for i, ligne in enumerate(lot):
                raison = rejetees.get(i + 2)
                db.modifie("lignes_attente", ligne["id"],
                           {"essais": ligne["essais"] + 1,
                            "raison": raison or ligne["raison"]})
            restants += len(lot)
            continue
        # Seules les lignes qui passent sont rejouées : les autres restent
        # exactement là où elles sont, avec ce qu'elles avaient.
        for i in passent:
            db.supprime("lignes_attente", lot[i]["id"])
        importe(contexte, cle, _en_csv(entetes, [rangs[i] for i in passent]),
                rejouer=False)
        repris += len(passent)
        restants += len(lot) - len(passent)
    return {"repris": repris, "restants": restants}


def rattache_reglements(societe_id: int) -> int:
    """Les encaissements non affectés retrouvent leur facture, si elle est là.

    Un règlement repris avant sa facture n'est pas une anomalie : l'argent
    est entré. Il attend simplement de savoir à quoi il se rapporte — et le
    saura tout seul.
    """
    rattaches = 0
    for r in db.lignes(
            "SELECT * FROM reglements WHERE societe_id = ? AND facture_id IS NULL "
            "AND reference_facture IS NOT NULL AND reference_facture <> ''",
            (societe_id,)):
        facture = db.ligne(
            "SELECT * FROM factures WHERE societe_id = ? AND numero = ? "
            "COLLATE NOCASE", (societe_id, r["reference_facture"]))
        if not facture:
            continue
        regle = facture["montant_regle"] + r["montant"]
        if regle > facture["net_a_payer"]:
            continue                    # le rattachement dépasserait le dû
        db.modifie("reglements", r["id"], {
            "facture_id": facture["id"],
            "tiers_id": r["tiers_id"] or facture["tiers_id"],
            "perimetre": facture["perimetre"],
            "libelle": f"Reprise — facture {facture['numero']}",
        })
        db.modifie("factures", facture["id"], {
            "montant_regle": regle,
            "statut": "reglee" if regle >= facture["net_a_payer"]
                      else ("partielle" if facture["statut"] != "brouillon"
                            else facture["statut"]),
        })
        rattaches += 1
    return rattaches


@route("GET", "/api/attente")
def api_attente(ctx):
    """Ce qui n'a pas pu être écrit, tel qu'il était dans le fichier."""
    societe_id = ctx.arg_int("societe")
    lignes = []
    for l in lignes_en_attente(societe_id, ctx.arg("modele") or None):
        lignes.append({
            "id": l["id"], "modele": l["modele"],
            "modele_libelle": MODELES.get(l["modele"], {}).get("libelle",
                                                              l["modele"]),
            "fichier": l["fichier"], "ligne": l["ligne"],
            "entetes": json.loads(l["entetes"] or "[]"),
            "valeurs": json.loads(l["valeurs"] or "[]"),
            "raison": l["raison"], "essais": l["essais"],
            "cree_le": l["cree_le"],
        })
    return {"lignes": lignes, "nombre": len(lignes)}


@route("POST", "/api/attente/corriger")
def api_corrige_attente(ctx):
    """Enregistre les valeurs corrigées, puis retente l'écriture."""
    ctx.interdit_lecture_seule()
    ctx.exige_role("admin", "comptable")
    societe_id = ctx.entier("societe_id") or ctx.arg_int("societe")
    for correction in ctx.champ("lignes") or []:
        ligne = db.ligne("SELECT * FROM lignes_attente WHERE id = ? AND "
                         "societe_id = ?", (correction.get("id"), societe_id))
        if not ligne:
            continue
        db.modifie("lignes_attente", ligne["id"], {
            "valeurs": json.dumps([str(v) if v is not None else ""
                                   for v in correction.get("valeurs") or []],
                                  ensure_ascii=False)})
    bilan = rejoue_attente(ctx, societe_id, ctx.champ("modele"))
    bilan["message"] = (
        f"{bilan['repris']} ligne(s) reprise(s)."
        + (f" {bilan['restants']} reste(nt) en attente."
           if bilan["restants"] else ""))
    return bilan


@route("POST", "/api/attente/rejouer")
def api_rejoue_attente(ctx):
    """Retente tout ce qui attend, sans rien corriger."""
    ctx.interdit_lecture_seule()
    ctx.exige_role("admin", "comptable")
    societe_id = ctx.entier("societe_id") or ctx.arg_int("societe")
    bilan = rejoue_attente(ctx, societe_id, ctx.champ("modele"))
    bilan["rattaches"] = rattache_reglements(societe_id)
    bilan["message"] = (
        f"{bilan['repris']} ligne(s) reprise(s)."
        + (f" {bilan['restants']} reste(nt) en attente."
           if bilan["restants"] else " Rien ne reste en attente."))
    return bilan


@route("DELETE", "/api/attente")
def api_oublie_attente(ctx):
    """Retire des lignes en attente : elles ne seront pas reprises."""
    ctx.interdit_lecture_seule()
    ctx.exige_role("admin", "comptable")
    societe_id = ctx.entier("societe_id") or ctx.arg_int("societe")
    identifiants = ctx.champ("ids") or []
    retires = 0
    for identifiant in identifiants:
        if db.ligne("SELECT id FROM lignes_attente WHERE id = ? AND "
                    "societe_id = ?", (identifiant, societe_id)):
            db.supprime("lignes_attente", identifiant)
            retires += 1
    return {"retires": retires,
            "message": f"{retires} ligne(s) retirée(s) de l'attente."}


def _photo_compteurs(societe_id: int) -> dict:
    """Où en est chaque compteur de numérotation du dossier, à cet instant."""
    return {f"{c['cle']}|{c['annee']}": c["valeur"] for c in db.lignes(
        "SELECT cle, annee, valeur FROM compteurs WHERE societe_id = ?",
        (societe_id,))}


def _compteurs_consommes(avant: dict, apres: dict) -> dict:
    """Les numéros que l'import a tirés : {clé|année: [avant, après]}.

    C'est ce couple qui dira plus tard si l'import est encore le dernier à
    avoir numéroté : si le compteur vaut toujours « après », personne n'a
    numéroté depuis, et supprimer ne laissera aucun trou.
    """
    return {k: [avant.get(k, 0), v] for k, v in apres.items()
            if v != avant.get(k, 0)}


def _rattache_a_import(import_id: int, bilan: dict) -> None:
    for table, colonne in (("ecritures", "ecritures"), ("factures", "factures"),
                           ("reglements", "reglements")):
        identifiants = bilan.get(colonne) or []
        for lot in range(0, len(identifiants), 400):
            tranche = identifiants[lot:lot + 400]
            marques = ",".join("?" for _ in tranche)
            db.execute(f"UPDATE {table} SET import_id = ? WHERE id IN ({marques})",
                       [import_id, *tranche])


def _importe_ecritures(ctx, societe_id, groupes) -> dict:
    identifiants = [compta.enregistre_ecriture(
        societe_id=societe_id,
        journal_code=groupe["journal"],
        date=groupe["date"],
        libelle=groupe["libelle"],
        lignes=groupe["lignes"],
        piece=groupe["piece"] or None,
        module="import",
        perimetre=groupe["perimetre"],
        utilisateur=ctx.nom_utilisateur,
        valider=False,       # importées en brouillon : le comptable relit
    ) for groupe in groupes]
    return {"nb": len(groupes), "ecritures": identifiants}


def _importe_balance(ctx, societe_id, balance) -> dict:
    """Une seule écriture d'à-nouveaux, dans le journal AN."""
    date = balance["date"] or db.valeur(
        "SELECT date_debut FROM exercices WHERE societe_id = ? AND cloture = 0 "
        "ORDER BY date_debut LIMIT 1", (societe_id,))
    if not date:
        raise ErreurApplicative("Aucun exercice ouvert : créez-le d'abord dans "
                                "Paramètres > Exercices.")
    identifiant = compta.enregistre_ecriture(
        societe_id=societe_id, journal_code="AN", date=date,
        libelle="Balance de reprise", lignes=balance["lignes"],
        module="import", source_type="balance_ouverture",
        perimetre="declare", utilisateur=ctx.nom_utilisateur, valider=True,
    )
    return {"nb": len(balance["lignes"]), "ecritures": [identifiant]}


def _importe_factures(ctx, societe_id, groupes) -> dict:
    """Écrit les factures, et les comptabilise sauf demande contraire.

    Elles arrivaient en brouillon : aucune écriture, donc rien au grand
    livre, et rien à l'écran pour le dire. « Il me dit qu'aucune n'est
    vraiment passée » — c'était exact. Reprendre des factures anciennes,
    c'est reprendre leur comptabilité : elles sont comptabilisées d'office,
    et qui veut les relire d'abord décoche la case.
    """
    from modules import facturation
    comptabiliser = ctx.booleen("comptabiliser", True)
    identifiants, comptabilisees, refus = [], 0, []
    for groupe in groupes:
        creee = facturation.cree_facture(
            societe_id, groupe["sens"], groupe["date"], groupe["lignes"],
            tiers_id=groupe["tiers_id"],
            numero=groupe["numero"],
            date_echeance=groupe["echeance"],
            objet=groupe["objet"] or None,
            origine="import",
            mode_reglement=groupe["mode_reglement"],
            perimetre=groupe["perimetre"],
            utilisateur=ctx.nom_utilisateur,
            valider=False,
        )
        identifiants.append(creee["id"])
        if not comptabiliser:
            continue
        try:
            facturation._valide(creee["id"], ctx.nom_utilisateur)
            comptabilisees += 1
        except ErreurApplicative as err:
            # Une facture qui ne passe pas reste en brouillon plutôt que
            # d'arrêter la reprise : elle est nommée dans le compte rendu.
            refus.append({"numero": creee["numero"], "raison": str(err)})
    return {"nb": len(groupes), "factures": identifiants,
            "comptabilisees": comptabilisees, "non_comptabilisees": refus}


def _importe_reglements(ctx, societe_id, rangs) -> dict:
    """Marque les factures réglées, sans écriture : la reprise l'a déjà portée."""
    identifiants = []
    # Ce que chaque facture portait avant : de quoi la remettre exactement
    # dans son état si la reprise est annulée.
    avant = {}
    for r in rangs:
        facture = r["facture"]
        if facture:
            avant.setdefault(facture["id"], {
                "id": facture["id"], "montant_regle": facture["montant_regle"],
                "statut": facture["statut"]})
        exercice = compta.exercice_pour_date(societe_id, r["date"])
        identifiants.append(db.insere("reglements", {
            "societe_id": societe_id,
            "exercice_id": exercice["id"],
            "sens": r["sens"],
            "date": r["date"],
            "tiers_id": facture["tiers_id"] if facture else None,
            "tresorerie_id": r["tresorerie_id"] or resout_reference(
                "tresorerie", societe_id, r.get("tresorerie")),
            "montant": r["montant"],
            # La colonne « Mode » est facultative dans le fichier ; la
            # colonne l'est moins en base. Un fichier sans elle faisait
            # échouer tout l'import sur une contrainte NOT NULL.
            "mode": r["mode"] or "virement",
            "reference": r["reference"],
            "libelle": (f"Reprise — facture {facture['numero']}" if facture
                        else f"Reprise — encaissement non affecté "
                             f"({r['reference_facture']})"),
            "facture_id": facture["id"] if facture else None,
            # Gardé dans tous les cas : c'est la clé du rattachement à venir.
            "reference_facture": r["reference_facture"],
            "perimetre": facture["perimetre"] if facture else "declare",
            "cree_le": util.maintenant(),
        }))
        if not facture:
            continue
        regle = facture["montant_regle"] + r["montant"]
        db.modifie("factures", facture["id"], {
            "montant_regle": regle,
            "statut": "reglee" if regle >= facture["net_a_payer"]
                      else ("partielle" if facture["statut"] != "brouillon"
                            else facture["statut"]),
        })
    return {"nb": len(rangs), "reglements": identifiants,
            "factures_reglees": list(avant.values())}


# ---------------------------------------------------------------------------
# Journal des reprises — et comment défaire un import
# ---------------------------------------------------------------------------
#
# Un import se fait en un clic et peut porter des centaines de lignes. Se
# tromper de fichier, ou passer le même deux fois, arrive. Jusqu'ici il ne
# restait qu'à reprendre les écritures une par une.
#
# Deux façons de défaire, et le logiciel choisit lui-même laquelle s'applique :
#
#   suppression       tant que l'import est le dernier à avoir numéroté ses
#                     journaux, ses écritures peuvent partir sans laisser de
#                     trou dans la numérotation. Les compteurs sont remis
#                     exactement où ils étaient.
#   contre_passation  dès qu'une écriture a été passée depuis, plus question
#                     d'effacer : chaque écriture importée est extournée, à
#                     une date que le comptable choisit. Tout reste visible.
#
# Pour un import de référentiel (tiers, comptes, biens…), qui ne porte aucune
# comptabilité, la question ne se pose pas : ce qui n'est pas encore utilisé
# est retiré, ce qui l'est déjà reste, et l'écran dit lequel est lequel.

#: Modèles dont l'import touche la comptabilité. Pour ceux-là, l'annulation
#: est tout ou rien : une reprise à moitié défaite ne s'explique plus.
MODELES_COMPTABLES = {"balance_ouverture", "ecritures", "reglements",
                      "factures_vente", "factures_achat"}


#: Rattachements que le schéma ne déclare pas en clé étrangère : ces colonnes
#: désignent bien un objet, mais SQLite ne le sait pas.
LIENS_IMPLICITES = {
    "programmes": [("lignes", "programme_id"), ("factures", "programme_id")],
    "lots": [("lignes", "lot_id"), ("factures", "lot_id"),
             ("contrats_vsp", "lot_id")],
    "biens": [("lignes", "bien_id"), ("factures", "bien_id")],
    "baux": [("factures", "bail_id"), ("quittances", "bail_id")],
    "contrats_vsp": [("factures", "contrat_vsp_id"), ("echeances_vsp", "contrat_id")],
    "quittances": [("reglements", "quittance_id")],
    "echeances_vsp": [("reglements", "echeance_id")],
}

#: Cas où le lien ne passe pas par un identifiant : une ligne comptable
#: désigne son compte par son numéro.
LIENS_PARTICULIERS = {
    "comptes": [
        ("écritures", "SELECT COUNT(*) FROM lignes WHERE compte = "
                      "(SELECT numero FROM comptes WHERE id = ?)"),
        ("journaux", "SELECT COUNT(*) FROM journaux WHERE compte_contrepartie = "
                     "(SELECT numero FROM comptes WHERE id = ?)"),
    ],
    "comptes_tresorerie": [
        ("écritures", "SELECT COUNT(*) FROM lignes WHERE compte = "
                      "(SELECT compte FROM comptes_tresorerie WHERE id = ?)"),
    ],
}


def _references(table: str) -> list[tuple[str, str]]:
    """Colonnes qui désignent cette table, lues dans le schéma lui-même.

    Les clés étrangères du schéma sont en « ON DELETE SET NULL » : supprimer
    un tiers employé ne déclencherait aucune erreur, la référence serait
    simplement effacée. Il faut donc regarder avant, pas après.
    """
    liens = []
    for t in db.lignes("SELECT name FROM sqlite_master WHERE type = 'table' "
                       "AND name NOT LIKE 'sqlite_%%'"):
        for fk in db.lignes(f"PRAGMA foreign_key_list({t['name']})"):
            if fk["table"] == table:
                liens.append((t["name"], fk["from"]))
    return liens + LIENS_IMPLICITES.get(table, [])


def _usages(table: str, identifiant: int, liens) -> list[str]:
    """Où cet objet sert encore. Vide = il peut partir sans rien casser."""
    trouves = []
    for cible, colonne in liens:
        condition, params = f"{colonne} = ?", [identifiant]
        if cible == table:
            condition += " AND id != ?"
            params.append(identifiant)
        try:
            combien = db.valeur(
                f"SELECT COUNT(*) FROM {cible} WHERE {condition}", params, 0)
        except sqlite3.OperationalError:
            continue                 # table absente d'une base ancienne
        if combien:
            trouves.append(f"{cible} ({combien})")
    for libelle, requete in LIENS_PARTICULIERS.get(table, []):
        if db.valeur(requete, (identifiant,), 0):
            trouves.append(libelle)
    return trouves


class _Simulation(Exception):
    """Sert à ressortir d'une transaction en la faisant annuler."""

    def __init__(self, resultat):
        super().__init__("simulation")
        self.resultat = resultat


def _simule(action):
    """Exécute `action` puis annule tout : rien n'est écrit, on sait quand même.

    C'est ce qui permet d'annoncer au comptable, avant qu'il ne décide, ce que
    l'annulation ferait exactement — sans le lui décrire de mémoire.
    """
    try:
        with db.transaction():
            raise _Simulation(action())
    except _Simulation as simulation:
        return simulation.resultat


def _import_ou_erreur(identifiant: int) -> dict:
    imp = db.ligne("SELECT * FROM imports WHERE id = ?", (identifiant,))
    if not imp:
        raise ErreurApplicative("Cet import est introuvable.", 404)
    return imp


def _details_import(imp: dict) -> dict:
    """Tout ce que cet import a laissé derrière lui."""
    try:
        objets = json.loads(imp["objets"] or "{}")
    except ValueError:
        objets = {}
    identifiant = imp["id"]
    ecritures = db.lignes(
        "SELECT e.*, j.code AS journal FROM ecritures e "
        "JOIN journaux j ON j.id = e.journal_id "
        "WHERE e.import_id = ? OR e.id IN ("
        "    SELECT ecriture_id FROM factures "
        "    WHERE import_id = ? AND ecriture_id IS NOT NULL) "
        "ORDER BY e.id", (identifiant, identifiant))
    return {
        "ecritures": ecritures,
        "factures": db.lignes(
            "SELECT * FROM factures WHERE import_id = ? ORDER BY id",
            (identifiant,)),
        "reglements": db.lignes(
            "SELECT * FROM reglements WHERE import_id = ? ORDER BY id",
            (identifiant,)),
        "tables": objets.get("tables") or {},
        "completes": objets.get("completes") or {},
        "compteurs": objets.get("compteurs") or {},
        "factures_reglees": objets.get("factures_reglees") or [],
    }


def _obstacles_suppression(imp: dict, detail: dict) -> list[str]:
    """Ce qui interdit d'effacer purement et simplement — pas d'annuler."""
    obstacles = []

    # 1. L'import est-il encore le dernier à avoir numéroté ?
    for cle_annee, (_avant, apres) in detail["compteurs"].items():
        cle, annee = cle_annee.rsplit("|", 1)
        actuel = db.valeur(
            "SELECT valeur FROM compteurs WHERE societe_id = ? AND cle = ? "
            "AND annee = ?", (imp["societe_id"], cle, int(annee)), 0)
        if actuel != apres:
            quoi = (f"le journal {cle[9:]}" if cle.startswith("ecriture_")
                    else f"la numérotation « {cle} »")
            obstacles.append(
                f"{actuel - apres} numéro(s) ont été attribués depuis dans "
                f"{quoi} ({annee}) : effacer laisserait un trou.")

    # 2. Un exercice clôturé ne se rouvre pas pour retirer une écriture.
    for ex in {e["exercice_id"] for e in detail["ecritures"]}:
        exercice = db.ligne("SELECT * FROM exercices WHERE id = ?", (ex,))
        if exercice and exercice["cloture"]:
            obstacles.append(
                f"l'exercice {exercice['libelle']} est clôturé.")

    # 3. Une écriture lettrée a servi à justifier un solde de tiers.
    if detail["ecritures"]:
        marques = ",".join("?" for _ in detail["ecritures"])
        lettrees = db.valeur(
            f"SELECT COUNT(*) FROM lignes WHERE ecriture_id IN ({marques}) "
            f"AND lettrage IS NOT NULL AND lettrage != ''",
            [e["id"] for e in detail["ecritures"]], 0)
        if lettrees:
            obstacles.append(
                f"{lettrees} ligne(s) ont été lettrées depuis.")

    # 4. Une facture importée a été réglée après coup.
    for f in detail["factures"]:
        depuis = db.valeur(
            "SELECT COUNT(*) FROM reglements WHERE facture_id = ? "
            "AND (import_id IS NULL OR import_id != ?)",
            (f["id"], imp["id"]), 0)
        if depuis:
            obstacles.append(
                f"la facture {f['numero']} a reçu {depuis} règlement(s) depuis.")
    return obstacles


def _mode_annulation(imp: dict, detail: dict) -> tuple[str, list[str]]:
    """Comment cet import peut être défait, et pourquoi pas autrement."""
    obstacles = _obstacles_suppression(imp, detail)
    if not obstacles:
        return "suppression", []
    if imp["modele"] in MODELES_COMPTABLES:
        return "contre_passation", obstacles
    return "partiel", obstacles


def _defait(imp: dict, detail: dict, mode: str, date: str,
            utilisateur: str | None) -> dict:
    """Applique l'annulation. À appeler dans une transaction.

    Renvoie le compte rendu de ce qui a été fait — le même objet, que l'appel
    soit réel ou qu'il tourne en simulation.
    """
    rendu = {"mode": mode, "supprimees": 0, "extournees": [], "factures": 0,
             "reglements": 0, "objets_retires": {}, "objets_gardes": {},
             "objets_pourquoi": {}}

    # -- Les règlements repris ne portent aucune écriture : la reprise l'a
    # -- déjà comptabilisée. Les retirer n'efface donc rien des comptes.
    for r in detail["reglements"]:
        db.supprime("reglements", r["id"])
        rendu["reglements"] += 1
    for etat in detail["factures_reglees"]:
        if db.ligne("SELECT id FROM factures WHERE id = ?", (etat["id"],)):
            db.modifie("factures", etat["id"], {
                "montant_regle": etat["montant_regle"],
                "statut": etat["statut"]})

    if mode == "contre_passation":
        for e in detail["ecritures"]:
            nouvelle = compta.extourne_ecriture(e["id"], date, utilisateur)
            rendu["extournees"].append(
                db.valeur("SELECT numero FROM ecritures WHERE id = ?",
                          (nouvelle,), str(nouvelle)))
        for f in detail["factures"]:
            db.modifie("factures", f["id"], {"statut": "annulee"})
            rendu["factures"] += 1
        return rendu

    # -- Suppression : les factures d'abord (leur écriture, s'il y en a une,
    # -- figure déjà dans la liste des écritures), les écritures ensuite.
    for f in detail["factures"]:
        db.supprime("factures", f["id"])
        rendu["factures"] += 1
    for e in detail["ecritures"]:
        compta.supprime_ecriture(e["id"], utilisateur, forcer=True)
        rendu["supprimees"] += 1

    # -- Les numéros repartent d'où ils venaient : aucun trou dans le journal.
    for cle_annee, (avant, apres) in detail["compteurs"].items():
        cle, annee = cle_annee.rsplit("|", 1)
        actuel = db.valeur(
            "SELECT valeur FROM compteurs WHERE societe_id = ? AND cle = ? "
            "AND annee = ?", (imp["societe_id"], cle, int(annee)), 0)
        if actuel == apres:
            db.execute(
                "UPDATE compteurs SET valeur = ? WHERE societe_id = ? "
                "AND cle = ? AND annee = ?",
                (avant, imp["societe_id"], cle, int(annee)))

    # -- Référentiel : ce qui sert encore reste, et l'écran dira lequel.
    for table, identifiants in detail["tables"].items():
        liens = _references(table)
        retires, gardes, pourquoi = 0, 0, []
        for identifiant in identifiants:
            if not db.ligne(f"SELECT id FROM {table} WHERE id = ?", (identifiant,)):
                continue           # déjà supprimé à la main entre-temps
            usages = _usages(table, identifiant, liens)
            if usages:
                gardes += 1
                pourquoi.extend(usages)
                continue
            try:
                db.supprime(table, identifiant)
                retires += 1
            except sqlite3.IntegrityError:
                gardes += 1
        if retires:
            rendu["objets_retires"][table] = retires
        if gardes:
            rendu["objets_gardes"][table] = gardes
            rendu.setdefault("objets_pourquoi", {})[table] = sorted(set(pourquoi))
    return rendu


def _libelle_mode(mode: str) -> str:
    return {
        "suppression": "suppression pure et simple",
        "contre_passation": "contre-passation (extourne)",
        "partiel": "retrait de ce qui n'est pas encore utilisé",
    }.get(mode, mode)


@route("GET", "/api/imports")
def api_journal_imports(ctx):
    """Les reprises faites sur ce dossier, la plus récente en tête."""
    societe_id = ctx.arg_int("societe")
    lignes = db.lignes(
        "SELECT * FROM imports WHERE societe_id = ? "
        "ORDER BY cree_le DESC, id DESC LIMIT ?",
        (societe_id, min(ctx.arg_int("limite", 50) or 50, 400)))
    for imp in lignes:
        imp["modele_libelle"] = (MODELES.get(imp["modele"], {})
                                 .get("libelle", imp["modele"]))
        imp["comptable"] = imp["modele"] in MODELES_COMPTABLES
        imp.pop("objets", None)          # détail inutile à la liste
    return {"imports": lignes}


@route("GET", "/api/imports/<id>/plan")
def api_plan_annulation(ctx):
    """Ce que l'annulation ferait, établi en la jouant pour de faux.

    Le compte rendu n'est pas une description écrite à la main : c'est le
    résultat de l'annulation réelle, exécutée puis annulée. Ce qui est
    annoncé est donc exactement ce qui se produira.
    """
    imp = _import_ou_erreur(int(ctx.params["id"]))
    date = ctx.arg("date") or util.aujourdhui()
    detail = _details_import(imp)
    mode, obstacles = _mode_annulation(imp, detail)
    plan = {
        "import": {k: imp[k] for k in
                   ("id", "modele", "libelle", "fichier", "nb_crees",
                    "nb_rejetes", "cree_le", "cree_par", "annule_le",
                    "annule_par", "annule_mode", "annule_note")},
        "modele_libelle": (MODELES.get(imp["modele"], {})
                           .get("libelle", imp["modele"])),
        "comptable": imp["modele"] in MODELES_COMPTABLES,
        "mode": mode,
        "mode_libelle": _libelle_mode(mode),
        "obstacles": obstacles,
        "porte": {
            "ecritures": len(detail["ecritures"]),
            "factures": len(detail["factures"]),
            "reglements": len(detail["reglements"]),
            "objets": {t: len(i) for t, i in detail["tables"].items()},
            # Ces fiches-là existaient avant l'import, qui n'a fait que les
            # remplir : elles restent, et l'écran doit le dire.
            "completes": {t: len(i) for t, i in detail["completes"].items()},
        },
    }
    if imp["annule_le"]:
        plan["possible"] = False
        plan["empechement"] = (
            f"Cet import a déjà été annulé le {util.date_fr(imp['annule_le'][:10])}.")
        return plan
    if not (detail["ecritures"] or detail["factures"] or detail["reglements"]
            or detail["tables"]):
        plan["possible"] = False
        plan["empechement"] = (
            "Cet import n'a rien laissé qui puisse être retiré : il date "
            "d'une version antérieure au journal des reprises.")
        return plan
    try:
        plan["rendu"] = _simule(
            lambda: _defait(imp, detail, mode, date, ctx.nom_utilisateur))
        plan["possible"] = True
    except ErreurApplicative as err:
        plan["possible"] = False
        plan["empechement"] = str(err)
        return plan
    # Un référentiel dont une partie sert déjà ne peut être retiré qu'en
    # partie : la simulation est seule à pouvoir le dire.
    if plan["rendu"].get("objets_gardes"):
        plan["mode"] = plan["rendu"]["mode"] = "partiel"
        plan["mode_libelle"] = _libelle_mode("partiel")
    return plan


@route("POST", "/api/imports/<id>/annuler")
def api_annule_import(ctx):
    ctx.interdit_lecture_seule()
    ctx.exige_role("admin", "comptable")
    imp = _import_ou_erreur(int(ctx.params["id"]))
    if imp["annule_le"]:
        raise ErreurApplicative(
            f"Cet import a déjà été annulé le "
            f"{util.date_fr(imp['annule_le'][:10])}.")
    date = ctx.date("date", util.aujourdhui())
    detail = _details_import(imp)
    mode, obstacles = _mode_annulation(imp, detail)

    # Le mode annoncé à l'écran doit être celui qui s'applique : si la
    # situation a changé entre-temps, on s'arrête plutôt que de faire autre
    # chose que ce que le comptable a validé.
    # « partiel » n'est qu'une suppression dont une part est retenue : c'est
    # la distinction entre effacer et contre-passer qui doit être confirmée.
    famille = {"partiel": "suppression"}
    attendu = famille.get(ctx.champ("mode"), ctx.champ("mode"))
    if attendu and attendu != famille.get(mode, mode):
        raise ErreurApplicative(
            f"La situation a changé depuis l'affichage : cet import ne peut "
            f"plus être annulé par {_libelle_mode(attendu)}, mais par "
            f"{_libelle_mode(mode)}. Reprenez l'écran d'annulation.")

    with db.transaction():
        rendu = _defait(imp, detail, mode, date, ctx.nom_utilisateur)
        note = []
        if rendu["supprimees"]:
            note.append(f"{rendu['supprimees']} écriture(s) supprimée(s)")
        if rendu["extournees"]:
            note.append(f"{len(rendu['extournees'])} extourne(s) : "
                        + ", ".join(rendu["extournees"][:12])
                        + (" …" if len(rendu["extournees"]) > 12 else ""))
        if rendu["factures"]:
            note.append(f"{rendu['factures']} facture(s)")
        if rendu["reglements"]:
            note.append(f"{rendu['reglements']} règlement(s) retiré(s)")
        for table, combien in rendu["objets_retires"].items():
            note.append(f"{combien} {table} retiré(s)")
        for table, combien in rendu["objets_gardes"].items():
            note.append(f"{combien} {table} conservé(s), déjà utilisé(s)")
        db.modifie("imports", imp["id"], {
            "annule_le": util.maintenant(),
            "annule_par": ctx.nom_utilisateur,
            "annule_mode": mode,
            "annule_note": " ; ".join(note) or "rien à retirer",
        })
        db.trace("annulation_import", "import", imp["id"],
                 {"mode": mode, "note": note}, ctx.nom_utilisateur)
    rendu["obstacles"] = obstacles
    rendu["mode_libelle"] = _libelle_mode(mode)
    return rendu
