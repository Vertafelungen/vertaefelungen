# stop-hugo.ps1
# Version: 2025-10-03 20:05 CEST
$ErrorActionPreference = "SilentlyContinue"
Get-Process hugo | Stop-Process -Force
Write-Host "Hugo (falls vorhanden) beendet."
