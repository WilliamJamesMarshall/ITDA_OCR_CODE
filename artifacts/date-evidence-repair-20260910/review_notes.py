"""Human-observed triage notes joined to measured replay; never inference input."""
import json
import hashlib
from pathlib import Path

OUT = Path(__file__).resolve().parent


def main():
    audit = json.loads((OUT / "regressions.json").read_text(encoding="utf-8"))
    replay = json.loads((OUT / "fixed_evidence.json").read_text(encoding="utf-8"))
    results = {row["id"]: row for group in replay["sets"].values() for row in group["details"]}
    image_root = OUT.parents[1] / "추가수집데이터"
    current_paths = {hashlib.sha256(path.read_bytes()).hexdigest(): str(path) for path in image_root.glob("*.jpg")}
    notes = {
        "003408": ("printed_legend", "후면표기일까지(연.월.일): OCR에도 있으나 연 변형을 놓쳤음"),
        "000014": ("printed_reference", "제품에 별도 표기일까지(읽는법: 년,월,일 순): 날짜와 떨어진 명시 지시문"),
        "003586": ("printed_legend", "곡면 라벨에 년년.월월.. 보임. 일 필드 전체는 보이지 않음; 앞 두 필드로 YMD 구분"),
        "003529": ("corresponding_month_name", "숫자 220904와 EXP04SEP22 병기. OCR EXPO4SEP22에서 EXP 접두어/O를 처리 못함"),
        "003613": ("partial_and_clock", "03.31 뒤 01:31 시각/로트 숫자를 연도로 빌려 완전 날짜를 생성했음"),
        "003405": ("digit_recognition", "원본의 2021.02.15에서 OCR가 앞의 20을 누락. 순서만의 문제가 아님"),
        "000063": ("digit_and_role_link", "원본 2025.06.17부터/2026.06.16까지. OCR 2U25 오독과 기울어진 역할 연결 문제"),
        "000088": ("digit_and_role_link", "원본 날짜 쌍과 OCR의 25:09.04 등 혼합 구분자. 동일 형식의 확실한 쌍 조건 미충족"),
        "000089": ("digit_recognition", "뚜껑 26.09.11; 본문 네 자리 연도를 OCR가 2028로 오독. 값 충돌을 임의 보정하지 않음"),
        "000245": ("digit_recognition", "원본 26.02.24를 2.02.244/26.02.244로 OCR. 후행 로트 혼입/자리 누락"),
    }
    observed_pairs = {"003389", "003411", "003556", "003561", "000007", "000086", "000246",
                      "000250", "000251", "000254", "000261", "000274", "000278", "000279", "000330"}
    for row in audit:
        result = results[row["id"]]
        category, note = notes.get(row["id"], (
            ("printed_pair_roles_unverified", "사진에 날짜 두 줄이 보임. 역할·구분자·OCR 판독이 실행 규칙 조건을 충족하는지 별도 확인 필요")
            if row["id"] in observed_pairs else
            ("order_evidence_not_verified", "축소 원본과 OCR 기록 대조만으로 순서 결정 근거를 확정하지 못함. 한국어/브랜드만으로 YMD 규칙 등록하지 않음")))
        if result["after"] == row["expected"] and category == "printed_pair_roles_unverified":
            category, note = "labelled_pair", "같은 블록의 제조/시작·기한/종료 역할과 동일 숫자 형식으로 날짜 순서를 제한"
        row.update(review_category=category, review_note=note,
                   review_scope="69장 원본 contact sheet와 저장 OCR 대조; 핵심 사례 확대 확인. 모든 미해결 포장의 세부 근거 확정 완료를 뜻하지 않음",
                   current_prediction=result["after"], recovered=result["after"] == row["expected"],
                   current_order_reason=result["order_reason"])
        old_path = Path(row["path"])
        row["current_path"] = (str(old_path) if old_path.exists() and hashlib.sha256(old_path.read_bytes()).hexdigest() == row["sha256"]
                               else current_paths.get(row["sha256"]))
    (OUT / "review_69.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    table = ["# 회귀 69장 검토 기록", "", "사진·OCR 근거에 대한 1차 분류이며 미확정은 근거 부재 확정이 아니다. 현재 번호는 SHA-256으로 동일 사진을 확인했다. 원본 재번호/삭제 작업은 이 OCR 수정과 별개다.", "",
             "| 작업 시작 시 ID | 현재 ID | 분류 | 이번 고정 증거 재생 복구 | 비고 |", "|---|---|---|---|---|"]
    table.extend(f"| {row['id']} | {Path(row['current_path']).stem if row['current_path'] else '동일 해시 파일 없음'} | {row['review_category']} | {'예' if row['recovered'] else '아니오'} | {row['review_note']} |" for row in audit)
    (OUT / "review_69.md").write_text("\n".join(table) + "\n", encoding="utf-8")
    print("reviewed", len(audit), "recovered", sum(row["recovered"] for row in audit))


if __name__ == "__main__":
    main()
