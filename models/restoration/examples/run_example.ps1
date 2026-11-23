# Portable CPU example for Model 2. Usage:  powershell -File models\restoration\examples\run_example.ps1 [-Python path\to\python.exe]
param([string]$Python = "python")
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
$env:PYTHONPATH = $root.Path
$env:CUDA_VISIBLE_DEVICES = ""
Push-Location $root
try { & $Python (Join-Path $PSScriptRoot "run_example.py"); exit $LASTEXITCODE } finally { Pop-Location }
