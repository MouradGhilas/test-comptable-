#!/usr/bin/env python3
"""Les écrans dans un vrai navigateur.

Un formulaire peut être syntaxiquement juste et ne rien afficher. C'est
arrivé : une carte sans titre perdait ses boutons d'action, et trois écrans
ont laissé leur action principale sans que rien ne le signale — ni Python,
ni la lecture du code. Seul un navigateur le voit.

Playwright n'est pas une dépendance de l'application : elle n'en a aucune.
Absent, ce fichier le dit et s'arrête sans échouer.

    python3 outils/test_ecrans.py
"""

from __future__ import annotations

import http.cookiejar
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
PORT = 8913
BASE = f"http://127.0.0.1:{PORT}"

#: Chromium livré avec l'image, s'il y est ; sinon celui de Playwright.
CHROMIUM = next(iter(sorted(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux/chrome"))
                     ), None) if Path("/opt/pw-browsers").exists() else None

RESULTATS: list[tuple[str, bool, str]] = []
POT = http.cookiejar.CookieJar()
OUVRE = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(POT))


def v(nom: str, condition, detail="") -> None:
    ok = bool(condition)
    RESULTATS.append((nom, ok, str(detail)))
    print(("  \033[32m✓\033[0m " if ok else "  \033[31m✗\033[0m ") + nom
          + ("" if ok else f"\n      {detail}"))


def titre(texte: str) -> None:
    print(f"\n\033[1m{texte}\033[0m")


def poste(chemin: str, corps=None):
    donnees = json.dumps(corps).encode() if corps is not None else None
    requete = urllib.request.Request(
        BASE + chemin, data=donnees,
        headers={"Content-Type": "application/json"})
    return json.loads(OUVRE.open(requete, timeout=30).read().decode())


def prepare_dossier() -> tuple[int, int]:
    """Un dossier minimal : un client, un compte annexe, une caisse à lui."""
    poste("/api/installation", {
        "identifiant": "demo", "mot_de_passe": "motdepasse123",
        "nom_complet": "Comptable", "raison_sociale": "SARL ECRANS",
        "nif": "000116001234567", "commune": "Alger", "wilaya": "16 Alger"})
    poste("/api/connexion", {"identifiant": "demo",
                             "mot_de_passe": "motdepasse123"})
    sid = poste("/api/societes")["societes"][0]["id"]
    poste("/api/tiers", {"societe_id": sid, "type": "client",
                         "raison_sociale": "RAMDANI ELMEHDI"})
    # Le sous-compte de caisse qu'il crée lui-même, à sept chiffres.
    poste("/api/comptes", {"societe_id": sid, "numero": "5300005",
                           "intitule": "Caisse annexe", "nature": "debit"})
    poste("/api/tresorerie", {"societe_id": sid, "code": "CA2",
                              "libelle": "Caisse annexe", "type": "caisse",
                              "compte": "5300005"})
    return sid, 0


