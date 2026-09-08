"""추출된 행을 사용자의 코딩시트 엑셀 템플릿에 이어서 기록한다."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import openpyxl

from .coding_book import SHEET_COLUMN_ORDER

SHEET_NAME = "코딩시트"
EXAMPLE_ROW_MARKER = "예시행"


def _next_case_number(ws, id_prefix: str) -> int:
    pattern = re.compile(re.escape(id_prefix) + r"(\d+)$")
    max_n = 0
    for row in ws.iter_rows(min_row=2, max_col=1, values_only=True):
        value = row[0]
        if not value:
            continue
        m = pattern.match(str(value).strip())
        if m:
            max_n = max(max_n, int(m.group(1)))
    return max_n + 1


def _find_insert_row(ws) -> int:
    """헤더/예시행 다음, 데이터가 없는 첫 행 번호를 찾는다."""
    last = 1
    for row_idx in range(2, ws.max_row + 1):
        case_id = ws.cell(row=row_idx, column=1).value
        note = ws.cell(row=row_idx, column=len(SHEET_COLUMN_ORDER) + 1).value
        is_example = bool(note) and EXAMPLE_ROW_MARKER in str(note)
        if case_id and not is_example:
            last = row_idx
        elif is_example:
            continue
    return last + 1


def write_rows(
    template_path: Path,
    output_path: Path,
    rows: list[dict],
    *,
    id_prefix: str = "DF-2024-",
) -> Path:
    """rows(각 항목이 SHEET_COLUMN_ORDER 키를 갖는 dict)를 템플릿에 이어붙여 output_path에 저장한다."""
    if output_path != template_path:
        shutil.copy(template_path, output_path)
        target = output_path
    else:
        target = template_path

    wb = openpyxl.load_workbook(target)
    if SHEET_NAME not in wb.sheetnames:
        raise ValueError(f"'{SHEET_NAME}' 시트를 템플릿 파일에서 찾을 수 없습니다: {template_path}")
    ws = wb[SHEET_NAME]

    next_row = _find_insert_row(ws)
    next_num = _next_case_number(ws, id_prefix)

    for row in rows:
        if not row.get("case_id"):
            row["case_id"] = f"{id_prefix}{next_num:03d}"
            next_num += 1
        for col_idx, col_name in enumerate(SHEET_COLUMN_ORDER, start=1):
            ws.cell(row=next_row, column=col_idx, value=row.get(col_name))
        next_row += 1

    wb.save(target)
    return target
