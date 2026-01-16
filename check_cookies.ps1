$cookiesPath = "$env:LOCALAPPDATA\Microsoft\Edge\User Data\Default\Network\Cookies"
Write-Host "Sciezka: $cookiesPath"
if (Test-Path $cookiesPath) {
    Write-Host "Plik istnieje, rozmiar:" (Get-Item $cookiesPath).Length
} else {
    Write-Host "Plik nie istnieje"
}

# Sprawdz wszystkie profile
Get-ChildItem "$env:LOCALAPPDATA\Microsoft\Edge\User Data\*\Network\Cookies" -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "Znaleziono: $($_.FullName) ($($_.Length) bytes)"
}
