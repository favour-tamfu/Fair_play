# Open port 8000 for the Fair Play server on PRIVATE networks only (hotspot). Run in an ADMIN PowerShell:
#   powershell -ExecutionPolicy Bypass -File .\scripts\firewall_b.ps1
# Remove later with: Remove-NetFirewallRule -DisplayName "Fair Play 8000"
$name = "Fair Play 8000"
if (Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue) {
    Write-Host "Firewall rule '$name' already exists." -ForegroundColor Yellow
} else {
    New-NetFirewallRule -DisplayName $name -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private | Out-Null
    Write-Host "Firewall rule '$name' created (TCP 8000 inbound, Private profile only)." -ForegroundColor Green
}
Write-Host "Network profiles (the hotspot / shared network must be Private):"
Get-NetConnectionProfile | Format-Table InterfaceAlias, Name, NetworkCategory -AutoSize
