# MC1 checkpoint — Laptop A (docs/02 §7). Run from the repo root on a/work after merging main.
#   .\scripts\cp1_a.ps1 -Url http://192.168.137.1:8000 -Config device\config\M-07.toml
# Steps: device and core tests, network check to B, then the agent in demo mode against B.
# The live-song and network-cut parts of the joint test are done by hand (plan 02 §7, MC1 row).
param(
    [string]$Url = "http://192.168.137.1:8000",
    [string]$Config = "device\config\M-07.toml"
)
$ErrorActionPreference = "Continue"
$fail = 0
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host "== 1. core and device tests" -ForegroundColor Cyan
& .\.venv\Scripts\python.exe -m pytest core device -q
if ($LASTEXITCODE -ne 0) { $fail++ }

Write-Host "== 2. network check to Laptop B" -ForegroundColor Cyan
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\netcheck.ps1 -Url $Url
if ($LASTEXITCODE -ne 0) { $fail++ }

Write-Host "== 3. agent in demo mode against B (Ctrl+C to stop)" -ForegroundColor Cyan
& .\.venv\Scripts\python.exe -m device.agent run --config $Config --mode demo
if ($LASTEXITCODE -ne 0) { $fail++ }

if ($fail -eq 0) { Write-Host "CP1 (A) prep: GREEN — now run the joint test with B" -ForegroundColor Green; exit 0 }
Write-Host "CP1 (A) prep: $fail step(s) FAILED" -ForegroundColor Red
exit 1
