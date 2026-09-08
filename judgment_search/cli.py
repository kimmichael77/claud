"""국가법령정보센터 Open API 판례 검색 CLI."""

import argparse
import csv
import json
import os
import sys
import time

from .client import SCOPE_CASE_NAME, SCOPE_FULLTEXT, LawGoKrClient, LawGoKrError
from .pdf_export import FontNotFoundError, save_detail_as_pdf

_SCOPE_MAP = {"case_name": SCOPE_CASE_NAME, "fulltext": SCOPE_FULLTEXT}

# 성폭력범죄의 처벌 등에 관한 특례법 제14조/제14조의2는 죄명(사건명)이 서로 달라
# 사건명 검색으로 구분하는 것이 본문 검색보다 정확하다.
DEFAULT_QUERY_ARTICLE_14 = "카메라등이용촬영"
DEFAULT_LABEL_ARTICLE_14 = "성폭력처벌법 제14조(카메라 등을 이용한 촬영)"
DEFAULT_QUERY_ARTICLE_14_2 = "허위영상물"
DEFAULT_LABEL_ARTICLE_14_2 = "성폭력처벌법 제14조의2(허위영상물 등의 반포등)"


def cmd_search(args):
    client = LawGoKrClient(oc=args.oc)
    result = client.search_precedents(
        query=args.query,
        page=args.page,
        display=args.display,
        court=args.court,
        scope=_SCOPE_MAP.get(args.scope),
    )
    items = result["items"]

    if args.pdf_dir:
        _save_items_as_pdfs(client, items, args.pdf_dir, args.font)

    if args.out:
        _save(items, args.out)
        print(
            f"{len(items)}건 저장 완료 -> {args.out} "
            f"(전체 {result['total_count']}건 중 {result['page']}페이지)"
        )
        return

    print(f"전체 {result['total_count']}건 중 {result['page']}페이지 ({len(items)}건 표시)\n")
    for item in items:
        print(f"[{item.get('판례일련번호')}] {item.get('사건명')} ({item.get('사건번호')})")
        print(f"  법원: {item.get('법원명')}  선고일자: {item.get('선고일자')}  유형: {item.get('사건종류명')}")
        print()


def cmd_detail(args):
    client = LawGoKrClient(oc=args.oc)
    detail = client.get_precedent_detail(args.id)
    if not detail:
        print("결과가 없습니다. ID를 확인하세요.", file=sys.stderr)
        sys.exit(1)

    if args.pdf:
        _save_detail_pdf(detail, args.pdf, args.font)
        print(f"PDF 저장 완료 -> {args.pdf}")

    if args.out:
        _save(detail, args.out)
        print(f"저장 완료 -> {args.out}")
        return

    print(f"사건명: {detail.get('사건명')}")
    print(f"사건번호: {detail.get('사건번호')}")
    print(f"선고일자: {detail.get('선고일자')}")
    print(f"법원명: {detail.get('법원명')}")
    print()
    print("[판시사항]")
    print((detail.get("판시사항") or "").strip() or "(없음)")
    print()
    print("[판결요지]")
    print((detail.get("판결요지") or "").strip() or "(없음)")
    print()
    print("[전문]")
    print((detail.get("판례내용") or "").strip() or "(없음)")


def cmd_compare(args):
    client = LawGoKrClient(oc=args.oc)
    groups = [
        (args.label1, args.query1),
        (args.label2, args.query2),
    ]
    scope = _SCOPE_MAP.get(args.scope)

    os.makedirs(args.out_dir, exist_ok=True)

    results = []
    for label, query in groups:
        result = client.search_precedents_all(
            query, court=args.court, scope=scope, max_results=args.max_results
        )
        items = result["items"]
        out_path = os.path.join(args.out_dir, f"{_safe_filename(label)}.json")
        _save(items, out_path)
        results.append((label, query, result["total_count"], items, out_path))

        if args.pdf:
            pdf_dir = os.path.join(args.out_dir, f"{_safe_filename(label)}_pdf")
            _save_items_as_pdfs(client, items, pdf_dir, args.font)

    print("검색 결과 요약")
    print("-" * 60)
    for label, query, total_count, items, out_path in results:
        print(f"- {label}")
        print(f"  검색어: {query!r}  범위: {args.scope}")
        print(f"  전체 {total_count}건 중 {len(items)}건 수집 -> {out_path}")
    print()

    ids_by_label = {
        label: {item.get("판례일련번호") for item in items}
        for label, _q, _t, items, _p in results
    }
    (label1, _q1), (label2, _q2) = groups
    overlap = ids_by_label[label1] & ids_by_label[label2]
    if overlap:
        print(
            f"[주의] 두 그룹에 동시에 포함된 판례 {len(overlap)}건이 있습니다 "
            "(하나의 판결문에서 두 죄명이 함께 다뤄졌을 가능성). "
            "구분이 필요하면 각 판례를 직접 확인하세요:"
        )
        for prec_id in sorted(overlap):
            print(f"  - {prec_id}")
    else:
        print("두 그룹 간 중복된 판례는 없습니다.")


def _save_detail_pdf(detail, path, font_path=None):
    try:
        save_detail_as_pdf(detail, path, font_path=font_path)
    except FontNotFoundError as exc:
        raise LawGoKrError(str(exc)) from exc


