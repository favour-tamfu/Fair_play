# Build the Windows meter as ONE file: dist\FairPlayMeter.exe. Run from anywhere; it works from the repo root.
#   .\device\packaging\build.ps1                          default address = the LAN server
#   .\device\packaging\build.ps1 -Url https://<address>   bake in another default address (kept out of git: build\)
param([string]$Url = "")
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $root
& .\.venv\Scripts\Activate.ps1
if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) { python -m pip install pyinstaller==6.11.1 }
$urlFile = Join-Path $root "build\meter_url\sonacam_url.txt"
if (Test-Path $urlFile) { Remove-Item $urlFile }
if ($Url) {
    New-Item -ItemType Directory -Force (Split-Path $urlFile) | Out-Null
    [IO.File]::WriteAllText($urlFile, $Url.TrimEnd('/'), (New-Object System.Text.UTF8Encoding $false))
    $env:FAIRPLAY_URL_FILE = $urlFile
} else { $env:FAIRPLAY_URL_FILE = "" }
# Safety: nothing private may be next to the sources PyInstaller reads from.
$leaks = Get-ChildItem device\packaging -Recurse -File | Where-Object { $_.Name -like '*.seed' -or $_.Name -like '*.toml' }
if ($leaks) { throw "Private files next to the build sources: $($leaks.FullName -join ', ')" }
pyinstaller device\packaging\FairPlayMeter.spec --noconfirm --distpath dist --workpath build\meter
$env:FAIRPLAY_URL_FILE = ""
$exe = Get-Item dist\FairPlayMeter.exe
Write-Host ("Built {0} ({1:N1} MB), one file." -f $exe.FullName, ($exe.Length / 1MB))
if ($Url) { Write-Host "Default SONACAM address baked in (not in git)." } else { Write-Host "Default SONACAM address: the LAN server." }
