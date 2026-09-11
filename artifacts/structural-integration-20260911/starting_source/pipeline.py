from __future__ import annotations

import csv
import json
import math
import os
import re
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "1"

import cv2
import numpy as np
from PIL import Image, ImageOps

from .date_extraction import DateSelection, OCRLine, ProductDateRule, parse_dates, select_date, submission_fields
from .ocr_trace import ImageFrame, ImageTrace

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
OUTPUT_COLUMNS = ["image_id", "year", "month", "day", "final_date"]
MODEL_FILES = ("inference.json", "inference.pdiparams", "inference.yml")


@dataclass(frozen=True)
class PipelineConfig:
    weights_dir: Path = field(
        default_factory=lambda: (
            Path(__file__).resolve().parents[1] / "weights" / "paddle"
        )
    )
    mobile_side_limit: int = 1600
    recovery_detector_name: str = "PP-OCRv6_small_det"
    recovery_side_limit: int = 1600
    cpu_threads: int = 4
    enable_clahe: bool = True
    enable_recovery_fallback: bool = True
    enable_rotation_fallback: bool = False
    enable_tile_fallback: bool = True
    tile_fraction: float = 0.62
    tile_max_original_lines: int = 32
    tile_sparse_line_limit: int = 5
    progress_every: int = 25
    product_date_rules: tuple[ProductDateRule, ...] = ()
    collect_trace: bool = True


@dataclass(frozen=True)
class ImagePrediction:
    image_id: str
    final_date: str | None
    selection: DateSelection
    elapsed_seconds: float
    passes: tuple[str, ...]
    error: str | None = None
    trace: dict[str, Any] | None = None


class PaddleOCRBackend:
    """Two-detector PaddleOCR backend with fully local model paths."""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self._validate_model("PP-OCRv5_mobile_det")
        self._validate_model("korean_PP-OCRv5_mobile_rec")
        self._mobile = self._build("PP-OCRv5_mobile_det", config.mobile_side_limit)
        self._recovery = None

    def _model_dir(self, name: str) -> Path:
        return self.config.weights_dir / name

    def _validate_model(self, name: str) -> None:
        model_dir = self._model_dir(name)
        missing = [
            filename for filename in MODEL_FILES if not (model_dir / filename).is_file()
        ]
        if missing:
            raise FileNotFoundError(
                f"Missing offline model files for {name}: {', '.join(missing)}. "
                "Run download_weights.sh before predict.ipynb."
            )

    def _build(self, detector_name: str, side_limit: int):
        from paddleocr import PaddleOCR

        return PaddleOCR(
            text_detection_model_name=detector_name,
            text_detection_model_dir=str(self._model_dir(detector_name)),
            text_recognition_model_name="korean_PP-OCRv5_mobile_rec",
            text_recognition_model_dir=str(
                self._model_dir("korean_PP-OCRv5_mobile_rec")
            ),
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            device="cpu",
            enable_mkldnn=True,
            cpu_threads=self.config.cpu_threads,
            text_recognition_batch_size=8,
            text_det_limit_type="max",
            text_det_limit_side_len=side_limit,
            text_det_thresh=0.25,
            text_det_box_thresh=0.40,
            text_det_unclip_ratio=1.8,
            text_rec_score_thresh=0.15,
        )

    def _recovery_model(self):
        if self._recovery is None:
            name = self.config.recovery_detector_name
            self._validate_model(name)
            self._recovery = self._build(name, self.config.recovery_side_limit)
        return self._recovery

    def recognize(
        self, image: np.ndarray, *, detector: str, variant: str
    ) -> list[OCRLine]:
        self.last_unrecognized_regions = []
        model = self._mobile if detector == "mobile" else self._recovery_model()
        results = list(model.predict(image))
        if not results:
            return []
        payload = results[0].json
        data = payload.get("res", payload)
        texts = data.get("rec_texts", [])
        scores = data.get("rec_scores", [])
        polygons = data.get("rec_polys", [])
        boxes = data.get("rec_boxes", [])
        lines: list[OCRLine] = []
        recognized_polygons = set()
        empty_regions = []
        for index, (text, score) in enumerate(zip(texts, scores)):
            polygon = ()
            geometry_valid = True
            geometry_source = "polygon"
            if index < len(polygons):
                points = np.asarray(polygons[index], dtype=float)
                polygon = tuple(tuple(point) for point in points.tolist())
                box = (
                    float(points[:, 0].min()),
                    float(points[:, 1].min()),
                    float(points[:, 0].max()),
                    float(points[:, 1].max()),
                )
            elif index < len(boxes):
                values = np.asarray(boxes[index], dtype=float).tolist()
                box = tuple(values[:4])
                geometry_source = "box"
            else:
                box = (0.0, float(index), 1.0, float(index + 1))
                geometry_valid = False
                geometry_source = "synthetic_index"
            line = OCRLine(
                text=str(text),
                score=float(score),
                box=box,
                source=f"paddle-{detector}",
                variant=variant,
                polygon=polygon,
                geometry_valid=geometry_valid,
                geometry_source=geometry_source,
            )
            if str(text).strip():
                lines.append(line)
                if polygon:
                    recognized_polygons.add(polygon)
            else:
                empty_regions.append(line)
        # PaddleX keeps detection polygons even when recognition was filtered out.
        # Do not feed these empty regions into the legacy selector or crop scheduler.
        unmatched = {}
        for points in data.get("dt_polys", []):
            polygon = tuple(tuple(float(v) for v in point) for point in points)
            if polygon and polygon not in recognized_polygons:
                xs, ys = zip(*polygon)
                unmatched[polygon] = OCRLine("", 0., (min(xs), min(ys), max(xs), max(ys)),
                    f"paddle-{detector}", variant, polygon=polygon, geometry_source="detector_polygon")
        for line in empty_regions:
            if line.polygon not in unmatched:
                self.last_unrecognized_regions.append(line)
        self.last_unrecognized_regions.extend(unmatched.values())
        return lines


