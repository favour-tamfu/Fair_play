# Fair Play - build the release folder: every part of the system, ready to hand over.
#
#   powershell -ExecutionPolicy Bypass -File .\scripts\make_release.ps1 -Version v1.0 [-SkipMeter]
#
# Output (release\ is not committed):
#   release\FairPlay_<version>\
#     START_HERE.md                        what each part is and how to install it
#     FairPlay_Server_<version>.zip        SONACAM server: code, web pages, installer (from git: no secrets, no audio)
#     FairPlayMeter_windows_<version>.zip  the meter program for a bar laptop (A's build, device\packaging\build.ps1)
#     FairPlay_Docs_<version>.zip          README, decisions, contract, plans
#     SHA256SUMS.txt                       checksums of the zips
# Not included on purpose: the song package (audio and rights: handed over separately), .env, keys, the database.
param(
    [string]$Version = "v1.0",
    [switch]$SkipMeter,
    [switch]$RebuildMeter      # default: reuse dist\FairPlayMeter_windows.zip when it exists
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
function Say($t, $c = 'Gray') { Write-Host $t -ForegroundColor $c }

$dirty = git status --porcelain
if ($dirty) { Say "Note: there are uncommitted changes; the zips are built from the last commit ($(git rev-parse --short HEAD))." Yellow }
$commit = git rev-parse --short HEAD
$out = Join-Path $root "release\FairPlay_$Version"
if (Test-Path $out) { Remove-Item $out -Recurse -Force }
New-Item -ItemType Directory -Force $out | Out-Null

# 1. server (everything the server needs to build and run, plus the installer)
$serverPaths = @("docker-compose.yml", ".env.example", ".gitignore", "README.md", "server", "core", "contract", "web", "scripts", "requirements-dev.txt")
git archive --format=zip --prefix="FairPlay_Server_$Version/" -o "$out\FairPlay_Server_$Version.zip" HEAD @serverPaths
Say "  OK  FairPlay_Server_$Version.zip"

# 2. meter (A's packaged FairPlayMeter.exe)
if (-not $SkipMeter) {
    if ($RebuildMeter -or -not (Test-Path "$root\dist\FairPlayMeter_windows.zip")) { & "$root\device\packaging\build.ps1" }
    else { Say "  ..  reusing dist\FairPlayMeter_windows.zip (built $((Get-Item "$root\dist\FairPlayMeter_windows.zip").LastWriteTime))" }
    if (-not (Test-Path "$root\dist\FairPlayMeter_windows.zip")) { throw "the meter build did not produce dist\FairPlayMeter_windows.zip" }
    Copy-Item "$root\dist\FairPlayMeter_windows.zip" "$out\FairPlayMeter_windows_$Version.zip"
    Say "  OK  FairPlayMeter_windows_$Version.zip"
} else {
    Say "  --  meter skipped (-SkipMeter)" Yellow
}

# 3. documents
$docPaths = @("README.md", "DECISIONS.md", "docs", "contract", "device/packaging/README.md")
git archive --format=zip --prefix="FairPlay_Docs_$Version/" -o "$out\FairPlay_Docs_$Version.zip" HEAD @docPaths
Say "  OK  FairPlay_Docs_$Version.zip"

# 4. start-here and checksums
(Get-Content "$root\docs\RELEASE_START_HERE.md" -Raw) -replace '\{VERSION\}', $Version -replace '\{COMMIT\}', $commit |
    Set-Content "$out\START_HERE.md" -Encoding utf8
$sums = Get-ChildItem $out -Filter *.zip | ForEach-Object { "{0}  {1}" -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower(), $_.Name }
$sums | Set-Content "$out\SHA256SUMS.txt" -Encoding ascii
Say ""
Say "Release $Version (commit $commit) in $out" Green
Get-ChildItem $out | ForEach-Object { Say ("  {0,-42} {1,8:N1} MB" -f $_.Name, ($_.Length / 1MB)) }
