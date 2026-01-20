@echo off
chcp 65001 >nul
title Wizyta - Instalator rozszerzenia

echo ============================================================
echo   WIZYTA - AUTOMATYCZNA INSTALACJA ROZSZERZENIA
echo ============================================================
echo.
echo Ten skrypt:
echo   1. Zainstaluje rozszerzenie do Edge (przez Registry)
echo   2. Otworzy claude.ai
echo   3. Pobierze klucz sesji automatycznie
echo   4. Posprzata po sobie (usunie rozszerzenie i wpisy Registry)
echo.
echo WYMAGANIA:
echo   - Uruchom jako Administrator
echo   - Aplikacja Wizyta musi byc wlaczona
echo.
pause

cd /d "%~dp0"
python installer.py

if errorlevel 1 (
    echo.
    echo BLAD: Python nie jest zainstalowany lub wystapil blad.
    pause
)
