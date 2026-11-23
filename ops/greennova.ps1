# Green Nova AI - the single control script.
#   powershell -ExecutionPolicy Bypass -File ops\greennova.ps1 <command> [name]
# ASCII only, Windows PowerShell 5.1.
param(
    [Parameter(Position = 0)][ValidateSet('start', 'stop', 'restart', 'status', 'health', 'install', 'uninstall', 'release', 'logs', 'help')][string]$Command = 'help',
    [Parameter(Position = 1)][string]$Name,
    [switch]$NoExternal,
    [switch]$Elevated,
    [string]$RunAsUser
)
$ErrorActionPreference = 'Stop'
$Here = Split-Path -Parent $PSCommandPath
. (Join-Path $Here 'lib\common.ps1')
. (Join-Path $Here 'lib\health.ps1')
$cfg = Get-Config
$run = $cfg.runRoot
$PsExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'

function Show-Help {
    @'
Green Nova AI control script
  health      full check: services, tunnel, public https URL, memory, disk, GPU. Exit code 1 if anything is wrong.
  status      short status of services and scheduled tasks
  start       start all services now (idempotent, never duplicates)
  stop        stop all services and keep them stopped until "start" (or the next reboot)
  restart     stop, then start
  logs [name] last log lines: backend | frontend | watchdog | install
  release     copy the current code/build into C:\GreenNovaRun (no admin needed after "install")
  install     register boot-time tasks (needs ONE administrator approval - UAC prompt)
  uninstall   remove the boot-time tasks (does not touch the Cloudflare Tunnel service)
'@ | Write-Host
}

function Get-SupervisorScript {
    $i = Join-Path $run 'ops\lib\supervisor.ps1'
    if (Test-Path $i) { return $i }
    return (Join-Path $Here 'lib\supervisor.ps1')
}

function Start-One([string]$n) {
    New-Item -ItemType Directory -Force (Join-Path $run 'control') | Out-Null
    Remove-Item -LiteralPath (Join-Path $run "control\$n.stop") -ErrorAction SilentlyContinue
    if (Test-SupervisorRunning $n) { Write-Host "$n : supervisor already running"; return }
    Start-Process $PsExe -WindowStyle Hidden -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + (Get-SupervisorScript) + '"'), '-Name', $n) | Out-Null
    Write-Host "$n : supervisor launched"
}

function Stop-One([string]$n) {
    New-Item -ItemType Directory -Force (Join-Path $run 'control') | Out-Null
    New-Item -ItemType File -Force (Join-Path $run "control\$n.stop") | Out-Null
    $d = (Get-Date).AddSeconds(40)
    while ((Test-SupervisorRunning $n) -and ((Get-Date) -lt $d)) { Start-Sleep -Seconds 2 }
    Write-Host ("{0} : {1}" -f $n, $(if (Test-SupervisorRunning $n) { 'still stopping (supervisor will exit shortly)' } else { 'stopped' }))
}

function Show-Status {
    foreach ($s in $cfg.services) {
        Write-Host ("{0,-10} supervisor={1,-5} port {2}={3}" -f $s.name, (Test-SupervisorRunning $s.name), $s.port, [bool](Get-PortOwner ([int]$s.port)))
    }
    $cf = Get-Service Cloudflared -ErrorAction SilentlyContinue
    Write-Host ("Cloudflared service: {0}" -f $(if ($cf) { "$($cf.Status) ($($cf.StartType))" } else { 'not found' }))
    Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object { $_.TaskName -like 'GreenNova-*' } | ForEach-Object { Write-Host ("task {0,-20} {1}" -f $_.TaskName, $_.State) }
}

