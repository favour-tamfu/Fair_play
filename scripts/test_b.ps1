# Agent B quick tests (docs/02 sec.3 step 5). Run from repo root: .\scripts\test_b.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
. .\.venv\Scripts\Activate.ps1
$targets = @("core/tests/test_schema.py", "core/tests/test_signing.py", "core/tests/test_landmarks.py", "core/tests/test_contract_schemas.py", "core/tests/test_vectors.py", "server/tests") | Where-Object { Test-Path $_ }
if ($targets.Count -eq 0) { Write-Host "test_b: no B tests exist yet"; exit 0 }
# The web pages are ES modules: check that every page script parses (a syntax error blanks a whole page). Needs Node.
$webFail = 0
if (Get-Command node -ErrorAction SilentlyContinue) {
    foreach ($f in Get-ChildItem web\js\*.js) {
        Get-Content $f.FullName -Raw | node --input-type=module --check 2>$null
        if ($LASTEXITCODE -ne 0) { Write-Host "web script does not parse: $($f.Name)" -ForegroundColor Red; $webFail = 1 }
    }
    if (-not $webFail) { Write-Host "web scripts: all parse as modules" }
} else { Write-Host "web scripts: not checked (Node is not installed)" }
python -m pytest @targets -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
exit $webFail