def discover_images(input_dir: str | os.PathLike[str]) -> list[Path]:
    root = Path(input_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"ITDA_INPUT_DIR is not a directory: {root}")
    images = sorted(
        (
            path
            for path in root.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        ),
        key=lambda path: path.name.casefold(),
    )
    if not images:
        raise ValueError(f"No supported images found in ITDA_INPUT_DIR: {root}")
    stems = [path.stem for path in images]
    duplicates = sorted(stem for stem, count in Counter(stems).items() if count > 1)
    if duplicates:
        raise ValueError(
            f"Duplicate image_id values after removing extensions: {duplicates[:5]}"
        )
    return images


def _load_bgr(path: Path) -> np.ndarray:
    with Image.open(path) as source:
        rgb = np.asarray(ImageOps.exif_transpose(source).convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def _clahe(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    enhanced = cv2.createCLAHE(clipLimit=2.4, tileGridSize=(8, 8)).apply(gray)
    return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)


def _date_fragment_lines(lines: Sequence[OCRLine]) -> list[OCRLine]:
    """Choose at most two recovery anchors, not two most legible numbers.

    Damaged date-like text is only a crop hint: no glyphs/digits are repaired
    here. Keep legacy numeric anchors as a last resort, including for tiles.
    """
    selected = []
    for line in lines:
        text = line.text.strip()
        digits = sum(character.isdigit() for character in text)
        separated = any(separator in text for separator in (".", "/", "-", ":"))
        legacy = digits >= 4 and separated
        # Explicit non-date context outranks superficial numeric resemblance.
        non_date = re.search(
            r"%|kcal|\d\s*(?:mg|ml|g|brix)\b|영양|내용량|지방|당류|고객|상담|전화|품목|보고번호|"
            r"\b(?:tel|fax|lot)\b|(?<!\d)0\d{1,2}[- )]\d{2,4}-\d{3,4}|"
            r"(?:로|길)\s*\d+.*\d+-\d+",
            text, re.IGNORECASE,
        )
        # Small, mostly numeric fragments can have missing digits/separators.
        # Do not promote arbitrary long ingredient lines or compact barcodes.
        fragment = (
            separated and len(text) <= 32
            and (digits >= 4 or (digits >= 3 and sum(text.count(s) for s in './-') >= 2))
            and digits / max(1, len(text)) >= 0.25 and not non_date
            and not re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?", text)
        )
        if legacy or fragment:
            priority = 2 if fragment and parse_dates(text) else 1 if fragment else 0
            selected.append((priority, line))
    return [line for _, line in sorted(
        selected, key=lambda item: (item[0], item[1].score), reverse=True
    )[:2]]


def _fragment_bounds(image: np.ndarray, line: OCRLine) -> tuple[int, int, int, int]:
    height, width = image.shape[:2]
    left, top, right, bottom = line.box
    box_width = max(1.0, right - left)
    box_height = max(1.0, bottom - top)
    x1 = max(0, int(left - max(64.0, box_width * 0.8)))
    x2 = min(width, int(right + max(64.0, box_width * 0.8)))
    y1 = max(0, int(top - max(64.0, box_height * 2.5)))
    y2 = min(height, int(bottom + max(64.0, box_height * 2.5)))
    return x1, y1, x2, y2


def _crop_fragment(image: np.ndarray, line: OCRLine) -> np.ndarray | None:
    x1, y1, x2, y2 = _fragment_bounds(image, line)
    if x2 - x1 < 24 or y2 - y1 < 16:
        return None
    crop = image[y1:y2, x1:x2]
    longest = max(crop.shape[:2])
    if longest < 900:
        scale = min(3.0, 900.0 / longest)
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    return crop


def _tile_bounds(image: np.ndarray, fraction: float) -> list[tuple[int, int, int, int]]:
    if not 0.5 < fraction < 1.0:
        raise ValueError("tile_fraction must be between 0.5 and 1.0")
    height, width = image.shape[:2]
    tile_height = max(1, int(height * fraction))
    tile_width = max(1, int(width * fraction))
    origins = (
        (0, 0),
        (0, width - tile_width),
        (height - tile_height, 0),
        (height - tile_height, width - tile_width),
    )
    return [(left, top, left+tile_width, top+tile_height) for top, left in origins]


def _overlapping_tiles(image: np.ndarray, fraction: float) -> list[np.ndarray]:
    return [image[top:bottom, left:right] for left, top, right, bottom in _tile_bounds(image, fraction)]


def _append_pass(
    all_lines: list[OCRLine],
    passes: list[str],
    backend: Any,
    image: np.ndarray,
    *,
    detector: str,
    variant: str,
    product_rules: Sequence[ProductDateRule] = (),
    trace: ImageTrace | None = None,
    frame: ImageFrame | None = None,
) -> DateSelection:
    if trace is not None:
        trace.start_pass(frame, detector, variant)
    started = time.perf_counter()
    try:
        lines = backend.recognize(image, detector=detector, variant=variant)
    except Exception as exc:
        if trace is not None:
            trace.record_pass([], [], frame, detector, variant, time.perf_counter()-started,
                              error=f"{type(exc).__name__}: {exc}")
        raise
    ocr_seconds = time.perf_counter()-started
    all_lines.extend(lines)
    passes.append(f"{detector}:{variant}")
    try:
        selection = select_date(all_lines, product_rules=product_rules)
    except Exception as exc:
        if trace is not None:
            trace.record_pass(lines, getattr(backend, "last_unrecognized_regions", ()), frame,
                              detector, variant, ocr_seconds, error=f"selection: {type(exc).__name__}: {exc}")
        raise
    if trace is not None:
        trace.record_pass(lines, getattr(backend, "last_unrecognized_regions", ()),
                          frame, detector, variant, ocr_seconds, selection)
    return selection


def predict_image(path: Path, backend: Any, config: PipelineConfig, *, trace: ImageTrace | None = None) -> ImagePrediction:
    started = time.perf_counter()
    image = _load_bgr(path)
    height, width = image.shape[:2]
    if trace is None and config.collect_trace:
        trace = ImageTrace(path.stem)
    if trace is not None:
        trace.start(width, height)
    original_frame = ImageFrame(width, height)
    all_lines: list[OCRLine] = []
    passes: list[str] = []

    def finish(selection):
        if trace is not None:
            trace.finish(selection)
        details = (dict(schema_version=1, original_size=trace.original_size,
                        coordinate_space='exif_oriented_image_edges',
                        frames=trace.frames, observations=trace.observations, regions=trace.regions,
                        outcomes=trace.outcomes, summary=trace.summary()) if trace is not None else None)
        return ImagePrediction(path.stem, selection.final_date, selection, time.perf_counter()-started,
                               tuple(passes), trace=details)

    selection = _append_pass(
        all_lines, passes, backend, image, detector="mobile", variant="original", product_rules=config.product_date_rules,
        trace=trace, frame=original_frame,
    )
    original_line_count = len(all_lines)
    original_fragments = _date_fragment_lines(all_lines)
    if selection.stop_ocr:
        return finish(selection)

    for index, fragment in enumerate(original_fragments, start=1):
        crop = _crop_fragment(image, fragment)
        if crop is None:
            continue
        selection = _append_pass(
            all_lines, passes, backend, crop, detector="mobile", variant=f"roi-{index}", product_rules=config.product_date_rules,
            trace=trace, frame=ImageFrame.crop(_fragment_bounds(image, fragment), crop.shape),
        )
        if selection.stop_ocr:
            return finish(selection)

    if config.enable_clahe:
        selection = _append_pass(
            all_lines,
            passes,
            backend,
            _clahe(image),
            detector="mobile",
            variant="clahe",
            product_rules=config.product_date_rules,
            trace=trace, frame=original_frame,
        )
        if selection.stop_ocr:
            return finish(selection)

    if config.enable_recovery_fallback:
        selection = _append_pass(
            all_lines, passes, backend, image, detector="recovery", variant="original", product_rules=config.product_date_rules,
            trace=trace, frame=original_frame,
        )
        if selection.stop_ocr:
            return finish(selection)

    if config.enable_rotation_fallback and (
        selection.final_date is None or selection.is_partial
        or (selection.candidates and selection.candidates[0].repaired)
    ):
        rotations = (
            (180, cv2.ROTATE_180),
            (90, cv2.ROTATE_90_CLOCKWISE),
            (270, cv2.ROTATE_90_COUNTERCLOCKWISE),
        )
        for angle, rotation in rotations:
            rotated = cv2.rotate(image, rotation)
            selection = _append_pass(
                all_lines,
                passes,
                backend,
                rotated,
                detector="mobile",
                variant=f"rot{angle}",
                product_rules=config.product_date_rules,
                trace=trace, frame=ImageFrame.rotated(width, height, angle),
            )
            if selection.stop_ocr:
                return finish(selection)

    # The last fallback zooms four overlapping quadrants. It is intentionally
    # restricted to images with no date after every full-image pass.
    if (
        config.enable_tile_fallback
        and (selection.final_date is None or selection.is_partial)
        and original_line_count <= config.tile_max_original_lines
        and (
            original_line_count <= config.tile_sparse_line_limit
            or bool(original_fragments)
        )
    ):
        for index, tile in enumerate(
            _overlapping_tiles(image, config.tile_fraction), start=1
        ):
            selection = _append_pass(
                all_lines,
                passes,
                backend,
                tile,
                detector="mobile",
                variant=f"tile-{index}",
                product_rules=config.product_date_rules,
                trace=trace, frame=ImageFrame.crop(_tile_bounds(image, config.tile_fraction)[index-1], tile.shape),
            )
            if selection.stop_ocr:
                return finish(selection)

    selection = select_date(all_lines, final=True, product_rules=config.product_date_rules)
    return finish(selection)


def _write_submission(path: Path, rows: Sequence[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows({"image_id": row["image_id"], **submission_fields(row["final_date"])} for row in rows)


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def run_pipeline(
    input_dir: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    *,
    config: PipelineConfig | None = None,
    backend: Any | None = None,
    max_images: int | None = None,
    on_image: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    total_started = time.perf_counter()
    config = config or PipelineConfig()
    images = discover_images(input_dir)
    if max_images is not None:
        if max_images <= 0:
            raise ValueError("max_images must be positive")
        images = images[:max_images]
    trace_path = Path(str(output_path) + ".trace.jsonl") if config.collect_trace else None
    if trace_path is not None:
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        with trace_path.open("w", encoding="utf-8"):
            pass

    def emit_trace(event):
        # Close/flush each completed pass so timeout retains earlier evidence.
        with trace_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")

    init_started = time.perf_counter()
    if backend is None:
        backend = PaddleOCRBackend(config)
    init_seconds = time.perf_counter() - init_started

    started = time.perf_counter()
    rows: list[dict[str, str]] = []
    timings: list[float] = []
    pass_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    failures: list[dict[str, str]] = []
    none_count = 0
    trace_totals: Counter[str] = Counter()

    for index, image_path in enumerate(images, start=1):
        image_started = time.perf_counter()
        trace = ImageTrace(image_path.stem, emit_trace) if config.collect_trace else None
        try:
            prediction = (predict_image(image_path, backend, config, trace=trace) if trace is not None
                          else predict_image(image_path, backend, config))
            fields = submission_fields(prediction.final_date)
        except Exception as exc:  # noqa: BLE001 - one bad image must not abort the submission.
            selection = DateSelection(
                None, float("-inf"), float("inf"), False, "exception", ()
            )
            prediction = ImagePrediction(
                image_path.stem,
                None,
                selection,
                time.perf_counter() - image_started,
                (),
                f"{type(exc).__name__}: {exc}",
            )
            failures.append({"image_id": image_path.stem, "error": prediction.error})
            fields = submission_fields(None)
            if trace is not None:
                trace.finish(selection, error=prediction.error)
        rows.append({"image_id": image_path.stem, **fields})
        timings.append(prediction.elapsed_seconds)
        pass_counts.update(prediction.passes)
        reason_counts.update([prediction.selection.reason])
        none_count += fields["final_date"] == "NONE-NONE-NONE"
        trace_summary = trace.summary() if trace is not None else {}
        trace_totals.update(trace_summary)
        if on_image is not None:
            on_image({"row": rows[-1], "seconds": prediction.elapsed_seconds,
                      "error": prediction.error, "passes": list(prediction.passes),
                      "trace_summary": trace_summary})
        if (
            config.progress_every > 0 and index % config.progress_every == 0
        ) or index == len(images):
            print(
                f"Processed {index}/{len(images)} images in {time.perf_counter() - started:.1f}s",
                flush=True,
            )

    output = Path(output_path)
    _write_submission(output, rows)
    elapsed = time.perf_counter() - started
    summary = {
        "images": len(images),
        "elapsed_seconds": round(elapsed, 3),
        "total_elapsed_seconds": round(time.perf_counter() - total_started, 3),
        "backend_init_seconds": round(init_seconds, 3),
        "timing_scope": "total starts at run_pipeline entry; caller/import startup excluded",
        "seconds_per_image": round(elapsed / len(images), 3),
        "p50_image_seconds": round(_percentile(timings, 0.50), 3),
        "p95_image_seconds": round(_percentile(timings, 0.95), 3),
        "predicted_none": none_count,
        "failures": failures,
        "passes": dict(pass_counts),
        "selection_reasons": dict(reason_counts),
        "ocr_calls": sum(pass_counts.values()),
        "trace_path": str(trace_path.resolve()) if trace_path is not None else None,
        "trace_summary": dict(trace_totals),
        "ocr_backend_seconds_per_image": trace_totals["ocr_seconds"] / len(images) if trace_path is not None else None,
        "output_path": str(output.resolve()),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return summary
