#!/usr/bin/env python3
"""Test du serveur HTTP : installation, session, API et interface web.

Démarre l'application sur un port libre, effectue un parcours complet
d'utilisateur, puis vérifie que les fichiers de l'interface sont bien servis.

    python3 outils/test_http.py
"""

from __future__ import annotations

import http.cookiejar
import json
import shutil
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

DOSSIER = Path(tempfile.mkdtemp(prefix="cabinet_http_"))

import noyau.config as module_config                                    # noqa: E402
module_config.config = module_config.Configuration({"dossier_donnees": str(DOSSIER)})

from noyau import base as db                                            # noqa: E402
from noyau import serveur                                               # noqa: E402

db.initialise()
import modules                                                          # noqa: F401,E402

SUCCES, ECHECS = [], []
BASE = None
_cookies = http.cookiejar.CookieJar()
_ouvreur = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_cookies))


def verifie(libelle, condition, detail=""):
    (SUCCES if condition else ECHECS).append(libelle)
    print(f"  {'✓' if condition else '✗'} {libelle}" + (f"   {detail}" if not condition and detail else ""))


def appel(chemin, corps=None, methode=None, brut=False):
    url = BASE + chemin
    donnees = json.dumps(corps).encode() if corps is not None else None
    requete = urllib.request.Request(url, data=donnees, method=methode or ("POST" if corps is not None else "GET"))
    if donnees:
        requete.add_header("Content-Type", "application/json")
    try:
        with _ouvreur.open(requete, timeout=15) as reponse:
            contenu = reponse.read()
            return (contenu if brut else json.loads(contenu.decode())), reponse.status
    except urllib.error.HTTPError as err:
        contenu = err.read()
        try:
            return json.loads(contenu.decode()), err.code
        except ValueError:
            return {"erreur": contenu[:200].decode(errors="replace")}, err.code


