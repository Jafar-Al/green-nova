# Loads both saved checkpoints and runs CPU inference on the small bundled samples (no retraining, no network, no GPU).
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = 'python' }
$env:PYTHONPATH = $root
$env:CUDA_VISIBLE_DEVICES = ''
Write-Host '=== Model 1: suitability (sample area near Shobak) ==='
$env:PYTHON = $py
powershell -NoProfile -ExecutionPolicy Bypass -File models\suitability\examples\run_example.ps1
if ($LASTEXITCODE -ne 0) { throw 'Model 1 example failed' }
Write-Host '=== Model 2: restoration (sample geometry + 3 Model 1 polygons) ==='
powershell -NoProfile -ExecutionPolicy Bypass -File models\restoration\examples\run_example.ps1 -Python $py
if ($LASTEXITCODE -ne 0) { throw 'Model 2 example failed' }
Write-Host 'Both models loaded from their checkpoints and produced predictions.'
