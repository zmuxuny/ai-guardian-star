<#
.SYNOPSIS
    Call a one-shot DeepSeek Harness headless session.

.DESCRIPTION
    Wraps the DSH CLI shipped with DeepSeek Harness. The selected working
    directory becomes the headless workspace root, so the session reads the
    AGENTS.md and project files from there.

    Defaults to read-only. Use -Mode workspace-write to allow edits inside the
    working directory. danger-full-access requires -AllowDangerFullAccess.

.PARAMETER Task
    Task text. Quote it when it contains spaces.

.PARAMETER TaskFile
    Read the task from a UTF-8 text file.

.PARAMETER Workdir
    Workspace root for the headless session. Defaults to the current directory.

.PARAMETER Mode
    read-only, workspace-write, or danger-full-access.

.PARAMETER Json
    Pass --json to DSH (newline-delimited run events instead of the final message).

.PARAMETER SessionId
    Resume an existing DSH session. The id must already exist.

.PARAMETER DshHome
    Optional DSH_HOME override for profiles, sessions, and credentials.

.PARAMETER DryRun
    Print the resolved invocation as JSON and exit without calling DSH.

.PARAMETER AllowDangerFullAccess
    Required when -Mode danger-full-access is used.

.EXAMPLE
    .\tools\dsh-headless.ps1 -Task "Read TASKS.md and report the next task. Do not modify files."

.EXAMPLE
    .\tools\dsh-headless.ps1 -Mode workspace-write -TaskFile .\task.md

.EXAMPLE
    .\tools\dsh-headless.ps1 -Json -Task "Return the current task list as JSON."

.EXAMPLE
    .\tools\dsh-headless.ps1 -DryRun -Task "smoke test"
#>
[CmdletBinding(DefaultParameterSetName = 'Text')]
param(
    [Parameter(Mandatory = $true, Position = 0, ParameterSetName = 'Text')]
    [ValidateNotNullOrEmpty()]
    [string]$Task,

    [Parameter(Mandatory = $true, ParameterSetName = 'File')]
    [ValidateNotNullOrEmpty()]
    [string]$TaskFile,

    [string]$Workdir = (Get-Location).Path,

    [ValidateSet('read-only', 'workspace-write', 'danger-full-access')]
    [string]$Mode = 'read-only',

    [switch]$Json,

    [string]$SessionId,

    [string]$DshHome,

    [switch]$DryRun,

    [switch]$AllowDangerFullAccess
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$dsh = 'C:\Users\Yang\AppData\Local\Programs\DeepSeek Harness\resources\runtime\cli\bin\dsh.cmd'
if (-not (Test-Path -LiteralPath $dsh -PathType Leaf)) {
    throw "DSH CLI not found: $dsh"
}

if ($Mode -eq 'danger-full-access' -and -not $AllowDangerFullAccess) {
    throw "Refusing danger-full-access without -AllowDangerFullAccess."
}

if (-not (Test-Path -LiteralPath $Workdir -PathType Container)) {
    throw "Workdir not found: $Workdir"
}
$workdirPath = (Resolve-Path -LiteralPath $Workdir).Path

if ($PSCmdlet.ParameterSetName -eq 'File') {
    if (-not (Test-Path -LiteralPath $TaskFile -PathType Leaf)) {
        throw "TaskFile not found: $TaskFile"
    }
    $Task = Get-Content -LiteralPath $TaskFile -Raw -Encoding utf8
}

if ([string]::IsNullOrWhiteSpace($Task)) {
    throw "Task text is empty."
}
$Task = $Task.Trim()

$dshArguments = @('--profile', 'headless')
if ($Json) {
    $dshArguments += '--json'
}
if ($SessionId) {
    $dshArguments += @('--session-id', $SessionId)
}
$dshArguments += $Task

$previousMode = $env:DSH_PERMISSION_MODE
$previousHome = $env:DSH_HOME
$exitCode = 1

try {
    $env:DSH_PERMISSION_MODE = $Mode
    if ($DshHome) {
        if (-not (Test-Path -LiteralPath $DshHome -PathType Container)) {
            throw "DshHome not found: $DshHome"
        }
        $env:DSH_HOME = (Resolve-Path -LiteralPath $DshHome).Path
    }

    if ($DryRun) {
        [pscustomobject]@{
            dsh         = $dsh
            profile     = 'headless'
            workdir     = $workdirPath
            mode        = $Mode
            json        = [bool]$Json
            sessionId   = $SessionId
            dshHome     = $env:DSH_HOME
            taskLength  = $Task.Length
            taskPreview = if ($Task.Length -gt 160) { $Task.Substring(0, 160) + '...' } else { $Task }
        } | ConvertTo-Json -Depth 3
        $exitCode = 0
        return
    }

    Write-Verbose "DSH: $dsh"
    Write-Verbose "Workdir: $workdirPath"
    Write-Verbose "Mode: $Mode"

    Push-Location -LiteralPath $workdirPath
    try {
        & $dsh @dshArguments
        if ($null -ne $LASTEXITCODE) {
            $exitCode = [int]$LASTEXITCODE
        } else {
            $exitCode = 0
        }
    } finally {
        Pop-Location
    }
} finally {
    if ($null -eq $previousMode) {
        Remove-Item Env:DSH_PERMISSION_MODE -ErrorAction SilentlyContinue
    } else {
        $env:DSH_PERMISSION_MODE = $previousMode
    }

    if ($null -eq $previousHome) {
        Remove-Item Env:DSH_HOME -ErrorAction SilentlyContinue
    } else {
        $env:DSH_HOME = $previousHome
    }
}

exit $exitCode