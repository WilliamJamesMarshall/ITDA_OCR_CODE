"""Strict CPU-only entrypoint for Korean PP-OCRv5 recognition training."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


PADDLEOCR_COMMIT = "b03f46425e8ff4442b268ce449e3eef758146cd4"
CHECKPOINT_SHA256 = "8975dede5e0c2f47e0a7712b3d79ffdc766972f872fd0441ebcccd9d77cd52a3"
DICTIONARY_SHA256 = "2193f5dd0c62a4f268902b5d96dadfec3908d299afa9a6e5cad2c6a96c772828"
SEED = 20260911
CPU_THREADS = 4
MAX_TEXT_LENGTH = 25

ROOT = Path(__file__).resolve().parents[3]
RUNTIME = ROOT / "training_runtime" / "PaddleOCR-v3.7.0"
CHECKPOINT = ROOT / "weights" / "training" / "korean_PP-OCRv5_mobile_rec_pretrained.pdparams"
DICTIONARY = RUNTIME / "ppocr" / "utils" / "dict" / "ppocrv5_korean_dict.txt"
CONFIG = ROOT / "notebooks" / "project" / "configs" / "training" / "korean_PP-OCRv5_mobile_rec_cpu.yml"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_head(path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def validate_label_file(path: Path) -> dict:
    seen: set[str] = set()
    labels = 0
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not raw_line.strip():
            continue
        try:
            image_text, label = raw_line.split("\t", 1)
        except ValueError as exc:
            raise ValueError(f"{path}:{line_number}: expected image<TAB>label") from exc
        image_path = Path(image_text)
        if not image_path.is_absolute():
            image_path = ROOT / image_path
        resolved = str(image_path.resolve()).casefold()
        if resolved in seen:
            raise ValueError(f"{path}:{line_number}: duplicate image path")
        if not image_path.is_file():
            raise FileNotFoundError(f"{path}:{line_number}: image not found: {image_path}")
        if not label:
            raise ValueError(f"{path}:{line_number}: empty label")
        if len(label) > MAX_TEXT_LENGTH:
            raise ValueError(f"{path}:{line_number}: label exceeds {MAX_TEXT_LENGTH} characters")
        seen.add(resolved)
        labels += 1
    if not labels:
        raise ValueError(f"{path}: no labels")
    return {"path": str(path.resolve()), "samples": labels, "images": seen}


def run_preflight(check_model: bool = True) -> dict:
    required = [RUNTIME, CHECKPOINT, DICTIONARY, CONFIG]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("missing training assets: " + ", ".join(missing))
    if sys.version_info[:2] != (3, 10):
        raise RuntimeError(f"Python 3.10 required, observed {sys.version.split()[0]}")
    checkpoint_hash = sha256(CHECKPOINT)
    dictionary_hash = sha256(DICTIONARY)
    if git_head(RUNTIME) != PADDLEOCR_COMMIT:
        raise RuntimeError("PaddleOCR runtime commit differs from the frozen contract")
    if checkpoint_hash != CHECKPOINT_SHA256:
        raise RuntimeError("initial checkpoint SHA-256 differs from the frozen contract")
    if dictionary_hash != DICTIONARY_SHA256:
        raise RuntimeError("Korean dictionary SHA-256 differs from the frozen contract")

    import paddle
    import yaml

    if paddle.__version__ != "3.2.2":
        raise RuntimeError(f"paddlepaddle 3.2.2 required, observed {paddle.__version__}")
    if paddle.is_compiled_with_cuda():
        raise RuntimeError("CPU-only PaddlePaddle build required")
    paddle.set_device("cpu")

    compatibility = None
    if check_model:
        sys.path.insert(0, str(RUNTIME))
        from ppocr.modeling.architectures import build_model
        from ppocr.postprocess import build_post_process

        config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
        config["Global"]["character_dict_path"] = str(DICTIONARY)
        post_process = build_post_process(config["PostProcess"], config["Global"])
        character_count = len(post_process.character)
        config["Architecture"]["Head"]["out_channels_list"] = {
            "CTCLabelDecode": character_count,
            "NRTRLabelDecode": character_count + 3,
        }
        model = build_model(config["Architecture"])
        model_state = model.state_dict()
        checkpoint_state = paddle.load(str(CHECKPOINT))
        mismatches = [
            key
            for key, value in checkpoint_state.items()
            if key not in model_state or list(value.shape) != list(model_state[key].shape)
        ]
        missing_keys = [key for key in model_state if key not in checkpoint_state]
        if mismatches or missing_keys:
            raise RuntimeError(
                f"checkpoint incompatible: mismatches={len(mismatches)}, missing={len(missing_keys)}"
            )
        compatibility = {
            "dictionary_classes_with_special_tokens": character_count,
            "model_tensors": len(model_state),
            "checkpoint_tensors": len(checkpoint_state),
            "matched_tensors": len(model_state),
            "model_parameters": sum(int(value.numel()) for value in model_state.values()),
        }

    return {
        "status": "passed",
        "checked_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "python": sys.version.split()[0],
        "paddlepaddle": paddle.__version__,
        "device": paddle.device.get_device(),
        "cpu_threads": CPU_THREADS,
        "seed": SEED,
        "paddleocr_commit": PADDLEOCR_COMMIT,
        "checkpoint": {
            "path": str(CHECKPOINT.relative_to(ROOT)),
            "bytes": CHECKPOINT.stat().st_size,
            "sha256": checkpoint_hash,
        },
        "dictionary": {
            "path": str(DICTIONARY.relative_to(ROOT)),
            "sha256": dictionary_hash,
        },
        "model_compatibility": compatibility,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--skip-model-check", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--round", type=int, choices=range(1, 9))
    parser.add_argument("--workspace", type=Path, default=Path('C:/ITDA_OCR_WORKSPACE/sequential-8-rounds'))
    parser.add_argument("--train-list", type=Path)
    parser.add_argument("--validation-list", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument('--inference-python', type=Path,
                        default=ROOT / '.labeling_paddle_env/Scripts/python.exe')
    args = parser.parse_args()

    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    os.environ["OMP_NUM_THREADS"] = str(CPU_THREADS)
    os.environ["FLAGS_num_threads"] = str(CPU_THREADS)
    os.environ["FLAGS_paddle_num_threads"] = str(CPU_THREADS)

    report = run_preflight(check_model=not args.skip_model_check)
    report_path = args.report
    if args.preflight_only:
        report_path = report_path or ROOT / "학습 및 테스트 결과" / "00_protocol" / "training_preflight.json"
        if report_path:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.round is None or args.train_list is None or args.validation_list is None:
        parser.error("--round, --train-list, and --validation-list are required for training")
    # Standalone invocation places scripts/ rather than the repository on sys.path.
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from scripts.sequential_rounds import require_training_release
    require_training_release(args.workspace,args.round,args.train_list.resolve(),args.validation_list.resolve())
    train_info = validate_label_file(args.train_list.resolve())
    validation_info = validate_label_file(args.validation_list.resolve())
    overlap = train_info["images"] & validation_info["images"]
    if overlap:
        raise ValueError(f"optimizer_train and inner_validation overlap: {len(overlap)} images")
    del train_info["images"], validation_info["images"]

    output_dir = (args.output_dir or args.workspace / "models" / f"round_{args.round:02d}").resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError('Training output is not empty; preserve previous results')
    output_dir.mkdir(parents=True, exist_ok=True)
    report.update({"round": args.round, "optimizer_train": train_info, "inner_validation": validation_info})
    report_path = report_path or output_dir / "training_preflight.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    command = [
        sys.executable,
        str(ROOT / 'notebooks/project/run.py'),
        'scripts.train_sequential_cpu',
        "-c",
        str(CONFIG),
        "-o",
        f"Global.use_gpu=False",
        f"Global.seed={SEED}",
        f"Global.pretrained_model={CHECKPOINT}",
        "Global.checkpoints=null",
        f"Global.save_model_dir={output_dir}",
        f"Global.save_res_path={output_dir / 'predicts.txt'}",
        f"Global.character_dict_path={DICTIONARY}",
        f"Train.dataset.label_file_list=[{args.train_list.resolve()}]",
        f"Eval.dataset.label_file_list=[{args.validation_list.resolve()}]",
    ]
    training_env = {**os.environ, 'ITDA_SEQUENTIAL_WORKSPACE': str(args.workspace.resolve()),
                    'ITDA_SEQUENTIAL_ROUND': str(args.round)}
    completed = subprocess.run(command, cwd=ROOT, env=training_env)
    if completed.returncode == 0:
        from scripts.sequential_rounds import complete_training
        complete_training(args.workspace, args.round, output_dir, args.inference_python)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