def parcours(page) -> None:
    page.goto(BASE, wait_until="networkidle")
    page.fill("input[name=identifiant]", "demo")
    page.fill("input[name=mot_de_passe]", "motdepasse123")
    page.click("button[type=submit], button.primaire")
    page.wait_for_selector("#application:not([hidden])", timeout=20000)

    # ======================================================================
    titre("1. Une vente qui porte ses deux parts")
    # ======================================================================
    page.goto(BASE + "/#/factures", wait_until="networkidle")
    page.wait_for_timeout(700)
    page.click("text=+ Facture")
    page.wait_for_selector("#f-perimetre", timeout=15000)
    v("l'écran de facture s'ouvre", page.is_visible("#f-perimetre"))
    v("le bloc « part non déclarée » est replié par défaut",
      page.is_hidden("#f-bloc-hors"))
    v("le troisième choix de périmètre existe",
      "totalite" in page.inner_html("#f-perimetre"))

    page.select_option("#f-perimetre", "totalite")
    page.wait_for_timeout(300)
    v("… et il ouvre le bloc", page.is_visible("#f-bloc-hors"))
    v("la caisse annexe y est proposée",
      "Caisse annexe" in page.inner_html("#f-hors-tresorerie"))

    page.fill(".d-designation", "Logement F3")
    page.fill(".d-pu", "100000")
    page.select_option(".d-compte", "7011")
    page.wait_for_timeout(300)
    v("le compte de la part non déclarée suit la ligne de facture",
      page.input_value("#f-hors-compte") == "7011",
      page.input_value("#f-hors-compte"))

    page.fill("#f-hors-montant", "77770")
    page.dispatch_event("#f-hors-montant", "input")
    page.wait_for_timeout(300)
    lu = page.inner_text("#f-recap-total").replace(" ", " ").replace(" ", " ")
    v("le prix réellement convenu se calcule à l'écran", lu == "196 770,00", lu)

    page.select_option("#f-mode", "mixte")
    page.wait_for_timeout(200)
    v("« dont espèces » n'apparaît qu'en paiement mixte",
      page.is_visible("#f-bloc-espece"))
    page.select_option("#f-mode", "")

    tresoreries = page.eval_on_selector(
        "#f-hors-tresorerie",
        "el => Array.from(el.options).map(o => o.value).filter(Boolean)")
    page.select_option("#f-hors-tresorerie", tresoreries[-1])
    page.click("text=Enregistrer et valider")
    page.wait_for_timeout(2500)
    v("la facture est enregistrée et comptabilisée", "/factures/" in page.url,
      page.url)
    contenu = page.content()
    v("les trois chiffres sont sur la fiche",
      "Prix réel" in contenu and "Non déclaré" in contenu)
    v("… et les deux écritures y figurent, chacune avec son périmètre",
      contenu.count("Voir le détail") >= 2)

    # ======================================================================
    titre("2. Le client apporte un chèque et des espèces")
    # ======================================================================
    page.click("text=Encaisser")
    page.wait_for_selector("#r-lignes", timeout=15000)
    v("l'encaissement s'ouvre à plusieurs lignes", page.is_visible("#r-ajout"))
    page.click("#r-ajout")
    page.wait_for_timeout(200)
    v("une seconde ligne s'ajoute",
      page.eval_on_selector_all("#r-lignes tr", "l => l.length") == 2)

    comptes = page.eval_on_selector_all(
        "#r-lignes .r-tresorerie",
        "l => Array.from(l[1].options).map(o => o.value).filter(Boolean)")
    page.select_option("#r-lignes tr:nth-child(1) .r-mode", "cheque")
    page.select_option("#r-lignes tr:nth-child(1) .r-tresorerie", comptes[0])
    page.fill("#r-lignes tr:nth-child(1) .r-reference", "CH-114520")
    page.fill("#r-lignes tr:nth-child(1) .r-montant", "80000")
    page.select_option("#r-lignes tr:nth-child(2) .r-mode", "espece")
    page.select_option("#r-lignes tr:nth-child(2) .r-tresorerie", comptes[-1])
    page.fill("#r-lignes tr:nth-child(2) .r-montant", "39000")
    page.dispatch_event("#r-lignes tr:nth-child(2) .r-montant", "input")
    page.wait_for_timeout(300)
    reste = page.inner_text("#r-apres").replace(" ", " ")
    v("le reste dû tombe à zéro sous les yeux", reste == "0,00", reste)
    page.click("text=Enregistrer")
    page.wait_for_timeout(2000)
    v("la facture est soldée par les deux moyens",
      "Payee" in page.content() or "payée" in page.content().lower(),
      page.content()[:120])

    # ======================================================================
    titre("3. Corriger un exercice mal saisi")
    # ======================================================================
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    page.goto(BASE + "/#/parametres/exercices", wait_until="networkidle")
    page.wait_for_timeout(900)
    contenu = page.content()
    v("le bouton Corriger est là", "Corriger" in contenu)
    v("le bouton Supprimer est là", "Supprimer" in contenu)
    page.click("text=Corriger")
    page.wait_for_timeout(600)
    v("la fenêtre de correction s'ouvre",
      "corrigeable" in page.content().lower(), page.content()[:200])


def principal() -> int:
    print("\n\033[1m═══ TEST ÉCRANS — CABINET IMMO ═══\033[0m")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("\n  Playwright n'est pas installé sur ce poste : essai ignoré.")
        print("  L'application, elle, n'a aucune dépendance.")
        print("  Pour l'installer : pip install playwright && playwright install chromium\n")
        return 0

    dossier = Path(tempfile.mkdtemp(prefix="essai_ecrans_"))
    proc = subprocess.Popen(
        [sys.executable, "app.py", "--donnees", str(dossier),
         "--port", str(PORT), "--sans-navigateur"],
        cwd=RACINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        try:
            urllib.request.urlopen(f"{BASE}/api/etat", timeout=2)
            break
        except Exception:                                      # noqa: BLE001
            time.sleep(0.5)
    else:
        proc.terminate()
        print(f"  L'application n'a pas démarré sur le port {PORT}.")
        return 1

    erreurs: list[str] = []
    try:
        prepare_dossier()
        lancement = {"executable_path": str(CHROMIUM)} if CHROMIUM else {}
        with sync_playwright() as pw:
            navigateur = pw.chromium.launch(**lancement)
            page = navigateur.new_page()
            page.on("pageerror", lambda e: erreurs.append(str(e)))
            page.on("console",
                    lambda m: erreurs.append(m.text) if m.type == "error" else None)
            try:
                parcours(page)
            finally:
                titre("4. Rien ne casse en silence")
                vraies = [e for e in erreurs if "favicon" not in e.lower()]
                v("aucune erreur JavaScript sur tout le parcours",
                  not vraies, vraies[:3])
                navigateur.close()
    finally:
        proc.terminate()

    echecs = [nom for nom, ok, _ in RESULTATS if not ok]
    print("\n" + "═" * 72)
    print(f"\033[1mRÉSULTAT : {len(RESULTATS) - len(echecs)} réussite(s), "
          f"{len(echecs)} échec(s)\033[0m")
    print("═" * 72)
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(principal())
