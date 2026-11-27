# End-to-end smoke test of the running system (frontend :3000 -> BFF -> backend :8000 -> real model outputs).
#   powershell -ExecutionPolicy Bypass -File web\scripts\smoke.ps1 [-Base http://127.0.0.1:3000] [-Backend http://127.0.0.1:8000]
# Exit code 0 = all checks passed, 1 = at least one failed. Prints one line per check. Needs BOTH models' outputs; a missing model FAILS the test.
param(
  [string]$Base = "http://127.0.0.1:3000",
  [string]$Backend = "http://127.0.0.1:8000",
  [int]$JobTimeoutSec = 420
)
$ErrorActionPreference = "Stop"
$script:fails = 0
function Check([string]$name, [scriptblock]$body) {
  try { $msg = & $body; Write-Host ("PASS  {0}  {1}" -f $name, $msg) }
  catch { $script:fails++; Write-Host ("FAIL  {0}  {1}" -f $name, $_.Exception.Message) }
}
function Assert($cond, [string]$msg) { if (-not $cond) { throw $msg } }
function Get-Status([string]$url, $headers = @{}) {
  try { return [int](Invoke-WebRequest -Uri $url -Headers $headers -UseBasicParsing -TimeoutSec 60).StatusCode }
  catch { if ($_.Exception.Response) { return [int]$_.Exception.Response.StatusCode } else { throw } }
}
function Api([string]$method, [string]$path, $body = $null) {
  $p = @{ Uri = "$Base/api/gn/$path"; Method = $method; UseBasicParsing = $true; TimeoutSec = 120 }
  if ($body) { $p.Body = ($body | ConvertTo-Json -Compress -Depth 6); $p.ContentType = "application/json" }
  $r = Invoke-WebRequest @p
  return ($r.Content | ConvertFrom-Json)
}
function Wait-Job([string]$id) {
  $t0 = Get-Date
  while ($true) {
    $j = Api GET "jobs/$id"
    if ($j.state -in @("succeeded", "failed", "cancelled")) { return $j }
    if (((Get-Date) - $t0).TotalSeconds -gt $JobTimeoutSec) { throw "job $id still $($j.state) after ${JobTimeoutSec}s" }
    Start-Sleep -Milliseconds 700
  }
}

# ---- 1. pages --------------------------------------------------------------------------------------------------------
foreach ($p in "/", "/dashboard", "/suitability", "/restoration", "/robots.txt", "/sitemap.xml") {
  Check "page $p" { $s = Get-Status "$Base$p"; Assert ($s -eq 200) "status $s"; "200" }
}
Check "works behind a reverse proxy (other Host header)" { $s = Get-Status "$Base/" @{ Host = "green-nova.example.test"; "X-Forwarded-Proto" = "https" }; Assert ($s -eq 200) "status $s"; "200" }
Check "live mode: no demo marker in HTML" {
  $h = (Invoke-WebRequest "$Base/dashboard" -UseBasicParsing).Content
  Assert ($h -notmatch "DEMONSTRATION DATA") "demo marker present: the build is still in demo mode"
  "marker absent"
}

# ---- 2. backend ------------------------------------------------------------------------------------------------------
Check "backend /health" { $r = Invoke-RestMethod "$Backend/health" -TimeoutSec 5; Assert ($r.status -eq "ok") "bad body"; "ok" }
$ready = $null
Check "backend /ready" {
  $script:ready = Invoke-RestMethod "$Backend/ready" -TimeoutSec 10
  Assert ($script:ready.status -in @("ready", "degraded")) "status $($script:ready.status)"
  "$($script:ready.status) suitability=$($script:ready.models.'jo-maan'.suitability.available) restoration=$($script:ready.models.'jo-maan'.restoration.available)"
}
Check "backend hides docs/openapi" { Assert ((Get-Status "$Backend/docs") -eq 404 -and (Get-Status "$Backend/openapi.json") -eq 404) "docs exposed"; "404" }
Check "BFF rejects non-allowlisted paths" { Assert ((Get-Status "$Base/api/gn/docs") -eq 404 -and (Get-Status "$Base/api/gn/health") -eq 404) "BFF forwarded an unknown path"; "404" }

