# Starts the FastAPI backend on 127.0.0.1:8000 (internal only, ONE worker). Keep this window open.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = 'python' }
if (-not $env:GREEN_NOVA_DATA) { $env:GREEN_NOVA_DATA = Join-Path $HOME 'GreenNovaData' }
New-Item -ItemType Directory -Force (Join-Path $env:GREEN_NOVA_DATA 'runtime') | Out-Null
$env:PYTHONPATH = $root
$env:CUDA_VISIBLE_DEVICES = ''
Write-Host "Backend: http://127.0.0.1:8000  (data/runtime dir: $env:GREEN_NOVA_DATA)"
& $py -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 1
