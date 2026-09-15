param([Parameter(Mandatory=$true)][string]$RunDirectory)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$runPath = (Resolve-Path -LiteralPath $RunDirectory).Path
$releasePath = Join-Path $runPath 'release/release.json'
$release = Get-Content -Raw -LiteralPath $releasePath | ConvertFrom-Json
if ($release.whole_image_test_allowed -ne $false) { throw 'Whole-image tests must remain disabled' }
$otherJobs = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match 'python' -and $_.CommandLine -match 'train_cumulative|train_joint|train_sequential|nbconvert|run_round_groups.*(test|train|worker)'
})
if ($otherJobs.Count) { throw "Existing OCR job detected: $($otherJobs.ProcessId -join ',')" }
$lockPath = Join-Path $runPath 'training.lock'
$runLock = [System.IO.File]::Open($lockPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
$clock = [System.Diagnostics.Stopwatch]::StartNew()
$samples = [System.Collections.Generic.List[object]]::new()
$result = [ordered]@{status='starting'; whole_image_tests='held_until_separate_user_instruction'; shared_weights_changed=$false}
$sharedLockPath = Join-Path (Split-Path $runPath -Parent) 'locks/execution.lock'
$sharedLockOwned = $false
try {
    # Register with the existing grouped coordinator before launching a future run.
    # This script's original running instance predates this fix; a PID-bound guard
    # attaches the same lock to that preserved instance.
    $sharedLockStream = [System.IO.File]::Open($sharedLockPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::Read)
    try {
        $lockBytes = [System.Text.Encoding]::UTF8.GetBytes((@{pid=$PID; started_at=[DateTimeOffset]::UtcNow.ToString('o')} | ConvertTo-Json -Compress))
        $sharedLockStream.Write($lockBytes, 0, $lockBytes.Length)
        $sharedLockOwned = $true
    } finally { $sharedLockStream.Dispose() }
    $env:ITDA_CUMULATIVE_RUN = $runPath
    $env:ITDA_ASSET_ROOT = $projectRoot
    $env:OMP_NUM_THREADS = '4'
    $env:MKL_NUM_THREADS = '4'
    $env:OPENBLAS_NUM_THREADS = '4'
    $env:ITDA_CPU_SET = '0,1,2,3'
    $trainer = Join-Path $runPath 'code/notebooks/project/scripts/train_cumulative_1_5.py'
    $process = Start-Process -FilePath (Join-Path $projectRoot '.training_env/Scripts/python.exe') -ArgumentList @($trainer) -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runPath 'training.stdout.log') -RedirectStandardError (Join-Path $runPath 'training.stderr.log')
    $result.pid = $process.Id
    while (-not $process.HasExited) {
        $process.Refresh()
        if (-not $process.HasExited) {
            # A virtualenv launcher can be a small parent of the actual trainer.
            $sampleProcess = $process
            $sampleScope = 'launcher_before_trainer_runtime'
            $runtimePath = Join-Path $runPath 'training-run/runtime.json'
            if (Test-Path -LiteralPath $runtimePath) {
                $trainerRuntime = Get-Content -Raw -LiteralPath $runtimePath | ConvertFrom-Json
                $actualTrainer = Get-Process -Id $trainerRuntime.pid -ErrorAction SilentlyContinue
                if ($actualTrainer) {
                    $sampleProcess = $actualTrainer
                    $sampleScope = 'trainer_only_not_process_tree'
                } else { $sampleScope = 'launcher_after_trainer_exit' }
            }
            $samples.Add([ordered]@{elapsed_seconds=$clock.Elapsed.TotalSeconds; pid=$sampleProcess.Id; scope=$sampleScope; working_set_bytes=$sampleProcess.WorkingSet64; peak_working_set_bytes=$sampleProcess.PeakWorkingSet64; private_bytes=$sampleProcess.PrivateMemorySize64; cpu_seconds=$sampleProcess.TotalProcessorTime.TotalSeconds; affinity=[long]$sampleProcess.ProcessorAffinity})
            $processRows = @(Get-CimInstance Win32_Process)
            $treeIds = [System.Collections.Generic.HashSet[int]]::new()
            [void]$treeIds.Add($process.Id)
            do {
                $added = $false
                foreach ($row in $processRows) {
                    if ($treeIds.Contains([int]$row.ParentProcessId) -and $treeIds.Add([int]$row.ProcessId)) { $added = $true }
                }
            } while ($added)
            $treeProcesses = @($treeIds | ForEach-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue })
            $samples.Add([ordered]@{elapsed_seconds=$clock.Elapsed.TotalSeconds; scope='launcher_and_descendants_sampled_tree'; pids=@($treeProcesses.Id); working_set_bytes=($treeProcesses | Measure-Object WorkingSet64 -Sum).Sum; private_bytes=($treeProcesses | Measure-Object PrivateMemorySize64 -Sum).Sum})
        }
        Start-Sleep -Seconds 5
    }
    $process.WaitForExit()
    $result.exit_code = $process.ExitCode
    $result.status = if ($process.ExitCode -eq 0) {'completed'} else {'failed'}
} catch {
    $result.status = 'supervisor_failed'
    $result.error = $_.Exception.Message
    throw
} finally {
    $result.total_process_seconds = $clock.Elapsed.TotalSeconds
    $result.samples = $samples.ToArray()
    $result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $runPath 'supervisor-result.json') -Encoding utf8
    $runLock.Dispose()
    if ($sharedLockOwned) { Remove-Item -LiteralPath $sharedLockPath }
    # Retain the consumed lock marker to prevent accidental duplicate execution.
}
if ($result.exit_code -ne 0) { exit 1 }
