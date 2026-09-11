"""Synchronize and protect the manually reviewed 1-3352 validation workbook."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import posixpath
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile


WORKBOOK_REL = Path("labels/validation_000001_003352_manual.xlsx")
CSV_REL = Path("labels/validation_000001_003352_manual.csv")
INSPECT_REL = Path("labels/validation_000001_003352_manual.xlsx.inspect.ndjson")
LOCK_REL = Path("labels/validation_000001_003352_manual.lock.json")
SHEET_NAME = "검수 정답지"
HEADERS = ["image_id", "추출한 날짜", "정답 날짜", "True/False", "라벨 상태", "난이도", "오류 유형", "비고"]
DATA_ROWS = 3352
CHANGED_EXTRACTED_DATES = 2445

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CELL_REF = re.compile(r"([A-Z]+)(\d+)")


@dataclass(frozen=True)
class WorkbookState:
    rows: list[list[str]]
    formulas: list[list[str]]
    sha256: str
    content_sha256: str


def _tag(name: str) -> str:
    return f"{{{MAIN_NS}}}{name}"


def _column_index(reference: str) -> int:
    match = CELL_REF.fullmatch(reference)
    if not match:
        raise ValueError(f"Invalid cell reference: {reference}")
    value = 0
    for character in match.group(1):
        value = value * 26 + ord(character) - ord("A") + 1
    return value - 1


def _text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return "".join(node.text or "" for node in element.iter(_tag("t")))


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return _text(cell.find(_tag("is")))
    value = cell.findtext(_tag("v"), default="")
    if cell_type == "s":
        return shared_strings[int(value)]
    if cell_type == "b":
        return "True" if value == "1" else "False"
    if value.endswith(".0"):
        return value[:-2]
    return value


def read_workbook(root: Path) -> WorkbookState:
    workbook_path = root / WORKBOOK_REL
    workbook_bytes = workbook_path.read_bytes()
    workbook_sha = hashlib.sha256(workbook_bytes).hexdigest()

    with ZipFile(io.BytesIO(workbook_bytes)) as archive:
        names = set(archive.namelist())
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in names:
            shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared_strings = [_text(item) for item in shared_root.findall(_tag("si"))]

        workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
        sheets = workbook_root.find(_tag("sheets"))
        if sheets is None or len(sheets) != 1:
            raise ValueError("Expected exactly one worksheet")
        sheet = sheets[0]
        if sheet.attrib.get("name") != SHEET_NAME:
            raise ValueError(f"Unexpected worksheet name: {sheet.attrib.get('name')}")
        relationship_id = sheet.attrib[f"{{{OFFICE_REL_NS}}}id"]

        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {
            item.attrib["Id"]: item.attrib["Target"]
            for item in relationships.findall(f"{{{PACKAGE_REL_NS}}}Relationship")
        }
        target = targets[relationship_id]
        sheet_path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
        sheet_root = ET.fromstring(archive.read(sheet_path))

    rows: list[list[str]] = []
    formulas: list[list[str]] = []
    shared_formula_ids: set[str] = set()
    sheet_data = sheet_root.find(_tag("sheetData"))
    if sheet_data is None:
        raise ValueError("Worksheet has no sheet data")

    for row_element in sheet_data.findall(_tag("row")):
        row_number = int(row_element.attrib["r"])
        values = [""] * len(HEADERS)
        row_formulas = [""] * len(HEADERS)
        for cell in row_element.findall(_tag("c")):
            reference = cell.attrib["r"]
            column = _column_index(reference)
            if column >= len(HEADERS):
                continue
            values[column] = _cell_value(cell, shared_strings)
            formula = cell.find(_tag("f"))
            if formula is None:
                continue
            if column != 3 or row_number < 2:
                raise ValueError(f"Unexpected formula at {reference}")
            expected = f'IF(B{row_number}=C{row_number},"True","False")'
            formula_text = formula.text or ""
            if formula_text:
                if formula_text != expected:
                    raise ValueError(f"Unexpected formula at {reference}: {formula_text}")
                shared_id = formula.attrib.get("si")
                if shared_id is not None:
                    shared_formula_ids.add(shared_id)
            else:
                shared_id = formula.attrib.get("si")
                if formula.attrib.get("t") != "shared" or shared_id not in shared_formula_ids:
                    raise ValueError(f"Invalid shared formula at {reference}")
            row_formulas[column] = f"={expected}"
        while len(rows) < row_number - 1:
            rows.append([""] * len(HEADERS))
            formulas.append([""] * len(HEADERS))
        rows.append(values)
        formulas.append(row_formulas)

    if len(rows) != DATA_ROWS + 1:
        raise ValueError(f"Expected {DATA_ROWS + 1} rows, found {len(rows)}")
    if rows[0] != HEADERS:
        raise ValueError(f"Unexpected headers: {rows[0]}")
    for index, row in enumerate(rows[1:], start=1):
        excel_row = index + 1
        if row[0] != str(index):
            raise ValueError(f"Unexpected image_id at row {excel_row}: {row[0]}")
        expected_result = "True" if row[1] == row[2] else "False"
        if row[3] != expected_result:
            raise ValueError(f"Stale formula value at D{excel_row}: {row[3]} != {expected_result}")
        if formulas[index][3] != f'=IF(B{excel_row}=C{excel_row},"True","False")':
            raise ValueError(f"Missing formula at D{excel_row}")

    content = json.dumps(
        {"sheet": SHEET_NAME, "rows": rows, "formulas": formulas},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return WorkbookState(rows, formulas, workbook_sha, hashlib.sha256(content).hexdigest())


def csv_bytes(state: WorkbookState) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerows(state.rows)
    return output.getvalue().encode("utf-8")


def inspect_bytes(state: WorkbookState) -> bytes:
    records = [
        {
            "kind": "workbook",
            "source": WORKBOOK_REL.as_posix(),
            "sha256": state.sha256,
            "sheets": 1,
            "rows": DATA_ROWS + 1,
            "dataRows": DATA_ROWS,
            "columns": len(HEADERS),
        },
        {"kind": "sheet", "name": SHEET_NAME, "range": f"A1:H{DATA_ROWS + 1}"},
    ]
    records.extend(
        {
            "kind": "row",
            "sheet": SHEET_NAME,
            "row": index,
            "values": values,
            "formulas": formulas,
        }
        for index, (values, formulas) in enumerate(zip(state.rows, state.formulas), start=1)
    )
    true_count = sum(row[3] == "True" for row in state.rows[1:])
    records.append(
        {
            "kind": "summary",
            "trueCount": true_count,
            "falseCount": DATA_ROWS - true_count,
            "changedExtractedDates": CHANGED_EXTRACTED_DATES,
        }
    )
    return ("\n".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) for record in records) + "\n").encode("utf-8")


def lock_bytes(state: WorkbookState) -> bytes:
    lock = {
        "schema_version": 1,
        "workbook": WORKBOOK_REL.as_posix(),
        "sheet": SHEET_NAME,
        "data_rows": DATA_ROWS,
        "content_sha256": state.content_sha256,
        "update_command": "python scripts/manual_validation_guard.py sync --update-lock",
    }
    return (json.dumps(lock, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def synchronize(root: Path, *, update_lock: bool) -> WorkbookState:
    state = read_workbook(root)
    _atomic_write(root / CSV_REL, csv_bytes(state))
    _atomic_write(root / INSPECT_REL, inspect_bytes(state))
    if update_lock:
        _atomic_write(root / LOCK_REL, lock_bytes(state))
    return state


def check_repository(root: Path) -> list[str]:
    errors: list[str] = []
    try:
        state = read_workbook(root)
    except Exception as error:
        return [f"workbook: {error}"]

    expected = {
        CSV_REL: csv_bytes(state),
        INSPECT_REL: inspect_bytes(state),
    }
    for relative_path, expected_bytes in expected.items():
        path = root / relative_path
        if not path.is_file():
            errors.append(f"missing synchronized file: {relative_path.as_posix()}")
        elif path.read_bytes() != expected_bytes:
            errors.append(f"stale synchronized file: {relative_path.as_posix()}")

    lock_path = root / LOCK_REL
    if not lock_path.is_file():
        errors.append(f"missing lock file: {LOCK_REL.as_posix()}")
    else:
        try:
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"invalid lock file: {error}")
        else:
            if lock.get("content_sha256") != state.content_sha256:
                errors.append("manual validation workbook content does not match its lock")
            if lock.get("data_rows") != DATA_ROWS:
                errors.append("manual validation lock has an unexpected row count")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "sync"))
    parser.add_argument("--update-lock", action="store_true")
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[1]

    if arguments.command == "sync":
        state = synchronize(root, update_lock=arguments.update_lock)
        print(json.dumps({"rows": DATA_ROWS, "xlsx_sha256": state.sha256, "content_sha256": state.content_sha256, "lock_updated": arguments.update_lock}))
        return 0

    errors = check_repository(root)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("manual validation workbook, CSV, NDJSON, and lock are consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
