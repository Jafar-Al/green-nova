# Portable CPU example (Windows PowerShell). Needs: Python 3.10+ with `pip install -r models/suitability/requirements.txt`.
# Optional: set $env:PYTHON to a specific interpreter. No network, no GPU, no large runtime data required.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:GREEN_NOVA_RUNTIME = (Resolve-Path (Join-Path $here '..\sample_data')).Path
$py = if ($env:PYTHON) { $env:PYTHON } else { 'python' }
& $py (Join-Path $here 'run_example.py') @args
exit $LASTEXITCODE
