$ErrorActionPreference = 'Stop'

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$RuntimePath = Join-Path $ProjectRoot 'training_runtime\PaddleOCR-v3.7.0'
$CheckpointPath = Join-Path $ProjectRoot 'weights\training\korean_PP-OCRv5_mobile_rec_pretrained.pdparams'
$EnvironmentPath = Join-Path $ProjectRoot '.training_env'
$ExpectedCommit = 'b03f46425e8ff4442b268ce449e3eef758146cd4'
$ExpectedCheckpointHash = '8975dede5e0c2f47e0a7712b3d79ffdc766972f872fd0441ebcccd9d77cd52a3'
$CheckpointUrl = 'https://paddle-model-ecology.bj.bcebos.com/paddlex/official_pretrained_model/korean_PP-OCRv5_mobile_rec_pretrained.pdparams'

if (-not (Test-Path -LiteralPath $RuntimePath)) {
    New-Item -ItemType Directory -Force -Path (Split-Path $RuntimePath) | Out-Null
    git clone --depth 1 --branch v3.7.0 https://github.com/PaddlePaddle/PaddleOCR.git $RuntimePath
}
$ObservedCommit = (git -C $RuntimePath rev-parse HEAD).Trim()
if ($ObservedCommit -ne $ExpectedCommit) {
    throw "PaddleOCR commit mismatch: $ObservedCommit"
}

if (-not (Test-Path -LiteralPath $CheckpointPath)) {
    New-Item -ItemType Directory -Force -Path (Split-Path $CheckpointPath) | Out-Null
    Invoke-WebRequest -Uri $CheckpointUrl -OutFile $CheckpointPath
}
$ObservedHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $CheckpointPath).Hash.ToLower()
if ($ObservedHash -ne $ExpectedCheckpointHash) {
    throw "Initial checkpoint SHA-256 mismatch: $ObservedHash"
}

if (-not (Test-Path -LiteralPath (Join-Path $EnvironmentPath 'Scripts\python.exe'))) {
    uv venv --python 3.10 $EnvironmentPath
}
uv pip sync --python (Join-Path $EnvironmentPath 'Scripts\python.exe') (Join-Path $ProjectRoot 'notebooks\environment\requirements-train-cpu.lock.txt')

$env:CUDA_VISIBLE_DEVICES = ''
$env:OMP_NUM_THREADS = '4'
$env:FLAGS_num_threads = '4'
$env:FLAGS_paddle_num_threads = '4'
& (Join-Path $EnvironmentPath 'Scripts\python.exe') (Join-Path $ProjectRoot 'notebooks\project\scripts\train_recognition_cpu.py') --preflight-only
