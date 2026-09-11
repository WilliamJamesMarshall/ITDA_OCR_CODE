#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
WEIGHTS_DIR="${SCRIPT_DIR}/weights/paddle"
BASE_URL="https://huggingface.co/PaddlePaddle"

hash_file() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | awk '{print $1}'
    else
        echo "A SHA-256 utility (sha256sum or shasum) is required." >&2
        return 1
    fi
}

fetch() {
    local model="$1"
    local revision="$2"
    local filename="$3"
    local expected="$4"
    local directory="${WEIGHTS_DIR}/${model}"
    local destination="${directory}/${filename}"
    local temporary="${destination}.download"
    local actual

    mkdir -p "$directory"
    if [[ -f "$destination" ]]; then
        actual="$(hash_file "$destination")"
        if [[ "$actual" == "$expected" ]]; then
            echo "Verified ${model}/${filename}"
            return
        fi
    fi

    if command -v curl >/dev/null 2>&1; then
        curl --fail --location --retry 3 --connect-timeout 20 \
            --output "$temporary" "${BASE_URL}/${model}/resolve/${revision}/${filename}"
    elif command -v wget >/dev/null 2>&1; then
        wget --tries=3 --timeout=20 --output-document="$temporary" \
            "${BASE_URL}/${model}/resolve/${revision}/${filename}"
    else
        echo "curl or wget is required to download model weights." >&2
        return 1
    fi

    actual="$(hash_file "$temporary")"
    if [[ "$actual" != "$expected" ]]; then
        rm -f -- "$temporary"
        echo "SHA-256 mismatch for ${model}/${filename}" >&2
        return 1
    fi
    mv -f -- "$temporary" "$destination"
    echo "Downloaded ${model}/${filename}"
}

fetch "PP-OCRv5_mobile_det" "0d63e78e2b680928f6b1747d76a08db6e645efb7" "inference.json" \
    "05feef1acb00aa4cd7362b15f7f501fc4f99d7b1fa73c1c871e0c7b1504b0f5c"
fetch "PP-OCRv5_mobile_det" "0d63e78e2b680928f6b1747d76a08db6e645efb7" "inference.pdiparams" \
    "afa1820cb16c1fd0dad589d0f8b389139061c1ef6d68019685fd07be997dda5b"
fetch "PP-OCRv5_mobile_det" "0d63e78e2b680928f6b1747d76a08db6e645efb7" "inference.yml" \
    "98069072e1b6b37d727fd9d9f11725faa46d6ea0de012f2ed26caea011c37699"

fetch "PP-OCRv6_small_det" "106c97591b235f607453300d9fc8c1cad1b25488" "inference.json" \
    "89240f689a4a77aad75ef55a8df0a15c8e1d4980a327d17e58f24bbadde5aeab"
fetch "PP-OCRv6_small_det" "106c97591b235f607453300d9fc8c1cad1b25488" "inference.pdiparams" \
    "5043d4ccc8d63402ccea8feefcee4db57077431a873e78d2191836a178a492da"
fetch "PP-OCRv6_small_det" "106c97591b235f607453300d9fc8c1cad1b25488" "inference.yml" \
    "193f435274bf9f0b5f71a929bbfbcf148282df7e633b34e7c373e8f44741b516"

fetch "korean_PP-OCRv5_mobile_rec" "24b085d9d3d9153a21d97f585fcaaee7a362a487" "inference.json" \
    "562404e3c590c50c93778d5f0a94df21b47b5ab8f3ea6d47c7f8a7930c3bc844"
fetch "korean_PP-OCRv5_mobile_rec" "24b085d9d3d9153a21d97f585fcaaee7a362a487" "inference.pdiparams" \
    "cac3e5f12cf04aaa77f6a5bc704e4e736ef2908476551891d84b41b4e9090462"
fetch "korean_PP-OCRv5_mobile_rec" "24b085d9d3d9153a21d97f585fcaaee7a362a487" "inference.yml" \
    "f757fa1c40e99edcf27e9cce879b93eb2a51fa46f5ef39095689b8c37dd75998"

fetch "en_PP-OCRv5_mobile_rec" "267c36e24c331595590fe7bd72bde2436fd286f2" "inference.json" \
    "fd1b6ec722ea841a72d3ba43e527df1d1066d5d7808e0503ee3eec7265188753"
fetch "en_PP-OCRv5_mobile_rec" "267c36e24c331595590fe7bd72bde2436fd286f2" "inference.pdiparams" \
    "3ec8a97ed6cefe8568d3e2ee90bb193299b566a7661aa4fd52d224b96b59f66b"
fetch "en_PP-OCRv5_mobile_rec" "267c36e24c331595590fe7bd72bde2436fd286f2" "inference.yml" \
    "27e91d0582f40168aa218303c76e184bc78fa7a5d105aad0cfbad8458b441067"

echo "All PaddleOCR weights are ready under ${WEIGHTS_DIR}."
