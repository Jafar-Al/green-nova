# Final security checks for the deployed system. Read-only. Exit code 1 if any check fails. ASCII only.
#   powershell -ExecutionPolicy Bypass -File ops\tests\security-check.ps1
param([string]$Domain = 'greennova.dosteam.org', [string]$Run = 'C:\GreenNovaRun')
$ErrorActionPreference = 'Continue'
$script:fails = 0
function Check([string]$Name, [bool]$Ok, [string]$Detail = '') {
    if (-not $Ok) { $script:fails++ }
    Write-Host ('[{0}] {1,-52} {2}' -f $(if ($Ok) { 'PASS' } else { 'FAIL' }), $Name, $Detail) -ForegroundColor $(if ($Ok) { 'Green' } else { 'Red' })
}
function Http([string]$Url, [string]$Method = 'GET') {
    try { $r = Invoke-WebRequest -Uri $Url -Method $Method -UseBasicParsing -TimeoutSec 35 -MaximumRedirection 0 -ErrorAction Stop; return @{ code = [int]$r.StatusCode; headers = $r.Headers; body = [string]$r.Content } }
    catch { $resp = $_.Exception.Response; if ($resp) { $b = ''; try { $b = (New-Object IO.StreamReader($resp.GetResponseStream())).ReadToEnd() } catch { }; return @{ code = [int]$resp.StatusCode; headers = $resp.Headers; body = $b } } return @{ code = 0; headers = @{}; body = '' } }
}

# 1) bindings: frontend on all interfaces, backend loopback only
$l3 = @(Get-NetTCPConnection -State Listen -LocalPort 3000 -ErrorAction SilentlyContinue)
$l8 = @(Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue)
Check 'frontend listens on 0.0.0.0:3000' ([bool]($l3 | Where-Object { $_.LocalAddress -in '0.0.0.0', '::' })) (($l3.LocalAddress | Sort-Object -Unique) -join ',')
Check 'backend listens ONLY on loopback :8000' ($l8.Count -gt 0 -and -not ($l8 | Where-Object { $_.LocalAddress -notin '127.0.0.1', '::1' })) (($l8.LocalAddress | Sort-Object -Unique) -join ',')
$lan = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notmatch '^(127\.|169\.254\.)' } | Select-Object -ExpandProperty IPAddress)
$exposed = @(); foreach ($ip in $lan) { $c = & curl.exe -s -o NUL -w '%{http_code}' --max-time 4 "http://${ip}:8000/health" 2>$null; if ($c -match '^[1-5]\d\d$') { $exposed += $ip } }
Check 'backend NOT reachable on any LAN address' ($exposed.Count -eq 0) ($exposed -join ',')

# 2) backend docs / admin / debug routes closed
foreach ($p in '/docs', '/redoc', '/openapi.json', '/admin', '/debug', '/metrics') { $r = Http "http://127.0.0.1:8000$p"; Check "backend $p not served" ($r.code -in 0, 401, 403, 404) "HTTP $($r.code)" }
# 3) frontend headers + no leaks (local and public)
foreach ($base in @("http://127.0.0.1:3000", "https://$Domain")) {
    $r = Http "$base/"
    $h = $r.headers
    Check "$base reachable" ($r.code -eq 200) "HTTP $($r.code)"
    if ($r.code -eq 200) {
        Check "$base X-Content-Type-Options" ($h['X-Content-Type-Options'] -eq 'nosniff') ([string]$h['X-Content-Type-Options'])
        Check "$base Referrer-Policy set" ([bool]$h['Referrer-Policy']) ([string]$h['Referrer-Policy'])
        Check "$base CSP or frame protection" ([bool]$h['Content-Security-Policy'] -or [bool]$h['X-Frame-Options']) ''
        Check "$base no X-Powered-By" (-not $h['X-Powered-By']) ([string]$h['X-Powered-By'])
        Check "$base body free of local paths/usernames" ($r.body -notmatch '(?i)[A-Z]:\\{1,2}(Users|GreenNova|Windows|Program ?Files|ProgramData)|OneDrive') ''
    }
}
$nf = Http 'http://127.0.0.1:3000/api/definitely-not-a-route'
Check 'unknown API route: no stack trace/path leak' ($nf.body -notmatch '(?i)Traceback|at \w+.*\(.*:\d+:\d+\)|[A-Z]:\\{1,2}(Users|GreenNova|Windows|Program ?Files|ProgramData)') "HTTP $($nf.code)"

# 4) release folder: no secrets, no env files
if (Test-Path $Run) {
    $envf = @(Get-ChildItem $Run -Recurse -Force -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^\.env($|\.)|kaggle\.json|\.pem$|\.key$|\.token$' -and $_.Name -ne '.env.example' })
    Check 'no env/credential files in run folder' ($envf.Count -eq 0) (($envf | Select-Object -First 3 -ExpandProperty Name) -join ',')
    $pat = 'eyJ[A-Za-z0-9_\-]{60,}|CLOUDFLARE_API_TOKEN\s*[=:]\s*\S{10,}|KAGGLE_KEY\s*[=:]\s*\S{10,}|"key"\s*:\s*"[0-9a-f]{32}"|cfut_[A-Za-z0-9]{20,}'
    $hits = @(Get-ChildItem $Run -Recurse -File -Include *.js, *.json, *.py, *.txt, *.md, *.yml, *.yaml, *.html, *.env -ErrorAction SilentlyContinue | Where-Object { $_.Length -lt 3MB -and $_.FullName -notmatch 'node_modules' } | Select-String -Pattern $pat -List -ErrorAction SilentlyContinue)
    Check 'no credential-like strings in run folder' ($hits.Count -eq 0) (($hits | Select-Object -First 3 -ExpandProperty Path) -join ',')
    $rw = (& icacls.exe (Join-Path $Run 'ops') 2>$null) -join ' '
    Check 'ops folder not writable by Users/Everyone' ($rw -notmatch '(Users|Everyone|Authenticated Users):\([^)]*\)?\(?(M|F|W)\)') ''
}
# 5) token hygiene
$tokInProc = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match 'CLOUDFLARE_API_TOKEN|eyJ[A-Za-z0-9_\-]{60,}' -and $_.Name -ne 'cloudflared.exe' })
Check 'no token on any process command line (except tunnel service)' ($tokInProc.Count -eq 0) ''
Write-Host $(if ($script:fails -eq 0) { 'SECURITY CHECK: ALL PASS' } else { "SECURITY CHECK: $($script:fails) FAILED" }) -ForegroundColor $(if ($script:fails -eq 0) { 'Green' } else { 'Red' })
if ($script:fails -gt 0) { exit 1 }
