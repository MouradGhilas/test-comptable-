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
    Colonne("Prix unitaire", "Prix hors taxes de l'unité", "500000",
            requis=True, synonymes=("prix", "pu", "prix unitaire ht", "montant ht")),
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
            "Les comptes absents du plan comptable sont signalés : créez-les",
            "d'abord par le modèle « Plan comptable ».",
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
            "Le propriétaire doit exister : importez vos tiers d'abord.",
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
            "Le bien et le mandant doivent exister : importez-les d'abord.",
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
            "Le bien, le propriétaire et le locataire doivent exister :",
            "importez vos tiers et vos biens d'abord.",
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
            "Le programme doit exister : importez vos programmes d'abord.",
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
            "Le programme, le lot et l'acquéreur doivent exister : importez-les",
            "d'abord.",
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
            "Le contrat doit exister : importez vos contrats VSP d'abord.",
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

#: Ordre dans lequel reprendre un dossier : chaque étape s'appuie sur la
#: précédente (une facture a besoin de son tiers, un bail de son bien…).
ORDRE_CONSEILLE = [
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
        "ordre_conseille": ORDRE_CONSEILLE,
        "modeles": [
            {"cle": cle, "libelle": MODELES[cle]["libelle"],
             "groupe": MODELES[cle].get("groupe", "Comptabilité"),
             "rang": ORDRE_CONSEILLE.index(cle) + 1 if cle in ORDRE_CONSEILLE else 99,
             "colonnes": [{"nom": c.nom, "requis": c.requis, "aide": c.aide}
                          for c in MODELES[cle]["colonnes"]]}
            for cle in sorted(MODELES,
                              key=lambda c: ORDRE_CONSEILLE.index(c)
                              if c in ORDRE_CONSEILLE else 99)
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
# Contrôle générique d'une table
# ---------------------------------------------------------------------------

def analyse_generique(societe_id, rangs, association, modele, cle_modele):
    """Contrôle et prépare les lignes d'une table décrite de façon déclarative."""
    prets, anomalies, apercu = [], [], []
    cle_unique = modele.get("cle_unique")
    table = modele["table"]
    deja_vus = set()
    if cle_unique:
        deja_vus = {str(r[cle_unique]).lower() for r in db.lignes(
            f"SELECT {cle_unique} FROM {table} WHERE societe_id = ?", (societe_id,))
            if r[cle_unique] is not None}

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
                if identifiant is None:
                    libelle = LIBELLES_REFERENCE[colonne.reference]
                    erreurs.append(f"{libelle} « {valeur} » introuvable")
                    continue
                resolus[colonne.nom] = identifiant
                enregistrement[colonne.champ] = identifiant
                continue
            try:
                enregistrement[colonne.champ] = CONVERTISSEURS[colonne.type](valeur)
            except (ValueError, TypeError):
                erreurs.append(f"« {colonne.nom} » : valeur « {valeur} » "
                               "incompréhensible")

        if cle_unique and not erreurs:
            reference = str(enregistrement.get(cle_unique, "")).lower()
            if reference and reference in deja_vus:
                erreurs.append(f"« {brut.get(_nom_de_champ(modele, cle_unique))} » "
                               "existe déjà")
            elif reference:
                deja_vus.add(reference)

        erreurs += _controles_specifiques(societe_id, cle_modele, brut,
                                          enregistrement)

        for message in erreurs:
            anomalies.append({"ligne": numero_ligne, "message": message})
        apercu.append({"ligne": numero_ligne, "valeurs": brut, "erreurs": erreurs})
        if not erreurs:
            prets.append(enregistrement)

    return {"prets": prets, "anomalies": anomalies, "apercu": apercu,
            "nb_valides": len(prets), "nb_rejetes": len(apercu) - len(prets)}


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


def _importe_generique(societe_id, modele, rangs) -> int:
    for enregistrement in rangs:
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
        db.insere(modele["table"], {c: v for c, v in enregistrement.items()
                                    if v is not None})
    return len(rangs)


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
        elif compte not in comptes_connus:
            suggestions = comptes_proches(comptes_connus, compte)
            precision = (f" — le plus proche dans votre plan : "
                         f"{', '.join(suggestions)}" if suggestions else "")
            erreurs.append(
                f"le compte {compte} n'existe pas dans le plan comptable"
                f"{precision}. Créez-le par le modèle « Plan comptable », ou "
                "corrigez le fichier.")
        if erreur_journal:
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
        })

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
            "lignes_ignorees": ignorees}


def analyse_balance(societe_id, rangs, association, date_reprise):
    """Contrôle une balance de reprise : comptes connus et totaux égaux."""
    anomalies, lignes, apercu, ignorees = [], [], [], []
    comptes_connus = {str(c["numero"]) for c in db.lignes(
        "SELECT numero FROM comptes WHERE societe_id = ?", (societe_id,))}
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
        elif compte not in comptes_connus:
            suggestions = comptes_proches(comptes_connus, compte)
            precision = (f" — le plus proche dans votre plan : "
                         f"{', '.join(suggestions)}" if suggestions else "")
            erreurs.append(
                f"le compte {compte} n'existe pas dans le plan comptable"
                f"{precision}. Créez-le par le modèle « Plan comptable », ou "
                "corrigez le fichier.")
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
            "lignes_ignorees": ignorees}


