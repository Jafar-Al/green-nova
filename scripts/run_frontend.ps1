# Builds and starts the Next.js production server on 0.0.0.0:3000. Start the backend first (scripts\run_backend.ps1).
# Use -Dev for the hot-reload dev server (also port 3000).
param([switch]$Dev)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root 'web')
if (-not (Test-Path 'node_modules')) { npm ci }
if (-not $env:BACKEND_URL) { $env:BACKEND_URL = 'http://127.0.0.1:8000' }
if ($Dev) { npm run dev } else { npm run build; npm start }
