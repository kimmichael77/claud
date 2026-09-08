"""판례 상세 내용을 한글이 포함된 PDF 파일로 저장하는 유틸리티.

law.go.kr Open API는 PDF를 직접 제공하지 않고 텍스트(JSON)만 내려주므로,
detail(get_precedent_detail) 결과를 받아 여기서 PDF로 변환한다.
한글 표시를 위해서는 한글 글리프가 포함된 TrueType 폰트가 반드시 필요하다.
"""

import os
import platform

from fpdf import FPDF

# OS별로 기본 내장된 한글 폰트 후보 경로.
_CANDIDATE_FONTS = {
    "Windows": [
        r"C:\Windows\Fonts\malgun.ttf",
        r"C:\Windows\Fonts\gulim.ttc",
    ],
    "Darwin": [
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    ],
    "Linux": [
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ],
}


class FontNotFoundError(RuntimeError):
    """시스템에서 한글 폰트를 찾지 못했을 때 발생."""


def find_korean_font():
    for path in _CANDIDATE_FONTS.get(platform.system(), []):
        if os.path.exists(path):
            return path
    raise FontNotFoundError(
        "한글을 표시할 수 있는 폰트를 찾지 못했습니다. "
        "나눔고딕 등 한글 TTF 폰트를 설치한 뒤 --font 옵션으로 "
        "폰트 파일 경로를 직접 지정해주세요."
    )


def _line(pdf, height, text):
    """multi_cell 기본값(new_x=RIGHT)이 커서를 우측 여백에 남겨 다음 줄의

    가용 너비를 거의 0으로 만드는 문제를 피하기 위해, 매번 커서를
    왼쪽 여백/다음 줄로 되돌리는 래퍼.
    """
    pdf.multi_cell(0, height, text, new_x="LMARGIN", new_y="NEXT")


def save_detail_as_pdf(detail, path, font_path=None):
    """판례 상세(detail) 딕셔너리를 하나의 PDF 파일로 저장한다."""
    font_path = font_path or find_korean_font()

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.add_font("Korean", "", font_path)

    pdf.set_font("Korean", size=14)
    _line(pdf, 10, detail.get("사건명") or "(사건명 없음)")

    pdf.set_font("Korean", size=10)
    pdf.ln(2)
    meta = (
        f"사건번호: {detail.get('사건번호', '')}    "
        f"선고일자: {detail.get('선고일자', '')}    "
        f"법원명: {detail.get('법원명', '')}"
    )
    _line(pdf, 7, meta)
    pdf.ln(4)

    sections = [
        ("판시사항", detail.get("판시사항")),
        ("판결요지", detail.get("판결요지")),
        ("전문", detail.get("판례내용")),
    ]
    for title, body in sections:
        body = (body or "").strip()
        if not body:
            continue
        pdf.set_font("Korean", size=12)
        _line(pdf, 8, f"[{title}]")
        pdf.set_font("Korean", size=10)
        _line(pdf, 6, body)
        pdf.ln(4)

    pdf.output(path)
