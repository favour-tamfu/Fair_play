# Quick test run for Laptop A (Agent A). Run from the repo root.
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
& .\.venv\Scripts\Activate.ps1
# core/tests/test_peaks.py and device/tests are added by A-T01 and A-T02+; skip paths that do not exist yet.
$targets = @('core/tests/test_peaks.py', 'device/tests', 'tools/mockgen/tests') | Where-Object { Test-Path $_ }
if (-not $targets) { Write-Host 'No test paths exist yet.'; exit 0 }
pytest @targets -q
exit $LASTEXITCODE
