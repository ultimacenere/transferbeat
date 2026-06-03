@echo off
chcp 65001 >nul
cd /d "%~dp0"
title TransferBeat - carica modifiche su GitHub

where git >nul 2>nul
if not %errorlevel%==0 (
  echo [!] Git non e' installato. Usa prima pubblica.bat.
  pause & exit /b
)

echo Carico le modifiche su GitHub...
git add .
git commit -m "aggiornamento"
git push

echo.
echo Fatto (se non ci sono errori in rosso). Vercel ripubblica da solo tra poco.
pause
