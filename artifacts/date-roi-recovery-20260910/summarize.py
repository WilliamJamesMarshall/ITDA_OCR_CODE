"""Summarize the paired run without treating selected cases as global accuracy."""
import json
from pathlib import Path
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
sys.path.insert(0, str(ROOT))
from src.date_extraction import OCRLine, parse_dates, select_date


def main():
    result = json.loads((OUT / "release_result.json").read_text(encoding="utf-8"))
    details = []
    for row in result["details"]:
        after = row["after"]
        lines = [OCRLine(**v) for e in after["events"] for v in e["lines"]]
        final = select_date(lines, final=True)
        parsed = {d.value.isoformat() for line in lines for d in parse_dates(line.text)}
        candidates = {c.value.isoformat() for c in final.candidates}
        expected = row["expected"]
        category = ("correct" if after["correct"] else "partial_or_none" if "NONE" in expected
                    else "ranking" if expected in candidates else "order_or_evidence" if expected in parsed
                    else "recognition_or_tokenization")
        details.append(dict(historical_id=row["historical_id"], current_id=row["current_id"], expected=expected,
                            before=row["before"]["prediction"], after=after["prediction"], category=category,
                            before_calls=len(row["before"]["passes"]), after_calls=len(after["passes"]),
                            same_original=row["before"]["events"][0] == after["events"][0]))
    result = dict(summary=result["summary"], count=len(details), code_sha256=result["code_sha256"],
                  identical_originals=sum(r["same_original"] for r in details),
                  scope="All changed reachable selectors in fixed 705-record development evidence plus six controls; not an independent sample",
                  details=details)
    (OUT / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    text = ["# 실제 ROI 비교 후 미해결 목록", "", "자동 원인 분류이며 전수 육안 확정 결과가 아니다. 번호 변경 전후를 함께 기록한다.", "",
            "| 이전 번호 | 현재 번호 | 정답 | 출력 | 자동 분류 |", "|---|---|---|---|---|"]
    for row in details:
        if row["category"] != "correct":
            text.append(f"| {row['historical_id']} | {row['current_id']} | {row['expected']} | {row['after']} | {row['category']} |")
    (OUT / "remaining.md").write_text("\n".join(text) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "details"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
