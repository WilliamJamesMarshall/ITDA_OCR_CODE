"""Create a non-gold, automatically triaged error queue from fixed evidence."""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent


def main():
    report = json.loads((OUT / "comparison.json").read_text(encoding="utf-8"))
    names = {
        "recognition_or_tokenization": "정답 날짜가 원문 파싱 후보에도 없음: 인식/문자 분할 재검토",
        "order_or_evidence_filter": "원문에 가능한 정답 후보가 있으나 순서/근거 선택에서 제외",
        "candidate_ranking": "선택 후보에 정답이 있으나 다른 날짜의 점수가 높음",
        "none_or_partial_requires_review": "NONE/부분 날짜 관련: 제조일·누락·비날짜 오탐 재검토",
    }
    lines = ["# 미해결 오류 검토 대기열", "", "자동 분류이며 전수 육안 검수 결과가 아니다. 정답 라벨을 수정하거나 사진에 근거가 없다고 확정하지 않는다.",
             "기존 ID는 저장 OCR 당시 번호이며 현재 ID/경로는 SHA-256으로 확인했다.", ""]
    for key, label in names.items():
        rows = [row for row in report["details"] if row["category"] == key]
        lines.extend([f"## {label} — {len(rows)}건", "", "| 기존 ID | 현재 ID | 정답 | 현재 예측 | 선택 사유 |", "|---|---|---|---|---|"])
        lines.extend(f"| {r['historical_id']} | {r['current_id']} | {r['expected']} | {r['after']} | {r['reason']} |" for r in rows)
        lines.append("")
    (OUT / "review_queue.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(report["counts"], report["error_categories"])


if __name__ == "__main__":
    main()
