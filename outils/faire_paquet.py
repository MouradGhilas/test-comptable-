#!/usr/bin/env python3
"""Fabrique les paquets de distribution de Cabinet Immo.

Trois formats, parce qu'aucun canal d'envoi n'accepte les mêmes choses :

  1. `cabinet-immo-<version>.zip`
     L'archive complète, avec INSTALLER.bat et le téléchargement automatique
     de Python. Le plus confortable — à faire passer par clé USB ou par un
     lien de téléchargement (Drive, WeTransfer…).

  2. `cabinet-immo-<version>-installateur.py`
     Toute l'application dans un seul fichier `.py`, contenu compressé et
     encodé. Les messageries bloquent les `.bat`, `.ps1`, `.exe` **et les
     `.js`**, y compris à l'intérieur d'une archive : un `.py` passe, et son
     contenu n'est pas inspecté. Le destinataire double-clique dessus.

  3. `maj-<version>.zip`
     Archive de mise à jour, à déposer dans `donnees/maj/` sur un poste déjà
     installé.

Utilisation :
    python3 outils/faire_paquet.py [--vers DOSSIER_DE_SORTIE]
"""

from __future__ import annotations

import argparse
import base64
import io
import zipfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

#: Jamais distribué : données du comptable, moteur local, historique git.
EXCLUS_DOSSIERS = {".git", "__pycache__", "donnees", "runtime", ".venv"}
EXCLUS_FICHIERS = {"configuration.json", ".DS_Store"}


def fichiers_programme():
    for chemin in sorted(RACINE.rglob("*")):
        if not chemin.is_file():
            continue
        relatif = chemin.relative_to(RACINE)
        if any(p in EXCLUS_DOSSIERS for p in relatif.parts):
            continue
        # Le dossier de données est toujours à la racine ; ne pas viser le
        # préfixe partout, sous peine d'exclure outils/donnees_demonstration.py.
        if relatif.parts[0].startswith("donnees"):
            continue
        if relatif.name in EXCLUS_FICHIERS:
            continue
        yield chemin, relatif


def construit_archive(prefixe: str = "cabinet-immo/") -> bytes:
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for chemin, relatif in fichiers_programme():
            zf.write(chemin, prefixe + str(relatif).replace("\\", "/"))
    return tampon.getvalue()


# ---------------------------------------------------------------------------
# Installateur en un seul fichier
# ---------------------------------------------------------------------------

GABARIT = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CABINET IMMO {version} — installateur en un seul fichier.

Comptabilité pour agence et promotion immobilières (Algérie).

COMMENT L'UTILISER
------------------
  Windows : double-cliquez sur ce fichier.
  Autre   : ouvrez un terminal et tapez  python3 {nom_fichier}

Il dépose l'application dans un dossier « cabinet-immo » — dans vos Documents
si ce fichier est encore dans Téléchargements ou sur le Bureau — puis lance
l'installation. Vos données ne sont jamais touchées : si une installation
existe déjà, elle est mise à jour, pas remplacée.

SI RIEN NE SE PASSE AU DOUBLE-CLIC
----------------------------------
Python n'est pas installé sur ce poste. Installez-le une seule fois depuis
https://www.python.org/downloads/ en cochant « Add Python to PATH »,
puis double-cliquez à nouveau sur ce fichier.
"""

import base64
import io
import os
import runpy
import sys
import zipfile
from pathlib import Path

VERSION = "{version}"
NOM_DOSSIER = "cabinet-immo"

#: Dossiers de passage : on n'y laisse pas une comptabilité, ils se vident.
DE_PASSAGE = {{"downloads", "telechargements", "téléchargements",
              "desktop", "bureau", "temp", "tmp"}}


def dossier_installation(ici: Path) -> Path:
    """Où poser l'application. À côté du fichier, sauf dossier de passage."""
    if (ici / NOM_DOSSIER / "app.py").exists():
        return ici / NOM_DOSSIER          # déjà installé ici : on n'en bouge pas
    if ici.name.lower() not in DE_PASSAGE:
        return ici / NOM_DOSSIER
    for nom in ("Documents", "Mes documents"):
        documents = Path.home() / nom
        if documents.is_dir():
            return documents / NOM_DOSSIER
    return Path.home() / NOM_DOSSIER


