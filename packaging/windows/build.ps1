# Build SelfScribe.exe and a shareable zip. Run from the repo root:
#   powershell -ExecutionPolicy Bypass -File packaging/windows/build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m pip install --upgrade pip
python -m pip install "../..[build]"
python -c "from selfscribe.assets import write_ico; from pathlib import Path; write_ico(Path('SelfScribe.ico'))"
if (Test-Path build) { Remove-Item -Recurse -Force build }
if (Test-Path dist) { Remove-Item -Recurse -Force dist }
python -m PyInstaller --noconfirm SelfScribe.spec

Compress-Archive -Path dist/SelfScribe -DestinationPath dist/SelfScribe-Windows-x64.zip -Force
Write-Host "built dist/SelfScribe-Windows-x64.zip"
