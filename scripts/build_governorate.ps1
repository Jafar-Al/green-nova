# Developer-time pipeline: builds the real assessment for one or more governorates (both models, CPU only).
# Needs the data cache described in docs/DATA_SOURCES*.md (GREEN_NOVA_DATA, default ~/GreenNovaData) and network access for one
# small SoilGrids/ISRIC window per region. NOT needed to run the application: the resulting outputs are committed to the repo.
#
#   powershell -ExecutionPolicy Bypass -File scripts\build_governorate.ps1 -Region jo-irbid,jo-jerash [-Force]
#
# Steps (each is skipped when its result exists, unless -Force):
#   1 Model 1 runtime window      2 Model 1 inference + agreement with observed cultivation
#   3 Model 2 climate slice       4 Model 2 runtime stack          5 Model 2 inference on Model 1's real polygons
param(
    [Parameter(Mandatory = $true)][string[]]$Region,
    [switch]$Force,
    [string]$Python
)
$ErrorActionPreference = 'Stop'
# accept "-Region a,b,c" even when launched through -File (which does not split commas into an array)
$Region = @($Region | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if (-not $env:GREEN_NOVA_DATA) { $env:GREEN_NOVA_DATA = Join-Path $HOME 'GreenNovaData' }
if (-not $Python) {
    $cand = Join-Path $env:GREEN_NOVA_DATA 'venv\Scripts\python.exe'
    $local = Join-Path $root '.venv\Scripts\python.exe'
    $Python = if (Test-Path $local) { $local } elseif (Test-Path $cand) { $cand } else { 'python' }
}
$env:PYTHONPATH = $root
$env:CUDA_VISIBLE_DEVICES = ''
$runtime1 = if ($env:GREEN_NOVA_M1_RUNTIME) { $env:GREEN_NOVA_M1_RUNTIME } else { Join-Path $env:GREEN_NOVA_DATA 'runtime\model1' }

function Invoke-Step([string]$Name, [bool]$Done, [scriptblock]$Run) {
    if ($Done -and -not $Force) { Write-Host ("[{0}] {1}: already done, skipping" -f (Get-Date -Format 'HH:mm:ss'), $Name); return }
    Write-Host ("[{0}] {1}: running" -f (Get-Date -Format 'HH:mm:ss'), $Name)
    $t0 = Get-Date
    & $Run
    if ($LASTEXITCODE -ne 0) { throw "$Name failed with exit code $LASTEXITCODE" }
    Write-Host ("[{0}] {1}: ok in {2:N0}s" -f (Get-Date -Format 'HH:mm:ss'), $Name, ((Get-Date) - $t0).TotalSeconds)
}

foreach ($r in $Region) {
    Write-Host "=== $r ==="
    $o1 = "models/suitability/outputs/$r"
    $o2 = "models/restoration/outputs/$r"
    Invoke-Step "$r model1 runtime window" (Test-Path (Join-Path $runtime1 "$r\features.npy")) { & $Python -m models.suitability.package_runtime --region $r }
    Invoke-Step "$r model1 inference" (Test-Path "$o1/summary.json") { & $Python -m models.suitability.infer --region $r --out $o1 --device cpu }
    Invoke-Step "$r model1 agreement with observed cultivation" $false { & $Python -m models.suitability.agreement --region $r --out $o1 }
    Invoke-Step "$r model2 climate slice" (Test-Path (Join-Path $env:GREEN_NOVA_DATA "cache\model2\tc_$r.npz")) { & $Python -m models.restoration.data.climate_from_cache --region $r }
    Invoke-Step "$r model2 runtime stack" (Test-Path "models/restoration/runtime_data/$r/stack.npz") { & $Python -m models.restoration.build_runtime --region $r }
    Invoke-Step "$r model2 inference" (Test-Path "$o2/summary.json") { & $Python -m models.restoration.infer --region $r --suitability-dir $o1 --out $o2 }
}
Write-Host 'done'
