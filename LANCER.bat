@echo off
REM Lance Cabinet Immo sous Windows. Double-cliquez sur ce fichier.
cd /d "%~dp0"
where py >nul 2>nul && (py app.py %* & goto :fin)
where python >nul 2>nul && (python app.py %* & goto :fin)
echo.
echo Python 3 est introuvable sur ce poste.
echo Installez-le depuis https://www.python.org/downloads/
echo Cochez "Add Python to PATH" pendant l'installation, puis relancez ce fichier.
echo.
pause
:fin
