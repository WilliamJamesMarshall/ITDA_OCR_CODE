"""Process-isolated validation: soft targets never interrupt OCR; deadline does."""
import json
from collections import Counter
import math
import multiprocessing
from pathlib import Path
import tempfile
import time


HARD_TIMEOUT_SECONDS = 2400.0


def _pipeline_worker(journal, input_dir, output_path, config, max_images):
    from src.pipeline import run_pipeline

    with open(journal, "a", encoding="utf-8") as stream:
        def emit(event):
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            stream.flush()

        try:
            runtime = run_pipeline(input_dir, output_path, config=config, max_images=max_images,
                                   on_image=lambda record: emit({"kind": "image", **record}))
            emit({"kind": "completed", "runtime": runtime})
        except Exception as exc:
            emit({"kind": "failed", "error": f"{type(exc).__name__}: {exc}"})


def _supervise(worker, worker_args, *, hard_timeout_seconds=HARD_TIMEOUT_SECONDS):
    """Journal only completed images; a killed image is never fabricated as NONE."""
    if not math.isfinite(hard_timeout_seconds) or hard_timeout_seconds <= 0:
        raise ValueError("hard_timeout_seconds must be finite and positive")
    with tempfile.TemporaryDirectory(prefix="itda-validation-") as directory:
        journal = str(Path(directory) / "progress.jsonl")
        process = multiprocessing.get_context("spawn").Process(target=worker, args=(journal, *worker_args))
        started = time.perf_counter()
        timed_out = False
        process.start()
        try:
            while process.is_alive():
                remaining = hard_timeout_seconds - (time.perf_counter() - started)
                if remaining <= 0:
                    timed_out = True
                    break
                process.join(timeout=min(.2, remaining))
            elapsed = time.perf_counter() - started
        finally:
            if process.is_alive():
                process.terminate()
                process.join(timeout=2)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=2)
            exit_code = process.exitcode
            process.close()
        events = []
        if Path(journal).exists():
            for raw in Path(journal).read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    events.append(json.loads(raw))
                except json.JSONDecodeError:
                    # Hard termination can interrupt the final journal write.
                    break
        complete = next((e for e in events if e["kind"] == "completed"), None)
        status = "timeout" if timed_out or elapsed > hard_timeout_seconds else (
            "completed" if complete is not None and exit_code == 0 else "failed")
        return {"status": status, "elapsed_seconds": elapsed, "exit_code": exit_code,
                "events": events, "hard_timeout_seconds": hard_timeout_seconds}


def run_timed_pipeline(input_dir, output_path, *, config, expected_images, max_images=None):
    from src.pipeline import _write_submission

    trace_path = Path(str(output_path) + '.trace.jsonl') if config and config.collect_trace else None
    if trace_path is not None:
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        with trace_path.open('w', encoding='utf-8'):
            pass  # An initialization timeout must not expose the previous run's trace.
    result = _supervise(_pipeline_worker, (str(input_dir), str(output_path), config, max_images))
    records = [e for e in result["events"] if e["kind"] == "image"]
    completed = next((e for e in result["events"] if e["kind"] == "completed"), None)
    runtime = dict(completed["runtime"]) if completed else {}
    runtime['pipeline_total_elapsed_seconds'] = runtime.get('total_elapsed_seconds')
    runtime['pipeline_seconds_per_image'] = runtime.get('seconds_per_image')
    if result["status"] != "completed":
        # Replace stale output with this run's completed rows, never invented rows.
        _write_submission(Path(output_path), [e["row"] for e in records])
    failures = [{"image_id": e["row"]["image_id"], "error": e["error"]} for e in records if e["error"]]
    trace_totals = Counter()
    for record in records:
        trace_totals.update(record.get('trace_summary', {}))
    runtime.update(
        images=len(expected_images), completed_images=len(records),
        unprocessed_images=len(expected_images) - len(records),
        status=result["status"], total_elapsed_seconds=result["elapsed_seconds"],
        seconds_per_image=(result["elapsed_seconds"] / len(records) if records else None),
        hard_timeout_seconds=result["hard_timeout_seconds"], worker_exit_code=result["exit_code"],
        failures=failures,
        trace_path=str(trace_path.resolve()) if trace_path is not None else None,
        completed_trace_summary=dict(trace_totals),
        ocr_backend_seconds_per_completed_image=(trace_totals['ocr_seconds'] / len(records)
                                                if records and trace_path is not None else None),
        worker_errors=[e["error"] for e in result["events"] if e["kind"] == "failed"],
        completed_prediction_seconds=sum(e["seconds"] for e in records),
        completed_prediction_seconds_per_image=(sum(e["seconds"] for e in records) / len(records) if records else None),
        timing_scope="Worker startup/imports, model initialization, image discovery/loading, OCR, selection and CSV output; "
                     "parent setup/label loading and final evaluation report excluded. "
                     "Timeout rate uses completed images and includes time spent on the interrupted image.",
    )
    return runtime
