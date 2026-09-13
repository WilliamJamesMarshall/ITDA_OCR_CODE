param(
    [ValidateSet('Qualify','Test','GroupQualify','GroupTest','GroupEvaluate')][string]$Action = 'Qualify',
    [ValidateRange(1,8)][int]$Round = 1,
    [string]$ApprovalPath,
    [string]$Workspace = 'C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2',
    [string]$ApprovalsDirectory,
    [string]$LabelsPath,
    [switch]$Integration,
    [switch]$Retain
)
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$taskPython = Join-Path $taskRoot '.labeling_paddle_env/Scripts/python.exe'
$taskRunner = Join-Path $taskRoot 'notebooks/project/run.py'
$taskGrouped = $Action.StartsWith('Group')
$taskIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
$taskPrincipal = [Security.Principal.WindowsPrincipal]::new($taskIdentity)
if (-not $taskPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script in an Administrator PowerShell. No firewall settings were changed.'
}
if ($Action -eq 'Test' -and -not (Test-Path -LiteralPath $ApprovalPath -PathType Leaf)) {
    throw 'Test requires an existing actual user start-instruction record.'
}
if ($taskGrouped) {
    & $taskPython $taskRunner scripts.run_round_groups verify --workspace $Workspace
    if ($LASTEXITCODE -ne 0) { throw 'Grouped plan verification failed before firewall changes' }
    if ($Action -eq 'GroupTest' -and -not (Test-Path -LiteralPath $ApprovalsDirectory -PathType Container)) {
        throw 'GroupTest requires per-round actual start approval records'
    }
    if ($Action -eq 'GroupEvaluate' -and -not (Test-Path -LiteralPath $LabelsPath -PathType Leaf)) {
        throw 'GroupEvaluate requires scorer labels'
    }
}
$taskPrograms = & $taskPython $taskRunner scripts.operating_environment paths | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve Python executables' }
$taskPrograms = @($taskPrograms | Sort-Object -Unique)
$taskEvidence = 'C:/ITDA_OCR_WORKSPACE/sequential-8-rounds/firewall-last-run.json'
if ($taskGrouped) {
    $taskEvidenceFolder = Join-Path $Workspace 'firewall'
    New-Item -ItemType Directory -Path $taskEvidenceFolder -Force | Out-Null
    $taskEvidence = Join-Path $taskEvidenceFolder (([guid]::NewGuid().ToString()) + '.json')
}
$taskRecord = [ordered]@{ status='running'; started_at=[DateTimeOffset]::Now.ToString('o'); programs=$taskPrograms; rules=@(); cleanup_complete=$false }
$taskRules = @()
$taskPrefix = 'ITDA-OFFLINE-' + [guid]::NewGuid().ToString()
try {
    foreach ($taskProgram in $taskPrograms) {
        $taskRule = $taskPrefix + '-' + $taskRules.Count
        New-NetFirewallRule -Name $taskRule -DisplayName $taskRule -Direction Outbound -Action Block -Program $taskProgram -Profile Any -Enabled True | Out-Null
        $taskRules += $taskRule
        $taskActiveRule = Get-NetFirewallRule -PolicyStore ActiveStore -Name $taskRule
        if ($taskActiveRule.Enabled -ne 'True' -or $taskActiveRule.Action -ne 'Block') {
            throw "Firewall rule is not active: $taskRule"
        }
        $taskRecord.rules += [ordered]@{ name=$taskRule; program=$taskProgram; active=$true }
    }
    $taskRecord | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $taskEvidence -Encoding UTF8
    if ($taskGrouped) {
        $taskGroupAction = @{GroupQualify='qualify';GroupTest='test';GroupEvaluate='evaluate'}[$Action]
        $taskArguments = @($taskRunner,'scripts.run_round_groups',$taskGroupAction,'--workspace',$Workspace,'--round',"$Round")
        if ($Action -eq 'GroupTest') { $taskArguments += @('--approvals-dir',$ApprovalsDirectory) }
        if ($Action -eq 'GroupEvaluate') { $taskArguments += @('--labels',$LabelsPath) }
        if ($Integration) { $taskArguments += '--integration' }
        if ($Retain) { $taskArguments += '--retain' }
        & $taskPython @taskArguments
    } elseif ($Action -eq 'Qualify') {
        & $taskPython $taskRunner scripts.operating_environment qualify
    } else {
        & $taskPython $taskRunner scripts.sequential_rounds infer --round $Round --approval $ApprovalPath
    }
    if ($LASTEXITCODE -ne 0) { throw "Verification/test failed with exit code $LASTEXITCODE" }
    $taskRecord.status = 'passed'
} catch {
    $taskRecord.status = 'failed'
    $taskRecord.error = $_.Exception.Message
    throw
} finally {
    $taskCleanupErrors = @()
    foreach ($taskRule in $taskRules) {
        try { Remove-NetFirewallRule -Name $taskRule -ErrorAction Stop }
        catch { $taskCleanupErrors += $_.Exception.Message; Write-Warning $_.Exception.Message }
    }
    $taskRecord.cleanup_complete = ($taskCleanupErrors.Count -eq 0)
    $taskRecord.cleanup_errors = $taskCleanupErrors
    $taskRecord.finished_at = [DateTimeOffset]::Now.ToString('o')
    $taskRecord | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $taskEvidence -Encoding UTF8
}
