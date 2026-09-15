"""coding_note를 파싱해 판결문 원문에서 근거 텍스트 span을 찾는다."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from .coding_book import FIELDS_BY_NAME

# 그룹별 형광펜 색상 (배경색, 텍스트색)
_GROUP_PALETTE: dict[str, tuple[str, str]] = {
    "식별":             ("#fef9c3", "#854d0e"),
    "식별/비교군":      ("#fef9c3", "#854d0e"),
    "시간":             ("#ffedd5", "#9a3412"),
    "사건지시자":       ("#ffedd5", "#9a3412"),
    "종속변수(주)":     ("#fee2e2", "#991b1b"),
    "종속변수(보조)":   ("#fee2e2", "#991b1b"),
    "종속변수(핵심2)":  ("#fce7f3", "#9d174d"),
    "양형기준":         ("#dbeafe", "#1e40af"),
    "사건특성":         ("#d1fae5", "#065f46"),
    "가해자":           ("#ede9fe", "#5b21b6"),
    "피해자":           ("#dcfce7", "#14532d"),
    "법원":             ("#e0e7ff", "#3730a3"),
    "법적맥락":         ("#e0f2fe", "#0c4a6e"),
    "관리":             ("#f3f4f6", "#374151"),
}
_DEFAULT_PALETTE = ("#fef9c3", "#854d0e")


def var_colors(var_name: str) -> tuple[str, str]:
    """변수명으로 (배경색, 텍스트색) 반환."""
    fd = FIELDS_BY_NAME.get(var_name)
    if fd:
        return _GROUP_PALETTE.get(fd.group, _DEFAULT_PALETTE)
    return _DEFAULT_PALETTE


def parse_coding_note(note: str) -> list[dict]:
    """
    coding_note 텍스트를 파싱해 변수별 항목 목록을 반환한다.

    반환: [{"var": str, "value": str, "evidence": str}, ...]
    """
    if not note:
        return []

    entries: list[dict] = []

    # "변수명=값: 근거텍스트" 패턴을 줄 단위로 파싱
    # 근거 텍스트가 여러 줄에 걸칠 수 있으므로 다음 "변수명=" 패턴이 나올 때까지 수집
    lines = note.splitlines()
    var_line_re = re.compile(
        r'^(?:\[.*?\]\s*)?'               # 선택적 태그 [AI 추출 ...]
        r'([a-zA-Z_][a-zA-Z0-9_]*)'       # 변수명
        r'\s*=\s*'
        r'([^:]{0,80}?)'                  # 값 (최대 80자, 탐욕적이지 않게)
        r'\s*:\s*'
        r'(.*)'                           # 근거 텍스트 (나머지)
    )

    current: dict | None = None
    for line in lines:
        m = var_line_re.match(line.strip())
        if m:
            if current:
                entries.append(current)
            current = {
                "var": m.group(1).strip(),
                "value": m.group(2).strip(),
                "evidence": m.group(3).strip(),
            }
        elif current and line.strip():
            # 이전 항목의 근거 텍스트가 이어지는 경우
            current["evidence"] += " " + line.strip()

    if current:
        entries.append(current)

    # 따옴표 정리 및 빈 근거 제거
    result = []
    skip_patterns = re.compile(r"판결문에 (해당 정보|언급|기재|명시).*없|결측|확인 ?불가|미기재|null|-99")
    for e in entries:
        ev = _strip_quotes(e["evidence"])
        # 의미 없는 근거(결측 설명)는 하이라이트 불필요
        if len(ev) >= 4 and not skip_patterns.search(ev):
            e["evidence"] = ev
            result.append(e)

    return result


def _strip_quotes(text: str) -> str:
    return text.strip('\'""\'“”‘’「」『』').strip()


def find_span(source: str, evidence: str, min_ratio: float = 0.62) -> tuple[int, int] | None:
    """
    source 텍스트에서 evidence에 가장 유사한 구간을 찾는다.
    min_ratio 미만이면 None 반환.
    """
    if not evidence or len(evidence) < 4:
        return None

    # 1. 완전 일치
    idx = source.find(evidence)
    if idx != -1:
        return (idx, idx + len(evidence))

    # 2. 짧은 핵심 구절로 재시도 (따옴표 안 텍스트)
    quoted = re.findall(r'["\'"「『](.*?)["\'"」』]', evidence)
    for q in quoted:
        if len(q) >= 4:
            idx = source.find(q)
            if idx != -1:
                return (idx, idx + len(q))

    # 3. 퍼지 매칭 (슬라이딩 윈도우)
    ev_len = len(evidence)
    window = min(int(ev_len * 1.4), max(ev_len + 30, 60))
    step = max(5, ev_len // 6)

    best_ratio = 0.0
    best_start = -1

    for start in range(0, len(source) - ev_len // 2, step):
        chunk = source[start : start + window]
        ratio = SequenceMatcher(None, evidence, chunk, autojunk=False).quick_ratio()
        if ratio > best_ratio:
            full = SequenceMatcher(None, evidence, chunk, autojunk=False).ratio()
            if full > best_ratio:
                best_ratio = full
                best_start = start

    if best_ratio >= min_ratio and best_start >= 0:
        return (best_start, min(best_start + ev_len + 15, len(source)))

    return None


def annotate(source: str, coding_note: str) -> list[dict]:
    """
    source 텍스트와 coding_note를 받아 span이 포함된 항목 목록을 반환한다.

    반환:
        [{"var": str, "value": str, "evidence": str,
          "span": (int, int) | None,
          "bg": str, "fg": str,
          "group": str, "definition": str}, ...]
    """
    entries = parse_coding_note(coding_note)
    result = []
    for e in entries:
        span = find_span(source, e["evidence"])
        fd = FIELDS_BY_NAME.get(e["var"])
        bg, fg = var_colors(e["var"])
        result.append({
            **e,
            "span": span,
            "bg": bg,
            "fg": fg,
            "group": fd.group if fd else "",
            "definition": fd.definition if fd else "",
        })
    return result
