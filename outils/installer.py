#!/usr/bin/env python3
"""Installation de Cabinet Immo — variante sans fichier exécutable.

Pourquoi ce fichier existe : les messageries (Gmail en tête) refusent les
archives contenant des `.bat`, `.ps1` ou `.exe`, même compressés. Cet
installateur est un simple `.py`, qui passe partout, et qui **fabrique les
lanceurs Windows directement sur le poste**. L'archive envoyée ne contient
donc aucun fichier bloqué.

Il fait le même travail que INSTALLER.bat :
  * vérifie que l'application fonctionne ;
  * crée DEMARRER.bat et METTRE-A-JOUR.bat, figés sur le Python utilisé ;
  * pose un raccourci sur le Bureau ;
  * propose le démarrage automatique à l'ouverture de session ;
  * lance l'application.

Utilisation : double-cliquez sur ce fichier, ou

    python installer.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
WINDOWS = os.name == "nt"


def titre(texte):
    print(f"\n\033[1m{texte}\033[0m" if not WINDOWS else f"\n{texte}")


def etape(texte):
    print(f"  -> {texte}")


def succes(texte):
    print(f"  OK  {texte}")


def avert(texte):
    print(f"  !   {texte}")


def echec(texte):
    print(f"  X   {texte}")


def demande(question: str, defaut_oui: bool = True) -> bool:
    suffixe = "(O/n)" if defaut_oui else "(o/N)"
    try:
        reponse = input(f"  {question} {suffixe} ").strip().lower()
    except EOFError:
        return defaut_oui
    if not reponse:
        return defaut_oui
    return reponse[0] in "oy"


# ---------------------------------------------------------------------------

def verifie_python() -> bool:
    if sys.version_info < (3, 9):
        echec(f"Python {sys.version.split()[0]} est trop ancien (3.9 minimum).")
        print()
        print("  Installez une version récente depuis :")
        print("    https://www.python.org/downloads/")
        print("  Cochez « Add Python to PATH » pendant l'installation,")
        print("  puis relancez ce fichier.")
        return False
    try:
        import sqlite3                                        # noqa: F401
    except ImportError:
        echec("Ce Python n'a pas le module sqlite3, indispensable ici.")
        return False
    succes(f"Python {sys.version.split()[0]} — {sys.executable}")
    return True


def verifie_application() -> bool:
    etape("Vérification de l'application…")
    resultat = subprocess.run(
        [sys.executable, str(RACINE / "app.py"), "--verifier"],
        capture_output=True, text=True, cwd=str(RACINE))
    if resultat.returncode > 1:
        echec("L'application ne démarre pas :")
        print(resultat.stdout or "")
        print(resultat.stderr or "")
        return False
    succes("Application prête.")
    return True


def ecrit_lanceurs_windows() -> None:
    """Fabrique les .bat sur place : ils ne transitent jamais par la messagerie."""
    python = sys.executable
    # pythonw.exe lance sans fenêtre noire ; on retombe sur python.exe sinon.
    sans_console = Path(python).with_name("pythonw.exe")
    lanceur = str(sans_console) if sans_console.exists() else python

    (RACINE / "DEMARRER.bat").write_text(
        "@echo off\r\n"
        "REM Genere par l'installateur - lance Cabinet Immo\r\n"
        'cd /d "%~dp0"\r\n'
        f'start "" "{lanceur}" "%~dp0app.py" %*\r\n',
        encoding="ascii", errors="replace")

    (RACINE / "METTRE-A-JOUR.bat").write_text(
        "@echo off\r\n"
        "REM Genere par l'installateur - met a jour Cabinet Immo\r\n"
        'cd /d "%~dp0"\r\n'
        f'"{python}" "%~dp0outils\\mise_a_jour.py" %*\r\n'
        "pause\r\n",
        encoding="ascii", errors="replace")

    (RACINE / "VERIFIER.bat").write_text(
        "@echo off\r\n"
        'cd /d "%~dp0"\r\n'
        f'"{python}" "%~dp0app.py" --verifier\r\n'
        "pause\r\n",
        encoding="ascii", errors="replace")

    succes("Lanceurs créés : DEMARRER.bat, METTRE-A-JOUR.bat, VERIFIER.bat")


def cree_raccourci_windows(dans_demarrage: bool = False) -> Path | None:
    """Raccourci Bureau via un script VBS temporaire (cscript est natif)."""
    dossier = ("Startup" if dans_demarrage else "Desktop")
    vbs = f'''
Set shell = CreateObject("WScript.Shell")
dossier = shell.SpecialFolders("{dossier}")
Set lien = shell.CreateShortcut(dossier & "\\Cabinet Immo.lnk")
lien.TargetPath = "{RACINE / 'DEMARRER.bat'}"
lien.WorkingDirectory = "{RACINE}"
lien.Description = "Comptabilite agence et promotion immobilieres"
lien.WindowStyle = 7
lien.Save
WScript.Echo dossier
'''
    fichier = Path(tempfile.gettempdir()) / "cabinet_raccourci.vbs"
    fichier.write_text(vbs, encoding="ascii", errors="replace")
    try:
        resultat = subprocess.run(["cscript", "//Nologo", str(fichier)],
                                  capture_output=True, text=True, timeout=30)
        if resultat.returncode != 0:
            avert(f"Raccourci non créé : {resultat.stderr.strip()}")
            return None
        return Path(resultat.stdout.strip())
    except (OSError, subprocess.SubprocessError) as err:
        avert(f"Raccourci non créé : {err}")
        return None
    finally:
        fichier.unlink(missing_ok=True)


def ecrit_lanceur_unix() -> None:
    script = RACINE / "lancer.sh"
    script.write_text(
        "#!/bin/sh\n"
        '# Genere par l\'installateur\n'
        'cd "$(dirname "$0")" || exit 1\n'
        f'exec "{sys.executable}" app.py "$@"\n')
    script.chmod(0o755)
    succes("Lanceur créé : lancer.sh")


# ---------------------------------------------------------------------------

def principal() -> int:
    print()
    print("  " + "=" * 58)
    print("    CABINET IMMO — Installation")
    print("  " + "=" * 58)
    print()
    print("  Rien n'est installé dans le système, aucun mot de passe")
    print("  administrateur n'est demandé.")

    titre("1. Moteur Python")
    if not verifie_python():
        input("\n  Appuyez sur Entrée pour fermer…")
        return 1

    titre("2. Application")
    if not verifie_application():
        input("\n  Appuyez sur Entrée pour fermer…")
        return 1

    titre("3. Raccourcis")
    if WINDOWS:
        ecrit_lanceurs_windows()
        bureau = cree_raccourci_windows()
        if bureau:
            succes(f"Raccourci « Cabinet Immo » créé dans {bureau}")
        print()
        if demande("Démarrer automatiquement à chaque ouverture de session ?"):
            if cree_raccourci_windows(dans_demarrage=True):
                succes("Démarrage automatique activé.")
        else:
            avert("Démarrage automatique non activé.")
            print("      À savoir : il est nécessaire pour la consultation à")
            print("      distance et l'envoi des résumés à heure fixe.")
    else:
        ecrit_lanceur_unix()

    print()
    print("  " + "=" * 58)
    print("    Installation terminée")
    print("  " + "=" * 58)
    print()
    print(f"    Vos données seront enregistrées dans :")
    print(f"    {RACINE / 'donnees'}")
    print()
    if WINDOWS:
        print("    Ouvrir l'application : raccourci « Cabinet Immo » du Bureau")
        print("    Mettre à jour        : METTRE-A-JOUR.bat")
    else:
        print("    Ouvrir l'application : ./lancer.sh")
        print("    Mettre à jour        : python3 outils/mise_a_jour.py")
    print()

    if demande("Ouvrir l'application maintenant ?"):
        subprocess.Popen([sys.executable, str(RACINE / "app.py")], cwd=str(RACINE))
        print("\n  L'application s'ouvre dans votre navigateur…")
    else:
        input("\n  Appuyez sur Entrée pour fermer…")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
