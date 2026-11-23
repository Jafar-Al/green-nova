# Runs all automated tests: Python (backend + both models) and the web app (typecheck, lint, unit tests).
param([switch]$SkipWeb)
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = 'python' }
$env:PYTHONPATH = $root
$env:CUDA_VISIBLE_DEVICES = ''
& $py -m pytest backend/tests models/suitability/tests models/restoration/tests -q
$rc = $LASTEXITCODE
if (-not $SkipWeb) {
    Push-Location web
    npm run typecheck; if ($LASTEXITCODE -ne 0) { $rc = 1 }
    npm run lint; if ($LASTEXITCODE -ne 0) { $rc = 1 }
    npm test; if ($LASTEXITCODE -ne 0) { $rc = 1 }
    Pop-Location
}
exit $rc
