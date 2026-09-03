@echo off
REM Lance Cabinet Immo sous Windows. Double-cliquez sur ce fichier.
title Cabinet Immo
cd /d "%~dp0"

REM Meme garde-fou que l'installateur : travailler depuis l'apercu d'un .zip
REM revient a tenir sa comptabilite dans un dossier que Windows va effacer.
set "ICI=%~dp0"
set "PROVISOIRE="
if not "%ICI%"=="%ICI:\AppData\Local\Temp\=%"    set "PROVISOIRE=1"
if not "%ICI%"=="%ICI:\AppData\LocalLow\Temp\=%" set "PROVISOIRE=1"
if not "%ICI%"=="%ICI:\Windows\Temp\=%"          set "PROVISOIRE=1"
if not "%ICI%"=="%ICI:.zip\=%"                   set "PROVISOIRE=1"
if not "%ICI%"=="%ICI:.rar\=%"                   set "PROVISOIRE=1"
if not "%ICI%"=="%ICI:.7z\=%"                    set "PROVISOIRE=1"
if defined PROVISOIRE goto :provisoire

REM Le moteur depose par l'installateur en premier : il est maitrise, et il
REM existe meme quand le poste n'a aucun Python -- le cas d'un ordinateur neuf.
if exist "runtime\python.exe" goto :embarque
where py >nul 2>nul && (py app.py %* & goto :fin)
where python >nul 2>nul && (python app.py %* & goto :fin)

REM Aucun moteur trouve. Ce n'est pas a l'utilisateur d'aller en chercher un :
REM l'installateur sait en deposer un, sans droit administrateur ni site web.
echo.
echo   Premiere utilisation : l'application doit d'abord etre installee.
echo   Lancement de l'installation.
echo.
call "%~dp0INSTALLER.bat"
goto :fin

:embarque
start "" "runtime\python.exe" "app.py" %*
goto :fin

:provisoire
echo.
echo   ARRET - l'archive n'a pas ete extraite.
echo.
echo   Vous etes dans l'apercu du fichier compresse : ce dossier est
echo   provisoire, Windows l'efface, et la comptabilite saisie ici
echo   serait perdue.
echo.
echo   Emplacement actuel :
echo   %ICI%
echo.
echo   Clic droit sur le fichier .zip, "Extraire tout...", choisissez
echo   Documents, puis relancez depuis le dossier extrait.
echo.
pause

:fin