def executer():
    print("\n\033[1m1. État initial et sécurité\033[0m")
    etat, code = appel("/api/etat")
    verifie("L'API d'état répond", code == 200)
    verifie("L'application se déclare non installée", etat["installe"] is False)

    refus, code = appel("/api/tiers?societe=1")
    verifie("Les données sont protégées avant connexion", code == 401, str(code))

    print("\n\033[1m2. Installation\033[0m")
    reponse, code = appel("/api/installation", {
        "identifiant": "comptable", "mot_de_passe": "motdepasse", "nom_complet": "Le comptable",
        "raison_sociale": "SARL TEST IMMO", "activite": "mixte", "wilaya": "16 Alger",
        "nif": "000116001234567", "annee_exercice": 2026,
    })
    verifie("Installation réussie", code == 200 and reponse.get("ok"), json.dumps(reponse)[:180])
    societe_id = reponse.get("societe_id")
    verifie("Session ouverte automatiquement (cookie)",
            any(c.name == "session_cabinet" for c in _cookies))

    doublon, code = appel("/api/installation", {"identifiant": "x", "mot_de_passe": "yyyyyy",
                                                "raison_sociale": "Z"})
    verifie("Réinstallation refusée", code == 409, str(code))

    print("\n\033[1m3. Session\033[0m")
    etat, _ = appel("/api/etat")
    verifie("Utilisateur connecté", etat.get("connecte") is True)
    verifie("Dossier disponible", len(etat.get("societes", [])) == 1)

    appel("/api/deconnexion", {})
    etat, _ = appel("/api/etat")
    verifie("Déconnexion effective", etat.get("connecte") is False)

    mauvais, code = appel("/api/connexion", {"identifiant": "comptable", "mot_de_passe": "faux"})
    verifie("Mot de passe erroné refusé", code == 401)

    bon, code = appel("/api/connexion", {"identifiant": "comptable", "mot_de_passe": "motdepasse"})
    verifie("Reconnexion réussie", code == 200 and bon.get("ok"))

    print("\n\033[1m4. Parcours métier via l'API\033[0m")
    exercices, _ = appel(f"/api/exercices?societe={societe_id}")
    exercice_id = exercices["exercices"][0]["id"]
    verifie("Exercice créé à l'installation", exercices["exercices"][0]["libelle"] == "2026")

    comptes, _ = appel(f"/api/comptes?societe={societe_id}&q=411")
    verifie("Plan comptable SCF interrogeable",
            any(c["numero"] == "411" for c in comptes["comptes"]))

    client, code = appel("/api/tiers", {
        "societe_id": societe_id, "type": "client", "forme": "morale",
        "raison_sociale": "ENTREPRISE CLIENTE", "nif": "000116007654321",
    })
    verifie("Création d'un client", code == 200 and client.get("id"), json.dumps(client)[:160])

    nif_invalide, code = appel("/api/tiers", {
        "societe_id": societe_id, "type": "client", "raison_sociale": "X", "nif": "123",
    })
    verifie("NIF mal formé rejeté avec un message clair",
            code == 400 and "NIF" in nif_invalide.get("erreur", ""),
            nif_invalide.get("erreur", ""))

    tresorerie, _ = appel(f"/api/tresorerie?societe={societe_id}")
    caisse = next(c for c in tresorerie["comptes"] if c["type"] == "caisse")

    facture, code = appel("/api/factures", {
        "societe_id": societe_id, "sens": "vente", "tiers_id": client["id"],
        "date": "2026-03-15", "objet": "Honoraires de gestion",
        "mode_reglement": "virement", "valider": True,
        "lignes": [{"designation": "Honoraires du 1er trimestre", "quantite": 1,
                    "prix_unitaire": "120000", "taux_tva": 19, "compte": "7063"}],
    })
    verifie("Facture créée et validée", code == 200 and facture.get("numero"),
            json.dumps(facture)[:160])

    detail, _ = appel(f"/api/factures/{facture['id']}")
    verifie("TVA 19 % calculée sur la facture", detail["montant_tva"] == 2280000,
            str(detail["montant_tva"]))
    verifie("Écriture comptable générée automatiquement", bool(detail["ecriture_id"]))

    balance, _ = appel(f"/api/balance?societe={societe_id}&exercice={exercice_id}")
    verifie("Balance équilibrée", balance["equilibree"])

    reglement, code = appel("/api/reglements", {
        "societe_id": societe_id, "sens": "encaissement", "date": "2026-03-20",
        "tresorerie_id": caisse["id"], "facture_id": facture["id"],
        "montant": "142800", "mode": "espece",
    })
    verifie("Encaissement enregistré", code == 200, json.dumps(reglement)[:160])

    trop, code = appel("/api/reglements", {
        "societe_id": societe_id, "sens": "encaissement", "date": "2026-03-21",
        "tresorerie_id": caisse["id"], "facture_id": facture["id"], "montant": "999999",
    })
    verifie("Sur-encaissement bloqué", code == 400 and "reste dû" in trop.get("erreur", ""),
            trop.get("erreur", ""))

    tdb, _ = appel(f"/api/tableau-de-bord?societe={societe_id}&exercice={exercice_id}")
    verifie("Tableau de bord alimenté",
            tdb["indicateurs"]["chiffre_affaires"] == 12000000,
            str(tdb["indicateurs"]["chiffre_affaires"]))
    verifie("Alerte G50 présente", any(a["type"] == "g50" for a in tdb["alertes"]))

    print("\n\033[1m5. Documents et exports\033[0m")
    html, code = appel(f"/api/factures/{facture['id']}/impression", brut=True)
    verifie("Facture imprimable servie en HTML",
            code == 200 and b"NET " in html and b"NIF" in html)

    xlsx, code = appel(f"/api/export/balance?societe={societe_id}&exercice={exercice_id}", brut=True)
    verifie("Export Excel de la balance", code == 200 and xlsx[:2] == b"PK",
            f"{len(xlsx)} octets")

    etats, code = appel(f"/api/export/etats-financiers?societe={societe_id}&exercice={exercice_id}", brut=True)
    verifie("Export de la liasse (bilan + TCR + flux)", code == 200 and etats[:2] == b"PK")

    print("\n\033[1m6. Interface web\033[0m")
    for fichier, attendu in [
        ("/", b"Cabinet Immo"), ("/style.css", b"--primaire"),
        ("/noyau.js", b"function api"), ("/pages-base.js", b"App.pages.accueil"),
        ("/pages-compta.js", b"saisieEcriture"), ("/pages-agence.js", b"quittances"),
        ("/pages-promotion.js", b"contrats-vsp"), ("/pages-fisc.js", b"vueG50"),
        ("/demarrage.js", b"MENU"),
    ]:
        contenu, code = appel(fichier, brut=True)
        verifie(f"Fichier {fichier} servi", code == 200 and attendu in contenu,
                f"code {code}")

    inconnu, code = appel("/api/route-inexistante")
    verifie("Route API inconnue → 404 JSON", code == 404)

    traverse, code = appel("/../app.py", brut=True)
    verifie("Traversée de répertoire bloquée", code in (403, 404) or b"import argparse" not in traverse,
            f"code {code}")

    print("\n\033[1m7. Sauvegarde\033[0m")
    sauvegarde, code = appel("/api/sauvegardes", {"motif": "test"})
    verifie("Sauvegarde créée par l'API", code == 200 and sauvegarde.get("nom"),
            json.dumps(sauvegarde)[:160])
    liste, _ = appel("/api/sauvegardes")
    verifie("Sauvegarde listée", len(liste["sauvegardes"]) >= 1)

    integrite, _ = appel("/api/systeme/verifier", {})
    verifie("Contrôle d'intégrité conforme", integrite.get("conforme"),
            json.dumps(integrite)[:220])


if __name__ == "__main__":
    print("\n\033[1m═══ TEST HTTP — CABINET IMMO ═══\033[0m")
    from app import trouve_port
    port = trouve_port("127.0.0.1", 8900)
    BASE = f"http://127.0.0.1:{port}"
    serveur_http = serveur.demarre("127.0.0.1", port)
    threading.Thread(target=serveur_http.serve_forever, daemon=True).start()
    time.sleep(0.4)
    print(f"Serveur de test : {BASE}")

    code_sortie = 0
    try:
        executer()
    except Exception:                                          # noqa: BLE001
        import traceback
        traceback.print_exc()
        ECHECS.append("Exception non rattrapée")
    finally:
        print("\n" + "═" * 72)
        print(f"\033[1mRÉSULTAT : {len(SUCCES)} réussite(s), {len(ECHECS)} échec(s)\033[0m")
        if ECHECS:
            code_sortie = 1
            for e in ECHECS:
                print(f"  ✗ {e}")
        print("═" * 72)
        serveur_http.shutdown()
        db.ferme()
        shutil.rmtree(DOSSIER, ignore_errors=True)
    raise SystemExit(code_sortie)
