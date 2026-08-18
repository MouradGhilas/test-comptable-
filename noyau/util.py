"""Utilitaires transverses : montants, dates, formats algériens.

Règle d'or du projet : **aucun montant n'est manipulé en flottant**.
Tout est stocké et calculé en centimes (entiers). Les conversions se font
uniquement aux frontières (saisie utilisateur / affichage).
"""

from __future__ import annotations

import datetime as _dt
import re
import unicodedata

# ---------------------------------------------------------------------------
# Montants
# ---------------------------------------------------------------------------

#: Les taux sont stockés en CENTIÈMES DE POUR-CENT : 19 % -> 1900, 1,5 % -> 150.
#: Cela donne deux décimales de précision sur le pourcentage, en arithmétique
#: entière. 100 % vaut donc 10 000.
BASE_TAUX = 10_000
TAUX_CENT_POUR_CENT = BASE_TAUX


def centimes(valeur) -> int:
    """Convertit une saisie utilisateur en centimes (entier).

    Accepte 1234.56, "1 234,56", "1234.56", "1.234,56 DA", None…
    """
    if valeur is None or valeur == "":
        return 0
    if isinstance(valeur, int):
        return valeur * 100
    if isinstance(valeur, float):
        return int(round(valeur * 100))
    texte = str(valeur).strip()
    texte = re.sub(r"[^\d,.\-]", "", texte)
    if not texte or texte in {"-", ".", ","}:
        return 0
    # Détermine le séparateur décimal : le dernier symbole rencontré, s'il
    # ne sépare pas un groupe de 3 chiffres (millier).
    dernier_point = texte.rfind(".")
    derniere_virgule = texte.rfind(",")
    sep = max(dernier_point, derniere_virgule)
    if sep == -1:
        partie_entiere, partie_dec = texte, ""
    else:
        decimales = texte[sep + 1:]
        if len(decimales) == 3 and texte.count(texte[sep]) >= 1 and len(texte) - sep - 1 == 3:
            # ex : "1.234" -> séparateur de milliers, pas de décimale
            partie_entiere, partie_dec = texte.replace(".", "").replace(",", ""), ""
        else:
            partie_entiere = texte[:sep]
            partie_dec = decimales
    partie_entiere = partie_entiere.replace(".", "").replace(",", "")
    negatif = partie_entiere.startswith("-")
    partie_entiere = partie_entiere.lstrip("-") or "0"
    partie_dec = (partie_dec + "00")[:2] if partie_dec else "00"
    try:
        total = int(partie_entiere) * 100 + int(partie_dec)
    except ValueError:
        return 0
    return -total if negatif else total


def en_dinars(cts: int) -> float:
    """Centimes -> dinars (pour affichage/JSON uniquement)."""
    return round((cts or 0) / 100.0, 2)


def formate_montant(cts: int, devise: str = "DA") -> str:
    """Format algérien : 1 234 567,89 DA (espace insécable fine en milliers)."""
    cts = int(cts or 0)
    signe = "-" if cts < 0 else ""
    cts = abs(cts)
    entier, dec = divmod(cts, 100)
    groupes = f"{entier:,}".replace(",", " ")
    suffixe = f" {devise}" if devise else ""
    return f"{signe}{groupes},{dec:02d}{suffixe}"


