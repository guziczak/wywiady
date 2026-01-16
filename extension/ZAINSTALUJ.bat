@echo off
chcp 65001 >nul
echo.
echo ══════════════════════════════════════════════════════
echo   INSTALACJA ROZSZERZENIA WYWIAD+ (30 sekund)
echo ══════════════════════════════════════════════════════
echo.
echo   1. Otworze strone rozszerzen Edge
echo   2. Wlacz "Tryb dewelopera" (lewy dolny rog)
echo   3. Kliknij "Zaladuj rozpakowane"
echo   4. Wybierz folder ktory sie otworzy
echo.
echo ══════════════════════════════════════════════════════
echo.
pause

:: Otwórz stronę rozszerzeń Edge
start msedge edge://extensions/

:: Poczekaj chwilę
timeout /t 2 /nobreak >nul

:: Otwórz folder z rozszerzeniem w eksploratorze
explorer "%~dp0"

echo.
echo Gotowe! Teraz:
echo   1. Wlacz "Tryb dewelopera" w Edge
echo   2. Kliknij "Zaladuj rozpakowane"
echo   3. Wybierz otwarty folder
echo.
pause
