$base = "$env:LOCALAPPDATA\Microsoft\Edge\User Data\Default\Network"
Get-ChildItem $base -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "$($_.Name): $($_.Length) bytes"
}