def applique_taux(base_cts: int, taux: int) -> int:
    """Applique un taux exprimé en millièmes de % à une base en centimes.

    Arrondi au centime le plus proche (arrondi commercial, demi vers le haut).
    """
    base_cts = int(base_cts or 0)
    taux = int(taux or 0)
    produit = base_cts * taux
    negatif = produit < 0
    produit = abs(produit)
    resultat = (produit + BASE_TAUX // 2) // BASE_TAUX
    return -resultat if negatif else resultat


def part_proportionnelle(total_cts: int, numerateur: int, denominateur: int) -> int:
    """Répartit `total_cts` proportionnellement, avec arrondi au centime."""
    if not denominateur:
        return 0
    produit = int(total_cts) * int(numerateur)
    negatif = produit < 0
    produit = abs(produit)
    res = (produit + abs(denominateur) // 2) // abs(denominateur)
    return -res if negatif else res


def repartir(total_cts: int, poids: list[int]) -> list[int]:
    """Répartit un total entre plusieurs postes sans perdre le moindre centime.

    Le reliquat d'arrondi est affecté au poids le plus élevé.
    """
    somme_poids = sum(poids)
    if somme_poids == 0:
        return [0] * len(poids)
    parts = [part_proportionnelle(total_cts, p, somme_poids) for p in poids]
    ecart = total_cts - sum(parts)
    if ecart and parts:
        i_max = max(range(len(poids)), key=lambda i: poids[i])
        parts[i_max] += ecart
    return parts


def ht_depuis_ttc(ttc_cts: int, taux_tva: int) -> tuple[int, int]:
    """Décompose un TTC en (HT, TVA) pour un taux donné."""
    ttc_cts = int(ttc_cts or 0)
    taux = int(taux_tva or 0)
    if taux == 0:
        return ttc_cts, 0
    ht = part_proportionnelle(ttc_cts, BASE_TAUX, BASE_TAUX + taux)
    return ht, ttc_cts - ht


def taux_pourcent(taux: int) -> float:
    """Millièmes de % -> pourcentage lisible (1900 -> 19.0)."""
    return round((taux or 0) / 100.0, 3)


def vers_taux(valeur) -> int:
    """Pourcentage saisi -> millièmes de % (19 ou "19,5" -> 1900 / 1950)."""
    if valeur is None or valeur == "":
        return 0
    if isinstance(valeur, int) and not isinstance(valeur, bool):
        return valeur * 100
    if isinstance(valeur, float):
        return int(round(valeur * 100))
    texte = str(valeur).replace("%", "").replace(",", ".").strip()
    try:
        return int(round(float(texte) * 100))
    except ValueError:
        return 0


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

def aujourdhui() -> str:
    return _dt.date.today().isoformat()


def maintenant() -> str:
    return _dt.datetime.now().replace(microsecond=0).isoformat(sep=" ")


def _date_reelle(iso: str, defaut: str | None) -> str | None:
    """Refuse les dates impossibles : le 32/13 n'existe pas plus qu'un 30/02."""
    try:
        _dt.date(int(iso[0:4]), int(iso[5:7]), int(iso[8:10]))
    except ValueError:
        return defaut
    return iso


def date_iso(valeur, defaut: str | None = None) -> str | None:
    """Normalise une date vers 'AAAA-MM-JJ'. Accepte jj/mm/aaaa."""
    if not valeur:
        return defaut
    texte = str(valeur).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", texte):
        return _date_reelle(texte, defaut)
    m = re.fullmatch(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", texte)
    if m:
        j, mo, a = m.groups()
        return _date_reelle(f"{a}-{int(mo):02d}-{int(j):02d}", defaut)
    if re.fullmatch(r"\d{4}-\d{2}", texte):
        return _date_reelle(texte + "-01", defaut)
    return defaut


def date_fr(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        a, m, j = iso[:10].split("-")
        return f"{j}/{m}/{a}"
    except ValueError:
        return iso


def periode_de(date: str) -> str:
    """'2026-03-17' -> '2026-03'."""
    return (date or "")[:7]


def mois_suivant(periode: str) -> str:
    a, m = int(periode[:4]), int(periode[5:7])
    if m == 12:
        return f"{a + 1}-01"
    return f"{a}-{m + 1:02d}"


def mois_precedent(periode: str) -> str:
    a, m = int(periode[:4]), int(periode[5:7])
    if m == 1:
        return f"{a - 1}-12"
    return f"{a}-{m - 1:02d}"


def dernier_jour(annee: int, mois: int) -> int:
    if mois == 12:
        suivant = _dt.date(annee + 1, 1, 1)
    else:
        suivant = _dt.date(annee, mois + 1, 1)
    return (suivant - _dt.timedelta(days=1)).day


def fin_de_mois(periode: str) -> str:
    a, m = int(periode[:4]), int(periode[5:7])
    return f"{a}-{m:02d}-{dernier_jour(a, m):02d}"


def ajoute_mois(date: str, nb_mois: int) -> str:
    d = _dt.date.fromisoformat(date[:10])
    total = d.month - 1 + nb_mois
    annee = d.year + total // 12
    mois = total % 12 + 1
    jour = min(d.day, dernier_jour(annee, mois))
    return _dt.date(annee, mois, jour).isoformat()


def jour_du_mois(periode: str, jour: int) -> str:
    a, m = int(periode[:4]), int(periode[5:7])
    return f"{a}-{m:02d}-{min(jour, dernier_jour(a, m)):02d}"


def jours_ecart(date_a: str, date_b: str) -> int:
    return (_dt.date.fromisoformat(date_b[:10]) - _dt.date.fromisoformat(date_a[:10])).days


MOIS_FR = [
    "", "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def libelle_periode(periode: str) -> str:
    try:
        a, m = int(periode[:4]), int(periode[5:7])
        return f"{MOIS_FR[m]} {a}"
    except (ValueError, IndexError):
        return periode


# ---------------------------------------------------------------------------
# Texte
# ---------------------------------------------------------------------------

def sans_accents(texte: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texte or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def code_depuis(texte: str, longueur: int = 12) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "", sans_accents(texte or "")).upper()
    return base[:longueur] or "X"


def nettoie(valeur) -> str | None:
    if valeur is None:
        return None
    texte = str(valeur).strip()
    return texte or None


# ---------------------------------------------------------------------------
# Montants en toutes lettres (obligatoire sur certains actes / factures)
# ---------------------------------------------------------------------------

_UNITES = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept",
           "huit", "neuf", "dix", "onze", "douze", "treize", "quatorze",
           "quinze", "seize"]
_DIZAINES = {20: "vingt", 30: "trente", 40: "quarante", 50: "cinquante",
             60: "soixante", 80: "quatre-vingt"}


def _sous_cent(n: int) -> str:
    if n < 17:
        return _UNITES[n]
    if n < 20:
        return "dix-" + _UNITES[n - 10]
    for base in (80, 60, 40, 30, 20):
        if n >= base:
            if base == 60 and n >= 70:
                reste = n - 60
                if reste == 11:
                    return "soixante-et-onze"
                return "soixante-" + _sous_cent(reste)
            if base == 80 and n >= 90:
                return "quatre-vingt-" + _sous_cent(n - 80)
            reste = n - base
            if reste == 0:
                return _DIZAINES[base] + ("s" if base == 80 else "")
            if reste == 1 and base not in (80,):
                return _DIZAINES[base] + "-et-un"
            return _DIZAINES[base] + "-" + _UNITES[reste]
    return _UNITES[n]


def _sous_mille(n: int) -> str:
    if n < 100:
        return _sous_cent(n)
    centaines, reste = divmod(n, 100)
    if centaines == 1:
        tete = "cent"
    else:
        tete = _UNITES[centaines] + " cent"
    if reste == 0:
        return tete + ("s" if centaines > 1 else "")
    return tete + " " + _sous_cent(reste)


def nombre_en_lettres(n: int) -> str:
    if n == 0:
        return "zéro"
    if n < 0:
        return "moins " + nombre_en_lettres(-n)
    paliers = [(1_000_000_000, "milliard"), (1_000_000, "million"), (1_000, "mille")]
    morceaux = []
    reste = n
    for valeur, nom in paliers:
        quotient, reste = divmod(reste, valeur)
        if quotient:
            if nom == "mille":
                prefixe = "" if quotient == 1 else _sous_mille(quotient) + " "
                morceaux.append(prefixe + "mille")
            else:
                pluriel = "s" if quotient > 1 else ""
                morceaux.append(_sous_mille(quotient) + " " + nom + pluriel)
    if reste:
        morceaux.append(_sous_mille(reste))
    return " ".join(morceaux)


def montant_en_lettres(cts: int, devise: str = "dinars algériens") -> str:
    """Ex : 125045 -> « mille deux cent cinquante dinars algériens et quarante-cinq centimes »."""
    cts = int(cts or 0)
    signe = "moins " if cts < 0 else ""
    cts = abs(cts)
    entier, dec = divmod(cts, 100)
    texte = f"{signe}{nombre_en_lettres(entier)} {devise}"
    if dec:
        texte += f" et {nombre_en_lettres(dec)} centimes"
    return texte[0].upper() + texte[1:]


# ---------------------------------------------------------------------------
# Contrôles de cohérence propres au contexte algérien
# ---------------------------------------------------------------------------

def valide_nif(nif: str | None) -> tuple[bool, str]:
    """Le NIF algérien comporte 15 chiffres (personnes morales) ou 20 pour
    certaines déclinaisons. On contrôle la forme, pas la clé."""
    if not nif:
        return True, ""
    net = re.sub(r"\s", "", nif)
    if not net.isdigit():
        return False, "Le NIF ne doit contenir que des chiffres."
    if len(net) not in (15, 20):
        return False, f"Le NIF comporte {len(net)} chiffres (attendu : 15 ou 20)."
    return True, ""


def valide_rc(rc: str | None) -> tuple[bool, str]:
    """N° de registre de commerce, forme usuelle : 16/00-1234567 B 09."""
    if not rc:
        return True, ""
    if len(re.sub(r"\s", "", rc)) < 8:
        return False, "Numéro de registre de commerce trop court."
    return True, ""


WILAYAS = [
    "01 Adrar", "02 Chlef", "03 Laghouat", "04 Oum El Bouaghi", "05 Batna",
    "06 Béjaïa", "07 Biskra", "08 Béchar", "09 Blida", "10 Bouira",
    "11 Tamanrasset", "12 Tébessa", "13 Tlemcen", "14 Tiaret",
    "15 Tizi Ouzou", "16 Alger", "17 Djelfa", "18 Jijel", "19 Sétif",
    "20 Saïda", "21 Skikda", "22 Sidi Bel Abbès", "23 Annaba",
    "24 Guelma", "25 Constantine", "26 Médéa", "27 Mostaganem",
    "28 M'Sila", "29 Mascara", "30 Ouargla", "31 Oran", "32 El Bayadh",
    "33 Illizi", "34 Bordj Bou Arreridj", "35 Boumerdès", "36 El Tarf",
    "37 Tindouf", "38 Tissemsilt", "39 El Oued", "40 Khenchela",
    "41 Souk Ahras", "42 Tipaza", "43 Mila", "44 Aïn Defla", "45 Naâma",
    "46 Aïn Témouchent", "47 Ghardaïa", "48 Relizane", "49 Timimoun",
    "50 Bordj Badji Mokhtar", "51 Ouled Djellal", "52 Béni Abbès",
    "53 In Salah", "54 In Guezzam", "55 Touggourt", "56 Djanet",
    "57 El M'Ghair", "58 El Meniaa",
]


def options_detachement() -> dict:
    """Arguments `subprocess.Popen` pour un processus qui doit survivre au sien.

    `start_new_session` est **ignoré sous Windows** : la signature interne de
    `subprocess` l'y nomme littéralement `unused_start_new_session`. Un
    processus lancé sans plus de précaution reste donc rattaché à la console
    qui a démarré l'application — un Ctrl+C dans cette fenêtre tue alors la
    mise à jour en plein travail, et fermer la fenêtre suffit à l'interrompre.
    Sous Windows il faut le détacher explicitement.
    """
    import os
    import subprocess
    if os.name != "nt":
        return {"start_new_session": True}
    detache = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
    nouveau_groupe = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    return {"creationflags": detache | nouveau_groupe, "close_fds": True}
