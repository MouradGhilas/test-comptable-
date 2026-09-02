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

    print("\n\033[1m7. Recherche globale\033[0m")
    # Un comptable ne se souvient pas de l'écran, mais d'un nom, d'un numéro
    # — ou d'un montant. Le champ unique doit rendre les trois.
    trop_court, code = appel(f"/api/recherche?societe={societe_id}&q=a")
    verifie("Une seule lettre est refusée", code == 400,
            trop_court.get("erreur", ""))

    rech, code = appel(f"/api/recherche?societe={societe_id}&q=ENTREPRISE")
    groupes = {g["cle"]: g for g in rech.get("groupes", [])}
    verifie("Le nom d'un tiers le retrouve", code == 200 and "tiers" in groupes,
            list(groupes))
    verifie("… avec le chemin qui y mène",
            groupes.get("tiers", {}).get("resultats", [{}])[0]
            .get("route", "").startswith("/tiers?q="),
            json.dumps(groupes.get("tiers", {}))[:200])

    rech, _ = appel(f"/api/recherche?societe={societe_id}&q={facture['numero']}")
    groupes = {g["cle"]: g for g in rech["groupes"]}
    verifie("Un numéro de facture retrouve la facture", "factures" in groupes,
            list(groupes))

    rech, _ = appel(f"/api/recherche?societe={societe_id}&q=7063")
    groupes = {g["cle"]: g for g in rech["groupes"]}
    verifie("Un numéro de compte retrouve le compte", "comptes" in groupes,
            list(groupes))
    verifie("… en menant à son grand livre",
            groupes["comptes"]["resultats"][0]["route"].startswith(
                "/comptabilite/grand-livre?compte_debut=7063"),
            groupes.get("comptes", {}).get("resultats", [{}])[0].get("route", ""))

    # 120 000 HT + 19 % = 142 800 TTC : le montant que porte l'écriture.
    rech, _ = appel(f"/api/recherche?societe={societe_id}&q=142%20800")
    groupes = {g["cle"]: g for g in rech["groupes"]}
    verifie("Un montant écrit avec des espaces est compris",
            rech["montant"] == 14280000, str(rech.get("montant")))
    verifie("… et retrouve la ligne d'écriture qui le porte",
            "montant" in groupes, list(groupes))
    verifie("… en menant à l'écriture elle-même",
            groupes.get("montant", {}).get("resultats", [{}])[0]
            .get("route", "").startswith("/comptabilite/ecritures?ecriture="),
            json.dumps(groupes.get("montant", {}))[:200])

    rech, _ = appel(f"/api/recherche?societe={societe_id}&q=%%")
    verifie("Un joker de recherche ne fait pas tout remonter",
            rech["total"] == 0, str(rech["total"]))

    # La contrepartie habituelle : apprise de l'historique, jamais devinée.
    cp, code = appel(f"/api/comptes/contrepartie?societe={societe_id}"
                     f"&journal=VE&compte=411")
    verifie("La contrepartie habituelle est apprise de l'historique",
            code == 200 and cp.get("compte") == "7063", json.dumps(cp)[:160])
    verifie("… en disant combien de fois elle a servi",
            cp.get("emplois", 0) >= 1, json.dumps(cp)[:160])
    # Le client a bien été encaissé en caisse : c'est au journal de paie,
    # où il n'a rien à faire, qu'il ne doit rien être proposé.
    vide, _ = appel(f"/api/comptes/contrepartie?societe={societe_id}"
                    f"&journal=PA&compte=411")
    verifie("Sans historique dans ce journal, rien n'est proposé",
            vide.get("compte") is None, json.dumps(vide)[:160])

    print("\n\033[1m8. Relevé de compte d'un tiers\033[0m")
    # La balance auxiliaire dit combien un client doit ; le relevé dit pourquoi.
    rel, code = appel(f"/api/tiers/{client['id']}/releve"
                      f"?societe={societe_id}&du=2026-01-01&au=2026-12-31")
    verifie("Le relevé répond", code == 200 and "mouvements" in rel,
            json.dumps(rel)[:180])
    verifie("Il porte les deux mouvements du client (facture, encaissement)",
            len(rel["mouvements"]) == 2, str(len(rel["mouvements"])))

    courant = rel["solde_anterieur"]
    exact = True
    for m in rel["mouvements"]:
        courant += m["debit"] - m["credit"]
        exact = exact and m["solde"] == courant
    verifie("Chaque ligne porte le solde cumulé exact", exact,
            json.dumps(rel["mouvements"])[:220])
    verifie("Solde antérieur + débits − crédits = solde final",
            rel["solde_anterieur"] + rel["total_debit"] - rel["total_credit"]
            == rel["solde_final"], str(rel["solde_final"]))
    # 142 800 facturés, 142 800 encaissés : le compte est soldé.
    verifie("Le solde final est nul, facture et règlement se compensant",
            rel["solde_final"] == 0, str(rel["solde_final"]))
    verifie("Le relevé annonce son périmètre",
            bool(rel.get("libelle_perimetre")), json.dumps(rel)[:150])

    impression, code = appel(f"/api/tiers/{client['id']}/releve/impression"
                             f"?societe={societe_id}&du=2026-01-01&au=2026-12-31",
                             brut=True)
    texte = impression.decode()
    verifie("Le relevé imprimable est produit",
            code == 200 and "RELEVÉ DE COMPTE" in texte, texte[:150])
    verifie("… il nomme le tiers et porte la mention d'usage",
            "ENTREPRISE CLIENTE" in texte and "Sauf erreur ou omission" in texte,
            texte[:150])

    classeur, code = appel(f"/api/export/releve-tiers?societe={societe_id}"
                           f"&tiers={client['id']}&du=2026-01-01&au=2026-12-31",
                           brut=True)
    verifie("L'export du relevé est un classeur",
            code == 200 and classeur[:2] == b"PK", str(classeur[:8]))

    inconnu, code = appel(f"/api/tiers/999999/releve?societe={societe_id}")
    verifie("Un tiers inconnu est refusé", code == 404, str(code))

    print("\n\033[1m9. Sauvegarde\033[0m")
    sauvegarde, code = appel("/api/sauvegardes", {"motif": "test"})
    verifie("Sauvegarde créée par l'API", code == 200 and sauvegarde.get("nom"),
            json.dumps(sauvegarde)[:160])
    liste, _ = appel("/api/sauvegardes")
    verifie("Sauvegarde listée", len(liste["sauvegardes"]) >= 1)

    integrite, _ = appel("/api/systeme/verifier", {})
    verifie("Contrôle d'intégrité conforme", integrite.get("conforme"),
            str(integrite))

    print("\n\033[1mInterface — pièges déjà rencontrés\033[0m")
    # Une carte sans titre perdait ses boutons d'action : l'en-tête, qui les
    # porte, ne s'affichait qu'en présence d'un titre. Trois écrans y ont
    # laissé leur action principale — lettrer une sélection, reverser aux
    # propriétaires, comptabiliser la paie — sans que rien ne le signale.
    noyau_js = (RACINE / "web" / "noyau.js").read_text(encoding="utf-8")
    corps_carte = noyau_js[noyau_js.index("function carte("):]
    corps_carte = corps_carte[:corps_carte.index("\n}")]
    verifie("Une carte sans titre affiche quand même ses actions",
            "titre || actions" in corps_carte, corps_carte[:200])

    # Les montants d'un même champ doivent suivre une seule convention : le
    # navigateur envoie ce qui est tapé, le serveur convertit une fois. Une
    # conversion des deux côtés multipliait les primes de paie par cent.
    fisc_js = (RACINE / "web" / "pages-fisc.js").read_text(encoding="utf-8")
    verifie("Les primes ne sont pas converties deux fois",
            "cts($('.p-montant'" not in fisc_js.replace(" ", ""))

    # Un Mac n'exécute pas un « .py » d'un double-clic. L'installateur doit
    # rester lançable par le shell autant que par Python.
    import subprocess as _sp
    from outils import faire_paquet
    entete = faire_paquet.ENTETE_POLYGLOTTE
    verifie("L'installateur reste un script shell valide",
            entete.startswith("#!/bin/sh") and "exec python3" in entete, entete)
    essai = Path(DOSSIER) / "polyglotte.command"
    essai.write_text(entete + "print('depuis python')\n", encoding="utf-8")
    essai.chmod(0o755)
    verifie("… et Python le lit comme du Python",
            _sp.run([sys.executable, str(essai)], capture_output=True,
                    text=True).stdout.strip() == "depuis python")
    verifie("… et le shell le confie à Python",
            _sp.run(["sh", str(essai)], capture_output=True,
                    text=True).stdout.strip() == "depuis python")


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
