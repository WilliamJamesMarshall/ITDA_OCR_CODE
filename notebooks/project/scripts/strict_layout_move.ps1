$ErrorActionPreference='Stop'
$root='C:\ITDA_OCR_CODE'
$backup='C:\ITDA_OCR_WORKSPACE\strict-layout-20260912'
if (Test-Path -LiteralPath $backup) { throw 'Existing migration snapshot; inspect before rerunning' }
New-Item -ItemType Directory -Path $backup | Out-Null
$protected=@('상품사진_정답지','상품사진입니다','추가수집_정답지','추가수집데이터','테스트용_정답지','테스트용데이터','학습대상_정답지','학습대상데이터')
$files=foreach($name in $protected){Get-ChildItem -LiteralPath (Join-Path $root $name) -Recurse -File | ForEach-Object {[pscustomobject]@{path=$_.FullName;size=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash}}}
$files | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $backup 'protected-before.json') -Encoding utf8
foreach($name in @('src','scripts','configs','tests')){Copy-Item -LiteralPath (Join-Path $root $name) -Destination (Join-Path $backup $name) -Recurse}
foreach($name in @('predict.ipynb','README.md','.gitignore','requirements.txt','download_weights.sh')){Copy-Item -LiteralPath (Join-Path $root $name) -Destination (Join-Path $backup $name)}
$project=Join-Path $root 'notebooks\project'
New-Item -ItemType Directory -Path $project | Out-Null
foreach($name in @('src','scripts','configs','tests')){
 $source=(Resolve-Path -LiteralPath (Join-Path $root $name)).Path
 $target=[IO.Path]::GetFullPath((Join-Path $project $name))
 if(-not $source.StartsWith($root+'\') -or -not $target.StartsWith($project+'\')){throw 'Move escaped workspace'}
 Move-Item -LiteralPath $source -Destination $target
}
Write-Output 'Snapshot and source relocation complete'
