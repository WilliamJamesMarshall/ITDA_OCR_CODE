$ErrorActionPreference = 'Stop'
$project = 'C:\ITDA_OCR_CODE'
$work = 'C:\ITDA_OCR_WORKSPACE'
$evidence = Join-Path $work 'migration-20260912'
$protectedNames = @('상품사진_정답지','상품사진입니다','추가수집_정답지','추가수집데이터','테스트용_정답지','테스트용데이터','학습대상_정답지','학습대상데이터')
if (Test-Path -LiteralPath (Join-Path $evidence 'stable-before.json')) { throw 'Migration baseline exists; inspect before repeating.' }
foreach ($name in $protectedNames) {
    $resolved = (Resolve-Path -LiteralPath (Join-Path $project $name)).Path
    if (-not $resolved.StartsWith($project + '\')) { throw "Invalid protected path: $resolved" }
}
New-Item -ItemType Directory -Force -Path $evidence | Out-Null
function Inventory($names) {
    foreach ($name in $names) {
        Get-ChildItem -LiteralPath (Join-Path $project $name) -File -Recurse | ForEach-Object {
            [pscustomobject]@{path=$_.FullName.Substring($project.Length+1);bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash}
        }
    }
}
Write-Output 'Hashing protected data, source code, weights and approved evidence before migration...'
if (Test-Path -LiteralPath (Join-Path $evidence 'protected-before.json')) {
    $before = @(Get-Content -LiteralPath (Join-Path $evidence 'protected-before.json') -Raw | ConvertFrom-Json)
} else {
    $before = @(Inventory $protectedNames)
    $before | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $evidence 'protected-before.json') -Encoding utf8
}
$stable = @(Inventory @('src','weights','학습 및 테스트 결과'))
$stable | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $evidence 'stable-before.json') -Encoding utf8
foreach ($name in @('src','scripts','tests','configs','docs')) {
    Copy-Item -LiteralPath (Join-Path $project $name) -Destination (Join-Path $evidence $name) -Recurse
}
foreach ($name in @('README.md','Harness_README.md','.gitignore','predict.ipynb','requirements.txt','requirements-train-cpu.lock.txt','download_weights.sh')) {
    Copy-Item -LiteralPath (Join-Path $project $name) -Destination (Join-Path $evidence $name)
}
$moves = @(
    @('학습 및 테스트 결과','workspace'),
    @('artifacts','archive\artifacts'),
    @('labels','archive\labels'),
    @('.codex-tmp','archive\codex-tmp'),
    @('outputs','runs\legacy-outputs')
)
foreach ($pair in $moves) {
    $source = (Resolve-Path -LiteralPath (Join-Path $project $pair[0])).Path
    $target = [IO.Path]::GetFullPath((Join-Path $work $pair[1]))
    if (-not $source.StartsWith($project+'\') -or -not $target.StartsWith($work+'\')) { throw 'Move escaped named roots' }
    if (Test-Path -LiteralPath $target) { throw "Destination exists: $target" }
    New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
    Move-Item -LiteralPath $source -Destination $target
    New-Item -ItemType Junction -Path $source -Target $target | Out-Null
    Write-Output "Moved with legacy compatibility junction: $source -> $target"
}
$docSource = (Resolve-Path -LiteralPath (Join-Path $project 'docs')).Path
$docTarget = [IO.Path]::GetFullPath((Join-Path $project 'notebooks\docs\architecture'))
if (-not $docSource.StartsWith($project+'\') -or -not $docTarget.StartsWith($project+'\')) { throw 'Invalid documentation move' }
New-Item -ItemType Directory -Force -Path (Split-Path $docTarget) | Out-Null
Move-Item -LiteralPath $docSource -Destination $docTarget
New-Item -ItemType Junction -Path $docSource -Target $docTarget | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $project 'notebooks\environment') | Out-Null
Move-Item -LiteralPath (Join-Path $project 'requirements-train-cpu.lock.txt') -Destination (Join-Path $project 'notebooks\environment\requirements-train-cpu.lock.txt')
Write-Output 'Verifying all preserved bytes...'
$after = @(Inventory $protectedNames)
$after | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $evidence 'protected-after.json') -Encoding utf8
$stableAfter = @(Inventory @('src','weights','학습 및 테스트 결과'))
$delta = @(Compare-Object $before $after -Property path,bytes,sha256)
$stableDelta = @(Compare-Object $stable $stableAfter -Property path,bytes,sha256)
[pscustomobject]@{protectedFiles=$before.Count;protectedChanges=$delta.Count;stableFiles=$stable.Count;stableChanges=$stableDelta.Count;protectedFolders=$protectedNames;workRoot=$work} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $evidence 'preservation.json') -Encoding utf8
if ($delta.Count -or $stableDelta.Count) { throw 'Preservation hash mismatch; inspect snapshots.' }
Write-Output "Preservation verified: $($before.Count) protected files, $($stable.Count) source/weight/evidence files."
