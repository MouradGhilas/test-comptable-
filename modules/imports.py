"""Reprise des données existantes depuis Excel.

Le principe demandé : l'application fournit les en-têtes, le comptable remplit
le fichier avec ses propres données, puis le réintègre. Il n'a donc jamais à
deviner un format.

L'import se fait toujours en deux temps :

  1. **Contrôle** — le fichier est lu et vérifié ligne par ligne, sans rien
     écrire. Chaque anomalie est rapportée avec son numéro de ligne.
  2. **Validation** — seules les lignes saines sont enregistrées, par le même
     chemin que la saisie manuelle (`comptabilite.enregistre_ecriture`), donc
     avec les mêmes contrôles d'équilibre, d'exercice et de plan comptable.

Formats acceptés : .xlsx et .csv (séparateur « ; », encodage Excel français).
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
# Description des modèles
# ---------------------------------------------------------------------------

class Colonne:
    """Une colonne du modèle : son en-tête, ce qu'elle attend, son exemple."""

    def __init__(self, nom, aide, exemple="", requis=False, synonymes=()):
        self.nom = nom
        self.aide = aide
        self.exemple = exemple
        self.requis = requis
        self.synonymes = synonymes


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


MODELES = {
    "ecritures": {
        "libelle": "Écritures comptables",
        "notice": [
            "Une ligne du fichier = une ligne d'écriture (un compte, un montant).",
            "Les lignes qui portent le même « N° écriture » forment une seule",
            "écriture : elles doivent s'équilibrer entre elles (total des débits",
            "égal au total des crédits).",
            "",
            "La colonne « Périmètre » accepte : Déclaré ou Non déclaré. Laissée",
            "vide, elle prend la valeur par défaut du dossier. Un même fichier",
            "peut donc contenir les deux.",
            "",
            "Les montants s'écrivent sans symbole : 16000000 ou 16 000 000,00.",
            "Les dates s'écrivent JJ/MM/AAAA ou AAAA-MM-JJ.",
        ],
        "colonnes": [
            Colonne("N° écriture", "Regroupe les lignes d'une même écriture",
                    "1", requis=True, synonymes=("n° ecriture", "numero", "n°", "piece")),
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
        "libelle": "Factures de vente",
        "sens": "vente",
        "notice": _NOTICE_FACTURES,
        "colonnes": _COLONNES_FACTURES,
    },
    "factures_achat": {
        "libelle": "Factures d'achat",
        "sens": "achat",
        "notice": _NOTICE_FACTURES,
        "colonnes": _COLONNES_FACTURES,
    },
    "tiers": {
        "libelle": "Tiers (clients, fournisseurs, propriétaires, locataires)",
        "notice": [
            "La colonne « Type » accepte : client, fournisseur, mandant,",
            "locataire, acquereur, salarie, autre.",
            "",
            "« mandant » désigne le propriétaire pour lequel l'agence gère un",
            "bien ; « acquereur » l'acheteur d'un lot en promotion.",
        ],
        "colonnes": [
            Colonne("Type", "client, fournisseur, mandant, locataire, acquereur",
                    "client", requis=True),
            Colonne("Raison sociale", "Nom de la personne ou de l'entreprise",
                    "BENALI Karim", requis=True,
                    synonymes=("nom", "raison_sociale", "denomination")),
            Colonne("NIF", "Numéro d'identification fiscale", "000116001234567"),
            Colonne("NIS", "Numéro d'identification statistique", ""),
            Colonne("RC", "Registre de commerce", ""),
            Colonne("Article", "Article d'imposition", "",
                    synonymes=("article imposition", "article_imposition")),
            Colonne("Adresse", "Adresse postale", "12 rue Didouche Mourad"),
            Colonne("Commune", "Commune", "Alger-Centre"),
            Colonne("Wilaya", "Wilaya", "16 Alger"),
            Colonne("Téléphone", "Numéro de téléphone", "0550112233",
                    synonymes=("telephone", "tel")),
            Colonne("Courriel", "Adresse e-mail", "", synonymes=("email", "mail")),
        ],
    },
    "comptes": {
        "libelle": "Plan comptable (comptes supplémentaires)",
        "notice": [
            "N'indiquez ici que les comptes qui manquent au plan SCF livré avec",
            "l'application : les comptes existants ne sont pas modifiés.",
            "",
            "La classe est déduite du premier chiffre du numéro.",
        ],
        "colonnes": [
            Colonne("Compte", "Numéro du compte", "4011", requis=True,
                    synonymes=("numero", "n° compte")),
            Colonne("Intitulé", "Libellé du compte", "Fournisseurs de travaux",
                    requis=True, synonymes=("intitule", "libelle")),
            Colonne("Lettrable", "oui / non — pour les comptes de tiers", "oui"),
        ],
    },
    "biens": {
        "libelle": "Biens en portefeuille (agence)",
        "notice": [
            "La colonne « Type » accepte : appartement, villa, local, terrain,",
            "bureau, hangar, autre.",
            "",
            "« Opération » accepte : vente ou location.",
        ],
        "colonnes": [
            Colonne("Référence", "Référence interne du bien", "APT-001",
                    requis=True, synonymes=("reference", "ref")),
            Colonne("Désignation", "Description du bien",
                    "F3 à Hydra, 95 m²", requis=True,
                    synonymes=("designation", "libelle", "intitule")),
            Colonne("Type", "appartement, villa, local, terrain…", "appartement"),
            Colonne("Opération", "vente ou location", "location",
                    synonymes=("operation",)),
            Colonne("Surface", "Surface en m²", "95"),
            Colonne("Adresse", "Adresse du bien", "14 rue des Frères Aïssou"),
            Colonne("Commune", "Commune", "Hydra"),
            Colonne("Wilaya", "Wilaya", "16 Alger"),
            Colonne("Prix", "Prix de vente ou loyer mensuel", "45000"),
            Colonne("Propriétaire", "Nom du mandant (tiers existant)",
                    "BENALI Karim", synonymes=("proprietaire", "mandant")),
        ],
    },
    "salaries": {
        "libelle": "Salariés",
        "notice": [
            "Le salaire de base s'entend brut mensuel, en dinars.",
            "",
            "La date d'embauche sert au calcul de l'ancienneté.",
        ],
        "colonnes": [
            Colonne("Matricule", "Identifiant interne", "S001", requis=True),
            Colonne("Nom", "Nom de famille", "SAADI", requis=True),
            Colonne("Prénom", "Prénom", "Yacine", requis=True,
                    synonymes=("prenom",)),
            Colonne("Poste", "Fonction occupée", "Comptable"),
            Colonne("Date d'embauche", "Date d'entrée", "01/02/2024",
                    synonymes=("date embauche", "embauche")),
            Colonne("Salaire de base", "Brut mensuel", "60000",
                    synonymes=("salaire", "salaire base")),
            Colonne("N° sécurité sociale", "Numéro CNAS", "",
                    synonymes=("cnas", "securite sociale", "n° cnas")),
        ],
    },
}


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
    return {"modeles": [
        {"cle": cle, "libelle": m["libelle"],
         "colonnes": [{"nom": c.nom, "requis": c.requis, "aide": c.aide}
                      for c in m["colonnes"]]}
        for cle, m in MODELES.items()
    ]}


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

def _sans_accent(texte: str) -> str:
    decompose = unicodedata.normalize("NFD", str(texte or ""))
    return "".join(c for c in decompose if unicodedata.category(c) != "Mn").lower()


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
        candidats = [colonne.nom, *colonne.synonymes]
        for candidat in candidats:
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


# ---------------------------------------------------------------------------
# Analyse par type
# ---------------------------------------------------------------------------

def analyse_ecritures(societe_id, rangs, association, defaut_perimetre):
    """Regroupe les lignes par numéro d'écriture et contrôle chaque groupe."""
    groupes: dict[str, dict] = {}
    ordre: list[str] = []
    anomalies = []

    comptes_connus = {str(c["numero"]) for c in db.lignes(
        "SELECT numero FROM comptes WHERE societe_id = ?", (societe_id,))}
    journaux_connus = {str(j["code"]).upper() for j in db.lignes(
        "SELECT code FROM journaux WHERE societe_id = ?", (societe_id,))}

    for decalage, rang in enumerate(rangs):
        numero_ligne = decalage + 2          # +1 en-tête, +1 pour compter de 1
        if not any(str(c).strip() for c in rang):
            continue
        cle = _valeur(rang, association, "N° écriture")
        date = _valeur(rang, association, "Date")
        journal = _valeur(rang, association, "Journal").upper()
        libelle = _valeur(rang, association, "Libellé")
        compte = _valeur(rang, association, "Compte")
        debit = _valeur(rang, association, "Débit")
        credit = _valeur(rang, association, "Crédit")
        perimetre = _valeur(rang, association, "Périmètre")

        erreurs = []
        if not cle:
            cle = f"auto-{date}-{libelle}-{journal}"
        if not compte:
            erreurs.append("compte manquant")
        elif compte not in comptes_connus:
            erreurs.append(f"le compte {compte} n'existe pas dans le plan comptable")
        if journal and journal not in journaux_connus:
            erreurs.append(f"le journal {journal} n'existe pas")
        montant_debit = util.centimes(debit) if debit else 0
        montant_credit = util.centimes(credit) if credit else 0
        if montant_debit and montant_credit:
            erreurs.append("débit et crédit renseignés sur la même ligne")
        if not montant_debit and not montant_credit:
            erreurs.append("aucun montant")

        groupe = groupes.get(cle)
        if groupe is None:
            iso = _date(date)
            if not iso:
                erreurs.append(f"date « {date} » incompréhensible")
            if not journal:
                erreurs.append("journal manquant")
            if not libelle:
                erreurs.append("libellé manquant")
            groupe = groupes[cle] = {
                "cle": cle, "date": iso, "journal": journal, "libelle": libelle,
                "piece": _valeur(rang, association, "N° de pièce"),
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
            "nb_valides": len(prets), "nb_rejetes": len(ordre) - len(prets)}


MODES_REGLEMENT = {"espece", "cheque", "virement", "traite"}


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


def _perimetre(valeur: str, defaut: str) -> str:
    propre = _sans_accent(valeur)
    if not propre:
        return defaut
    if propre.startswith("non") or "hors" in propre:
        return "hors_declaration"
    return "declare"


def _tiers_id(societe_id: int, nom: str):
    if not nom:
        return None
    trouve = db.ligne(
        "SELECT id FROM tiers WHERE societe_id = ? AND "
        "(raison_sociale = ? COLLATE NOCASE OR code = ? COLLATE NOCASE)",
        (societe_id, nom, nom))
    return trouve["id"] if trouve else None


def analyse_simple(societe_id, rangs, association, modele, cle_modele):
    """Contrôle générique pour les tables sans regroupement de lignes."""
    prets, anomalies, apercu = [], [], []
    requis = [c for c in modele["colonnes"] if c.requis]
    for decalage, rang in enumerate(rangs):
        numero_ligne = decalage + 2
        if not any(str(c).strip() for c in rang):
            continue
        valeurs = {c.nom: _valeur(rang, association, c.nom)
                   for c in modele["colonnes"]}
        erreurs = [f"« {c.nom} » est obligatoire"
                   for c in requis if not valeurs[c.nom]]
        erreurs += _controles_specifiques(societe_id, cle_modele, valeurs)
        for message in erreurs:
            anomalies.append({"ligne": numero_ligne, "message": message})
        apercu.append({"ligne": numero_ligne, "valeurs": valeurs,
                       "erreurs": erreurs})
        if not erreurs:
            prets.append(valeurs)
    return {"prets": prets, "anomalies": anomalies, "apercu": apercu,
            "nb_valides": len(prets),
            "nb_rejetes": len(apercu) - len(prets)}


TYPES_TIERS = {"client", "fournisseur", "mandant", "locataire", "acquereur",
               "salarie", "autre"}


def _controles_specifiques(societe_id, cle_modele, valeurs) -> list[str]:
    erreurs = []
    if cle_modele == "tiers":
        type_tiers = _sans_accent(valeurs["Type"])
        if type_tiers and type_tiers not in TYPES_TIERS:
            erreurs.append(f"type « {valeurs['Type']} » inconnu "
                           f"({', '.join(sorted(TYPES_TIERS))})")
        if valeurs["Raison sociale"] and db.ligne(
                "SELECT id FROM tiers WHERE societe_id = ? AND "
                "raison_sociale = ? COLLATE NOCASE",
                (societe_id, valeurs["Raison sociale"])):
            erreurs.append(f"« {valeurs['Raison sociale']} » existe déjà")
    elif cle_modele == "comptes":
        numero = valeurs["Compte"]
        if numero and not numero.isdigit():
            erreurs.append(f"le numéro de compte « {numero} » "
                           "doit être composé de chiffres")
        if numero and db.ligne(
                "SELECT id FROM comptes WHERE societe_id = ? AND numero = ?",
                (societe_id, numero)):
            erreurs.append(f"le compte {numero} existe déjà")
    elif cle_modele == "biens":
        if valeurs["Référence"] and db.ligne(
                "SELECT id FROM biens WHERE societe_id = ? AND reference = ? "
                "COLLATE NOCASE", (societe_id, valeurs["Référence"])):
            erreurs.append(f"la référence {valeurs['Référence']} existe déjà")
    elif cle_modele == "salaries":
        if valeurs["Matricule"] and db.ligne(
                "SELECT id FROM salaries WHERE societe_id = ? AND matricule = ? "
                "COLLATE NOCASE", (societe_id, valeurs["Matricule"])):
            erreurs.append(f"le matricule {valeurs['Matricule']} existe déjà")
    return erreurs


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
    elif "sens" in modele:
        resultat = analyse_factures(societe_id, rangs, association, defaut,
                                    modele["sens"])
    else:
        resultat = analyse_simple(societe_id, rangs, association, modele,
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
        elif cle.startswith("factures_"):
            crees = _importe_factures(ctx, societe_id, prets)
        elif cle == "tiers":
            crees = _importe_tiers(societe_id, prets)
        elif cle == "comptes":
            crees = _importe_comptes(societe_id, prets)
        elif cle == "biens":
            crees = _importe_biens(societe_id, prets)
        else:
            crees = _importe_salaries(societe_id, prets)
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


def _importe_tiers(societe_id, rangs) -> int:
    for valeurs in rangs:
        db.insere("tiers", {
            "societe_id": societe_id,
            "code": db.numero_suivant(societe_id, "tiers"),
            "type": _sans_accent(valeurs["Type"]) or "client",
            "raison_sociale": valeurs["Raison sociale"],
            "nif": valeurs["NIF"] or None,
            "nis": valeurs["NIS"] or None,
            "rc": valeurs["RC"] or None,
            "article_imposition": valeurs["Article"] or None,
            "adresse": valeurs["Adresse"] or None,
            "commune": valeurs["Commune"] or None,
            "wilaya": valeurs["Wilaya"] or None,
            "telephone": valeurs["Téléphone"] or None,
            "email": valeurs["Courriel"] or None,
            "actif": 1,
            "cree_le": util.maintenant(),
        })
    return len(rangs)


def _importe_comptes(societe_id, rangs) -> int:
    for valeurs in rangs:
        numero = valeurs["Compte"]
        db.insere("comptes", {
            "societe_id": societe_id,
            "numero": numero,
            "intitule": valeurs["Intitulé"],
            "classe": int(numero[0]),
            "lettrable": 1 if _sans_accent(valeurs["Lettrable"]).startswith(("o", "y"))
                         else 0,
            "actif": 1,
        })
    return len(rangs)


def _importe_biens(societe_id, rangs) -> int:
    for valeurs in rangs:
        # Selon l'opération, le prix saisi est un prix de vente ou un loyer.
        location = _sans_accent(valeurs["Opération"]).startswith("loc")
        montant = util.centimes(valeurs["Prix"]) if valeurs["Prix"] else None
        db.insere("biens", {
            "societe_id": societe_id,
            "reference": valeurs["Référence"],
            "designation": valeurs["Désignation"],
            "type_bien": _sans_accent(valeurs["Type"]) or "appartement",
            "surface": util.centimes(valeurs["Surface"]) if valeurs["Surface"] else None,
            "adresse": valeurs["Adresse"] or None,
            "commune": valeurs["Commune"] or None,
            "wilaya": valeurs["Wilaya"] or None,
            "loyer_mensuel": (montant or 0) if location else 0,
            "prix_demande": 0 if location else (montant or 0),
            "proprietaire_id": _tiers_id(societe_id, valeurs["Propriétaire"]),
            "statut": "disponible",
            "cree_le": util.maintenant(),
        })
    return len(rangs)


def _importe_salaries(societe_id, rangs) -> int:
    for valeurs in rangs:
        db.insere("salaries", {
            "societe_id": societe_id,
            "matricule": valeurs["Matricule"],
            "nom": valeurs["Nom"],
            "prenom": valeurs["Prénom"],
            "poste": valeurs["Poste"] or None,
            "date_embauche": _date(valeurs["Date d'embauche"]),
            "salaire_base": util.centimes(valeurs["Salaire de base"])
                            if valeurs["Salaire de base"] else 0,
            "num_secu": valeurs["N° sécurité sociale"] or None,
            "actif": 1,
        })
    return len(rangs)