def _save_items_as_pdfs(client, items, out_dir, font_path=None):
    """검색 결과 목록(요약 정보만 있음)을 받아 각 판례의 상세를 조회한 뒤

    개별 PDF 파일로 저장한다.
    """
    os.makedirs(out_dir, exist_ok=True)
    print(f"{len(items)}건을 PDF로 저장합니다 (폴더: {out_dir})...")
    for i, item in enumerate(items, 1):
        prec_id = item.get("판례일련번호")
        if not prec_id:
            continue
        detail = client.get_precedent_detail(prec_id)
        case_no = detail.get("사건번호") or prec_id
        filename = f"{_safe_filename(str(case_no))}_{prec_id}.pdf"
        path = os.path.join(out_dir, filename)
        _save_detail_pdf(detail, path, font_path)
        print(f"  [{i}/{len(items)}] {path}")
        time.sleep(0.2)


def _safe_filename(label):
    keep = "".join(ch if ch.isalnum() else "_" for ch in label)
    return keep.strip("_") or "result"


def _save(data, path):
    if path.endswith(".csv"):
        rows = data if isinstance(data, list) else [data]
        if not rows:
            open(path, "w", encoding="utf-8-sig").close()
            return
        fieldnames = sorted({key for row in rows for key in row.keys()})
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    else:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="judgment_search",
        description="국가법령정보센터 Open API를 이용한 판례 검색 도구",
    )
    parser.add_argument("--oc", help="OC 값 (미지정 시 환경변수 LAW_GO_KR_OC 사용)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_search = sub.add_parser("search", help="키워드로 판례 검색")
    p_search.add_argument("query", help="검색어")
    p_search.add_argument("--page", type=int, default=1)
    p_search.add_argument("--display", type=int, default=20, help="페이지당 건수 (최대 100)")
    p_search.add_argument("--court", help="법원명으로 필터 (예: 대법원)")
    p_search.add_argument(
        "--scope",
        choices=["case_name", "fulltext"],
        default=None,
        help="검색 범위: case_name(사건명/죄명) 또는 fulltext(본문). 미지정 시 API 기본값 사용",
    )
    p_search.add_argument("--out", help="결과를 저장할 파일 경로 (.json 또는 .csv)")
    p_search.add_argument(
        "--pdf-dir", help="검색된 판례 각각의 상세를 조회해 PDF로 저장할 폴더"
    )
    p_search.add_argument(
        "--font", help="PDF에 사용할 한글 TTF 폰트 경로 (미지정 시 OS 기본 폰트 자동 탐색)"
    )
    p_search.set_defaults(func=cmd_search)

    p_detail = sub.add_parser("detail", help="판례일련번호로 상세(전문) 조회")
    p_detail.add_argument("id", help="판례일련번호 (search 결과의 대괄호 안 번호)")
    p_detail.add_argument("--out", help="결과를 저장할 파일 경로 (.json)")
    p_detail.add_argument("--pdf", help="상세 내용을 저장할 PDF 파일 경로")
    p_detail.add_argument(
        "--font", help="PDF에 사용할 한글 TTF 폰트 경로 (미지정 시 OS 기본 폰트 자동 탐색)"
    )
    p_detail.set_defaults(func=cmd_detail)

    p_compare = sub.add_parser(
        "compare",
        help="두 죄명(조문)을 구분해서 판례를 검색하고 결과를 비교 (기본값: 성폭력처벌법 제14조 vs 제14조의2)",
    )
    p_compare.add_argument("--query1", default=DEFAULT_QUERY_ARTICLE_14, help="첫 번째 그룹 검색어")
    p_compare.add_argument("--label1", default=DEFAULT_LABEL_ARTICLE_14, help="첫 번째 그룹 이름표")
    p_compare.add_argument("--query2", default=DEFAULT_QUERY_ARTICLE_14_2, help="두 번째 그룹 검색어")
    p_compare.add_argument("--label2", default=DEFAULT_LABEL_ARTICLE_14_2, help="두 번째 그룹 이름표")
    p_compare.add_argument("--court", help="법원명으로 필터 (예: 대법원)")
    p_compare.add_argument(
        "--scope",
        choices=["case_name", "fulltext"],
        default="case_name",
        help="검색 범위. 두 조문을 구분할 때는 사건명(case_name) 검색을 권장. 기본값 case_name",
    )
    p_compare.add_argument(
        "--max-results", type=int, default=200, help="그룹당 최대 수집 건수 (기본 200)"
    )
    p_compare.add_argument(
        "--out-dir", default="compare_results", help="결과 json을 저장할 디렉터리 (기본 compare_results)"
    )
    p_compare.add_argument(
        "--pdf",
        action="store_true",
        help="각 그룹의 판례를 개별 PDF로도 저장 (out-dir 하위 <이름표>_pdf 폴더)",
    )
    p_compare.add_argument(
        "--font", help="PDF에 사용할 한글 TTF 폰트 경로 (미지정 시 OS 기본 폰트 자동 탐색)"
    )
    p_compare.set_defaults(func=cmd_compare)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except LawGoKrError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
