# Shared helpers for the Green Nova ops layer. Windows PowerShell 5.1 compatible. ASCII only.
$script:OpsDir = Split-Path -Parent $PSScriptRoot

function Expand-Vars([string]$s, $c) {
    if ($null -eq $s) { return '' }
    return $s.Replace('${RUN}', $c.runRoot).Replace('${DATA}', $c.dataRoot)
}

function Get-Config {
    $p = $env:GREENNOVA_CONFIG
    if (-not $p) { $p = Join-Path $script:OpsDir 'services.json' }
    $c = Get-Content -LiteralPath $p -Raw | ConvertFrom-Json
    foreach ($s in $c.services) {
        $s.exe = Expand-Vars $s.exe $c
        $s.cwd = Expand-Vars $s.cwd $c
        $s.args = @($s.args | ForEach-Object { Expand-Vars $_ $c })
    }
    return $c
}

function Write-Log([string]$File, [string]$Msg) {
    $dir = Split-Path -Parent $File
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
    if ((Test-Path $File) -and ((Get-Item $File).Length -gt 5MB)) { Move-Item -Force $File ($File + '.1') }
    Add-Content -LiteralPath $File -Value ('{0} {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Msg)
}

function Test-Http([string]$Url, [int]$TimeoutSec = 5) {
    if (-not $Url) { return $true }
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec -MaximumRedirection 0 -ErrorAction Stop
        return (($r.StatusCode -ge 200) -and ($r.StatusCode -lt 400))
    } catch {
        $resp = $_.Exception.Response
        if ($resp) { $c = [int]$resp.StatusCode; return (($c -ge 200) -and ($c -lt 400)) }
        return $false
    }
}

function Get-PortOwner([int]$Port) {
    $c = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { return [int]$c.OwningProcess }
    return $null
}

function ConvertTo-QuotedArg([string]$a) {
    if ($a -match '[\s"]') { return '"' + $a.Replace('"', '\"') + '"' }
    return $a
}

# Try to take a named mutex without waiting. Returns the mutex (caller must keep it) or $null if somebody else holds it.
function Enter-NamedMutex([string]$MutexName) {
    $m = $null
    try { $m = New-Object System.Threading.Mutex($false, $MutexName) } catch { return $null }
    $got = $false
    try { $got = $m.WaitOne(0) } catch {
        if (($_.Exception -is [System.Threading.AbandonedMutexException]) -or ($_.Exception.InnerException -is [System.Threading.AbandonedMutexException])) { $got = $true }
        else { $m.Dispose(); return $null }
    }
    if ($got) { return $m }
    $m.Dispose()
    return $null
}

function Test-SupervisorRunning([string]$Name) {
    $m = Enter-NamedMutex "Global\GreenNova.$Name"
    if ($null -eq $m) { return $true }
    try { $m.ReleaseMutex() } catch { }
    $m.Dispose()
    return $false
}

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    return ([Security.Principal.WindowsPrincipal]$id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}
