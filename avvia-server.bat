@echo off
chcp 65001 >nul
cd /d "%~dp0"
title TransferBeat - server locale

echo ============================================
echo    TransferBeat - server locale
echo --------------------------------------------
echo  Apro il sito su http://localhost:8000
echo  Per FERMARE il server: chiudi questa finestra
echo ============================================
echo.

REM Apri il browser dopo 2 secondi (il tempo che il server parta)
start "" cmd /c "timeout /t 2 >nul & start http://localhost:8000/index.html"

REM Avvia il server: prova prima 'py', poi 'python'
where py >nul 2>nul
if %errorlevel%==0 (
    py -m http.server 8000
) else (
    python -m http.server 8000
)

REM Se arriva qui, Python non e' stato trovato
echo.
echo [!] Python non trovato. Installalo da https://www.python.org/downloads/
echo     ricordando di spuntare "Add Python to PATH".
pause
