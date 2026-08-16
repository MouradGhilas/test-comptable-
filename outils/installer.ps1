# =============================================================================
#  Cabinet Immo - installation sous Windows 10 / 11
#
#  Objectif : que l'utilisateur n'ait rien a installer, rien a configurer et
#  aucun droit administrateur a demander.
#
#  1. Cherche un Python 3.9+ deja present sur le poste.
#  2. S'il n'y en a pas, telecharge la version « embarquee » officielle de
#     Python et la depose dans le sous-dossier runtime\ de l'application.
#     Rien n'est ajoute au PATH, rien n'est installe pour le systeme.
#  3. Cree un raccourci sur le Bureau.
#  4. Propose le demarrage automatique a l'ouverture de session, pour que
#     l'application reste joignable a distance et envoie ses resumes.
# =============================================================================

$ErrorActionPreference = 'Stop'
$Racine = Split-Path -Parent $PSScriptRoot
Set-Location $Racine

# Version embarquee utilisee lorsque Python est absent du poste.
$VersionPython = '3.11.9'
$Architecture  = if ([Environment]::Is64BitOperatingSystem) { 'amd64' } else { 'win32' }
$UrlPython     = "https://www.python.org/ftp/python/$VersionPython/python-$VersionPython-embed-$Architecture.zip"
$DossierRuntime = Join-Path $Racine 'runtime'

function Etape($texte)   { Write-Host "  -> $texte" -ForegroundColor Cyan }
function Succes($texte)  { Write-Host "  OK  $texte" -ForegroundColor Green }
function Avert($texte)   { Write-Host "  !   $texte" -ForegroundColor Yellow }
function Echec($texte)   { Write-Host "  X   $texte" -ForegroundColor Red }

function Test-Python($chemin) {
    try {
        $sortie = & $chemin -c "import sys,sqlite3;print(sys.version_info[0],sys.version_info[1])" 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $sortie) { return $false }
        $parties = $sortie.Trim() -split ' '
        return ([int]$parties[0] -eq 3 -and [int]$parties[1] -ge 9)
    } catch { return $false }
}

function Trouve-Python {
    # Runtime deja installe par ce script : on le privilegie, il est maitrise.
    $embarque = Join-Path $DossierRuntime 'python.exe'
    if ((Test-Path $embarque) -and (Test-Python $embarque)) { return $embarque }

    foreach ($candidat in @('py', 'python3', 'python')) {
        $commande = Get-Command $candidat -ErrorAction SilentlyContinue
        if (-not $commande) { continue }
        $chemin = $commande.Source
        if ($candidat -eq 'py') {
            try {
                $reel = (& py -3 -c "import sys;print(sys.executable)" 2>$null)
                if ($LASTEXITCODE -eq 0 -and $reel) { $chemin = $reel.Trim() }
            } catch { continue }
        }
        if (Test-Python $chemin) { return $chemin }
    }
    return $null
}

function Installe-PythonEmbarque {
    Etape "Telechargement de Python $VersionPython (environ 11 Mo)..."
    $archive = Join-Path $env:TEMP "python-embed-$VersionPython.zip"
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $UrlPython -OutFile $archive -UseBasicParsing
    } catch {
        Echec "Telechargement impossible : $($_.Exception.Message)"
        Write-Host ""
        Write-Host "  Deux solutions :" -ForegroundColor Yellow
        Write-Host "   - verifiez la connexion Internet puis relancez ce fichier ;"
        Write-Host "   - ou installez Python depuis https://www.python.org/downloads/"
        Write-Host "     en cochant « Add Python to PATH », puis relancez."
        throw
    }

    Etape 'Installation du moteur dans le dossier de l''application...'
    if (Test-Path $DossierRuntime) { Remove-Item $DossierRuntime -Recurse -Force }
    Expand-Archive -Path $archive -DestinationPath $DossierRuntime -Force
    Remove-Item $archive -Force

    # Le fichier ._pth restreint les chemins d'import : on y ajoute la racine
    # de l'application pour que « noyau » et « modules » soient trouves.
    Get-ChildItem $DossierRuntime -Filter 'python*._pth' | ForEach-Object {
        $contenu = Get-Content $_.FullName
        if ($contenu -notcontains '..') { Add-Content $_.FullName "`n.." }
    }

    $exe = Join-Path $DossierRuntime 'python.exe'
    if (-not (Test-Python $exe)) {
        Echec 'Le moteur telecharge ne fonctionne pas sur ce poste.'
        throw 'runtime invalide'
    }
    Succes "Python $VersionPython installe (uniquement pour cette application)."
    return $exe
}

