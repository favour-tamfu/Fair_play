# Network check for Laptop A (A-T08, plan section 3). Run from the repo root.
#   .\scripts\netcheck.ps1                                  # default http://192.168.137.1:8000
#   .\scripts\netcheck.ps1 -Url http://192.168.137.1:8000
param(
    [string]$Url = "http://192.168.137.1:8000"
)
$ErrorActionPreference = "Continue"
$fail = 0
$uri = [Uri]$Url

Write-Host "== 1. TCP reachability of $($uri.Host):$($uri.Port)" -ForegroundColor Cyan
$tcp = Test-NetConnection -ComputerName $uri.Host -Port $uri.Port -WarningAction SilentlyContinue
if ($tcp.TcpTestSucceeded) { Write-Host "   OK" -ForegroundColor Green } else { Write-Host "   FAILED: cannot reach $($uri.Host):$($uri.Port)" -ForegroundColor Red; $fail++ }

Write-Host "== 2. $Url/health" -ForegroundColor Cyan
try {
    $h = Invoke-RestMethod -Uri "$Url/health" -TimeoutSec 5
    Write-Host "   ok=$($h.ok) server_time=$($h.server_time)" -ForegroundColor Green
} catch {
    Write-Host "   FAILED: $($_.Exception.Message)" -ForegroundColor Red
    $fail++
}

Write-Host "== 3. network profile of the hotspot connection (must be Private)" -ForegroundColor Cyan
$profiles = Get-NetConnectionProfile -ErrorAction SilentlyContinue
foreach ($p in $profiles) { Write-Host "   $($p.InterfaceAlias): $($p.NetworkCategory)" }
$private = $profiles | Where-Object { $_.NetworkCategory -eq "Private" }
if (-not $private) {
    Write-Host "   Not Private. Fix (admin PowerShell):" -ForegroundColor Yellow
    Write-Host "   Set-NetConnectionProfile -InterfaceAlias ""<alias above>"" -NetworkCategory Private" -ForegroundColor Yellow
}

if ($fail -eq 0) { Write-Host "NETCHECK: GREEN" -ForegroundColor Green; exit 0 }
Write-Host "NETCHECK: $fail step(s) FAILED" -ForegroundColor Red
exit 1
