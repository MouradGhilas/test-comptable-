@echo off
REM ===========================================================================
REM  CABINET IMMO - Installation
REM  Double-cliquez sur ce fichier. Il n'y a rien d'autre a faire.
REM ===========================================================================
title Installation de Cabinet Immo
cd /d "%~dp0"

REM --------------------------------------------------------------------------
REM  Windows ouvre un .zip comme un dossier sans l'extraire : il en recopie le
REM  contenu dans un dossier provisoire, sous AppData\Local\Temp, qu'il efface
REM  ensuite. L'installation y reussit, l'application y fonctionne -- et tout
REM  disparait. C'est arrive. On s'arrete donc avant, tant qu'il n'y a encore
REM  rien a perdre.
REM
REM  Aucun bloc entre parentheses ici : le chemin d'un apercu de zip contient
REM  des parentheses -- "..._maj1.8.4 (3).zip\" -- et cmd refermerait le
REM  bloc dessus. Le garde-fou tomberait justement sur le cas qu'il vise.
REM --------------------------------------------------------------------------
set "ICI=%~dp0"
set "PROVISOIRE="
if not "%ICI%"=="%ICI:\AppData\Local\Temp\=%"    set "PROVISOIRE=1"
if not "%ICI%"=="%ICI:\AppData\LocalLow\Temp\=%" set "PROVISOIRE=1"
if not "%ICI%"=="%ICI:\Windows\Temp\=%"          set "PROVISOIRE=1"
if not "%ICI%"=="%ICI:.zip\=%"                   set "PROVISOIRE=1"
if not "%ICI%"=="%ICI:.rar\=%"                   set "PROVISOIRE=1"
if not "%ICI%"=="%ICI:.7z\=%"                    set "PROVISOIRE=1"
if defined PROVISOIRE goto :provisoire

echo.
echo   ============================================================
echo     CABINET IMMO - Installation
echo   ============================================================
echo.
echo   Cette operation ne modifie rien d'autre sur votre ordinateur.
echo   Elle ne demande aucun droit administrateur.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0outils\installer.ps1"
if errorlevel 1 goto :echec

echo.
pause
exit /b 0

:echec
echo.
echo   L'installation a rencontre un probleme.
echo   Envoyez une photo de cet ecran a la personne qui vous assiste.
echo.
pause
exit /b 1

:provisoire
echo.
echo   ============================================================
echo     ARRET - l'archive n'a pas ete extraite
echo   ============================================================
echo.
echo   Vous etes dans l'apercu du fichier compresse. Windows en montre
echo   le contenu comme un dossier, mais il ne l'a pas extrait : ce
echo   dossier est provisoire, et Windows l'efface. Une comptabilite
echo   installee ici serait perdue, sans avertissement.
echo.
echo   Emplacement actuel :
echo   %ICI%
echo.
echo   A FAIRE :
echo     1. Fermez cette fenetre, et la fenetre du fichier compresse.
echo     2. Clic droit sur le fichier .zip, puis "Extraire tout...".
echo     3. Choisissez le dossier Documents, puis "Extraire".
echo     4. Ouvrez le dossier extrait, double-cliquez INSTALLER.bat.
echo.
pause
exit /b 1
