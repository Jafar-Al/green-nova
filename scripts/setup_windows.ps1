# One-time setup on a Windows machine (CPU only). Usage: powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1 [-SkipWeb]
param([switch]$SkipWeb)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw 'Python 3.10-3.12 not found on PATH. Install it from python.org and re-run.' }
python --version
if (-not (Test-Path '.venv\Scripts\python.exe')) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not $SkipWeb) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw 'Node.js >= 20.9 not found on PATH. Install it from nodejs.org and re-run (or use -SkipWeb).' }
    node --version
    Push-Location web
    npm ci
    if (-not (Test-Path '.env.local')) { Copy-Item '.env.example' '.env.local'; Write-Host 'created web\.env.local from the template (edit if needed)' }
    Pop-Location
}
Write-Host 'Setup finished. Next: scripts\run_model_examples.ps1, then scripts\run_backend.ps1 and scripts\run_frontend.ps1'
