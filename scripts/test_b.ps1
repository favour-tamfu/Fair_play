# Agent B quick tests (docs/02 sec.3 step 5). Run from repo root: .\scripts\test_b.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
. .\.venv\Scripts\Activate.ps1
$targets = @("core/tests/test_schema.py", "core/tests/test_signing.py", "core/tests/test_landmarks.py", "core/tests/test_contract_schemas.py", "core/tests/test_vectors.py", "server/tests") | Where-Object { Test-Path $_ }
if ($targets.Count -eq 0) { Write-Host "test_b: no B tests exist yet"; exit 0 }
python -m pytest @targets -q
exit $LASTEXITCODE
