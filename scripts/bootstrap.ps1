# SP-404 Jam Box bootstrap for Windows (PowerShell 5.1+).
# Creates .venv with the Python launcher, installs deps, and runs the setup check.
#   powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1
$ErrorActionPreference = 'Stop'

$RepoDir = Split-Path -Parent $PSScriptRoot
$VenvDir = Join-Path $RepoDir '.venv'
$Python = Join-Path $VenvDir 'Scripts\python.exe'

Write-Host '=== SP-404 Jam Box Bootstrap ==='

if (-not (Test-Path $Python)) {
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        throw 'Python launcher (py) not found. Install Python 3.11+ first.'
    }
    Write-Host "Creating virtual environment at $VenvDir"
    & py -3 -m venv $VenvDir
}

Write-Host 'Installing Python dependencies...'
& $Python -m pip install -r (Join-Path $RepoDir 'requirements.txt') -r (Join-Path $RepoDir 'requirements-dev.txt')

Write-Host ''
Write-Host 'Running setup validation...'
& $Python (Join-Path $RepoDir 'scripts\check_setup.py')

Write-Host ''
Write-Host 'Bootstrap complete.'
Write-Host 'Next steps:'
Write-Host '  - Review any MISSING items above (winget install Gyan.FFmpeg for ffmpeg/ffprobe).'
Write-Host "  - Start the app with: $Python web\app.py"
