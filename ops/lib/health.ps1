# Health check used by `greennova.ps1 health` and by the watchdog. ASCII only.
. (Join-Path $PSScriptRoot 'common.ps1')

function Test-ExternalSite([string]$Domain) {
    try {
        $r = Invoke-WebRequest -Uri "https://$Domain/" -UseBasicParsing -TimeoutSec 25 -ErrorAction Stop
        return @{ ok = (($r.StatusCode -eq 200) -and ($r.Content -match 'Green\s*Nova')); code = [int]$r.StatusCode }
    } catch {
        $resp = $_.Exception.Response
        if ($resp) { return @{ ok = $false; code = [int]$resp.StatusCode } }
        return @{ ok = $false; code = 0 }
    }
}

function Test-HostHeader([string]$Domain, [int]$Port) {
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if (-not $curl) { return $null }
    $code = & curl.exe -s -o NUL -w '%{http_code}' --max-time 10 -H "Host: $Domain" "http://127.0.0.1:$Port/"
    return [int]$code
}

function Invoke-HealthCheck($cfg, [bool]$External = $true) {
    $ok = $true
    $row = { param($label, $good, $detail) $mark = if ($good) { 'OK  ' } else { 'FAIL' }; $col = if ($good) { 'Green' } else { 'Red' }; Write-Host ('[{0}] {1,-34} {2}' -f $mark, $label, $detail) -ForegroundColor $col }

    Write-Host ("Green Nova health check - {0}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
    foreach ($s in $cfg.services) {
        $sup = Test-SupervisorRunning $s.name
        $owner = Get-PortOwner ([int]$s.port)
        $http = Test-Http $s.health 8
        $good = ($sup -and $owner -and $http)
        if (-not $good) { $ok = $false }
        & $row ("service " + $s.name) $good ("supervisor={0} port {1} pid={2} health={3}" -f $sup, $s.port, $owner, $http)
        if ($s.ready) {
            try { $body = (Invoke-WebRequest -Uri $s.ready -UseBasicParsing -TimeoutSec 8 -ErrorAction Stop).Content; & $row ("  ready " + $s.name) $true ($body.Substring(0, [Math]::Min(160, $body.Length))) }
            catch { & $row ("  ready " + $s.name) $false 'not ready (models/data missing or still loading)'; $ok = $false }
        }
        $supLog = Join-Path (Join-Path $cfg.runRoot 'logs') ($s.name + '.supervisor.log')
        if (Test-Path $supLog) {
            $today = Get-Date -Format 'yyyy-MM-dd'
            $restarts = @(Select-String -LiteralPath $supLog -Pattern "^$today .*service exited" -ErrorAction SilentlyContinue).Count
            Write-Host ("       restarts today: {0}" -f $restarts)
        }
    }
    $cf = Get-Service -Name 'Cloudflared' -ErrorAction SilentlyContinue
    $cfOk = ($cf -and $cf.Status -eq 'Running')
    if (-not $cfOk) { $ok = $false }
    & $row 'Cloudflare Tunnel service' $cfOk $(if ($cf) { "$($cf.Status), start type $($cf.StartType)" } else { 'service not found' })

    $fe = @($cfg.services | Where-Object { $_.name -eq 'frontend' })[0]
    if ($fe) {
        $hc = Test-HostHeader $cfg.domain ([int]$fe.port)
        $hcOk = ($hc -ge 200 -and $hc -lt 400)
        if (-not $hcOk) { $ok = $false }
        & $row ("localhost with Host: " + $cfg.domain) $hcOk ("HTTP $hc")
    }
    if ($External) {
        $x = Test-ExternalSite $cfg.domain
        if (-not $x.ok) { $ok = $false }
        & $row ("public https://" + $cfg.domain) $x.ok ("HTTP " + $x.code)
    }
    $os = Get-CimInstance Win32_OperatingSystem
    $freeGB = [math]::Round($os.FreePhysicalMemory / 1MB, 1)
    $diskGB = [math]::Round((Get-PSDrive C).Free / 1GB, 1)
    & $row 'memory free (GB)' ($freeGB -gt 1.0) ("$freeGB of " + [math]::Round($os.TotalVisibleMemorySize / 1MB, 1))
    & $row 'disk C: free (GB)' ($diskGB -gt 5) "$diskGB"
    if ($freeGB -le 1.0 -or $diskGB -le 5) { $ok = $false }
    $smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if ($smi) { Write-Host ("       GPU memory used/total: " + ((& nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader) -join ' ')) }
    $net = Test-Connection -ComputerName 1.1.1.1 -Count 1 -Quiet
    & $row 'internet reachable' $net ''
    Write-Host $(if ($ok) { 'RESULT: ALL OK' } else { 'RESULT: PROBLEMS FOUND' }) -ForegroundColor $(if ($ok) { 'Green' } else { 'Red' })
    return $ok
}
