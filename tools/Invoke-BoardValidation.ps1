[CmdletBinding()]
param(
    [ValidateSet('Prepare','Probe','BaselineResources','Stability','RecoverOff','StartShadow','Mark','Observe','Assess2','Restart','Feedback','Media','EnableWeekly','WeeklyFixture','WeeklyLifecycle','CompleteStep','AudioReadiness','RollbackReadiness','CodeRollback','DownloadEvidence')]
    [string]$Action = 'Prepare',
    [string]$HostName = '47.108.167.0',
    [int]$Port = 6022,
    [string]$UserName = 'root',
    [string]$IdentityFile,
    [string]$Session = '/root/guardian-care-staging/care-validation-20261117',
    [string]$AppRoot = '/root/ai_guardian',
    [string]$OutputDirectory,
    [string]$PythonPath,
    [ValidateSet('baseline','seated','standing','stand-still','cover','leave','return','quiet')]
    [string]$Phase = 'baseline',
    [ValidateRange(1,1800)][int]$Seconds = 50,
    [ValidateSet('short','long')][string]$RestartKind = 'short',
    [ValidatePattern('^(auto|P[0-9]+)$')][string]$Role = 'auto',
    [ValidateRange(2,6)][int]$Step = 2,
    [string]$Proof,
    [string[]]$IncludeSession = @(),
    [switch]$ConfirmedAction,
    [switch]$Quiet
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $repoRoot '.tmp/board-ready-kit' }
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$bundlePath = Join-Path $OutputDirectory 'board-kit.zip'
$baselinePath = Join-Path $repoRoot 'deploy/board/care-validation-baseline.json'

function Quote-Posix([string]$Value) {
    return "'" + $Value.Replace("'", "'\''") + "'"
}
function Invoke-Local([string[]]$Arguments) {
    $result = & $PythonPath @Arguments
    if ($LASTEXITCODE -ne 0) { throw 'Local readiness action failed; inspect the reported codes.' }
    return ($result | ConvertFrom-Json)
}

if ($Action -eq 'Prepare') {
    if (-not $PythonPath) {
        $candidate = Join-Path $repoRoot '.tmp/offline-python/cpython-3.9.25-windows-x86_64-none/python.exe'
        if (Test-Path -LiteralPath $candidate) { $PythonPath = $candidate }
        else { $PythonPath = (Get-Command python3.11 -ErrorAction Stop).Source }
    }
    $audit = Invoke-Local -Arguments @((Join-Path $PSScriptRoot 'board_validation.py'),'offline','--output',(Join-Path $OutputDirectory 'compile'))
    $kit = Invoke-Local -Arguments @((Join-Path $PSScriptRoot 'board_validation.py'),'pack','--output',$bundlePath)
    [ordered]@{ status='PASS'; interpreter=$audit.interpreter; compiled_files=$audit.files.Count; kit_sha256=$kit.sha256; board_contacted=$false } | ConvertTo-Json
    exit 0
}

# No SSH or discovery occurs above this line. Device actions are explicit.
if (-not (Test-Path -LiteralPath $bundlePath)) { throw 'Run -Action Prepare first; do not build while the operator is doing physical actions.' }
$bundleHash = (Get-FileHash -LiteralPath $bundlePath -Algorithm SHA256).Hash.ToLowerInvariant()
$remoteRoot = '/root/guardian-care-staging/ready-kit-' + $bundleHash.Substring(0,12)
$connection = @('-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10')
$target = "$UserName@$HostName"
if ($IdentityFile) {
    if (-not (Test-Path -LiteralPath $IdentityFile -PathType Leaf)) { throw 'Private identity file is unavailable.' }
    $connection += @('-i',$IdentityFile)
} else {
    # Use existing local identities, without displaying key contents or paths.
    $keyCandidates = @(Get-ChildItem -LiteralPath (Join-Path $env:USERPROFILE '.ssh') -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Length -lt 20000 -and $_.Extension -notin @('.pub','.log') } |
        Where-Object { try { (Get-Content -LiteralPath $_.FullName -TotalCount 1) -match 'PRIVATE KEY' } catch { $false } } |
        Select-Object -First 4)
    $found = $false
    foreach ($key in $keyCandidates) {
        $trial = $connection + @('-i',$key.FullName)
        & ssh @trial -p $Port $target 'printf ready-key-probe' 1>$null 2>$null
        if ($LASTEXITCODE -eq 0) { $connection = $trial; $found = $true; break }
    }
    if (-not $found) { throw 'No existing noninteractive identity worked. Supply -IdentityFile from local private configuration.' }
}

if ($Action -eq 'DownloadEvidence') {
    $destination = Join-Path $OutputDirectory 'private-evidence'
    New-Item -ItemType Directory -Force -Path $destination | Out-Null
    # Deliberately exclude token/config/roles, database backups, images and media.
    foreach ($name in @('ledger.json','probe.json','off-resources.json','observations.jsonl','step2-assessment.json','restart-short.json','restart-long.json','step3-feedback.json','step3-media.json','step3-signoff.json','step4-weekly.json','step4-lifecycle.json','step4-signoff.json','step5-audio.json','step6-resources.json')) {
        & scp @connection -q -P $Port "${target}:$Session/$name" $destination 2>$null
        if ($LASTEXITCODE -ne 0) { Write-Output "Evidence not available: $name" }
    }
    exit 0
}

