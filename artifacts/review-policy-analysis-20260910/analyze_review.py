"""Read-only comparison of reviewer order labels with the existing parser.

Print diagnostics only. No source images, labels, or application files are changed.
"""
from collections import Counter
import json
from pathlib import Path
import re
import sys
from xml.etree import ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.date_extraction import parse_dates

DOC = Path(r"C:\Users\ujkio\OneDrive - 경희대학교\바탕 화면\상품사진입니다 데이터셋 검수.docx")
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
with ZipFile(DOC) as archive:
    xml = ET.fromstring(archive.read("word/document.xml"))
    paragraphs = ["".join(t.text or "" for t in p.findall(".//w:t", NS)) for p in xml.findall(".//w:p", NS)]
    print("DOCUMENT_STRUCTURE", json.dumps({
        "tables": len(xml.findall(".//w:tbl", NS)),
        "insertions": len(xml.findall(".//w:ins", NS)),
        "deletions": len(xml.findall(".//w:del", NS)),
        "media_or_comments": [n for n in archive.namelist() if "media/" in n or "comments" in n],
    }, ensure_ascii=False))

orders = {"년월일": "ymd", "일월년": "dmy", "월일년": "mdy"}
records = []
section = None
for paragraph in paragraphs:
    if paragraph.startswith("년월일"):
        section = "ymd"
    elif paragraph.startswith("월일년"):
        section = "mdy"
    elif paragraph.startswith("일월년"):
        section = "dmy"
    elif paragraph.startswith("판정보류"):
        section = "hold"
    match = re.match(r"^(\d{6})\s*(년월일|일월년|월일년)?\s*$", paragraph)
    if match:
        records.append({"id": match[1], "old_section": section, "review_order": orders[match[2]] if match[2] else section})
    elif re.search(r"\d{6}", paragraph):
        raise ValueError(f"Unparsed record: {paragraph}")

ledger = json.loads((ROOT / "artifacts/date-order-full-audit-20260910/inspection_ledger.json").read_text(encoding="utf-8"))
by_id = {row["id"]: row for row in ledger}
expected = {row["id"] for row in ledger if row["status"] == "ambiguous"}
actual = [row["id"] for row in records]
assert len(actual) == len(set(actual)) == 441
assert set(actual) == expected
assert all(row["old_section"] == by_id[row["id"]]["recommendation"] for row in records)

print("COUNTS", dict(Counter(row["review_order"] for row in records)))
print("TRANSITIONS", dict(Counter(f'{row["old_section"]}->{row["review_order"]}' for row in records)))
print("HOLD_TO_YMD", [row["id"] for row in records if row["old_section"] == "hold" and row["review_order"] == "ymd"])
# Later direct user clarification takes precedence over the original document.
for row in records:
    if row["id"] == "000675":
        row["document_order"] = row["review_order"]
        row["review_order"] = "mdy"
        row["clarification"] = "User explicitly confirmed 2028-03-06 in this conversation."
print("FINAL_COUNTS_AFTER_USER_CLARIFICATION", dict(Counter(row["review_order"] for row in records)))
parser_results = Counter()
consistent_parser_results = Counter()
invalid = []
for row in records:
    previous = by_id[row["id"]]
    value = previous["interpretations"].get(row["review_order"])
    if not value:
        invalid.append(row["id"])
    parsed = sorted({p.value.isoformat() for p in parse_dates(previous["raw"])})
    category = "contains_review_date" if value in parsed else "no_full_candidate" if not parsed else "other_candidate_only"
    parser_results[category] += 1
    if value:
        consistent_parser_results[category] += 1
    if row["id"] in {"000478", "000626", "000628", "000675", "002333", "002334", "001975", "003172", "003213", "003214", "002790", "002791"}:
        print("EXAMPLE", json.dumps({**row, "raw": previous["raw"], "review_date_from_previous_transcription": value, "existing_parser": parsed, "note": previous["note"], "date_kind": previous.get("date_kind")}, ensure_ascii=False))
print("INVALID_REVIEW_ORDER_VS_OLD_TRANSCRIPTION", invalid)
print("PARSER_ONLY_DIAGNOSTIC_NOT_OCR_ACCURACY", dict(parser_results))
print("PARSER_ONLY_EXCLUDING_INCONSISTENT_LABEL", dict(consistent_parser_results))
