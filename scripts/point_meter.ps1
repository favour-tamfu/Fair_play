# Point an existing meter (the Python agent in this repo, e.g. M-07) at a new SONACAM address, e.g. the public one.
#
#   powershell -ExecutionPolicy Bypass -File .\scripts\point_meter.ps1 -Url https://<public address> [-Meter M-07]
#
# Changes only sonacam_url in device\config\<Meter>.toml (this laptop's copy; do not commit it), checks that the server
# answers, and says how to restart the meter. The meter keeps its key and its numbering; nothing is re-registered.
param(
    [Parameter(Mandatory = $true)][string]$Url,
    [string]$Meter = "M-07"
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$cfg = Join-Path $root "device\config\$Meter.toml"
if (-not (Test-Path $cfg)) { Write-Host "No config for $Meter at $cfg" -ForegroundColor Red; exit 1 }
$Url = $Url.TrimEnd('/')
try {
    $h = Invoke-WebRequest "$Url/health" -UseBasicParsing -TimeoutSec 20
    Write-Host "OK  $Url answers (HTTP $($h.StatusCode))" -ForegroundColor Green
} catch {
    Write-Host "STOPPED: $Url does not answer ($($_.Exception.Message)). Nothing changed." -ForegroundColor Red; exit 1
}
$text = Get-Content $cfg -Raw
$old = [regex]::Match($text, '(?m)^sonacam_url\s*=\s*"([^"]*)"').Groups[1].Value
$new = [regex]::Replace($text, '(?m)^sonacam_url\s*=\s*"[^"]*"', "sonacam_url = `"$Url`"")
[IO.File]::WriteAllText($cfg, $new, (New-Object System.Text.UTF8Encoding $false))
Write-Host "OK  $Meter now sends to $Url (was $old)"
Write-Host "Now restart the meter: stop it (Ctrl+C in its window), then start it again the way you usually do."
Write-Host "Reports made while it was stopped wait in its outbox and are sent after the restart."