function Cree-Raccourci($python) {
    $bureau = [Environment]::GetFolderPath('Desktop')
    $lien = Join-Path $bureau 'Cabinet Immo.lnk'
    $shell = New-Object -ComObject WScript.Shell
    $raccourci = $shell.CreateShortcut($lien)
    $raccourci.TargetPath = $python
    $raccourci.Arguments = '"' + (Join-Path $Racine 'app.py') + '"'
    $raccourci.WorkingDirectory = $Racine
    $raccourci.Description = 'Comptabilite agence et promotion immobilieres'
    $raccourci.WindowStyle = 7          # demarre reduit dans la barre des taches
    $icone = Join-Path $Racine 'web\icone.ico'
    if (Test-Path $icone) { $raccourci.IconLocation = $icone }
    $raccourci.Save()
    Succes "Raccourci « Cabinet Immo » cree sur le Bureau."
    return $lien
}

function Configure-Demarrage($lien) {
    $demarrage = [Environment]::GetFolderPath('Startup')
    $cible = Join-Path $demarrage 'Cabinet Immo.lnk'
    Copy-Item $lien $cible -Force
    Succes 'Demarrage automatique active a l''ouverture de session.'
}

function Ecrit-Lanceur($python) {
    # Lanceur fige sur le moteur retenu : plus rapide et insensible aux
    # changements de PATH.
    $contenu = @"
@echo off
REM Genere par l'installateur - lance Cabinet Immo
cd /d "%~dp0"
start "" "$python" "%~dp0app.py" %*
"@
    Set-Content -Path (Join-Path $Racine 'DEMARRER.bat') -Value $contenu -Encoding ASCII
    $contenuMaj = @"
@echo off
REM Genere par l'installateur - met a jour Cabinet Immo
cd /d "%~dp0"
"$python" "%~dp0outils\mise_a_jour.py" %*
pause
"@
    Set-Content -Path (Join-Path $Racine 'METTRE-A-JOUR.bat') -Value $contenuMaj -Encoding ASCII
}

# ----------------------------------------------------------------------------
try {
    Etape 'Recherche de Python sur ce poste...'
    $python = Trouve-Python
    if ($python) {
        Succes "Python trouve : $python"
    } else {
        Avert 'Aucun Python compatible trouve. Installation du moteur embarque.'
        $python = Installe-PythonEmbarque
    }

    Etape 'Verification de l''application...'
    $verif = & $python (Join-Path $Racine 'app.py') --verifier 2>&1
    if ($LASTEXITCODE -gt 1) {
        Echec 'L''application ne demarre pas correctement :'
        Write-Host $verif
        throw 'verification echouee'
    }
    Succes 'Application prete.'

    Ecrit-Lanceur $python
    $lien = Cree-Raccourci $python

    Write-Host ''
    $reponse = Read-Host '  Demarrer Cabinet Immo automatiquement a chaque ouverture de session ? (O/n)'
    if ($reponse -eq '' -or $reponse -match '^[oOyY]') {
        Configure-Demarrage $lien
    } else {
        Avert 'Demarrage automatique non active. Utilisez le raccourci du Bureau.'
    }

    Write-Host ''
    Write-Host '  ============================================================' -ForegroundColor Green
    Write-Host '    Installation terminee' -ForegroundColor Green
    Write-Host '  ============================================================' -ForegroundColor Green
    Write-Host ''
    Write-Host "    Vos donnees seront enregistrees dans :"
    Write-Host "    $(Join-Path $Racine 'donnees')"
    Write-Host ''
    Write-Host '    Pour ouvrir l''application : double-cliquez sur le raccourci'
    Write-Host '    « Cabinet Immo » du Bureau.'
    Write-Host ''
    Write-Host '    Pour mettre a jour plus tard : METTRE-A-JOUR.bat'
    Write-Host ''

    $lancer = Read-Host '  Ouvrir l''application maintenant ? (O/n)'
    if ($lancer -eq '' -or $lancer -match '^[oOyY]') {
        Start-Process -FilePath $python -ArgumentList "`"$(Join-Path $Racine 'app.py')`"" -WorkingDirectory $Racine
    }
    exit 0
} catch {
    Write-Host ''
    Echec $_.Exception.Message
    exit 1
}
