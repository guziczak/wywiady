@echo off
setlocal EnableDelayedExpansion

:: --- KONFIGURACJA ---
set "REPO_URL=https://github.com/guziczak/wywiady/archive/refs/heads/main.zip"
set "APP_NAME=AsystentMedyczny"
set "INSTALL_DIR=%LOCALAPPDATA%\%APP_NAME%"
set "SHORTCUT_NAME=Asystent Medyczny.lnk"
set "MAIN_SCRIPT=stomatolog_nicegui.py"

title Instalator - %APP_NAME%
echo ========================================================
echo   INSTALATOR ASYSTENTA MEDYCZNEGO
echo ========================================================
echo.

:: 1. SPRAWDZENIE PYTHONA
echo [*] Sprawdzanie instalacji Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Nie znaleziono Pythona!
    echo.
    echo Prosze zainstalowac Python 3.10 lub nowszy ze strony python.org.
    echo Pamiętaj, aby zaznaczyc opcje "Add Python to PATH" podczas instalacji.
    echo.
    echo Otwieram strone pobierania...
    start https://www.python.org/downloads/
    pause
    exit /b
)
echo [OK] Python wykryty.

:: 2. PRZYGOTOWANIE KATALOGU
echo [*] Przygotowanie katalogu: %INSTALL_DIR%
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
cd /d "%INSTALL_DIR%"

:: 3. POBIERANIE I ROZPAKOWANIE (Jeśli nie ma plików lub wymuszamy aktualizację)
:: Prostota: na razie pobieramy zawsze, aby zaktualizować kod.
echo [*] Pobieranie najnowszej wersji aplikacji...

powershell -Command "Invoke-WebRequest -Uri '%REPO_URL%' -OutFile 'repo.zip'"
if %errorlevel% neq 0 (
    echo [!] Blad pobierania. Sprawdz polaczenie internetowe.
    pause
    exit /b
)

echo [*] Rozpakowywanie...
powershell -Command "Expand-Archive -Path 'repo.zip' -DestinationPath '.' -Force"
del repo.zip

:: GitHub zip rozpakowuje sie do folderu wywiady-main. Przenosimy zawartosc wyzej.
if exist "wywiady-main" (
    xcopy /E /Y "wywiady-main\*" "." >nul
    rmdir /S /Q "wywiady-main"
)

:: 4. KONFIGURACJA VENV (Wirtualne Srodowisko)
if not exist "venv" (
    echo [*] Tworzenie wirtualnego srodowiska Python (pierwsze uruchomienie, to moze potrwac)...
    python -m venv venv
)

:: 5. INSTALACJA ZALEZNOSCI
echo [*] Aktualizacja bibliotek (pip)...
call venv\Scripts\activate.bat
pip install --upgrade pip >nul
echo     Instalowanie requirements.txt...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [!] Blad instalacji bibliotek.
    pause
    exit /b
)

:: 6. TWORZENIE SKRÓTU NA PULPICIE (PowerShell)
set "TARGET_SCRIPT=%INSTALL_DIR%\run_app.bat"
:: Tworzymy pomocniczy bat do uruchamiania z venv bezposrednio
(
echo @echo off
echo cd /d "%INSTALL_DIR%"
echo call venv\Scripts\activate.bat
echo python %MAIN_SCRIPT%
echo pause
) > "%TARGET_SCRIPT%"

echo [*] Tworzenie skrotu na pulpicie...
set "DESKTOP_DIR=%USERPROFILE%\Desktop"
set "ICON_PATH=%INSTALL_DIR%\extension\icon.png"

powershell "$s=(New-Object -COM WScript.Shell).CreateShortcut('%DESKTOP_DIR%\%SHORTCUT_NAME%');$s.TargetPath='%TARGET_SCRIPT%';$s.WorkingDirectory='%INSTALL_DIR%';$s.IconLocation='%ICON_PATH%';$s.Save()"

echo.
echo ========================================================
echo   INSTALACJA ZAKONCZONA SUKCESEM!
echo ========================================================
echo.
echo Aplikacja zostanie uruchomiona za chwile.
echo Skrot "%SHORTCUT_NAME%" zostal utworzony na pulpicie.
echo.
timeout /t 5

:: 7. URUCHOMIENIE
call "%TARGET_SCRIPT%"
