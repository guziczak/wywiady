# Tworzy skrót Edge z remote debugging na pulpicie

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\Edge (Wywiad+).lnk")

# Znajdź Edge
$edgePath = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if (-not (Test-Path $edgePath)) {
    $edgePath = "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
}

$Shortcut.TargetPath = $edgePath
$Shortcut.Arguments = "--remote-debugging-port=9222"
$Shortcut.WorkingDirectory = Split-Path $edgePath
$Shortcut.Description = "Edge z remote debugging dla aplikacji Wywiad+"
$Shortcut.IconLocation = "$edgePath,0"
$Shortcut.Save()

Write-Host "Utworzono skrot: $env:USERPROFILE\Desktop\Edge (Wywiad+).lnk"
Write-Host ""
Write-Host "INSTRUKCJA:"
Write-Host "1. Zamknij wszystkie okna Edge"
Write-Host "2. Uruchom Edge z tego skrotu (na pulpicie)"
Write-Host "3. Kliknij 'Auto' w aplikacji Wywiad+"
