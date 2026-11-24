# MC1 checkpoint - Laptop B (docs/02 sec.7). Run from repo root on main:
#   .\scripts\cp1_b.ps1 -Songs data\song1.wav,data\song2.mp3,data\song3.wav
# Brings the stack up, checks health, uploads the demo songs (waits for ready), runs the fixture batches.
param([string[]]$Songs = @())
$ErrorActionPreference = "Continue"
Set-Location (Split-Path $PSScriptRoot -Parent)
. .\.venv\Scripts\Activate.ps1
$fail = 0

Write-Host "== 1. stack up" -ForegroundColor Cyan
docker compose up -d --build
for ($i = 0; $i -lt 60; $i++) {
    try { $h = Invoke-RestMethod http://localhost:8000/health -TimeoutSec 2; if ($h.db) { break } } catch { }
    Start-Sleep -Seconds 1
}
docker compose ps --format "table {{.Service}}\t{{.Status}}"

Write-Host "== 2. health" -ForegroundColor Cyan
try { $h = Invoke-RestMethod http://localhost:8000/health; $h | ConvertTo-Json -Compress; if (-not $h.db) { $fail++ } }
catch { Write-Host "health FAILED: $_" -ForegroundColor Red; $fail++ }

Write-Host "== 3. tests" -ForegroundColor Cyan
.\scripts\test_b.ps1
if ($LASTEXITCODE -ne 0) { $fail++ }

Write-Host "== 4. upload demo songs" -ForegroundColor Cyan
$ownersFile = Join-Path $env:TEMP "fairplay_owners.json"   # PS 5.1 strips quotes from native args: pass JSON via a file
[IO.File]::WriteAllText($ownersFile, '[{"name":"Demo Owner","role":"singer","share_pct":100,"momo":"+237699000001"}]')
foreach ($s in $Songs) {
    $title = [IO.Path]::GetFileNameWithoutExtension($s)
    $r = curl.exe -s -F "file=@$s" -F "title=$title" -F "artist_name=Demo Artist" -F "consent=true" -F "owners=<$ownersFile" http://localhost:8000/api/v1/songs | ConvertFrom-Json
    if (-not $r.song_id) { Write-Host "upload of $s FAILED: $r" -ForegroundColor Red; $fail++; continue }
    for ($i = 0; $i -lt 60; $i++) {
        $d = Invoke-RestMethod "http://localhost:8000/api/v1/songs/$($r.song_id)"
        if ($d.status -notin @("uploaded", "processing")) { break }
        Start-Sleep -Milliseconds 500
    }
    Write-Host ("   {0} {1,-30} -> {2} ({3} hashes)" -f $r.song_id, $title, $d.status, $d.n_hashes)
    if ($d.status -notin @("ready", "duplicate_suspected")) { $fail++ }
}

Write-Host "== 5. fixture batches (test meter M-90)" -ForegroundColor Cyan
python -m server.tools.send_fixtures --count 3
if ($LASTEXITCODE -ne 0) { $fail++ }

Write-Host "== 6. catalogue ready" -ForegroundColor Cyan
(Invoke-RestMethod "http://localhost:8000/api/v1/songs?status=ready") | Format-Table song_id, title, n_hashes -AutoSize

if ($fail -eq 0) { Write-Host "CP1 (B): GREEN - now run the joint test with Laptop A (docs/02 sec.7 MC1 row)" -ForegroundColor Green; exit 0 }
Write-Host "CP1 (B): $fail step(s) FAILED" -ForegroundColor Red
exit 1
