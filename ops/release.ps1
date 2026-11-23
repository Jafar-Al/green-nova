# Copies the current production build + backend + models into the run root (C:\GreenNovaRun) and restarts the services.
# No admin rights needed after "install" (the run root is writable by the service user; ops\ is not and is not touched here).
#   powershell -ExecutionPolicy Bypass -File ops\release.ps1 [-NoRestart] [-Source <project root>]
# ASCII only, Windows PowerShell 5.1.
param([string]$Source, [switch]$NoRestart)
$ErrorActionPreference = 'Stop'
$Here = Split-Path -Parent $PSCommandPath
if (-not $Source) { $Source = Split-Path -Parent $Here }
. (Join-Path $Here 'lib\common.ps1')
$cfg = Get-Config
$run = $cfg.runRoot
$ctl = Join-Path $Here 'greennova.ps1'
$secretFiles = @('.env', '.env.*', '*.token', 'kaggle.json', '*.pem', '*.key', '*.pfx', 'credentials*')
$skipDirs = @('__pycache__', '.pytest_cache', 'tests', '.git', 'node_modules_cache', '.ipynb_checkpoints')

function Copy-Tree([string]$From, [string]$To, [string[]]$ExtraDirs = @()) {
    if (-not (Test-Path $From)) { Write-Host "skip (missing): $From"; return $false }
    New-Item -ItemType Directory -Force $To | Out-Null
    $a = @($From, $To, '/MIR', '/NFL', '/NDL', '/NJH', '/NJS', '/NP', '/R:2', '/W:2', '/XD') + $skipDirs + $ExtraDirs + @('/XF') + $secretFiles + @('*.pyc', '*.ipynb')
    & robocopy.exe @a | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE) copying $From" }
    return $true
}

Write-Host "Release from $Source to $run"
if (-not $NoRestart) { Write-Host 'stopping services...'; & $ctl stop }

# --- web (Next.js standalone) ---
# Preferred: the self-contained release folder produced by web\scripts\build-release.ps1 (server.js + .next\static + public + traced node_modules).
$sa = Join-Path $Source 'web\.next\standalone'
$prebuilt = Join-Path $cfg.dataRoot 'web\release'
if (Test-Path (Join-Path $prebuilt 'server.js')) {
    $null = Copy-Tree $prebuilt (Join-Path $run 'web') @('.next\cache')
    Write-Host "web: copied prebuilt release from $prebuilt"
} elseif (Test-Path $sa) {
    $server = Get-ChildItem $sa -Recurse -Filter server.js -File -ErrorAction SilentlyContinue | Where-Object { $_.FullName -notmatch 'node_modules' } | Sort-Object { $_.FullName.Length } | Select-Object -First 1
    if (-not $server) { throw 'standalone build found but no server.js inside it' }
    $dest = Join-Path $run 'web'
    $null = Copy-Tree $sa $dest @('.next\cache')
    $rel = $server.DirectoryName.Substring($sa.Length).TrimStart('\')
    $serverDirDest = if ($rel) { Join-Path $dest $rel } else { $dest }
    $null = Copy-Tree (Join-Path $Source 'web\.next\static') (Join-Path $serverDirDest '.next\static')
    $null = Copy-Tree (Join-Path $Source 'web\public') (Join-Path $serverDirDest 'public')
    if ($rel) { Set-Content -LiteralPath (Join-Path $dest 'server.js') -Value ("require('./" + ($rel -replace '\\', '/') + "/server.js');") -Encoding ASCII }
    Write-Host "web: copied (server.js at '$rel')"
} else { Write-Host 'WARN web\.next\standalone not found - run the production build first (npm run build with output: standalone)' }

# --- backend + models + regions ---
$null = Copy-Tree (Join-Path $Source 'backend') (Join-Path $run 'app\backend')
$null = Copy-Tree (Join-Path $Source 'models') (Join-Path $run 'app\models') @('raw', 'data', 'scratch')
$null = Copy-Tree (Join-Path $Source 'regions') (Join-Path $run 'app\regions')

foreach ($d in 'web', 'app') { $p = Join-Path $run $d; if (Test-Path $p) { Write-Host ("{0,-4} {1:N0} MB" -f $d, ((Get-ChildItem $p -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum / 1MB)) } }
New-Item -ItemType Directory -Force (Join-Path $cfg.dataRoot 'runtime') | Out-Null
Set-Content -LiteralPath (Join-Path $run 'RELEASE.txt') -Value ("released {0}" -f (Get-Date -Format s)) -Encoding ASCII
if (-not $NoRestart) { Write-Host 'starting services...'; & $ctl start }
Write-Host 'release done'