& ssh @connection -p $Port $target ('umask 077; mkdir -p ' + (Quote-Posix $remoteRoot))
if ($LASTEXITCODE -ne 0) { throw 'SSH staging failed; no application change attempted.' }
& scp @connection -q -P $Port $bundlePath "${target}:$remoteRoot/board-kit.zip"
if ($LASTEXITCODE -ne 0) { throw 'Kit upload failed; no application change attempted.' }
$verify = @'
import sys,hashlib,zipfile,json,pathlib
p=pathlib.Path(sys.argv[1]);expected=sys.argv[2];root=p.parent
assert hashlib.sha256(p.read_bytes()).hexdigest()==expected,'kit archive mismatch'
with zipfile.ZipFile(p) as z:
 m=json.loads(z.read('kit-manifest.json'))
 assert len(z.namelist())==len(m['files'])+1 and set(z.namelist())==set(m['files'])|{'kit-manifest.json'}
 for name,h in m['files'].items():
  q=root/name
  assert not pathlib.PurePosixPath(name).is_absolute() and '..' not in pathlib.PurePosixPath(name).parts
  assert root.resolve() in q.resolve().parents
  cursor=root
  for part in pathlib.PurePosixPath(name).parts:
   cursor=cursor/part
   assert not cursor.is_symlink(),'symlink staging path refused'
  assert hashlib.sha256(z.read(name)).hexdigest()==h
  if q.exists():assert hashlib.sha256(q.read_bytes()).hexdigest()==h,'modified staging file refused'
 for name,h in m['files'].items():
  q=root/name
  q.parent.mkdir(parents=True,exist_ok=True)
  if not q.exists():q.write_bytes(z.read(name))
'@
# Prefer exactly the current service executable; inactive services use the
# existing system inspector only, and probe will refuse to pass the gate.
$bootstrap = 'pid=$(systemctl show guardian-board.service -p MainPID --value); board_py=$(readlink "/proc/$pid/exe"); if [ -z "$board_py" ]; then board_py=$(command -v python3); fi; PYTHONDONTWRITEBYTECODE=1 "$board_py" -c '
$bootstrap += (Quote-Posix $verify) + ' ' + (Quote-Posix "$remoteRoot/board-kit.zip") + ' ' + (Quote-Posix $bundleHash)
& ssh @connection -p $Port $target $bootstrap
if ($LASTEXITCODE -ne 0) { throw 'Kit integrity/extraction failed; no application change attempted.' }
$actions = @{ Probe='probe';RecoverOff='recover-off';StartShadow='start-shadow';Mark='mark';Observe='observe';Assess2='assess2';Restart='restart-case';Feedback='feedback';Media='media';EnableWeekly='enable-weekly';WeeklyFixture='weekly-fixture';WeeklyLifecycle='weekly-lifecycle';CompleteStep='complete-step';AudioReadiness='audio-readiness';RollbackReadiness='rollback-readiness';CodeRollback='code-rollback' }
$actions.BaselineResources='baseline-resources';$actions.Stability='stability'
$arguments = @($actions[$Action],'--session',$Session,'--app-root',$AppRoot)
if ($Action -in @('Probe','StartShadow')) {
    $arguments += @('--reference-time',([DateTimeOffset]::UtcNow.ToUnixTimeSeconds().ToString([System.Globalization.CultureInfo]::InvariantCulture)))
}
switch ($Action) {
    'Mark' { $arguments += @('--phase',$Phase,'--role',$Role); if ($ConfirmedAction) { $arguments += '--confirmed-action' } }
    'Observe' { $arguments += @('--seconds',"$Seconds") }
    'BaselineResources' { $arguments += @('--seconds',"$Seconds") }
    'Stability' { $arguments += @('--seconds',"$Seconds") }
    'Restart' { $arguments += @('--kind',$RestartKind,'--role',$Role) }
    'Feedback' { $arguments += @('--role',$Role) }
    'WeeklyLifecycle' { $arguments += @('--role',$Role) }
    'CompleteStep' { $arguments += @('--step',"$Step"); if ($Proof) { $arguments += @('--proof',$Proof) } }
    'StartShadow' { if ($Quiet) { $arguments += '--quiet' } }
    'Assess2' { foreach ($folder in $IncludeSession) { $arguments += @('--include-session',$folder) } }
}
$command = 'pid=$(systemctl show guardian-board.service -p MainPID --value); board_py=$(readlink "/proc/$pid/exe"); if [ -z "$board_py" ]; then board_py=$(command -v python3); fi; cd ' + (Quote-Posix $remoteRoot) + '; PYTHONDONTWRITEBYTECODE=1 "$board_py" tools/board_validation.py '
$command += (($arguments | ForEach-Object { Quote-Posix $_ }) -join ' ')
& ssh @connection -p $Port $target $command
exit $LASTEXITCODE
