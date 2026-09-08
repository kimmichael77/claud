"""수동 모드 CLI: Anthropic API 키 없이 claude.ai 웹 채팅으로 코딩시트를 채운다.

1단계 (프롬프트 생성):
    python3 -m case_extractor.manual_cli make-prompts \\
        --input-dir ~/Desktop/판결문모음 \\
        --prompts-dir ~/Desktop/prompts

    생성된 각 "*.prompt.txt" 파일의 내용을 통째로 복사해서 claude.ai 채팅창에
    붙여넣고, 받은 JSON 답변 전체를 같은 이름(.json)으로 responses 폴더에
    저장하세요. 예: 판결문1.pdf -> prompts/판결문1.prompt.txt -> responses/판결문1.json

2단계 (엑셀로 합치기):
    python3 -m case_extractor.manual_cli import \\
        --template ~/Desktop/코딩시트.xlsx \\
        --input-dir ~/Desktop/판결문모음 \\
        --responses-dir ~/Desktop/responses \\
        --output ~/Desktop/코딩시트_결과.xlsx \\
        --coder-id C1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .excel_writer import write_rows
from .llm_extract import LLMExtractError
from .manual_mode import build_row, load_response, make_prompt_file
from .text_extract import TextExtractError, find_case_files
from .validate import NotJudgmentLikelyError


def _collect_files(args: argparse.Namespace) -> list[Path]:
    if args.input_dir is not None:
        return find_case_files(args.input_dir)
    return args.input_files


def cmd_make_prompts(args: argparse.Namespace) -> int:
    files = _collect_files(args)
    if not files:
        print("오류: 처리할 판결문 파일을 찾지 못했습니다.", file=sys.stderr)
        return 1

    print(f"{len(files)}개 파일의 프롬프트를 만듭니다...")
    made = 0
    for f in files:
        try:
            out = make_prompt_file(f, args.prompts_dir, skip_judgment_check=args.skip_judgment_check)
            print(f"  {f.name} -> {out}")
            made += 1
        except (TextExtractError, NotJudgmentLikelyError) as e:
            print(f"  건너뜀: {e}", file=sys.stderr)

    print(f"\n완료: {made}개 프롬프트 파일을 {args.prompts_dir} 에 만들었습니다.")
    print("각 파일 내용을 claude.ai 채팅창에 붙여넣고, 받은 JSON 답변 전체를 같은 이름(.json)으로")
    print("저장한 뒤 'import' 명령으로 엑셀을 만드세요.")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    files = _collect_files(args)
    if not files:
        print("오류: 처리할 판결문 파일을 찾지 못했습니다.", file=sys.stderr)
        return 1

    rows: list[dict] = []
    errors: list[str] = []
    for f in files:
        try:
            extracted = load_response(f, args.responses_dir)
            rows.append(build_row(f, extracted, coder_id=args.coder_id))
        except LLMExtractError as e:
            print(f"  건너뜀: {e}", file=sys.stderr)
            errors.append(str(e))

    if rows:
        out = write_rows(args.template, args.output, rows, id_prefix=args.id_prefix)
        print(f"완료: {len(rows)}건을 {out} 에 저장했습니다.")
        print("주의: AI가 추출한 값입니다. coding_note에 '[AI 추출-수동]' 표시가 된 행은 반드시 원문과 대조해 검수하세요.")

    if errors:
        print(f"\n{len(errors)}건 실패:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 2
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Anthropic API 키 없이 claude.ai 채팅으로 코딩시트를 채우는 수동 모드")
    sub = p.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    group = common.add_mutually_exclusive_group(required=True)
    group.add_argument("--input-dir", type=Path, help="판결문 PDF/DOCX 파일들이 있는 폴더")
    group.add_argument("--input-files", type=Path, nargs="+", help="판결문 PDF/DOCX 파일 경로 목록")

    mp = sub.add_parser("make-prompts", parents=[common], help="판결문마다 프롬프트 .txt 생성")
    mp.add_argument("--prompts-dir", required=True, type=Path, help="프롬프트 .txt를 저장할 폴더")
    mp.add_argument("--skip-judgment-check", action="store_true")
    mp.set_defaults(func=cmd_make_prompts)

    im = sub.add_parser("import", parents=[common], help="claude.ai 응답(JSON)들을 엑셀로 합치기")
    im.add_argument("--template", required=True, type=Path)
    im.add_argument("--responses-dir", required=True, type=Path, help="응답(.json/.txt) 파일들이 있는 폴더")
    im.add_argument("--output", required=True, type=Path)
    im.add_argument("--coder-id", default="")
    im.add_argument("--id-prefix", default="DF-2024-")
    im.set_defaults(func=cmd_import)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
