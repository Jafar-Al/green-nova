# Configures ONLY greennova.dosteam.org: the tunnel's public-hostname rule (-> http://localhost:3000) and that one DNS record.
# DEFAULT = DRY RUN (reads only). Add -Apply to change anything. Never deletes. Never prints the token.
# Needs the user environment variable CLOUDFLARE_API_TOKEN with: Zone:DNS:Edit, Zone:Zone:Read (zone dosteam.org),
# Account:Cloudflare Tunnel:Edit. ASCII only, Windows PowerShell 5.1.
param([switch]$Apply, [string]$Hostname = 'greennova.dosteam.org', [string]$Service = 'http://localhost:3000', [string]$ZoneName = 'dosteam.org')
$ErrorActionPreference = 'Stop'
$Here = Split-Path -Parent $PSCommandPath
. (Join-Path (Split-Path -Parent $Here) 'lib\health.ps1')

function Get-CfToken { foreach ($s in 'Process', 'User', 'Machine') { $v = [Environment]::GetEnvironmentVariable('CLOUDFLARE_API_TOKEN', $s); if ($v) { return $v.Trim() } } return $null }
$tok = Get-CfToken
if (-not $tok) {
    Write-Host 'BLOCKED: no CLOUDFLARE_API_TOKEN found. Save it as a user environment variable (Windows: Edit environment variables for your account).'
    Write-Host 'Scopes: Zone > DNS > Edit and Zone > Zone > Read for zone dosteam.org; Account > Cloudflare Tunnel > Edit.'
    exit 2
}
$script:Hdr = @{ Authorization = "Bearer $tok"; 'Content-Type' = 'application/json' }

function Invoke-Cf([string]$Method, [string]$Path, $Body = $null) {
    $uri = "https://api.cloudflare.com/client/v4$Path"
    try {
        if ($null -ne $Body) { return Invoke-RestMethod -Method $Method -Uri $uri -Headers $script:Hdr -Body ($Body | ConvertTo-Json -Depth 30 -Compress) -TimeoutSec 40 }
        return Invoke-RestMethod -Method $Method -Uri $uri -Headers $script:Hdr -TimeoutSec 40
    } catch {
        $msg = $_.Exception.Message
        try { $sr = New-Object IO.StreamReader($_.Exception.Response.GetResponseStream()); $j = $sr.ReadToEnd() | ConvertFrom-Json; $msg = (($j.errors | ForEach-Object { "$($_.code): $($_.message)" }) -join '; ') } catch { }
        throw "Cloudflare API $Method $Path failed: $msg"
    }
}

Write-Host ('Mode: ' + $(if ($Apply) { 'APPLY' } else { 'DRY RUN (no changes)' }) + " | hostname=$Hostname service=$Service zone=$ZoneName")
# 1) zone
$z = (Invoke-Cf GET "/zones?name=$ZoneName").result | Select-Object -First 1
if (-not $z) { throw "zone $ZoneName not visible to this token" }
$acct = $z.account.id
Write-Host "zone $ZoneName found (status $($z.status))"
# 2) current DNS for the hostname only
$recs = @((Invoke-Cf GET "/zones/$($z.id)/dns_records?name=$Hostname").result)
foreach ($r in $recs) { Write-Host ("DNS now: {0} {1} -> {2} proxied={3}" -f $r.type, $r.name, $r.content, $r.proxied) }
if ($recs.Count -eq 0) { Write-Host 'DNS now: (no record for this hostname)' }
# 3) tunnels: find the one that owns the hostname, else the one connected from this machine's public IP
$tunnels = @((Invoke-Cf GET "/accounts/$acct/cfd_tunnel?is_deleted=false&per_page=100").result)
$myIp = $null
try { $myIp = ((Invoke-RestMethod 'https://www.cloudflare.com/cdn-cgi/trace' -TimeoutSec 15) -split "`n" | Where-Object { $_ -like 'ip=*' }) -replace 'ip=', '' } catch { }
$cands = @()
foreach ($t in $tunnels) {
    $cfgR = $null; try { $cfgR = (Invoke-Cf GET "/accounts/$acct/cfd_tunnel/$($t.id)/configurations").result } catch { }
    $ing = @(); if ($cfgR -and $cfgR.config -and $cfgR.config.ingress) { $ing = @($cfgR.config.ingress) }
    $owns = [bool]($ing | Where-Object { $_.hostname -eq $Hostname })
    $conns = @(); try { $conns = @((Invoke-Cf GET "/accounts/$acct/cfd_tunnel/$($t.id)/connections").result) } catch { }
    $fromMe = $false; foreach ($c in $conns) { foreach ($cn in @($c.conns)) { if ($myIp -and $cn.origin_ip -eq $myIp) { $fromMe = $true } } }
    $managed = if ($cfgR -and $cfgR.source) { $cfgR.source } else { 'unknown' }
    Write-Host ("tunnel {0,-28} id={1} status={2} source={3} ownsHostname={4} connectedFromThisMachine={5} rules={6}" -f $t.name, $t.id, $t.status, $managed, $owns, $fromMe, $ing.Count)
    $cands += [pscustomobject]@{ t = $t; cfg = $cfgR; ing = $ing; owns = $owns; fromMe = $fromMe; managed = $managed }
}
$pick = @($cands | Where-Object { $_.owns })
if ($pick.Count -eq 0) { $pick = @($cands | Where-Object { $_.fromMe }) }
if ($pick.Count -ne 1) { Write-Host "STOP: could not identify exactly one target tunnel (matches: $($pick.Count)). Nothing changed."; exit 3 }
$tun = $pick[0]
if ($tun.managed -ne 'cloudflare') { Write-Host "STOP: tunnel '$($tun.t.name)' is configured locally (source=$($tun.managed)), not through Cloudflare, so its routes cannot be edited by API. Nothing changed."; exit 4 }
Write-Host "target tunnel: $($tun.t.name) ($($tun.t.id))"

