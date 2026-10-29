@echo off
title English Class Monitor & Transcriber
cd /d "%~dp0"
echo ==================================================================
echo   English Class Monitor (Padrao BotTonho / AulasDescomplica)
echo ==================================================================
echo.
echo Iniciando ambiente virtual e servidor...
call .venv\Scripts\activate.bat
python app.py
pause
