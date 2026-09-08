"""판결문(PDF/DOCX) -> 코딩시트 엑셀 변환 CLI.

사용 예:
    python -m case_extractor.cli \\
        --template ~/Desktop/코딩시트.xlsx \\
        --input-dir ~/Desktop/판결문모음 \\
        --output ~/Desktop/코딩시트_결과.xlsx \\
        --coder-id C1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .coding_book import LLM_REQUESTED_FIELDS, SHEET_COLUMN_ORDER
from .compute import apply_computed_fields
from .excel_writer import write_rows
from .llm_extract import LLMExtractError, extract_fields
from .text_extract import TextExtractError, extract_text, find_case_files


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="판결문 PDF/DOCX를 코딩시트 엑셀로 변환합니다.")
    p.add_argument("--template", required=True, type=Path, help="열/코딩북이 정의된 원본 코딩시트 xlsx 경로")
    p.add_argument("--input-dir", required=True, type=Path, help="판결문 PDF/DOCX 파일들이 있는 폴더")
    p.add_argument("--output", required=True, type=Path, help="결과를 저장할 xlsx 경로 (템플릿과 달라야 안전함)")
    p.add_argument("--coder-id", default="", help="coder_id 컬럼에 채울 코딩 담당자 식별자")
    p.add_argument("--id-prefix", default="DF-2024-", help="case_id 자동 생성 시 사용할 접두어")
    p.add_argument("--model", default=None, help="사용할 Claude 모델 (기본값: 환경변수 ANTHROPIC_MODEL 또는 claude-sonnet-5)")
    p.add_argument("--dry-run", action="store_true", help="LLM 추출 결과를 엑셀에 쓰지 않고 화면에만 출력")
    return p


def process_file(path: Path, *, coder_id: str, model: str | None) -> dict:
    text = extract_text(path)
    extracted = extract_fields(text, model=model)

    row = {name: extracted.get(name) for name in LLM_REQUESTED_FIELDS}
    row["coder_id"] = coder_id
    row["case_id"] = None  # excel_writer가 자동 채번

    row = apply_computed_fields(row)

    note = str(row.get("coding_note") or "").strip()
    ai_tag = f"[AI 추출: {path.name}] 검토 필요"
    row["coding_note"] = f"{ai_tag} {note}".strip()

    return {name: row.get(name) for name in SHEET_COLUMN_ORDER}


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    if not args.template.exists():
        print(f"오류: 템플릿 파일을 찾을 수 없습니다: {args.template}", file=sys.stderr)
        return 1
    if not args.input_dir.is_dir():
        print(f"오류: 입력 폴더를 찾을 수 없습니다: {args.input_dir}", file=sys.stderr)
        return 1

    files = find_case_files(args.input_dir)
    if not files:
        print(f"오류: {args.input_dir} 폴더에서 .pdf/.docx 파일을 찾지 못했습니다.", file=sys.stderr)
        return 1

    print(f"총 {len(files)}개 판결문 파일을 처리합니다.")
    rows: list[dict] = []
    errors: list[str] = []

    for i, path in enumerate(files, start=1):
        print(f"[{i}/{len(files)}] {path.name} 처리 중...")
        try:
            row = process_file(path, coder_id=args.coder_id, model=args.model)
            rows.append(row)
        except (TextExtractError, LLMExtractError) as e:
            print(f"  -> 실패: {e}", file=sys.stderr)
            errors.append(f"{path.name}: {e}")

    if args.dry_run:
        for row in rows:
            print(row)
    elif rows:
        out = write_rows(args.template, args.output, rows, id_prefix=args.id_prefix)
        print(f"완료: {len(rows)}건을 {out} 에 저장했습니다.")
        print("주의: AI가 추출한 값입니다. coding_note에 '[AI 추출]' 표시가 된 행은 반드시 원문과 대조해 검수하세요.")

    if errors:
        print(f"\n{len(errors)}개 파일 처리에 실패했습니다:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
