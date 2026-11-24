# MC0 checkpoint - Laptop B (docs/02 sec.7). Run from repo root on main after merging b/work + a/work:
#   .\scripts\cp0_b.ps1                                   # core install + tests + golden SHA + test vectors
#   .\scripts\cp0_b.ps1 -BatchFromA <batch.json> -PubFromA contract\meters\M-07.pub.json   # + verify A's batch
param(
    [string]$BatchFromA = "",
    [string]$PubFromA = ""
)
$ErrorActionPreference = "Continue"
Set-Location (Split-Path $PSScriptRoot -Parent)
. .\.venv\Scripts\Activate.ps1
$fail = 0

Write-Host "== 1. install core" -ForegroundColor Cyan
pip install -q -e core -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { $fail++ }

Write-Host "== 2. all core tests (A's + B's)" -ForegroundColor Cyan
python -m pytest core -q
if ($LASTEXITCODE -ne 0) { $fail++ }

Write-Host "== 3. golden SHA of extract_peaks (compare with Laptop A)" -ForegroundColor Cyan
python -m server.tools.golden_sha
if ($LASTEXITCODE -eq 3) { Write-Host "   (waiting for A-T01 - not counted as failure yet)" -ForegroundColor Yellow }
elseif ($LASTEXITCODE -ne 0) { $fail++ }

Write-Host "== 4. contract test vectors" -ForegroundColor Cyan
python -m server.tools.check_batch contract\fixtures\batches\tv_batch_valid.json contract\fixtures\batches\tv_keys.json
if ($LASTEXITCODE -ne 0) { $fail++ }

if ($BatchFromA -ne "") {
    Write-Host "== 5. batch signed on Laptop A" -ForegroundColor Cyan
    python -m server.tools.check_batch $BatchFromA $PubFromA
    if ($LASTEXITCODE -ne 0) { $fail++ }
}

if ($fail -eq 0) { Write-Host "CP0 (B): GREEN" -ForegroundColor Green; exit 0 }
Write-Host "CP0 (B): $fail step(s) FAILED" -ForegroundColor Red
exit 1
