@echo off
chcp 65001 >nul
cd /d "%~dp0"
title TransferBeat - carica modifiche su GitHub

where git >nul 2>nul
if not %errorlevel%==0 (
  echo [!] Git non e' installato. Usa prima pubblica.bat.
  pause & exit /b
)

echo Controllo anti-troncamento dei file sorgente...
if not defined TB_FORCE (
  python scripts\guard.py
  if errorlevel 1 (
    echo.
    echo Caricamento ANNULLATO. Nessuna modifica inviata.
    pause & exit /b
  )
) else (
  echo [TB_FORCE attivo] guard saltato.
)

echo Carico le modifiche su GitHub...
git add .
git commit -m "aggiornamento"
echo Sincronizzo con eventuali aggiornamenti automatici del bot...
git pull --rebase origin main
git push

echo.
echo Fatto (se non ci sono errori in rosso). Vercel ripubblica da solo tra poco.
pause
