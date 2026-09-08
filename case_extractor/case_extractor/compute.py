"""LLM에게 맡기지 않고 코드로 결정론적으로 계산하는 파생 변수들.

이 값들은 산술/규칙 기반이라 LLM보다 코드로 계산하는 편이 정확하다.
"""

from __future__ import annotations

from datetime import date, datetime

MISSING = -99


def _parse_date(value) -> date | None:
    if value in (None, "", MISSING, "-99"):
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _num(value) -> float | None:
    if value in (None, "", MISSING, "-99"):
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n == MISSING:
        return None
    return n


def compute_duration(start_date, end_date) -> int | None:
    s, e = _parse_date(start_date), _parse_date(end_date)
    if s is None or e is None:
        return None
    return (e - s).days


def compute_appeal_duration(end_date, prior_judgment_date) -> int | None:
    e, p = _parse_date(end_date), _parse_date(prior_judgment_date)
    if e is None or p is None:
        return None
    return (e - p).days


def compute_rel_position(sentence_months, lo, hi) -> float | None:
    s, lo_v, hi_v = _num(sentence_months), _num(lo), _num(hi)
    if s is None or lo_v is None or hi_v is None or hi_v == lo_v:
        return None
    return round((s - lo_v) / (hi_v - lo_v), 4)


def compute_guideline_deviation(sentence_months, guideline_min, guideline_max) -> int:
    s, lo, hi = _num(sentence_months), _num(guideline_min), _num(guideline_max)
    if s is None or lo is None or hi is None:
        return 9
    return 1 if (s < lo or s > hi) else 0


def compute_deviation_direction(sentence_months, guideline_min, guideline_max, rel_position) -> int:
    s, lo, hi = _num(sentence_months), _num(guideline_min), _num(guideline_max)
    if s is None or lo is None or hi is None:
        return 9
    if s < lo:
        return 1
    if s > hi:
        return 2
    if rel_position is not None:
        if rel_position <= 0.15:
            return 3
        if rel_position >= 0.85:
            return 4
    return 0


def apply_computed_fields(row: dict) -> dict:
    """row(dict, LLM 추출 결과 + manual 필드)에 계산 필드를 채워 넣고 반환한다."""
    row = dict(row)

    row["duration"] = compute_duration(row.get("start_date"), row.get("end_date"))
    row["appeal_duration"] = compute_appeal_duration(row.get("end_date"), row.get("prior_judgment_date"))

    row["guideline_rel_position"] = compute_rel_position(
        row.get("sentence_months"), row.get("guideline_min_months"), row.get("guideline_max_months")
    )
    row["area_rel_position"] = compute_rel_position(
        row.get("sentence_months"), row.get("area_min_months"), row.get("area_max_months")
    )

    row["guideline_deviation"] = compute_guideline_deviation(
        row.get("sentence_months"), row.get("guideline_min_months"), row.get("guideline_max_months")
    )
    row["deviation_direction"] = compute_deviation_direction(
        row.get("sentence_months"),
        row.get("guideline_min_months"),
        row.get("guideline_max_months"),
        row.get("guideline_rel_position"),
    )

    return row