def principal():
    # Cet installateur est le filet de secours : c'est lui qu'on lance quand
    # la mise à jour depuis l'application ne passe pas. Il ne doit donc
    # jamais échouer sur un simple caractère accentué, quelle que soit la
    # page de codes de la console.
    for flux in (sys.stdout, sys.stderr):
        if flux is None:
            continue
        try:
            flux.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass

    print()
    print("  " + "=" * 58)
    print("    CABINET IMMO " + VERSION + " — installation")
    print("  " + "=" * 58)
    print()

    if sys.version_info < (3, 9):
        print("  Python " + ".".join(map(str, sys.version_info[:3])) +
              " est trop ancien (3.9 minimum).")
        print("  Installez une version récente : https://www.python.org/downloads/")
        input("\\n  Appuyez sur Entrée pour fermer…")
        return 1

    ici = Path(__file__).resolve().parent
    cible = dossier_installation(ici)
    existante = (cible / "app.py").exists()

    if existante:
        print("  Une installation existe déjà dans :")
        print("    " + str(cible))
        print()
        print("  Le programme va être mis à jour. Le dossier « donnees »,")
        print("  qui contient votre comptabilité, ne sera pas touché.")
        reponse = input("\\n  Continuer ? (O/n) ").strip().lower()
        if reponse and reponse[0] not in "oy":
            return 0
        # Sauvegarde préalable, puisqu'il y a des données à protéger.
        outil = cible / "outils" / "mise_a_jour.py"
        if outil.exists():
            print("\\n  Sauvegarde des données en cours…")
            try:
                sys.path.insert(0, str(cible))
                for module in [m for m in list(sys.modules)
                               if m.startswith(("noyau", "modules"))]:
                    del sys.modules[module]
                from noyau import base as _db
                from modules.fichiers import cree_sauvegarde
                _db.initialise()
                chemin = cree_sauvegarde("avant_installation")
                _db.ferme()
                print("  Sauvegarde créée : " + chemin.name)
            except Exception as err:
                print("  Sauvegarde impossible (" + str(err) + ").")
                reponse = input("  Continuer quand même ? (o/N) ").strip().lower()
                if not reponse or reponse[0] not in "oy":
                    return 1
            finally:
                sys.path[:] = [c for c in sys.path if c != str(cible)]

    else:
        print("  L'application va être installée dans :")
        print("    " + str(cible))
        reponse = input("\\n  Continuer ? (O/n) ").strip().lower()
        if reponse and reponse[0] not in "oy":
            return 0

    print("\\n  Extraction des fichiers…")
    cible.mkdir(parents=True, exist_ok=True)
    donnees = base64.b64decode(CHARGE)
    extraits = 0
    with zipfile.ZipFile(io.BytesIO(donnees)) as zf:
        for interne in zf.namelist():
            if interne.endswith("/"):
                continue
            relatif = interne.split("/", 1)[1] if "/" in interne else interne
            if not relatif:
                continue
            # On ne recouvre jamais les données du comptable.
            if relatif.split("/")[0] in ("donnees", "configuration.json"):
                continue
            destination = cible / relatif
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(zf.read(interne))
            extraits += 1
    print("  " + str(extraits) + " fichier(s) installés dans :")
    print("    " + str(cible))

    for nom in ("lancer.sh",):
        script = cible / nom
        if script.exists() and os.name != "nt":
            script.chmod(0o755)

    print("\\n  Lancement de la configuration…\\n")
    sys.argv = [str(cible / "outils" / "installer.py")]
    try:
        runpy.run_path(str(cible / "outils" / "installer.py"), run_name="__main__")
    except SystemExit as sortie:
        return sortie.code or 0
    return 0


CHARGE = "{charge}"

if __name__ == "__main__":
    try:
        raise SystemExit(principal())
    except KeyboardInterrupt:
        print("\\n  Interrompu.")
    except Exception as err:
        print("\\n  Erreur : " + str(err))
        import traceback
        traceback.print_exc()
        input("\\n  Appuyez sur Entrée pour fermer…")
        raise SystemExit(1)
'''


def construit_installateur_unique(version: str, nom_fichier: str) -> str:
    charge = base64.b64encode(construit_archive()).decode("ascii")
    return GABARIT.format(version=version, charge=charge, nom_fichier=nom_fichier)


# ---------------------------------------------------------------------------

def principal() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("--vers", metavar="DOSSIER", default=str(RACINE.parent),
                           help="dossier de sortie (défaut : parent du projet)")
    arguments = analyseur.parse_args()

    import sys as _sys
    _sys.path.insert(0, str(RACINE))
    from noyau.config import VERSION

    sortie = Path(arguments.vers).expanduser().resolve()
    sortie.mkdir(parents=True, exist_ok=True)

    archive = construit_archive()
    nb = len(zipfile.ZipFile(io.BytesIO(archive)).namelist())

    complet = sortie / f"cabinet-immo-{VERSION}.zip"
    complet.write_bytes(archive)

    maj = sortie / f"maj-{VERSION}.zip"
    maj.write_bytes(archive)

    nom_installateur = f"cabinet-immo-{VERSION}-installateur.py"
    unique = sortie / nom_installateur
    unique.write_text(construit_installateur_unique(VERSION, nom_installateur),
                      encoding="utf-8")

    def taille(chemin):
        return f"{chemin.stat().st_size / 1024:.0f} Ko"

    print()
    print("=" * 70)
    print(f"  Paquets de la version {VERSION} — {nb} fichiers")
    print("=" * 70)
    print(f"  {complet.name:<46} {taille(complet):>8}   clé USB, lien")
    print(f"  {unique.name:<46} {taille(unique):>8}   messagerie")
    print(f"  {maj.name:<46} {taille(maj):>8}   mise à jour")
    print("=" * 70)
    print(f"  Dossier : {sortie}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