function Install-All {
    if (-not (Test-Admin)) {
        Write-Host 'One administrator approval (UAC) is needed to register the boot-time tasks. Please approve the prompt on screen.'
        $who = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        New-Item -ItemType Directory -Force (Join-Path $run 'logs') | Out-Null
        $a = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $PSCommandPath + '"'), 'install', '-Elevated', '-RunAsUser', ('"' + $who + '"'))
        Start-Process $PsExe -Verb RunAs -ArgumentList $a -Wait
        $tx = Join-Path $run 'logs\install.log'
        if (Test-Path $tx) { Get-Content $tx -Tail 40 } else { Write-Host 'No install log found - the UAC prompt may have been declined.' }
        return
    }
    if (-not $RunAsUser) { $RunAsUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name; Write-Host "RunAsUser not given - using the current user: $RunAsUser" }
    New-Item -ItemType Directory -Force (Join-Path $run 'logs'), (Join-Path $run 'control'), (Join-Path $run 'ops') | Out-Null
    Start-Transcript -Path (Join-Path $run 'logs\install.log') -Force | Out-Null
    try {
        Write-Host "Installing Green Nova services for user $RunAsUser into $run"
        # 1) ops scripts into the run root (locked down afterwards)
        & robocopy.exe $Here (Join-Path $run 'ops') /MIR /XD logs control /NFL /NDL /NJH /NJS /NP | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE)" }
        # 2) ACLs on OUR folder only: run root writable by the service user; ops read-only (admin-write) so SYSTEM never runs tamperable code
        & icacls.exe $run /inheritance:r /grant:r 'SYSTEM:(OI)(CI)F' 'Administrators:(OI)(CI)F' ("{0}:(OI)(CI)M" -f $RunAsUser) | Out-Null
        & icacls.exe (Join-Path $run 'ops') /inheritance:r /grant:r 'SYSTEM:(OI)(CI)F' 'Administrators:(OI)(CI)F' ("{0}:(OI)(CI)RX" -f $RunAsUser) | Out-Null
        # 3) tasks
        $set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
        $boot = New-ScheduledTaskTrigger -AtStartup
        $boot.Delay = 'PT30S'
        $svcPrincipal = New-ScheduledTaskPrincipal -UserId $RunAsUser -LogonType S4U -RunLevel Limited
        foreach ($s in $cfg.services) {
            $arg = ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -Name {1}' -f (Join-Path $run 'ops\lib\supervisor.ps1'), $s.name)
            $act = New-ScheduledTaskAction -Execute $PsExe -Argument $arg -WorkingDirectory $run
            Register-ScheduledTask -TaskName ("GreenNova-" + $s.name) -Action $act -Trigger $boot -Settings $set -Principal $svcPrincipal -Description "Green Nova AI $($s.name) supervisor (restarts the service if it dies)" -Force | Out-Null
            Write-Host "registered task GreenNova-$($s.name)"
        }
        $rep = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 7300)
        $wdPrincipal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
        $wdAct = New-ScheduledTaskAction -Execute $PsExe -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f (Join-Path $run 'ops\lib\watchdog.ps1')) -WorkingDirectory $run
        Register-ScheduledTask -TaskName 'GreenNova-watchdog' -Action $wdAct -Trigger @($boot, $rep) -Settings $set -Principal $wdPrincipal -Description 'Green Nova AI watchdog: revives supervisors, keeps Cloudflared running, checks the public site' -Force | Out-Null
        Write-Host 'registered task GreenNova-watchdog'
        # 4) start now
        foreach ($s in $cfg.services) { Start-ScheduledTask -TaskName ("GreenNova-" + $s.name) }
        Start-ScheduledTask -TaskName 'GreenNova-watchdog'
        Write-Host 'tasks started. INSTALL OK'
    } catch {
        Write-Host ("INSTALL FAILED: " + $_.Exception.Message) -ForegroundColor Red
    } finally {
        Stop-Transcript | Out-Null
    }
}

function Uninstall-All {
    if (-not (Test-Admin)) {
        Write-Host 'Administrator approval (UAC) needed to remove the tasks.'
        Start-Process $PsExe -Verb RunAs -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $PSCommandPath + '"'), 'uninstall', '-Elevated') -Wait
        return
    }
    foreach ($t in 'GreenNova-backend', 'GreenNova-frontend', 'GreenNova-watchdog') { Unregister-ScheduledTask -TaskName $t -Confirm:$false -ErrorAction SilentlyContinue; Write-Host "removed $t" }
    Write-Host 'Done. Services stay as they are until stopped (greennova.ps1 stop). The Cloudflared service was not touched.'
}

switch ($Command) {
    'help' { Show-Help }
    'status' { Show-Status }
    'health' { $ok = Invoke-HealthCheck $cfg (-not $NoExternal); if (-not $ok) { exit 1 } }
    'start' { foreach ($s in $cfg.services) { Start-One $s.name } }
    'stop' { foreach ($s in @($cfg.services)[($cfg.services.Count - 1)..0]) { Stop-One $s.name } }
    'restart' { foreach ($s in @($cfg.services)[($cfg.services.Count - 1)..0]) { Stop-One $s.name }; foreach ($s in $cfg.services) { Start-One $s.name } }
    'logs' {
        $n = if ($Name) { $Name } else { 'backend' }
        $files = @("$n.supervisor.log", "$n.err.log", "$n.out.log", "$n.log")
        foreach ($f in $files) { $p = Join-Path $run "logs\$f"; if (Test-Path $p) { Write-Host "==== $f"; Get-Content $p -Tail 25 } }
    }
    'release' {
        $rel = Join-Path $Here 'release.ps1'
        if (Test-Path $rel) { & $rel } else { Write-Host 'ops\release.ps1 not present yet (created when the production build exists).' }
    }
    'install' { Install-All }
    'uninstall' { Uninstall-All }
}
