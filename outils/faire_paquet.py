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

#: Version de Python déposée quand le poste n'en a aucun. Même principe que
#: l'installateur Windows, qui télécharge la version « embarquée » officielle :
#: rien n'est installé dans le système, tout tient dans un dossier à part.
PYTHON_PORTABLE = "3.11.9"
PYTHON_PORTABLE_TAG = "20240726"

#: Les premières lignes d'un fichier qui est à la fois un script shell et un
#: programme Python : le shell exécute le préambule, Python n'y voit qu'une
#: chaîne de caractères sans effet.
#:
#: Ce préambule fait le travail que l'utilisateur ne doit pas avoir à faire —
#: chercher un Python utilisable et, s'il n'y en a aucun, en déposer un dans
#: un coin à lui. Personne n'a à installer quoi que ce soit, ni à savoir ce
#: qu'est Python.
PREAMBULE_SHELL = """#!/bin/sh
''''true
# --- Cabinet Immo : trouver un moteur Python, ou en deposer un -----------
# Rien n'est installe dans le systeme : le moteur telecharge, s'il l'est,
# reste dans ~/.cabinet-immo/runtime et ne sert qu'a cette application.
RUNTIME="$HOME/.cabinet-immo/runtime"

utilisable() {
  [ -n "$1" ] && [ -x "$1" ] && "$1" -c \\
    'import sys,sqlite3; sys.exit(0 if sys.version_info >= (3,9) else 1)' \\
    >/dev/null 2>&1
}

for candidat in \\
    "$RUNTIME/python/bin/python3" \\
    "$(command -v python3 2>/dev/null)" \\
    /opt/homebrew/bin/python3 \\
    /usr/local/bin/python3 \\
    /usr/bin/python3
do
  if utilisable "$candidat"; then exec "$candidat" -- "$0" ${1+"$@"}; fi
done

case "$(uname -s)-$(uname -m)" in
  Darwin-arm64)  ARCHI="aarch64-apple-darwin" ;;
  Darwin-x86_64) ARCHI="x86_64-apple-darwin" ;;
  Linux-x86_64)  ARCHI="x86_64-unknown-linux-gnu" ;;
  Linux-aarch64) ARCHI="aarch64-unknown-linux-gnu" ;;
  *) ARCHI="" ;;
esac
if [ -z "$ARCHI" ]; then
  echo ""
  echo "  Systeme non reconnu ($(uname -s) $(uname -m))."
  echo "  Installez Python 3 puis relancez ce fichier."
  exit 1
fi

URL="https://github.com/astral-sh/python-build-standalone/releases/download/__TAG__/cpython-__VERSION__+__TAG__-$ARCHI-install_only.tar.gz"
echo ""
echo "  Cabinet Immo a besoin d'un moteur pour fonctionner, et ce poste"
echo "  n'en a pas. Telechargement en cours (17 Mo, une seule fois)."
echo "  Rien ne sera installe dans le systeme."
echo ""
mkdir -p "$RUNTIME" || exit 1
ARCHIVE="$RUNTIME/moteur.tar.gz"
if ! curl -fL --progress-bar -o "$ARCHIVE" "$URL"; then
  echo ""
  echo "  Telechargement impossible. Verifiez la connexion Internet,"
  echo "  puis relancez ce fichier."
  exit 1
fi
tar -xzf "$ARCHIVE" -C "$RUNTIME" || exit 1
rm -f "$ARCHIVE"
if utilisable "$RUNTIME/python/bin/python3"; then
  echo "  Moteur installe."
  exec "$RUNTIME/python/bin/python3" -- "$0" ${1+"$@"}
fi
echo "  Le moteur telecharge ne fonctionne pas sur ce poste."
exit 1
# '''
"""

ENTETE_POLYGLOTTE = (PREAMBULE_SHELL
                     .replace("__TAG__", PYTHON_PORTABLE_TAG)
                     .replace("__VERSION__", PYTHON_PORTABLE))