def analyse_factures(societe_id, rangs, association, defaut_perimetre, sens):
    """Regroupe les lignes par numéro de facture et contrôle chaque facture."""
    groupes: dict[str, dict] = {}
    ordre: list[str] = []
    anomalies = []
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

        erreurs = []
        if not designation:
            erreurs.append("désignation manquante")
        if not prix:
            erreurs.append("prix unitaire manquant")

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
                erreurs.append(f"le tiers « {tiers} » est introuvable : "
                               "importez d'abord vos tiers")
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
        "nb_lignes": len(g["lignes"]), "lignes_fichier": g["lignes_fichier"],
        "erreurs": g["erreurs"],
    } for g in (groupes[c] for c in ordre)]

    return {"prets": prets, "anomalies": anomalies, "apercu": apercu,
            "nb_valides": len(prets), "nb_rejetes": len(ordre) - len(prets)}


SENS_REGLEMENT = {"encaissement", "decaissement"}


def analyse_reglements(societe_id, rangs, association):
    """Rattache chaque règlement à sa facture et contrôle le reste dû."""
    prets, anomalies, apercu = [], [], []
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
        elif not facture:
            erreurs.append(f"la facture n° {numero} est introuvable : "
                           "importez d'abord vos factures")
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
            erreurs.append(f"compte de trésorerie « {tresorerie} » introuvable")

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
            "facture": facture, "date": date, "montant": montant,
            "sens": sens or ("encaissement" if facture["sens"] == "vente"
                             else "decaissement"),
            "mode": mode or None, "tresorerie_id": tresorerie_id,
            "reference": _valeur(rang, association, "Référence") or None,
        })

    return {"prets": prets, "anomalies": anomalies, "apercu": apercu,
            "nb_valides": len(prets),
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
        "colonnes_reconnues": sorted(association),
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
    resultat.pop("prets", None)          # inutile au navigateur, parfois volumineux
    return resultat


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

    resultat = _analyse(ctx, _decode_fichier(ctx), cle)
    if resultat["anomalies"] and not ctx.booleen("ignorer_anomalies"):
        raise ErreurApplicative(
            f"{len(resultat['anomalies'])} anomalie(s) : rien n'a été importé. "
            "Corrigez le fichier, ou demandez l'import des seules lignes saines.",
            details=resultat["anomalies"][:50])

    societe_id = resultat["societe_id"]
    prets = resultat["prets"]
    if not prets:
        raise ErreurApplicative("Aucune ligne exploitable dans ce fichier.")

    # Un seul bloc : ou tout passe, ou rien n'est écrit.
    with db.transaction():
        if cle == "ecritures":
            crees = _importe_ecritures(ctx, societe_id, prets)
        elif cle == "balance_ouverture":
            crees = _importe_balance(ctx, societe_id, prets[0])
        elif cle == "reglements":
            crees = _importe_reglements(ctx, societe_id, prets)
        elif cle.startswith("factures_"):
            crees = _importe_factures(ctx, societe_id, prets)
        else:
            crees = _importe_generique(societe_id, MODELES[cle], prets)
        db.trace("import", cle, societe_id,
                 {"crees": crees, "rejetes": resultat["nb_rejetes"]},
                 ctx.nom_utilisateur)

    return {"crees": crees, "rejetes": resultat["nb_rejetes"],
            "anomalies": resultat["anomalies"], "libelle": resultat["libelle"]}


def _importe_ecritures(ctx, societe_id, groupes) -> int:
    for groupe in groupes:
        compta.enregistre_ecriture(
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
        )
    return len(groupes)


def _importe_balance(ctx, societe_id, balance) -> int:
    """Une seule écriture d'à-nouveaux, dans le journal AN."""
    date = balance["date"] or db.valeur(
        "SELECT date_debut FROM exercices WHERE societe_id = ? AND cloture = 0 "
        "ORDER BY date_debut LIMIT 1", (societe_id,))
    if not date:
        raise ErreurApplicative("Aucun exercice ouvert : créez-le d'abord dans "
                                "Paramètres > Exercices.")
    compta.enregistre_ecriture(
        societe_id=societe_id, journal_code="AN", date=date,
        libelle="Balance de reprise", lignes=balance["lignes"],
        module="import", source_type="balance_ouverture",
        perimetre="declare", utilisateur=ctx.nom_utilisateur, valider=True,
    )
    return len(balance["lignes"])


def _importe_factures(ctx, societe_id, groupes) -> int:
    from modules import facturation
    for groupe in groupes:
        facturation.cree_facture(
            societe_id, groupe["sens"], groupe["date"], groupe["lignes"],
            tiers_id=groupe["tiers_id"],
            numero=groupe["numero"],
            date_echeance=groupe["echeance"],
            objet=groupe["objet"] or None,
            origine="import",
            mode_reglement=groupe["mode_reglement"],
            perimetre=groupe["perimetre"],
            utilisateur=ctx.nom_utilisateur,
            valider=False,       # brouillon : l'écriture attend la relecture
        )
    return len(groupes)


def _importe_reglements(ctx, societe_id, rangs) -> int:
    """Marque les factures réglées, sans écriture : la reprise l'a déjà portée."""
    for r in rangs:
        facture = r["facture"]
        exercice = compta.exercice_pour_date(societe_id, r["date"])
        db.insere("reglements", {
            "societe_id": societe_id,
            "exercice_id": exercice["id"],
            "sens": r["sens"],
            "date": r["date"],
            "tiers_id": facture["tiers_id"],
            "tresorerie_id": r["tresorerie_id"],
            "montant": r["montant"],
            "mode": r["mode"],
            "reference": r["reference"],
            "libelle": f"Reprise — facture {facture['numero']}",
            "facture_id": facture["id"],
            "perimetre": facture["perimetre"],
            "cree_le": util.maintenant(),
        })
        regle = facture["montant_regle"] + r["montant"]
        db.modifie("factures", facture["id"], {
            "montant_regle": regle,
            "statut": "reglee" if regle >= facture["net_a_payer"]
                      else ("partielle" if facture["statut"] != "brouillon"
                            else facture["statut"]),
        })
    return len(rangs)