# ---- 3. Model 1 ------------------------------------------------------------------------------------------------------
$m1id = $null
Check "Model 1 job via BFF -> real result" {
  $j = Api POST "jobs" @{ kind = "suitability"; region_id = "jo-maan" }
  $j = Wait-Job $j.id
  Assert ($j.state -eq "succeeded") "job $($j.state): $($j.error.message)"
  $res = Api GET "jobs/$($j.id)/result"
  Assert ($res.run.polygon_count -gt 0) "empty result"
  Assert ($res.run.stats.Count -eq 5) "stats not per class"
  Assert ($res.run.demo -eq $false) "result flagged demo"
  Assert ($res.run.metadata.effective_resolution_m -gt 0) "effective resolution missing"
  "polygons=$($res.run.polygon_count) total_ha=$($res.run.total_area_ha) grid=$($res.run.metadata.grid_resolution_m)m effective=$($res.run.metadata.effective_resolution_m)m"
}
$polys = $null
Check "Model 1 polygons (contract fields)" {
  $script:polys = Api GET "regions/jo-maan/suitability/polygons"
  Assert ($script:polys.features.Count -gt 0) "no polygons"
  $p = $script:polys.features[0].properties
  foreach ($f in "id", "class_code", "area_ha", "area_dunum", "confidence", "confidence_method", "factors", "effective_resolution_m") { Assert ($null -ne $p.$f) "missing $f" }
  $script:m1id = $p.id
  "features=$($script:polys.features.Count) first=$($p.id)"
}

# ---- 4. Model 2 ------------------------------------------------------------------------------------------------------
$resId = $null
Check "Model 2 job via BFF -> real result" {
  $cand = @($script:polys.features | Where-Object { $_.properties.class_code -in 3, 4 } | Select-Object -First 3)
  Assert ($cand.Count -gt 0) "no class 3/4 polygons to analyse"
  $ids = @($cand | ForEach-Object { $_.properties.id })
  $j = Api POST "jobs" @{ kind = "restoration"; region_id = "jo-maan"; polygon_ids = $ids }
  $j = Wait-Job $j.id
  Assert ($j.state -eq "succeeded") "job $($j.state): $($j.error.message)"
  $res = Api GET "jobs/$($j.id)/result"
  Assert ($res.features.Count -gt 0) "empty Model 2 result"
  $p = $res.features[0].properties
  Assert ($ids -contains $p.source_polygon_id) "result not linked to the selected Model 1 ids"
  Assert ($null -ne $p.feasibility.class -and $null -ne $p.feasibility.interval) "feasibility fields missing"
  Assert ($null -ne $p.limiting_factors -and $null -ne $p.scenarios) "limiting_factors/scenarios missing"
  foreach ($s in $p.scenarios) { Assert ($s.evidence -eq "simulated") "scenario not tagged simulated" }
  $script:resId = $p.source_polygon_id
  "units=$($res.features.Count) first=$($p.source_polygon_id) feasibility=$($p.feasibility.class) scenarios=$($p.scenarios.Count)"
}

# ---- 5. polygon detail + exports -------------------------------------------------------------------------------------
Check "land detail" {
  $id = if ($script:resId) { $script:resId } else { $script:m1id }
  $d = Api GET "land/$id"
  Assert ($d.suitability.properties.id -eq $id) "wrong unit"
  Assert ($d.demo -eq $false) "flagged demo"
  "unit=$id class=$($d.suitability.properties.class_code) restoration=$($null -ne $d.restoration)"
}
Check "export: GeoTIFF clip (real raster)" {
  $r = Invoke-WebRequest "$Base/api/gn/land/$($script:m1id)/geotiff?layer=suitability" -UseBasicParsing -TimeoutSec 120
  $b = $r.RawContentLength
  Assert ($b -gt 100) "empty file"
  $head = [System.Text.Encoding]::ASCII.GetString($r.Content[0..1])
  Assert ($head -in @("II", "MM")) "not a TIFF"
  "$b bytes, $($r.Headers['Content-Type'])"
}
Check "land page renders" { $s = Get-Status "$Base/land/$($script:m1id)"; Assert ($s -eq 200) "status $s"; "200" }

if ($script:fails -gt 0) { Write-Host "`nSMOKE FAILED: $($script:fails) check(s)"; exit 1 }
Write-Host "`nSMOKE OK"; exit 0
