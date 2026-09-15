"""Claude API를 이용해 판결문 텍스트에서 코딩시트 항목을 추출한다."""

from __future__ import annotations

import json
import os

from .coding_book import FIELDS_BY_NAME, LLM_REQUESTED_FIELDS

DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")

_SYSTEM_PROMPT_HEADER = """당신은 형사판결문을 읽고 연구용 코딩시트 항목을 채우는 법학 연구 보조원입니다.
아래는 디지털 성범죄(몰카/딥페이크) 양형 연구의 코딩북(변수 정의서)입니다.
각 변수의 정의와 코딩 규칙을 정확히 지켜서, 판결문 원문에 실제로 근거가 있는 값만 채우세요.

규칙:
- 판결문에 명시적 근거가 없어 확정할 수 없는 항목은 절대 추측하지 말고, 숫자형 항목은 -99, 텍스트/날짜 항목은 null로 두세요.
  단, 코딩 규칙에 "9=확인불가" 또는 "9=판결문 미기재" 처럼 별도 결측 코드가 정의된 항목은 그 코드를 사용하세요.
- 날짜는 반드시 "YYYY-MM-DD" 형식의 문자열로 쓰세요. 판결문에 연호나 음력 표기가 있어도 서기/양력으로 환산하세요.
- 범주형 항목은 코딩 규칙에 정의된 숫자 코드만 사용하세요 (텍스트로 쓰지 마세요). court_region만 예외로 텍스트("수도권"/"광역시"/"기타")를 씁니다.
- sentence_months, guideline_min_months 등 개월수 항목은 "1년 2개월"=14 처럼 정수(월)로 환산하세요.
- coding_note에는 모든 변수의 코딩 근거를 한국어로 기재하세요. 형식: "변수명=값: 판결문 원문 근거". 값을 결측(-99/null/9)으로 처리한 항목은 "변수명=-99: 판결문에 해당 정보 없음" 처럼 이유를 명시하세요. 줄바꿈으로 구분하여 모든 항목을 나열하세요.
- 반드시 아래 JSON 스키마의 키만 사용해서, 다른 설명 없이 JSON 객체 하나만 출력하세요.

[코딩북]
"""


def _build_system_prompt() -> str:
    lines = [_SYSTEM_PROMPT_HEADER]
    for name in LLM_REQUESTED_FIELDS:
        f = FIELDS_BY_NAME[name]
        lines.append(f"- {f.name} ({f.group}): {f.definition}\n  코딩 규칙: {f.rule}")
    lines.append(
        "\n[출력 JSON 스키마] 아래 키를 모두 포함한 JSON 객체 하나만 출력하세요. "
        "null 자리에 판결문에서 추출한 실제 값을 채우세요. null을 그대로 두면 안 됩니다:\n"
        + json.dumps({name: None for name in LLM_REQUESTED_FIELDS}, ensure_ascii=False, indent=2)
    )
    return "\n".join(lines)


SYSTEM_PROMPT = _build_system_prompt()


class LLMExtractError(Exception):
    pass


def extract_fields(case_text: str, *, model: str | None = None, max_chars: int = 180_000) -> dict:
    """판결문 텍스트를 Claude에 보내 코딩시트 항목(JSON)을 받아온다."""
    try:
        import anthropic
    except ImportError as e:
        raise LLMExtractError(
            "anthropic 패키지가 설치되어 있지 않습니다. 'pip install -r requirements.txt'를 실행하세요."
        ) from e

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise LLMExtractError(
            "ANTHROPIC_API_KEY 환경변수가 설정되어 있지 않습니다. "
            "https://console.anthropic.com 에서 발급받은 API 키를 설정하세요."
        )

    text = case_text[:max_chars]

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model or DEFAULT_MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"다음은 판결문 전문입니다. 코딩시트 JSON을 출력하세요.\n\n[판결문]\n{text}",
            }
        ],
    )

    raw = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
    return parse_json_response(raw)


def parse_json_response(raw: str) -> dict:
    raw = raw.strip()
    # 코드블록으로 감싸져 오는 경우 대비
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        raise LLMExtractError(f"모델 응답에서 JSON을 찾지 못했습니다:\n{raw[:500]}")
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError as e:
        raise LLMExtractError(f"모델이 반환한 JSON을 파싱하지 못했습니다: {e}\n응답: {raw[:500]}") from e
    # "..." 플레이스홀더가 그대로 남아있으면 None으로 치환
    return {k: (None if v == "..." else v) for k, v in data.items()}
