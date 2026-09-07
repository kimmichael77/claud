"""국가법령정보센터 Open API 판례 검색 CLI."""

import argparse
import csv
import json
import sys

from .client import LawGoKrClient, LawGoKrError


def cmd_search(args):
    client = LawGoKrClient(oc=args.oc)
    result = client.search_precedents(
        query=args.query,
        page=args.page,
        display=args.display,
        court=args.court,
    )
    items = result["items"]

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
    p_search.add_argument("--out", help="결과를 저장할 파일 경로 (.json 또는 .csv)")
    p_search.set_defaults(func=cmd_search)

    p_detail = sub.add_parser("detail", help="판례일련번호로 상세(전문) 조회")
    p_detail.add_argument("id", help="판례일련번호 (search 결과의 대괄호 안 번호)")
    p_detail.add_argument("--out", help="결과를 저장할 파일 경로 (.json)")
    p_detail.set_defaults(func=cmd_detail)

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
