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
    CLIENT.append(poste("/api/tiers", {
        "societe_id": sid, "type": "client",
        "raison_sociale": "RAMDANI ELMEHDI"})["id"])
    # Le sous-compte de caisse qu'il crée lui-même, à sept chiffres.
    poste("/api/comptes", {"societe_id": sid, "numero": "5300005",
                           "intitule": "Caisse annexe", "nature": "debit"})
    poste("/api/tresorerie", {"societe_id": sid, "code": "CA2",
                              "libelle": "Caisse annexe", "type": "caisse",
                              "compte": "5300005"})
    SOCIETE.append(sid)
    exercice = poste(f"/api/exercices?societe={sid}")["exercices"][0]
    DATE_ESSAI.append(exercice["date_debut"][:4] + "-05-10")
    return sid, 0


#: Le dossier, le client et une date de l'exercice courant, poses par
#: prepare_dossier() : les sections suivantes s'en servent.
SOCIETE: list[int] = []
CLIENT: list[int] = []
DATE_ESSAI: list[str] = []


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

    # « Pas encore réglée » est le choix par défaut : la part non déclarée
    # naît due, et c'est justement ce qu'il faut pouvoir suivre.
    v("la part non déclarée peut rester à recevoir",
      page.input_value("#f-hors-tresorerie") == "",
      page.input_value("#f-hors-tresorerie"))
    page.click("text=Enregistrer et valider")
    page.wait_for_timeout(2500)
    v("la facture est enregistrée et comptabilisée", "/factures/" in page.url,
      page.url)
    contenu = page.content()
    v("les trois chiffres sont sur la fiche",
      "Prix réel" in contenu and "Non déclaré" in contenu)
    v("… et les deux écritures y figurent, chacune avec son périmètre",
      contenu.count("Voir le détail") >= 2)
    sans_espaces = "".join(c if not c.isspace() else " " for c in contenu)
    v("… la fiche dit ce qui reste dû sur la part non déclarée",
      "reste 77 770,00" in sans_espaces,
      [m for m in sans_espaces.split("<") if "reste" in m][:2])

    # ======================================================================
    titre("2. Le client apporte un chèque et des espèces")
    # ======================================================================
    page.click("text=Encaisser")
    page.wait_for_selector("#r-lignes", timeout=15000)
    v("l'encaissement s'ouvre à plusieurs lignes", page.is_visible("#r-ajout"))
    # Une vente à deux parts s'ouvre sur ses deux restes dus : une ligne pour
    # chacune, déjà servie. C'est le cas ordinaire, pas une exception.
    v("… une ligne par part, déjà servies",
      page.eval_on_selector_all("#r-lignes tr", "l => l.length") == 2)
    v("la colonne « Part » existe sur une vente mixte",
      page.query_selector("#r-lignes .r-part") is not None)
    v("… et la seconde ligne vise bien le non déclaré",
      page.input_value("#r-lignes tr:nth-child(2) .r-part") == "hors_declaration",
      page.input_value("#r-lignes tr:nth-child(2) .r-part"))

    comptes = page.eval_on_selector_all(
        "#r-lignes .r-tresorerie",
        "l => Array.from(l[1].options).map(o => o.value).filter(Boolean)")
    page.select_option("#r-lignes tr:nth-child(1) .r-mode", "cheque")
    page.select_option("#r-lignes tr:nth-child(1) .r-tresorerie", comptes[0])
    page.fill("#r-lignes tr:nth-child(1) .r-reference", "CH-114520")
    page.select_option("#r-lignes tr:nth-child(2) .r-mode", "espece")
    page.select_option("#r-lignes tr:nth-child(2) .r-tresorerie", comptes[-1])
    page.dispatch_event("#r-lignes tr:nth-child(2) .r-montant", "input")
    page.wait_for_timeout(300)
    reste = "".join(c for c in page.inner_text("#r-apres") if not c.isspace())
    v("le reste dû tombe à zéro sous les yeux", reste == "0,00", reste)
    page.click("text=Enregistrer")
    page.wait_for_timeout(2000)
    v("la facture est soldée, les deux parts comprises",
      "payée" in page.content().lower() or "payee" in page.content().lower(),
      page.content()[:120])

    # ======================================================================
    titre("2 bis. La situation du client dit s'il a payé le black")
    # ======================================================================
    page.goto(BASE + "/#/tiers", wait_until="networkidle")
    page.wait_for_timeout(900)
    page.click("text=RAMDANI ELMEHDI")
    page.wait_for_timeout(1200)
    contenu = page.content()
    v("la fiche du client porte une situation", "Situation" in contenu)
    v("… avec la colonne « Non déclaré »", "Non déclaré" in contenu)
    v("… et le total réel", "Total réel" in contenu)

    # ======================================================================
    titre("3. Une liste vide dit ce qui manque")
    # ======================================================================
    # « Quand il allait dans contrat VSP pour mettre le lot vendu, il ne
    #   trouvait pas de lots : la barre glissante ne proposait rien, juste un
    #   rectangle gris. » Deux causes, l'une et l'autre muettes : aucun lot
    #   dans le dossier, ou des lots qui existent mais que l'ecran filtrait
    #   plus severement que le serveur.
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    page.goto(BASE + "/#/promotion/contrats", wait_until="networkidle")
    page.wait_for_timeout(900)
    page.click("text=+ Contrat VSP")
    page.wait_for_selector("[name=lot_id]", timeout=15000)
    v("sans aucun lot, la liste dit pourquoi",
      "Aucun lot dans ce dossier" in page.content(),
      page.inner_text("[name=lot_id] ~ .manquant") if
      page.query_selector("[name=lot_id] ~ .manquant") else "(rien)")
    v("… et ou creer ce qui manque", "Programmes" in page.content())
    # Le dossier d'essai a un client mais pas de notaire : la liste des
    # notaires est donc celle qui doit parler ici.
    v("le notaire absent le dit aussi, sans bloquer",
      "Aucun notaire enregistré" in page.content())
    v("… et l'acquereur, lui, est bien propose",
      page.eval_on_selector("[name=acquereur_id]", "el => el.options.length") > 1)
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # Un lot repris avec le statut « vendu » — le cas d'un dossier en cours —
    # doit rester saisissable : le serveur l'accepte, l'ecran le cachait.
    programme = poste("/api/programmes", {
        "societe_id": SOCIETE[0], "code": "PRG1",
        "intitule": "Residence El Feth", "wilaya": "16 Alger"})
    poste("/api/lots", {"societe_id": SOCIETE[0],
                        "programme_id": programme["id"], "numero": "A01",
                        "type_lot": "logement", "typologie": "F3",
                        "prix_vente": "5000000", "statut": "vendu"})
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(900)
    page.click("text=+ Contrat VSP")
    page.wait_for_selector("[name=lot_id]", timeout=15000)
    libelles = page.eval_on_selector(
        "[name=lot_id]",
        "el => Array.from(el.options).map(o => o.textContent).filter(Boolean)")
    v("un lot deja marque « vendu » reste proposable",
      any("A01" in l for l in libelles), libelles)
    v("… et son etat est dit dans la liste",
      any("vendu" in l for l in libelles), libelles)

    # ======================================================================
    titre("3 bis. Cocher des factures et les comptabiliser d'un coup")
    # ======================================================================
    # « Une fois importe tu dois les valider une par une, c'est chiant. »
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    for numero in ("B-001", "B-002", "B-003"):
        poste("/api/factures", {
            "societe_id": SOCIETE[0], "sens": "vente", "numero": numero,
            "tiers_id": CLIENT[0], "date": DATE_ESSAI[0],
            "lignes": [{"designation": "Vente", "quantite": 1,
                        "prix_unitaire": "100000", "taux_tva": 19,
                        "compte": "7011"}]})
    page.goto(BASE + "/#/factures", wait_until="networkidle")
    page.wait_for_timeout(1200)
    v("la barre d'actions est cachee sans selection",
      page.is_hidden("#f-actions"))
    page.check("#f-tout")
    page.wait_for_timeout(300)
    v("« tout selectionner » coche toutes les lignes",
      page.eval_on_selector_all(".f-choix", "l => l.every(c => c.checked)"))
    v("… et la barre d'actions apparait", page.is_visible("#f-actions"))
    v("… en disant combien sont a comptabiliser",
      "brouillon" in page.inner_text("#f-compte"), page.inner_text("#f-compte"))
    page.click("#f-valider")
    page.wait_for_timeout(2500)
    contenu = page.content()
    v("les brouillons sont comptabilises d'un coup",
      "B-001" in contenu and contenu.count("brouillon") == 0,
      [m for m in contenu.split("<") if "brouillon" in m][:2])
    v("la colonne « Reste » est la", "Reste" in contenu)

    # ======================================================================
    titre("3 bis 2. Supprimer une facture depuis sa fiche")
    # ======================================================================
    # « Il appuie sur supprimer mais elle ne se supprime pas vraiment. »
    # On verifie ici que la ligne quitte reellement le tableau — la
    # notification, elle, porte le numero et peut faire illusion.
    cible = poste("/api/factures", {
        "societe_id": SOCIETE[0], "sens": "vente", "numero": "VE — A-SUPPRIMER",
        "tiers_id": CLIENT[0], "date": DATE_ESSAI[0], "valider": True,
        "lignes": [{"designation": "A supprimer", "quantite": 1,
                    "prix_unitaire": "900000", "taux_tva": 19,
                    "compte": "7011"}]})["id"]
    page.goto(BASE + f"/#/factures/{cible}", wait_until="networkidle")
    page.wait_for_timeout(1200)
    page.click("#actions-page button.danger")
    page.wait_for_timeout(600)
    v("la fenêtre de suppression s'ouvre", not page.is_hidden("#fenetre"))
    page.click("#corps-modale .pied-modale button.danger")
    page.wait_for_timeout(2500)
    numeros = page.eval_on_selector_all(
        "table tbody tr td:nth-child(2)", "l => l.map(c => c.textContent.trim())")
    v("la facture a quitté le tableau",
      not any("A-SUPPRIMER" in n for n in numeros), numeros)
    v("… et les autres sont toujours là", len(numeros) >= 1, numeros)

    # ======================================================================
    titre("3 ter. La documentation, dans la barre de gauche")
    # ======================================================================
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    v("l'entrée « Documentation » est au menu",
      page.query_selector("#menu a[href='#/documentation']") is not None)
    page.click("#menu a[href='#/documentation']")
    page.wait_for_selector("#doc-liste", timeout=15000)
    contenu = page.content()
    v("les fiches sont là",
      contenu.count("fiche-doc") >= 20, contenu.count("fiche-doc"))
    v("… rangées par domaine", "Reprendre un dossier déjà tenu" in contenu)
    v("… et chacune dit ce qui coince souvent",
      "Ce qui coince souvent" in contenu)
    v("… sa facon de faire y a sa fiche",
      "tel qu'il sort d'Excel" in contenu.replace("&#39;", "'")
      .replace("\u2019", "'"), None)
    page.fill("#doc-q", "montant ht")
    page.wait_for_timeout(400)
    ouvertes = page.eval_on_selector_all(
        ".fiche-doc", "l => l.filter(f => !f.hidden).length")
    v("la recherche ne garde que ce qui correspond",
      0 < ouvertes < 8, ouvertes)
    v("… et trouve bien le piège des montants d'import",
      "Importer vos factures" in page.eval_on_selector_all(
          ".fiche-doc:not([hidden]) summary", "l => l.map(s => s.textContent).join(' ')"))
    page.fill("#doc-q", "")
    page.wait_for_timeout(300)
    v("… vider la recherche rend tout", page.is_hidden("#doc-vide"))

    # ======================================================================
    titre("3 quater. Deposer un fichier sans dire ce qu'il contient")
    # ======================================================================
    # « Tu prends ce qu'on te donne. » Le type de donnees est une question
    # pour qui connait le logiciel ; lui a un fichier, et il le depose.
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    page.goto(BASE + "/#/parametres/import", wait_until="networkidle")
    page.wait_for_selector("#import-modele", timeout=15000)
    v("« Détection automatique » est proposée d'office",
      page.eval_on_selector("#import-modele", "s => s.value") == "auto",
      page.eval_on_selector("#import-modele", "s => s.value"))

    journal = Path(tempfile.gettempdir()) / "journal-depose.csv"
    journal.write_text(
        "N° écriture;Date;Journal;Libellé;Compte;Tiers;Débit;Crédit;"
        "Raison sociale\n"
        "1;2026-03-04;BQ ;Versement;512000;T00001\u00a0;500000;0;BENALI Karim\n"
        "1;2026-03-04;BQ ;Versement;455001;T00001;0;500000;BENALI Karim\n"
        "1;2026-03-05;OD;Achat;606001;;120000;0;\n"
        "1;2026-03-05;OD;Achat;401001;T00002;0;120000;SARL DJAZAIR\n",
        encoding="utf-8")
    page.set_input_files("#import-fichier", str(journal))
    page.click("#bouton-controler")
    page.wait_for_selector("#import-resultat .message", timeout=20000)
    apercu = page.content()
    v("il dit ce qu'il a trouvé dans le fichier",
      "Votre fichier contient" in apercu, apercu[apercu.find("import-resultat"):][:300])
    v("… les écritures", "Écritures comptables" in apercu)
    v("… et les clients qui étaient dedans", "Tiers (" in apercu)
    page.click("#bouton-importer")
    page.wait_for_selector("text=Import terminé", timeout=30000)
    v("l'import passe en un seul dépôt", "Import terminé" in page.content())

    ecrit = page.evaluate(
        "fetch('/api/ecritures?societe=' + App.etat.societe.id)"
        ".then(r => r.json()).then(d => d.ecritures"
        ".filter(e => e.libelle === 'Versement' || e.libelle === 'Achat')"
        ".length)")
    v("… et les deux écritures sont au journal", ecrit == 2, ecrit)
    noms = page.evaluate(
        "fetch('/api/tiers?societe=' + App.etat.societe.id)"
        ".then(r => r.json()).then(d => d.tiers.map(t => t.raison_sociale))")
    v("… les clients portent leur nom, pas leur code",
      "BENALI Karim" in noms and "SARL DJAZAIR" in noms, noms)

    # ======================================================================
    titre("3 quinquies. Ressortir ses tiers")
    # ======================================================================
    page.goto(BASE + "/#/tiers", wait_until="networkidle")
    page.wait_for_timeout(900)
    v("le bouton « Exporter la liste » est sur l'ecran des tiers",
      page.query_selector("[data-export='tiers']") is not None,
      page.content()[:400])
    with page.expect_download(timeout=30000) as attente:
        page.click("[data-export='tiers']")
    fichier = attente.value
    depose = Path(tempfile.gettempdir()) / "tiers-exportes.xlsx"
    fichier.save_as(str(depose))
    v("… il produit bien un classeur", depose.stat().st_size > 2000,
      depose.stat().st_size)

    # Et ce classeur se redepose : c'est tout l'interet.
    page.goto(BASE + "/#/parametres/import", wait_until="networkidle")
    page.wait_for_selector("#import-modele", timeout=15000)
    v("« Ce que j'ai déjà » est proposé à côté du modèle vierge",
      page.query_selector("#zone-page [data-export='tiers']") is not None
      or "Ce que j'ai déjà" in page.content())
    page.set_input_files("#import-fichier", str(depose))
    page.click("#bouton-controler")
    page.wait_for_selector("#import-resultat .message", timeout=20000)
    lu = page.content()
    v("… et il est reconnu tout seul comme une liste de tiers",
      "Votre fichier contient" in lu and "Tiers" in lu,
      lu[lu.find("import-resultat"):][:300])
    v("… sans mettre une seule ligne de côté",
      "mise(s) de côté" not in lu.split("import-resultat")[1][:600],
      lu.split("import-resultat")[1][:300])

    # ======================================================================
    titre("4. Corriger un exercice mal saisi")
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
                titre("5. Rien ne casse en silence")
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
