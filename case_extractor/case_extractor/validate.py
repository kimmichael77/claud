"""업로드된 파일이 형사판결문처럼 보이는지 간단히 검사한다.

LLM 호출 전에 값싼 휴리스틱으로 걸러내서, 판례가 아닌 파일에 API 비용을
쓰거나 엉뚱한 값을 채우지 않도록 한다.
"""

from __future__ import annotations

# 형사판결문에 흔히 등장하는 표지 문구들. 이 중 일정 개수 이상 나와야 판결문으로 인정한다.
JUDGMENT_MARKERS = [
    "판    결", "판결", "주    문", "주문",
    "이    유", "이유", "피고인", "검    사", "검사",
    "선고", "법원", "공소사실", "범죄사실", "양형의 이유",
]

MIN_TEXT_LENGTH = 200
MIN_MARKER_HITS = 3


def looks_like_judgment(text: str) -> tuple[bool, list[str]]:
    """(판결문처럼 보이는지 여부, 발견된 표지 문구 목록)을 반환한다."""
    if not text or len(text.strip()) < MIN_TEXT_LENGTH:
        return False, []

    found = [marker.strip() for marker in JUDGMENT_MARKERS if marker in text]
    # 공백 제거형과 일반형이 중복 매치되는 걸 방지
    found = sorted(set(found))
    return len(found) >= MIN_MARKER_HITS, found


class NotJudgmentLikelyError(Exception):
    """텍스트가 판결문처럼 보이지 않을 때 발생시키는 예외."""

    def __init__(self, filename: str):
        super().__init__(
            f"{filename}: 이 파일은 판결문이 아닌 것 같습니다. "
            "올바른 판결문 파일이 맞는지 다시 확인한 뒤 넣어주세요."
        )
        self.filename = filename
