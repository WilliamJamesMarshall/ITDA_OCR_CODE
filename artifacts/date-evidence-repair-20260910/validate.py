"""Compare frozen starting policy to repaired policy on identical OCR evidence."""
import importlib.util
import json
from pathlib import Path
import sys
import time
from collections import Counter
import hashlib

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from src import date_extraction as current


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    starting = load("starting_policy", OUT / "starting_source/date_extraction.py")
    helper = load("evidence_helper", ROOT / "artifacts/date-order-implementation-20260910/validate.py")
    sets = {}
    for name, rows, truth, _ in helper.evidence_sets():
        counts, timings, details = Counter(), Counter(), []
        for row in rows:
            if row["image_id"] not in truth:
                continue
            expected = truth[row["image_id"]]
            selections = {}
            for key, module in (("before", starting), ("after", current)):
                lines = [module.OCRLine(**line) for event in row["events"] for line in event["lines"]]
                begin = time.perf_counter()
                selections[key] = module.select_date(lines, final=True)
                timings[key] += time.perf_counter() - begin
            before, after = (selections[key].final_date or "NONE" for key in ("before", "after"))
            counts["total"] += 1
            counts["before_correct"] += before == expected and not row["error"]
            counts["after_correct"] += after == expected and not row["error"]
            counts["gained"] += before != expected and after == expected and not row["error"]
            counts["lost"] += before == expected and after != expected and not row["error"]
            selected = selections["after"]
            details.append(dict(id=row["image_id"], expected=expected, before=before, after=after,
                                order_reason=selected.candidates[0].order_reason if selected.candidates else None,
                                reason=selected.reason, error=row["error"]))
        sets[name] = dict(counts=counts, parser_seconds_not_ocr=timings, details=details)
        print(name, dict(counts), dict(timings), flush=True)
        print("Changes:", [r for r in details if r["before"] != r["after"]], flush=True)
    result = dict(measurement="Fixed recorded evidence, not fresh OCR, independent test accuracy or 500-image runtime",
                  source_sha256=hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest(), sets=sets)
    (OUT / "fixed_evidence.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
