# Różne metody kopiowania zablokowanego pliku

$source = "$env:LOCALAPPDATA\Microsoft\Edge\User Data\Default\Network\Cookies"
$destDir = $env:TEMP
$destFile = "$destDir\cookies_test"

Write-Host "=== Test kopiowania ==="

# Metoda 1: robocopy (kopiuje bajt-po-bajcie)
Write-Host "`n1. Robocopy..."
$result = robocopy "$env:LOCALAPPDATA\Microsoft\Edge\User Data\Default\Network" $destDir "Cookies" /COPY:D 2>&1
if (Test-Path "$destDir\Cookies") {
    $size = (Get-Item "$destDir\Cookies").Length
    Write-Host "   Robocopy: $size bytes"
    Remove-Item "$destDir\Cookies" -Force
}

# Metoda 2: xcopy
Write-Host "`n2. Xcopy..."
xcopy $source $destFile /Y 2>&1 | Out-Null
if (Test-Path $destFile) {
    $size = (Get-Item $destFile).Length
    Write-Host "   Xcopy: $size bytes"
    Remove-Item $destFile -Force
}

# Metoda 3: .NET FileStream z Read sharing
Write-Host "`n3. FileStream Read+Delete..."
try {
    $fs = [System.IO.File]::Open($source,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read,
        [System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete)
    $len = $fs.Length
    Write-Host "   FileStream Length: $len bytes"

    if ($len -gt 0) {
        $buffer = New-Object byte[] $len
        $read = $fs.Read($buffer, 0, $len)
        $fs.Close()
        [System.IO.File]::WriteAllBytes($destFile, $buffer)
        $size = (Get-Item $destFile).Length
        Write-Host "   Zapisano: $size bytes"
        Remove-Item $destFile -Force
    } else {
        $fs.Close()
        Write-Host "   Plik pusty (dane w pamieci Edge)"
    }
} catch {
    Write-Host "   Blad: $_"
}

# Metoda 4: cmd copy
Write-Host "`n4. CMD copy..."
cmd /c "copy `"$source`" `"$destFile`"" 2>&1 | Out-Null
if (Test-Path $destFile) {
    $size = (Get-Item $destFile).Length
    Write-Host "   CMD copy: $size bytes"
    Remove-Item $destFile -Force
}
