[CmdletBinding()]
param(
    [ValidateSet('Prepare','Start','Stop','Status')][string]$Action = 'Status',
    [string]$IdentityFile,
    [ValidatePattern('^$|^127\.0\.0\.1:[0-9]{1,5}$')][string]$SocksProxy,
    [switch]$AudioDemo
)
$ErrorActionPreference = 'Stop'
if ($AudioDemo -and $Action -ne 'Start') { throw '-AudioDemo requires Start.' }
$root = Join-Path (Split-Path $PSScriptRoot -Parent) '.tmp/care-demo-operator'
New-Item -ItemType Directory -Force -Path $root | Out-Null
$statePath = Join-Path $root 'state.json'
$output = Join-Path $root 'kit'
New-Item -ItemType Directory -Force -Path $output | Out-Null
$lock = [IO.File]::Open((Join-Path $root 'operator.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
try {
    $state = if (Test-Path -LiteralPath $statePath) { Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json -AsHashtable } else { $null }
    if (-not $PSBoundParameters.ContainsKey('SocksProxy') -and $state) { $SocksProxy = $state.socks_proxy }
    function Save-State {
        $state | ConvertTo-Json | Set-Content -LiteralPath "$statePath.new" -Encoding utf8
        Move-Item -LiteralPath "$statePath.new" -Destination $statePath -Force
    }
    function Invoke-Validation([string]$Operation) {
        $arguments = @('-NoProfile','-File',(Join-Path $PSScriptRoot 'Invoke-BoardValidation.ps1'),'-Action',$Operation,'-OutputDirectory',$output)
        if ($state) { $arguments += @('-Session',$state.session) }
        if ($IdentityFile) { $arguments += @('-IdentityFile',$IdentityFile) }
        if ($SocksProxy) { $arguments += @('-SocksProxy',$SocksProxy) }
        if ($Operation -eq 'StartShadow') {
            $arguments += '-FastDemo'
            if ($AudioDemo) { $arguments += '-AudioDemo' }
        }
        $result = & (Join-Path $PSHOME 'pwsh.exe') @arguments
        if ($LASTEXITCODE -ne 0) { throw "Validation action failed: $Operation. Ownership retained; use Stop to recover." }
        return ($result | Out-String | ConvertFrom-Json)
    }
    function Get-ReadyProbe([string]$Mode) {
        for ($attempt=0; $attempt -lt 7; $attempt++) {
            try {
                $probe = Invoke-Validation 'Probe'
                if ($probe.status -eq 'PASS' -and $probe.care_mode -eq $Mode -and
                    ($Mode -ne 'off' -or -not $probe.care_config_present)) { return $probe }
            } catch { if ($attempt -eq 6) { throw } }
            if ($attempt -lt 6) { Start-Sleep -Seconds 3 }
        }
        throw "Device has not confirmed $Mode; ownership retained."
    }
    if ($Action -eq 'Prepare') { Invoke-Validation 'Prepare' | ConvertTo-Json -Depth 12; return }
    if ($Action -eq 'Start') {
        if ($state -and $state.status -ne 'closed') { throw 'An owned session is pending/running. Run Stop before starting again.' }
        if (-not (Test-Path -LiteralPath (Join-Path $output 'board-kit.zip'))) { $null = Invoke-Validation 'Prepare' }
        $null = Get-ReadyProbe 'off'
        $state = @{ session=('/root/guardian-care-staging/operator-' + [guid]::NewGuid().ToString('N')); status='pending'; socks_proxy=$SocksProxy }
        Save-State
        $null = Invoke-Validation 'StartShadow'
        $probe = Get-ReadyProbe 'shadow'
        $state.status='running'; Save-State
        @{status='RUNNING';audio=[bool]$AudioDemo;session=$state.session;probe=$probe}|ConvertTo-Json -Depth 12
    } elseif ($Action -eq 'Stop') {
        if (-not $state) { throw 'No owned session recorded. Off has not been confirmed.' }
        try { $null = Invoke-Validation 'RecoverOff' } catch { Write-Warning $_.Exception.Message }
        $probe = Get-ReadyProbe 'off'
        $state.status='closed'; Save-State
        @{status='CLOSED';probe=$probe}|ConvertTo-Json -Depth 12
    } else {
        if (-not (Test-Path -LiteralPath (Join-Path $output 'board-kit.zip'))) { $null = Invoke-Validation 'Prepare' }
        Invoke-Validation 'Probe' | ConvertTo-Json -Depth 12
    }
} finally { $lock.Dispose() }
