@echo off
chcp 65001 >nul
cd /d "%~dp0"
title TransferBeat - aggiorna dati

REM Sceglie il comando Python disponibile
where py >nul 2>nul
if %errorlevel%==0 (set "PY=py") else (set "PY=python")

echo ============================================
echo    TransferBeat - aggiornamento dati
echo ============================================
echo.

REM Chiave LLM opzionale per la vista "Nomi": se esiste groq_key.txt la legge
if exist groq_key.txt (
    set /p GROQ_API_KEY=<groq_key.txt
    echo Vista Nomi: chiave LLM trovata, estrazione movimenti ATTIVA.
) else (
    echo Vista Nomi: nessuna chiave ^(groq_key.txt^) - solo Notizie. Vedi README.
)
echo.
echo [1/2] Controllo dipendenze...
%PY% -m pip install -r requirements.txt
echo.
echo [2/2] Scarico e classifico le notizie...
%PY% scripts\build.py
echo.
echo Fatto. I file data\board.json e data\home.json sono aggiornati.
echo Aggiorna la pagina nel browser per vedere le novita.
echo.
pause