# 4) plan: ingress (all other rules untouched, catch-all stays last)
$new = New-Object System.Collections.ArrayList
$placed = $false
foreach ($r in $tun.ing) {
    if ($r.hostname -eq $Hostname) { [void]$new.Add([pscustomobject]@{ hostname = $Hostname; service = $Service }); $placed = $true }
    elseif (-not $r.hostname -and -not $placed) { [void]$new.Add([pscustomobject]@{ hostname = $Hostname; service = $Service }); $placed = $true; [void]$new.Add($r) }
    else { [void]$new.Add($r) }
}
if (-not $placed) { [void]$new.Add([pscustomobject]@{ hostname = $Hostname; service = $Service }) }
if (-not ($new | Where-Object { -not $_.hostname })) { [void]$new.Add([pscustomobject]@{ service = 'http_status:404' }) }
$cname = "$($tun.t.id).cfargotunnel.com"
$dnsOk = ($recs.Count -eq 1 -and $recs[0].type -eq 'CNAME' -and $recs[0].content -eq $cname -and $recs[0].proxied)
$ingChanged = -not ($tun.ing | Where-Object { $_.hostname -eq $Hostname -and $_.service -eq $Service })
Write-Host ("PLAN: ingress change needed={0}; DNS change needed={1} (want proxied CNAME {2} -> {3})" -f $ingChanged, (-not $dnsOk), $Hostname, $cname)
if (-not $Apply) { Write-Host 'Dry run finished. Re-run with -Apply to make exactly the changes above.'; exit 0 }

# 5) apply with a local backup first (no secrets in it)
$bk = Join-Path 'C:\GreenNovaData\runtime' ("cloudflare-backup-{0}.json" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Force (Split-Path $bk) | Out-Null
@{ tunnel = $tun.t.id; config = $tun.cfg.config; dns = $recs } | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $bk
Write-Host "backup of previous values written: $bk"
if ($ingChanged) {
    $cfgObj = $tun.cfg.config
    if ($cfgObj.PSObject.Properties.Name -contains 'ingress') { $cfgObj.ingress = $new.ToArray() } else { $cfgObj | Add-Member -NotePropertyName ingress -NotePropertyValue $new.ToArray() }
    [void](Invoke-Cf PUT "/accounts/$acct/cfd_tunnel/$($tun.t.id)/configurations" @{ config = $cfgObj })
    Write-Host 'tunnel ingress updated'
}
if (-not $dnsOk) {
    $body = @{ type = 'CNAME'; name = $Hostname; content = $cname; proxied = $true; ttl = 1; comment = 'Green Nova AI (tunnel)' }
    if ($recs.Count -eq 0) { [void](Invoke-Cf POST "/zones/$($z.id)/dns_records" $body); Write-Host 'DNS record created' }
    elseif ($recs.Count -eq 1) { [void](Invoke-Cf PUT "/zones/$($z.id)/dns_records/$($recs[0].id)" $body); Write-Host 'DNS record updated' }
    else { Write-Host 'STOP: several DNS records exist for the hostname - not touching them.'; exit 5 }
}
# 6) verify publicly
Write-Host 'verifying https (up to 4 minutes)...'
$ok = $false
for ($i = 0; $i -lt 24 -and -not $ok; $i++) { Start-Sleep -Seconds 10; $x = Test-ExternalSite $Hostname; Write-Host ("  attempt {0}: HTTP {1} ok={2}" -f ($i + 1), $x.code, $x.ok); $ok = $x.ok }
if ($ok) { Write-Host "PUBLIC OK: https://$Hostname serves the app" } else { Write-Host 'PUBLIC NOT OK yet - check tunnel connector status and the app on port 3000'; exit 6 }
