"""coding_note를 파싱해 판결문 원문에서 근거 텍스트 span을 찾는다."""

from __future__ import annotations

import re
from difflib import SequenceMatcher


def _normalize_ws(text: str) -> str:
    """연속 공백/탭/줄바꿈을 공백 하나로 축약."""
    return re.sub(r'\s+', ' ', text).strip()


def _make_norm_map(original: str) -> tuple[str, list[int]]:
    """
    원본 텍스트의 공백-정규화 버전과 (정규화 위치 → 원본 위치) 매핑을 반환한다.
    PDF에서 '피 해자' 같이 불필요한 공백이 삽입된 경우도 매칭하기 위해 사용.
    """
    norm_chars: list[str] = []
    orig_pos: list[int] = []  # norm 인덱스 → orig 인덱스
    prev_space = False
    for i, c in enumerate(original):
        if c in ' \t\n\r':
            if not prev_space and norm_chars:
                norm_chars.append(' ')
                orig_pos.append(i)
            prev_space = True
        else:
            norm_chars.append(c)
            orig_pos.append(i)
            prev_space = False
    return ''.join(norm_chars), orig_pos

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


def find_span(source: str, evidence: str, min_ratio: float = 0.58) -> tuple[int, int] | None:
    """
    source 텍스트에서 evidence에 가장 유사한 구간을 찾는다.
    min_ratio 미만이면 None 반환.

    매칭 순서:
      1. 원문 완전 일치
      2. 공백 정규화 후 완전 일치 (PDF 공백 오염 대응)
      3. 따옴표 안 핵심 구절 정확 일치
      4. 따옴표 안 핵심 구절 공백 정규화 일치
      5. 공백 정규화된 공간에서 퍼지 매칭
    """
    if not evidence or len(evidence) < 4:
        return None

    # ── 1. 원문 완전 일치 ──────────────────────────────────────────
    idx = source.find(evidence)
    if idx != -1:
        return (idx, idx + len(evidence))

    # ── 2. 공백 정규화 후 완전 일치 ───────────────────────────────
    norm_src, norm_map = _make_norm_map(source)
    norm_ev = _normalize_ws(evidence)
    idx = norm_src.find(norm_ev)
    if idx != -1:
        orig_start = norm_map[idx]
        orig_end = norm_map[min(idx + len(norm_ev) - 1, len(norm_map) - 1)] + 1
        return (orig_start, orig_end)

    # ── 3 & 4. 따옴표 안 핵심 구절 ────────────────────────────────
    quoted = re.findall(r'["\'"「『](.*?)["\'"」』]', evidence)
    for q in quoted:
        if len(q) >= 4:
            idx = source.find(q)
            if idx != -1:
                return (idx, idx + len(q))
            # 공백 정규화
            nq = _normalize_ws(q)
            idx = norm_src.find(nq)
            if idx != -1:
                orig_start = norm_map[idx]
                orig_end = norm_map[min(idx + len(nq) - 1, len(norm_map) - 1)] + 1
                return (orig_start, orig_end)

    # ── 5. 퍼지 매칭 (정규화 공간에서 슬라이딩 윈도우) ────────────
    ev_len = len(norm_ev)
    src_len = len(norm_src)
    window = min(int(ev_len * 1.3), max(ev_len + 20, 50))
    step = max(2, ev_len // 10)   # 더 촘촘한 보폭

    best_ratio = 0.0
    best_norm_start = -1

    for start in range(0, src_len - ev_len // 2, step):
        chunk = norm_src[start : start + window]
        ratio = SequenceMatcher(None, norm_ev, chunk, autojunk=False).quick_ratio()
        if ratio > best_ratio:
            full = SequenceMatcher(None, norm_ev, chunk, autojunk=False).ratio()
            if full > best_ratio:
                best_ratio = full
                best_norm_start = start

    if best_ratio >= min_ratio and best_norm_start >= 0:
        orig_start = norm_map[best_norm_start]
        end_norm = min(best_norm_start + ev_len + 10, len(norm_map) - 1)
        orig_end = norm_map[end_norm] + 1
        return (orig_start, orig_end)

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