GABARIT = '''# -*- coding: utf-8 -*-
"""CABINET IMMO {version} — installateur en un seul fichier.

Comptabilité pour agence et promotion immobilières (Algérie).

La première ligne fait de ce fichier à la fois un script shell et un
programme Python : renommé en « .command », il se lance d'un double-clic
sur un Mac, où un « .py » n'est ouvert que dans un éditeur de texte.

COMMENT L'UTILISER
------------------
  Windows : double-cliquez sur ce fichier.
  macOS   : ouvrez Terminal, tapez « sh » et un espace, puis faites
            glisser ce fichier dans la fenêtre et appuyez sur Entrée.
            (macOS refuse d'ouvrir d'un double-clic un fichier reçu
            d'Internet qui n'est pas signé par un éditeur enregistré ;
            passer par Terminal contourne ce blocage sans rien
            désactiver.)
  Linux   : ouvrez un terminal et tapez  sh {nom_fichier}

Il dépose l'application dans un dossier « cabinet-immo » — dans vos Documents
si ce fichier est encore dans Téléchargements ou sur le Bureau — puis lance
l'installation. Vos données ne sont jamais touchées : si une installation
existe déjà, elle est mise à jour, pas remplacée.

SI RIEN NE SE PASSE AU DOUBLE-CLIC (Windows)
--------------------------------------------
Ce poste n'a pas encore de moteur Python — c'est le cas d'un ordinateur
neuf. Ne l'installez pas vous-même : utilisez plutôt le fichier
« cabinet-immo-{version}.zip ». Faites un clic droit dessus,
« Extraire tout… », choisissez Documents, puis double-cliquez
INSTALLER.bat dans le dossier extrait : il dépose le moteur lui-même,
sans droit administrateur.

N'ouvrez jamais le .zip d'un simple double-clic pour lancer l'installation
depuis la fenêtre qui s'affiche : Windows n'a alors rien extrait, et le
dossier qu'il montre est provisoire.
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

#: Emplacements que le système efface de lui-même. Le nom du dossier ne suffit
#: pas à les reconnaître : l'aperçu d'une archive s'appelle
#: « ..._maj1.8.4 (3).zip », et se trouve sous AppData\\Local\\Temp.
PROVISOIRES = ("/appdata/local/temp/", "/appdata/locallow/temp/",
               "/windows/temp/", "/local settings/temp/",
               "/var/folders/", "/tmp/", "/private/tmp/")
ARCHIVES = (".zip", ".rar", ".7z", ".cab", ".tar", ".gz")


def de_passage(ici: Path) -> bool:
    """Un endroit où l'on ne laisse pas une comptabilité.

    Windows ouvre un .zip comme un dossier sans l'extraire : on y installe,
    on y saisit, et il l'efface. Le cas s'est produit ; il se reconnaît au
    chemin, pas au nom du dossier.
    """
    if ici.name.lower() in DE_PASSAGE:
        return True
    chemin = str(ici).replace("\\\\", "/").lower() + "/"
    if any(marque in chemin for marque in PROVISOIRES):
        return True
    return any(part.endswith(ARCHIVES) for part in chemin.split("/") if part)


def dossier_installation(ici: Path) -> Path:
    """Où poser l'application. À côté du fichier, sauf dossier de passage."""
    if not de_passage(ici):
        if (ici / NOM_DOSSIER / "app.py").exists():
            return ici / NOM_DOSSIER      # déjà installé ici : on n'en bouge pas
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
        print("  Le moteur Python de ce poste est trop ancien : " +
              ".".join(map(str, sys.version_info[:3])) + " (3.9 minimum).")
        print()
        print("  Vous n'avez rien à installer vous-même. Utilisez plutôt")
        print("  le fichier « cabinet-immo-" + VERSION + ".zip » :")
        print("    1. clic droit dessus, « Extraire tout… », dans Documents ;")
        print("    2. ouvrez le dossier extrait, double-cliquez INSTALLER.bat.")
        print("  Il dépose son propre moteur, sans rien changer au système.")
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
    return ENTETE_POLYGLOTTE + GABARIT.format(
        version=version, charge=charge, nom_fichier=nom_fichier)


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
    contenu = construit_installateur_unique(VERSION, nom_installateur)
    unique.write_text(contenu, encoding="utf-8")

    # Le même installateur, sous le nom que macOS sait ouvrir d'un
    # double-clic. Un « .py » y est ouvert dans un éditeur de texte ; un
    # « .command » est exécuté par le Terminal.
    pour_mac = sortie / f"cabinet-immo-{VERSION}-installateur-MAC.command"
    pour_mac.write_text(contenu, encoding="utf-8")
    pour_mac.chmod(0o755)

    def taille(chemin):
        return f"{chemin.stat().st_size / 1024:.0f} Ko"

    print()
    print("=" * 70)
    print(f"  Paquets de la version {VERSION} — {nb} fichiers")
    print("=" * 70)
    print(f"  {complet.name:<46} {taille(complet):>8}   clé USB, lien")
    print(f"  {unique.name:<46} {taille(unique):>8}   messagerie")
    print(f"  {pour_mac.name:<46} {taille(pour_mac):>8}   macOS")
    print(f"  {maj.name:<46} {taille(maj):>8}   mise à jour")
    print("=" * 70)
    print(f"  Dossier : {sortie}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
