@echo off
chcp 65001 >nul
title TransferBeat - svuota cache DNS

echo ============================================
echo    Svuoto la cache DNS del PC...
echo ============================================
ipconfig /flushdns
echo.
echo Fatto. Provo ad aprire transferbeat.com...
start "" https://transferbeat.com
echo.
echo Se ancora non si vede:
echo  - riavvia il router di casa (spento 30 secondi, poi riacceso)
echo  - oppure riprova tra qualche minuto.
echo.
pause
