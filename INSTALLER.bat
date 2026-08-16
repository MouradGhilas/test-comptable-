@echo off
REM ===========================================================================
REM  CABINET IMMO - Installation
REM  Double-cliquez sur ce fichier. Il n'y a rien d'autre a faire.
REM ===========================================================================
title Installation de Cabinet Immo
cd /d "%~dp0"

echo.
echo   ============================================================
echo     CABINET IMMO - Installation
echo   ============================================================
echo.
echo   Cette operation ne modifie rien d'autre sur votre ordinateur.
echo   Elle ne demande aucun droit administrateur.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0outils\installer.ps1"

if errorlevel 1 (
  echo.
  echo   L'installation a rencontre un probleme.
  echo   Envoyez une photo de cet ecran a la personne qui vous assiste.
  echo.
  pause
  exit /b 1
)

echo.
pause
