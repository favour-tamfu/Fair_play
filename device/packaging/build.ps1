# Build the Windows meter (FairPlayMeter.exe) and zip it. Run from anywhere; it works from the repo root.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $root
& .\.venv\Scripts\Activate.ps1
if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) { python -m pip install pyinstaller==6.11.1 }
pyinstaller device\packaging\FairPlayMeter.spec --noconfirm --distpath dist --workpath build\meter
# Safety: the build must not contain any meter key, config or state.
$leaks = Get-ChildItem dist\FairPlayMeter -Recurse -File | Where-Object { $_.Name -like '*.seed' -or $_.FullName -match '\\(secrets|state)\\' }
if ($leaks) { throw "Build contains private files: $($leaks.FullName -join ', ')" }
Copy-Item device\packaging\README.md dist\FairPlayMeter\README.md
if (Test-Path dist\FairPlayMeter_windows.zip) { Remove-Item dist\FairPlayMeter_windows.zip }
Compress-Archive -Path dist\FairPlayMeter\* -DestinationPath dist\FairPlayMeter_windows.zip
Write-Host ("Built dist\FairPlayMeter_windows.zip ({0:N1} MB)" -f ((Get-Item dist\FairPlayMeter_windows.zip).Length / 1MB))
