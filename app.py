#!/usr/bin/env python3
"""CABINET IMMO — application comptable pour agence et promotion immobilières.

Comptabilité conforme au SCF algérien, données stockées dans un dossier local.
Aucune dépendance externe : Python 3.9 ou supérieur suffit.

Lancement :
    python3 app.py                              (démarrage standard)
    python3 app.py --donnees /media/usb/compta   (dossier de données choisi)
    python3 app.py --port 9000 --sans-navigateur
    python3 app.py --verifier                    (contrôle d'intégrité)
"""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import webbrowser
from pathlib import Path

RACINE = Path(__file__).resolve().parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

if sys.version_info < (3, 9):
    print("Python 3.9 ou supérieur est requis. Version détectée : "
          f"{sys.version.split()[0]}")
    raise SystemExit(1)


def analyse_arguments():
    analyseur = argparse.ArgumentParser(
        description="Cabinet Immo — comptabilité agence & promotion immobilières (Algérie)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    analyseur.add_argument("--donnees", metavar="DOSSIER",
                           help="dossier local où sont stockées les données")
    analyseur.add_argument("--port", type=int, help="port d'écoute (défaut : 8781)")
    analyseur.add_argument("--hote", help="adresse d'écoute (défaut : 127.0.0.1)")
    analyseur.add_argument("--sans-navigateur", action="store_true",
                           help="ne pas ouvrir le navigateur au démarrage")
    analyseur.add_argument("--verifier", action="store_true",
                           help="vérifier l'intégrité des données puis quitter")
    analyseur.add_argument("--sauvegarder", action="store_true",
                           help="créer une sauvegarde puis quitter")
    return analyseur.parse_args()


def port_disponible(hote: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as prise:
        prise.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            prise.bind((hote, port))
            return True
        except OSError:
            return False


def trouve_port(hote: str, depart: int) -> int:
    for port in range(depart, depart + 40):
        if port_disponible(hote, port):
            return port
    raise SystemExit(f"Aucun port libre entre {depart} et {depart + 40}.")


def principal():
    arguments = analyse_arguments()

    import noyau.config as module_config
    module_config.config = module_config.Configuration({
        "dossier_donnees": arguments.donnees,
        "port": arguments.port,
        "hote": arguments.hote,
    })
    config = module_config.config

    from noyau import base as db
    from noyau import serveur
    from noyau.config import APPLICATION, VERSION

    config.prepare_dossiers()
    db.initialise()

    if arguments.verifier:
        integrite = db.valeur("PRAGMA integrity_check", (), "?")
        desequilibrees = db.lignes(
            "SELECT e.id, e.numero, e.date, e.libelle, "
            "  COALESCE(SUM(l.debit),0) AS d, COALESCE(SUM(l.credit),0) AS c "
            "FROM ecritures e LEFT JOIN lignes l ON l.ecriture_id = e.id "
            "GROUP BY e.id HAVING d <> c")
        print(f"Base           : {config.base_de_donnees}")
        print(f"Intégrité      : {integrite}")
        print(f"Écritures      : {db.valeur('SELECT COUNT(*) FROM ecritures', (), 0)}")
        print(f"Déséquilibrées : {len(desequilibrees)}")
        for e in desequilibrees[:20]:
            print(f"   ⚠ {e['numero']} du {e['date']} — {e['libelle']} "
                  f"(débit {e['d'] / 100:.2f} ≠ crédit {e['c'] / 100:.2f})")
        return 0 if integrite == "ok" and not desequilibrees else 1

    if arguments.sauvegarder:
        from modules.fichiers import cree_sauvegarde
        chemin = cree_sauvegarde("ligne_de_commande")
        print(f"Sauvegarde créée : {chemin}")
        return 0

    import modules  # noqa: F401  — enregistre toutes les routes de l'API

    hote = config["hote"]
    port = config["port"]
    if not port_disponible(hote, port):
        nouveau = trouve_port(hote, port + 1)
        print(f"Le port {port} est occupé, utilisation du port {nouveau}.")
        port = nouveau

    adresse = f"http://{hote}:{port}/"
    installe = bool(db.valeur("SELECT COUNT(*) FROM utilisateurs", (), 0))

    largeur = 68
    print()
    print("╔" + "═" * largeur + "╗")
    print("║" + f"  {APPLICATION}  —  version {VERSION}".ljust(largeur) + "║")
    print("║" + "  Comptabilité agence & promotion immobilières (SCF Algérie)".ljust(largeur) + "║")
    print("╠" + "═" * largeur + "╣")
    print("║" + f"  Adresse   : {adresse}".ljust(largeur) + "║")
    print("║" + f"  Données   : {config.dossier_donnees}".ljust(largeur) + "║")
    if not installe:
        print("║" + "  ".ljust(largeur) + "║")
        print("║" + "  Première utilisation : créez votre compte dans le".ljust(largeur) + "║")
        print("║" + "  navigateur qui va s'ouvrir.".ljust(largeur) + "║")
    print("╠" + "═" * largeur + "╣")
    print("║" + "  Arrêter l'application : Ctrl + C".ljust(largeur) + "║")
    print("╚" + "═" * largeur + "╝")
    print()

    serveur_http = serveur.demarre(hote, port)

    # Écoute Telegram et envoi des résumés à heure fixe.
    from modules import rapports
    rapports.demarre_taches_de_fond()

    if config.get("ouvrir_navigateur", True) and not arguments.sans_navigateur:
        threading.Timer(0.8, lambda: webbrowser.open(adresse)).start()

    try:
        serveur_http.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt en cours…")
        rapports.arrete_taches_de_fond()
        if config.get("sauvegarde_auto", True):
            try:
                from modules.fichiers import cree_sauvegarde
                chemin = cree_sauvegarde("arret")
                print(f"Sauvegarde automatique : {chemin.name}")
            except Exception as err:                      # noqa: BLE001
                print(f"Sauvegarde automatique impossible : {err}")
        serveur_http.shutdown()
        print("Application arrêtée. Vos données restent dans "
              f"{config.dossier_donnees}")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
