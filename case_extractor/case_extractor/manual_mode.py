"""API 키 없이, claude.ai 웹 채팅으로 복사/붙여넣기 하며 진행하는 수동 모드.

흐름:
1) 판결문마다 프롬프트(.txt)를 만든다 (make_prompt_file).
2) 그 내용을 claude.ai 채팅창에 붙여넣고, 받은 JSON 답변 전체를 같은 이름의
   .json 파일로 저장한다 (사용자가 손으로).
3) 판결문 + 그 응답을 짝지어 코딩시트 엑셀 행으로 합친다 (load_response, build_row).
"""

from __future__ import annotations

from pathlib import Path

from .coding_book import LLM_REQUESTED_FIELDS, SHEET_COLUMN_ORDER
from .compute import apply_computed_fields
from .llm_extract import SYSTEM_PROMPT, LLMExtractError, parse_json_response
from .text_extract import extract_text
from .validate import NotJudgmentLikelyError, looks_like_judgment

MAX_CHARS = 180_000


def build_prompt(case_text: str, *, max_chars: int = MAX_CHARS) -> str:
    text = case_text[:max_chars]
    return (
        SYSTEM_PROMPT
        + "\n\n다음은 판결문 전문입니다. 위 규칙에 따라 코딩시트 JSON을 출력하세요. "
          "다른 설명 없이 JSON 객체 하나만 출력하세요.\n\n[판결문]\n"
        + text
    )


def make_prompt_file(source: Path, out_dir: Path, *, skip_judgment_check: bool = False) -> Path:
    """source 판결문에서 텍스트를 뽑아 프롬프트 .txt 파일을 만들고 그 경로를 반환한다."""
    text = extract_text(source)
    if not skip_judgment_check:
        ok, _markers = looks_like_judgment(text)
        if not ok:
            raise NotJudgmentLikelyError(source.name)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{source.stem}.prompt.txt"
    out_path.write_text(build_prompt(text), encoding="utf-8")
    return out_path


def load_response(source: Path, responses_dir: Path) -> dict:
    """source와 이름이 같은 응답 파일(.json 또는 .txt)을 찾아 JSON으로 파싱한다."""
    for ext in (".json", ".txt"):
        candidate = responses_dir / f"{source.stem}{ext}"
        if candidate.exists():
            raw = candidate.read_text(encoding="utf-8")
            return parse_json_response(raw)
    raise LLMExtractError(
        f"{source.name}: 응답 파일을 찾지 못했습니다 "
        f"({responses_dir} 폴더에 '{source.stem}.json' 또는 '{source.stem}.txt' 파일이 있어야 합니다)"
    )


def build_row(source: Path, extracted: dict, *, coder_id: str) -> dict:
    row = {name: extracted.get(name) for name in LLM_REQUESTED_FIELDS}
    row["coder_id"] = coder_id
    row["case_id"] = None  # excel_writer가 자동 채번

    row = apply_computed_fields(row)

    note = str(row.get("coding_note") or "").strip()
    ai_tag = f"[AI 추출-수동: {source.name}] 검토 필요"
    row["coding_note"] = f"{ai_tag} {note}".strip()

    return {name: row.get(name) for name in SHEET_COLUMN_ORDER}
