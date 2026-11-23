# THIS PC ONLY (OneDrive workaround). On any other machine use the generic path in web/README.md: npm ci && npm run build && npm start.
# Build the production release OUTSIDE OneDrive and assemble a self-contained folder.
#   powershell -ExecutionPolicy Bypass -File web\scripts\build-release.ps1 [-DataRoot <dir>] [-Out <dir>]
#
# Why a separate build dir: web\node_modules is a junction to <DataRoot>\web\node_modules (keeps ~30k files out of OneDrive).
# Next's standalone tracer refuses files outside the project root, so the release build runs in <DataRoot>\web, which owns a
# REAL node_modules. Source is mirrored from web\ first; nothing is edited there. DataRoot defaults to $env:GREEN_NOVA_DATA.
param(
  [string]$DataRoot = $(if ($env:GREEN_NOVA_DATA) { $env:GREEN_NOVA_DATA } else { Join-Path $env:USERPROFILE "GreenNovaData" }),
  [string]$Build = (Join-Path $DataRoot "web"),
  [string]$Out = (Join-Path $Build "release")
)
$ErrorActionPreference = "Stop"
$src = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
New-Item -ItemType Directory -Force $Build | Out-Null

Write-Host "[1/4] mirroring source $src -> $Build"
robocopy $src $Build /MIR /XD node_modules .next coverage release /XF .env .env.local "*.tsbuildinfo" next-env.d.ts /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE)" }

Push-Location $Build
try {
  $lock = (Get-FileHash package-lock.json -Algorithm SHA256).Hash
  $stamp = Join-Path $Build "node_modules\.lockhash"
  if (-not (Test-Path $stamp) -or (Get-Content $stamp -ErrorAction SilentlyContinue) -ne $lock) {
    Write-Host "[2/4] npm ci (lockfile changed or first run)"
    npm ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }
    Set-Content -Path $stamp -Value $lock
  } else { Write-Host "[2/4] node_modules up to date" }

  Write-Host "[3/4] next build (standalone)"
  $env:GN_STANDALONE = "1"
  npm run build
  if ($LASTEXITCODE -ne 0) { throw "next build failed" }

  Write-Host "[4/4] assemble standalone -> $Out"
  node scripts\assemble-standalone.mjs $Out
  if ($LASTEXITCODE -ne 0) { throw "assemble failed" }
} finally { Pop-Location }
Write-Host "Done. Run: cd $Out; `$env:PORT='3000'; `$env:HOSTNAME='0.0.0.0'; node server.js"
