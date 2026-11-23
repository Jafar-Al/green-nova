# Runs every 5 minutes (and at boot) from Task Scheduler. Brings missing supervisors back,
# keeps the Cloudflared service running, and restarts the tunnel only when the public site is down
# while internet and the local frontend are fine (at most once per hour). ASCII only.
$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'common.ps1')
. (Join-Path $PSScriptRoot 'health.ps1')

$cfg = Get-Config
$logDir = Join-Path $cfg.runRoot 'logs'
$ctl = Join-Path $cfg.runRoot 'control'
New-Item -ItemType Directory -Force $logDir, $ctl | Out-Null
$wlog = Join-Path $logDir 'watchdog.log'

$wm = Enter-NamedMutex 'Global\GreenNova.watchdog'
if ($null -eq $wm) { exit 0 }
try {
    $statePath = Join-Path $ctl 'watchdog.state.json'
    $state = @{ extFails = 0; lastTunnelRestart = '2000-01-01T00:00:00' }
    if (Test-Path $statePath) { try { $o = Get-Content $statePath -Raw | ConvertFrom-Json; $state.extFails = [int]$o.extFails; $state.lastTunnelRestart = [string]$o.lastTunnelRestart } catch { } }

    # 1) supervisors
    foreach ($s in $cfg.services) {
        if ((Test-SupervisorRunning $s.name) -or (Test-Path (Join-Path $ctl ($s.name + '.stop')))) { continue }
        Write-Log $wlog "supervisor '$($s.name)' missing - starting it"
        # start through its own scheduled task so it runs under the service account, not SYSTEM
        try { Start-ScheduledTask -TaskName ("GreenNova-" + $s.name) -ErrorAction Stop }
        catch {
            Write-Log $wlog "WARN task GreenNova-$($s.name) not startable ($($_.Exception.Message)); launching directly"
            Start-Process powershell.exe -WindowStyle Hidden -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + (Join-Path $PSScriptRoot 'supervisor.ps1') + '"'), '-Name', $s.name) | Out-Null
        }
    }

    # 2) tunnel service must be running
    $cf = Get-Service -Name 'Cloudflared' -ErrorAction SilentlyContinue
    if ($cf -and $cf.Status -ne 'Running') { Write-Log $wlog "Cloudflared service was $($cf.Status) - starting it"; try { Start-Service Cloudflared } catch { Write-Log $wlog "ERROR starting Cloudflared: $($_.Exception.Message)" } }

    # 3) public reachability
    $fe = @($cfg.services | Where-Object { $_.name -eq 'frontend' })[0]
    $localOk = Test-Http $fe.health 8
    $internet = Test-Connection -ComputerName 1.1.1.1 -Count 1 -Quiet
    $x = Test-ExternalSite $cfg.domain
    if ($x.ok) {
        if ($state.extFails -gt 0) { Write-Log $wlog "public site reachable again (was failing $($state.extFails) checks)" }
        $state.extFails = 0
    } else {
        $state.extFails++
        Write-Log $wlog "WARN public check failed (HTTP $($x.code)); consecutive=$($state.extFails) local=$localOk internet=$internet"
        $since = ((Get-Date) - [datetime]$state.lastTunnelRestart).TotalMinutes
        if ($state.extFails -ge 3 -and $localOk -and $internet -and $since -ge 60 -and $cf) {
            Write-Log $wlog 'ERROR public site down while local+internet OK for 3 checks - restarting Cloudflared service'
            try { Restart-Service Cloudflared -Force; $state.lastTunnelRestart = (Get-Date).ToString('s'); $state.extFails = 0 } catch { Write-Log $wlog "ERROR restarting Cloudflared: $($_.Exception.Message)" }
        }
    }

    # 4) housekeeping warnings
    $freeGB = [math]::Round((Get-PSDrive C).Free / 1GB, 1)
    if ($freeGB -lt 5) { Write-Log $wlog "WARN low disk space on C: $freeGB GB" }
    @{ extFails = $state.extFails; lastTunnelRestart = $state.lastTunnelRestart } | ConvertTo-Json | Set-Content -LiteralPath $statePath
} finally {
    try { $wm.ReleaseMutex() } catch { }
    $wm.Dispose()
}
