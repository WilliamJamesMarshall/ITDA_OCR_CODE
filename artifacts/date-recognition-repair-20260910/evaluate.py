"""Hash-bound development comparison, including the dataset renumbering."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
from collections import Counter

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


def save(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def prepare():
    if (OUT / "manifest.json").exists():
        return
    starting = OUT / "starting_source"
    starting.mkdir(exist_ok=True)
    for filename in ("date_extraction.py", "pipeline.py"):
        shutil.copy2(ROOT / "src" / filename, starting / filename)
    inventory = json.loads((ROOT / "artifacts/duplicate_audit_20260910/inventory.json").read_text(encoding="utf-8"))
    old = {(row["folder"], Path(row["path"]).stem): row["sha256"] for row in inventory}
    extra = {hashlib.sha256(p.read_bytes()).hexdigest(): str(p) for p in (ROOT / "추가수집데이터").glob("*.jpg")}
    helper = load("old_evidence", ROOT / "artifacts/date-order-implementation-20260910/validate.py")
    included, excluded = [], []
    for name, rows, truth, folder in helper.evidence_sets():
        files = {p.stem: p for p in folder.iterdir() if p.is_file()}
        for row in rows:
            identifier = row["image_id"]
            if identifier not in truth:
                continue
            digest = old[(folder.name, identifier)]
            path = extra.get(digest) if name == "additional386" else str(files[identifier])
            if path is None:
                excluded.append(dict(set=name, historical_id=identifier, sha256=digest, reason="removed during separate deduplication"))
                continue
            assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest, path
            included.append(dict(set=name, historical_id=identifier, current_id=Path(path).stem,
                                 path=path, sha256=digest, expected=truth[identifier], evidence=row))
    save("manifest.json", dict(included=included, excluded=excluded,
                               scope="Development data, not independent holdout. Images identified by pre-renumbering SHA-256."))


def replay():
    prepare()
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    before = load("starting_policy_next", OUT / "starting_source/date_extraction.py")
    counts, categories, details = Counter(), Counter(), []
    for row in manifest["included"]:
        evidence = row["evidence"]
        lines = [current.OCRLine(**line) for event in evidence["events"] for line in event["lines"]]
        old_lines = [before.OCRLine(**line) for event in evidence["events"] for line in event["lines"]]
        previous = before.select_date(old_lines, final=True).final_date or "NONE"
        selected = current.select_date(lines, final=True)
        prediction = selected.final_date or "NONE"
        expected = row["expected"]
        counts["total"] += 1
        counts["before_correct"] += previous == expected and not evidence["error"]
        counts["after_correct"] += prediction == expected and not evidence["error"]
        counts["gained"] += previous != expected and prediction == expected and not evidence["error"]
        counts["lost"] += previous == expected and prediction != expected and not evidence["error"]
        category = "correct"
        if prediction != expected:
            raw_values = {p.value.isoformat() for line in lines + current.merge_horizontal_lines(lines) for p in current.parse_dates(line.text)}
            if expected in {c.iso for c in selected.candidates}:
                category = "candidate_ranking"
            elif expected in raw_values:
                category = "order_or_evidence_filter"
            elif "NONE" in expected:
                category = "none_or_partial_requires_review"
            else:
                category = "recognition_or_tokenization"
            categories[category] += 1
        details.append(dict(historical_id=row["historical_id"], current_id=row["current_id"], set=row["set"],
                            expected=expected, before=previous, after=prediction, category=category,
                            reason=selected.reason, path=row["path"],
                            candidate_top=[dict(raw=c.raw, value=c.iso, score=c.score, order_reason=c.order_reason,
                                                variant=c.variant, source=c.source, box=c.box) for c in selected.candidates[:6]],
                            date_like_text=list(dict.fromkeys(line.text for line in lines if
                                current.parse_dates(line.text) or (len(line.text) < 70 and sum(c.isdigit() for c in line.text) >= 4
                                                                  and any(c in line.text for c in ".-/"))))))
    save("comparison.json", dict(counts=counts, error_categories=categories, details=details,
                                  source_sha256=hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest()))
    print(dict(counts), dict(categories), flush=True)
    for row in details:
        if row["before"] != row["after"]:
            print({k: row[k] for k in ("historical_id", "expected", "before", "after")}, flush=True)


if __name__ == "__main__":
    replay()
