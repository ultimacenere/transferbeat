@echo off
chcp 65001 >nul
cd /d "%~dp0"
title TransferBeat - pubblica ora (push diretto)

echo Invio a GitHub il commit gia' pronto e verificato...
git push origin main

echo.
echo Se sopra non ci sono errori in rosso, e' fatto: Vercel ripubblica tra poco.
pause
