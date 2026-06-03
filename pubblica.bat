@echo off
chcp 65001 >nul
cd /d "%~dp0"
title TransferBeat - pubblica su GitHub

where git >nul 2>nul
if not %errorlevel%==0 (
  echo [!] Git non e' installato.
  echo     Scaricalo da https://git-scm.com/download/win  poi rilancia questo file.
  pause & exit /b
)

echo ============================================
echo    TransferBeat - primo caricamento su GitHub
echo ============================================
echo.
echo PRIMA crea un repository VUOTO su github.com
echo  (niente README, niente .gitignore: lasciali deselezionati).
echo Poi copia il suo indirizzo, es:
echo    https://github.com/tuonome/transferbeat.git
echo.
set /p REPO=Incolla qui l'indirizzo del repository e premi Invio:
if "%REPO%"=="" (echo. & echo Nessun indirizzo inserito. Esco. & pause & exit /b)

echo.
echo Carico i file su GitHub...
git init
git config user.name "ultimacenere"
git config user.email "ultimacenere@users.noreply.github.com"
git add .
git commit -m "TransferBeat - primo commit"
git branch -M main
git remote remove origin 2>nul
git remote add origin %REPO%
git push -u origin main

echo.
echo ============================================
echo  Se sopra non ci sono errori in rosso, il codice e' online su GitHub.
echo  Prossimo passo: vai su vercel.com, importa il repo e premi Deploy.
echo  Tutti i dettagli (Vercel, dominio, chiave LLM) sono in DEPLOY.md
echo ============================================
echo.
echo  Per i prossimi aggiornamenti manuali del codice baster\340:
echo     git add .  ^&^&  git commit -m "modifiche"  ^&^&  git push
pause
