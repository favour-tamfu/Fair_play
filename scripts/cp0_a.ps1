# MC0 checkpoint — Laptop A (docs/02 §7). Run from repo root on a/work after merging b/work:
#   .\scripts\cp0_a.ps1
# Steps: install core, run A + B core tests and device tests, print golden SHA,
# build one batch signed with the real M-07 key, and check it with B's check_batch.
$ErrorActionPreference = "Continue"
Set-Location (Split-Path $PSScriptRoot -Parent)
. .\.venv\Scripts\Activate.ps1
$fail = 0

Write-Host "== 1. install core and device requirements" -ForegroundColor Cyan
pip install -q -e core -r device\requirements.txt
if ($LASTEXITCODE -ne 0) { $fail++ }

Write-Host "== 2. core and device tests" -ForegroundColor Cyan
python -m pytest core device -q
if ($LASTEXITCODE -ne 0) { $fail++ }

Write-Host "== 3. golden SHA (compare with Laptop B) and batch signed with M-07" -ForegroundColor Cyan
python scripts\cp0_a.py
if ($LASTEXITCODE -ne 0) { $fail++ }

Write-Host "== 4. B's checker verifies A's batch with M-07 public key" -ForegroundColor Cyan
python -m server.tools.check_batch data\cp0\batch_M07.json contract\meters\M-07.pub.json
if ($LASTEXITCODE -ne 0) { $fail++ }

if ($fail -eq 0) { Write-Host "CP0 (A): GREEN" -ForegroundColor Green; exit 0 }
Write-Host "CP0 (A): $fail step(s) FAILED" -ForegroundColor Red
exit 1
