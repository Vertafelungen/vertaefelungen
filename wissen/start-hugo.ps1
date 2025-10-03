# start-hugo.ps1
# Version: 2025-10-03 20:05 CEST
$ErrorActionPreference = "Stop"
Set-Location "C:\Users\Administrator\vertaefelungen\wissen"

# freien Port wählen (1313, sonst 1314)
$port = 1313
try {
  $tcp = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Parse("127.0.0.1"), $port)
  $tcp.Start(); $tcp.Stop()
} catch {
  Write-Host "Port $port ist belegt → wechsle auf 1314"
  $port = 1314
}

# Dev-Config verwenden
hugo server --config "hugo.dev.toml" -D --navigateToChanged --disableFastRender --printPathWarnings --port $port
