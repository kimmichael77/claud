"""국가법령정보센터(law.go.kr) Open API 판례 검색 클라이언트."""

import os
import time

import requests

SEARCH_URL = "https://www.law.go.kr/DRF/lawSearch.do"
SERVICE_URL = "https://www.law.go.kr/DRF/lawService.do"

# search 파라미터: 1=판례명(사건명) 검색, 2=본문 검색
SCOPE_CASE_NAME = 1
SCOPE_FULLTEXT = 2
MAX_DISPLAY = 100


class LawGoKrError(RuntimeError):
    """API 호출/응답 관련 오류."""


class LawGoKrClient:
    def __init__(self, oc=None, timeout=10):
        self.oc = oc or os.environ.get("LAW_GO_KR_OC")
        if not self.oc:
            raise LawGoKrError(
                "OC 값이 없습니다. 환경변수 LAW_GO_KR_OC를 설정하거나 --oc 옵션을 사용하세요. "
                "https://open.law.go.kr 에서 오픈API 신청 후 발급받은 이메일 아이디(@ 앞부분)를 사용합니다."
            )
        self.timeout = timeout

    def search_precedents(self, query, page=1, display=20, court=None, scope=None):
        """판례명/본문을 키워드로 검색한다.

        law.go.kr는 target=prec 검색 결과에서 항목이 1건이면 dict를,
        여러 건이면 list를 반환하므로 항상 list로 정규화해 돌려준다.

        scope: SCOPE_CASE_NAME(1, 사건명/죄명 검색) 또는 SCOPE_FULLTEXT(2, 본문 검색).
        서로 다른 조문(예: 제14조 vs 제14조의2)을 구분해서 찾을 때는
        본문 검색보다 죄명이 그대로 반영되는 사건명 검색이 더 정확하다.
        """
        params = {
            "OC": self.oc,
            "target": "prec",
            "type": "JSON",
            "query": query,
            "page": page,
            "display": display,
        }
        if court:
            params["curt"] = court
        if scope:
            params["search"] = scope

        data = self._get(SEARCH_URL, params)
        root = data.get("PrecSearch", {})
        items = root.get("prec", [])
        if isinstance(items, dict):
            items = [items]

        return {
            "total_count": int(root.get("totalCnt", 0) or 0),
            "page": int(root.get("page", page) or page),
            "items": items,
        }

    def search_precedents_all(
        self, query, court=None, scope=None, max_results=200, delay=0.2
    ):
        """여러 페이지를 순회하며 최대 max_results건까지 모아서 반환한다.

        API 호출 사이에 delay(초)만큼 대기해 과도한 요청을 피한다.
        """
        collected = []
        page = 1
        total_count = 0
        while len(collected) < max_results:
            remaining = max_results - len(collected)
            display = min(MAX_DISPLAY, remaining)
            result = self.search_precedents(
                query, page=page, display=display, court=court, scope=scope
            )
            total_count = result["total_count"]
            items = result["items"]
            if not items:
                break
            collected.extend(items)
            if len(items) < display:
                break
            page += 1
            if delay:
                time.sleep(delay)

        return {"total_count": total_count, "items": collected}

    def get_precedent_detail(self, prec_id):
        """판례일련번호로 상세(전문 포함)를 조회한다."""
        params = {
            "OC": self.oc,
            "target": "prec",
            "ID": prec_id,
            "type": "JSON",
        }
        data = self._get(SERVICE_URL, params)
        return data.get("PrecService", {})

    def _get(self, url, params):
        try:
            resp = requests.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise LawGoKrError(f"API 요청에 실패했습니다: {exc}") from exc

        try:
            return resp.json()
        except ValueError as exc:
            raise LawGoKrError(
                "API 응답을 JSON으로 해석할 수 없습니다. OC 값이 잘못되었거나 "
                f"일시적인 API 오류일 수 있습니다. 응답 일부: {resp.text[:300]!r}"
            ) from exc
