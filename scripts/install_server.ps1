# Fair Play - install and start the SONACAM server on one Windows computer, in one command.
#
#   powershell -ExecutionPolicy Bypass -File .\scripts\install_server.ps1 [-SongPackage C:\path\to\package] [-Port 8000]
#
# What it does (safe to run again):
#   1. checks that Docker Desktop is installed and running
#   2. creates .env from .env.example with new random passwords (database, admin) if .env does not exist yet
#   3. builds and starts every part: database, API + web pages, fingerprint, matcher, play logger, scheduler
#   4. waits until the server answers
#   5. with -SongPackage: imports the songs (catalogue.csv + audio/) and waits until they are fingerprinted
#   6. runs the readiness check (demo_seed: migrations, meters, catalogue, owners, mock month, stats, play log)
#   7. prints the addresses: this computer, and the address meters on the same network use
# The admin password is ADMIN_TOKEN in .env. It is never printed: open .env to read it, and give it only to SONACAM admins.
param(
    [string]$SongPackage = "",
    [int]$Port = 0
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
function Say($text, $colour = 'Gray') { Write-Host $text -ForegroundColor $colour }
function Fail($text) { Write-Host "STOPPED: $text" -ForegroundColor Red; exit 1 }

Say "Fair Play SONACAM server - install / start" Cyan

# 1. Docker
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Fail "Docker is not installed. Install Docker Desktop (https://www.docker.com/products/docker-desktop/) and run this again." }
docker info *> $null
if ($LASTEXITCODE -ne 0) { Fail "Docker Desktop is not running. Start it, wait until it says 'Engine running', and run this again." }
Say "  OK  Docker is running"

# 2. .env with fresh secrets
function New-Secret([int]$bytes = 24) {
    $b = New-Object byte[] $bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
    return ([Convert]::ToBase64String($b) -replace '[+/=]', '')
}
if (-not (Test-Path .env)) {
    $db = New-Secret 18; $admin = New-Secret 24
    $text = (Get-Content .env.example -Raw) -replace 'change-me-too', $admin -replace 'change-me', $db
    [IO.File]::WriteAllText("$root\.env", $text, (New-Object System.Text.UTF8Encoding $false))   # no BOM
    Say "  OK  .env created with new random passwords (the admin password is ADMIN_TOKEN in .env)"
} else {
    Say "  OK  .env already exists (kept as it is)"
}
if ($Port -gt 0) {
    $t = Get-Content .env -Raw
    $t = if ($t -match '(?m)^API_PORT=') { $t -replace '(?m)^API_PORT=.*$', "API_PORT=$Port" } else { $t.TrimEnd() + "`nAPI_PORT=$Port`n" }
    [IO.File]::WriteAllText("$root\.env", $t, (New-Object System.Text.UTF8Encoding $false))
}
$apiPort = 8000
$m = Select-String -Path .env -Pattern '^API_PORT=(\d+)' | Select-Object -First 1
if ($m) { $apiPort = [int]$m.Matches[0].Groups[1].Value }
$base = "http://localhost:$apiPort"

# 3. build and start
Say "  ..  building and starting the server (the first time takes a few minutes)"
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { Fail "docker compose could not start the server (see the messages above)." }

# 4. wait for the API
$ok = $false
for ($i = 0; $i -lt 90; $i++) {
    try { if ((Invoke-WebRequest "$base/health" -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200) { $ok = $true; break } } catch { }
    Start-Sleep 2
}
if (-not $ok) { Fail "the server did not answer at $base/health within 3 minutes. See: docker compose logs api" }
Say "  OK  server answers at $base"

# 5. songs
if ($SongPackage) {
    if (-not (Test-Path (Join-Path $SongPackage 'catalogue.csv'))) { Fail "no catalogue.csv in $SongPackage" }
    $cid = (docker compose ps -q api).Trim()
    docker compose exec -T api sh -c "rm -rf /tmp/pkg" | Out-Null
    docker cp "$SongPackage" "${cid}:/tmp/pkg"
    if ($LASTEXITCODE -ne 0) { Fail "could not copy the song package into the server" }
    docker compose exec -T api python -m server.tools.import_catalogue /tmp/pkg
    if ($LASTEXITCODE -ne 0) { Fail "the song import failed (see above)" }
    New-Item -ItemType Directory -Force data | Out-Null
    docker cp "${cid}:/tmp/pkg/song_map.csv" data\song_map.csv | Out-Null   # package id -> server id; the package is left untouched
    Say "  ..  fingerprinting the songs (about 2 minutes per 60 songs)"
    docker compose exec -T api python -m server.tools.wait_fingerprints
    if ($LASTEXITCODE -ne 0) { Fail "fingerprinting did not finish (see: docker compose logs worker_fp)" }
    Say "  OK  songs imported and fingerprinted"
}

# 6. readiness check
Say "  ..  readiness check"
docker compose exec -T api python -m server.tools.demo_seed --url "http://localhost:8000"
$ready = $LASTEXITCODE -eq 0

# 7. addresses
$lan = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -match '^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)' -and $_.PrefixOrigin -ne 'WellKnown' -and $_.InterfaceAlias -notlike 'vEthernet*' } |
    Select-Object -ExpandProperty IPAddress
Say ""
Say "Fair Play is running." Green
Say "  Public page        $base/"
Say "  Sign in            $base/login.html"
Say "    SONACAM: name sonacam, password = ADMIN_TOKEN in .env (opens the dashboard and operations)"
Say "    Artists: their artist name; prototype password SONACAM (opens the artist portal)"
foreach ($ip in $lan) { Say "  Meters on this network send to   http://${ip}:$apiPort" }
Say "  Let meters reach this computer once (admin PowerShell): .\scripts\firewall_b.ps1"
if (-not $ready) { Say "Some readiness checks are not OK yet (see the lines above): import the song package with -SongPackage, then run this again." Yellow }
