# Supervises ONE service: starts it, restarts it when it exits or hangs, never switches ports,
# waits for dependencies, logs everything, refuses to run twice. Usage: supervisor.ps1 -Name backend
param([Parameter(Mandatory = $true)][string]$Name)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')

$cfg = Get-Config
$svc = @($cfg.services | Where-Object { $_.name -eq $Name })[0]
if (-not $svc) { throw "Unknown service '$Name'" }
$logDir = Join-Path $cfg.runRoot 'logs'
$ctl = Join-Path $cfg.runRoot 'control'
New-Item -ItemType Directory -Force $logDir, $ctl | Out-Null
$sup = Join-Path $logDir "$Name.supervisor.log"

$mutex = Enter-NamedMutex "Global\GreenNova.$Name"
if ($null -eq $mutex) { Write-Log $sup 'another supervisor already holds the lock - exiting (no duplicate instance)'; exit 0 }

$pidFile = Join-Path $ctl "$Name.supervisor.pid"
$stopFile = Join-Path $ctl "$Name.stop"
Set-Content -LiteralPath $pidFile -Value $PID
Remove-Item -LiteralPath $stopFile -ErrorAction SilentlyContinue   # a fresh supervisor start always means "run"
Write-Log $sup "supervisor started (pid $PID) for '$Name'"

foreach ($p in $svc.env.PSObject.Properties) { [Environment]::SetEnvironmentVariable($p.Name, (Expand-Vars ([string]$p.Value) $cfg), 'Process') }
$argLine = (($svc.args | ForEach-Object { ConvertTo-QuotedArg $_ }) -join ' ')
$out = Join-Path $logDir "$Name.out.log"
$err = Join-Path $logDir "$Name.err.log"
$backoff = 2
$stopping = $false

try {
    while (-not $stopping) {
        if (Test-Path $stopFile) { Write-Log $sup 'stop file present - supervisor exiting'; break }

        # 1) wait for dependencies (then start anyway in degraded mode so the site is never held hostage)
        foreach ($d in @($svc.dependsOn)) {
            if (-not $d) { continue }
            $dep = @($cfg.services | Where-Object { $_.name -eq $d })[0]
            if (-not $dep) { continue }
            $deadline = (Get-Date).AddSeconds([int]$cfg.dependencyWaitSec)
            while ((-not (Test-Http $dep.health)) -and ((Get-Date) -lt $deadline) -and (-not (Test-Path $stopFile))) { Start-Sleep -Seconds 3 }
            if (Test-Http $dep.health) { Write-Log $sup "dependency '$d' is healthy" }
            else { Write-Log $sup "WARN dependency '$d' not healthy after $($cfg.dependencyWaitSec)s - starting anyway (degraded)" }
        }
        if (Test-Path $stopFile) { continue }

        # 2) the port is fixed: free it only from our own orphan, otherwise wait (never switch ports)
        $owner = Get-PortOwner ([int]$svc.port)
        if ($owner) {
            $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$owner" -ErrorAction SilentlyContinue).CommandLine
            if ($cmd -and $svc.match -and ($cmd -like "*$($svc.match)*")) {
                Write-Log $sup "orphan of this service holds port $($svc.port) (pid $owner) - killing it"
                & taskkill.exe /PID $owner /T /F | Out-Null
                Start-Sleep -Seconds 2
            } else {
                Write-Log $sup "ERROR port $($svc.port) is held by a foreign process (pid $owner) - will NOT switch ports, retrying in 15s"
                Start-Sleep -Seconds 15
                continue
            }
        }

        # 3) launch with logs
        foreach ($f in @($out, $err)) { if ((Test-Path $f) -and ((Get-Item $f).Length -gt 0)) { Move-Item -Force $f ($f + '.1') } }
        $sp = @{ FilePath = $svc.exe; WorkingDirectory = $svc.cwd; WindowStyle = 'Hidden'; PassThru = $true; RedirectStandardOutput = $out; RedirectStandardError = $err }
        if ($argLine) { $sp.ArgumentList = $argLine }
        try { $proc = Start-Process @sp } catch { Write-Log $sup "ERROR failed to launch: $($_.Exception.Message)"; Start-Sleep -Seconds $backoff; $backoff = [Math]::Min($backoff * 2, 60); continue }
        $null = $proc.Handle
        $started = Get-Date
        Write-Log $sup "started pid $($proc.Id): $($svc.exe) $argLine"

        # 4) watch: exit, stop request, or failing health checks
        $fails = 0
        $lastCheck = Get-Date
        while (-not $proc.HasExited) {
            Start-Sleep -Seconds 5
            if (Test-Path $stopFile) { Write-Log $sup 'stop requested - killing service'; & taskkill.exe /PID $proc.Id /T /F | Out-Null; $stopping = $true; break }
            $age = ((Get-Date) - $started).TotalSeconds
            if (($age -gt [int]$svc.graceSec) -and (((Get-Date) - $lastCheck).TotalSeconds -ge [int]$svc.healthIntervalSec)) {
                $lastCheck = Get-Date
                if (Test-Http $svc.health 8) { $fails = 0 }
                else {
                    $fails++
                    Write-Log $sup "WARN health check failed ($fails/$($svc.failThreshold)) $($svc.health)"
                    if ($fails -ge [int]$svc.failThreshold) { Write-Log $sup 'ERROR service hung - killing for restart'; & taskkill.exe /PID $proc.Id /T /F | Out-Null; break }
                }
            }
        }
        $proc.WaitForExit(5000) | Out-Null
        $ran = ((Get-Date) - $started).TotalSeconds
        Write-Log $sup ("service exited (code {0}) after {1:N0}s" -f $proc.ExitCode, $ran)
        if ($stopping) { break }
        if ($ran -gt 120) { $backoff = 2 } else { $backoff = [Math]::Min($backoff * 2, 60) }
        Write-Log $sup "restarting in ${backoff}s"
        Start-Sleep -Seconds $backoff
    }
} finally {
    Write-Log $sup 'supervisor stopped'
    Remove-Item -LiteralPath $pidFile -ErrorAction SilentlyContinue
    try { $mutex.ReleaseMutex() } catch { }
    $mutex.Dispose()
}
