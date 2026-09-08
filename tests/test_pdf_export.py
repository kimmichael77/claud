import os
import tempfile
import unittest
from unittest.mock import patch

from judgment_search.pdf_export import (
    FontNotFoundError,
    find_korean_font,
    save_detail_as_pdf,
)

# 이 저장소/CI 환경에는 한글 글리프를 가진 폰트가 없을 수 있으므로,
# PDF 생성 파이프라인 자체(줄바꿈, 페이지 넘김, 파일 출력)만 검증하기 위해
# 시스템에 존재하는 임의의 ttf 폰트를 사용한다. 실제 사용자 환경에서는
# find_korean_font()가 찾아주는 한글 폰트(맑은 고딕 등)가 쓰인다.
_ANY_TTF_CANDIDATES = [
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    r"C:\Windows\Fonts\arial.ttf",
]


def _find_any_ttf():
    for path in _ANY_TTF_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


class FindKoreanFontTest(unittest.TestCase):
    def test_returns_first_existing_candidate(self):
        with patch("judgment_search.pdf_export.platform.system", return_value="Windows"), patch(
            "judgment_search.pdf_export.os.path.exists",
            side_effect=lambda p: p == r"C:\Windows\Fonts\malgun.ttf",
        ):
            self.assertEqual(find_korean_font(), r"C:\Windows\Fonts\malgun.ttf")

    def test_raises_when_nothing_found(self):
        with patch("judgment_search.pdf_export.platform.system", return_value="Linux"), patch(
            "judgment_search.pdf_export.os.path.exists", return_value=False
        ):
            with self.assertRaises(FontNotFoundError):
                find_korean_font()


@unittest.skipUnless(_find_any_ttf(), "테스트용 ttf 폰트를 찾을 수 없어 건너뜀")
class SaveDetailAsPdfTest(unittest.TestCase):
    def test_creates_non_empty_pdf_with_all_sections(self):
        font_path = _find_any_ttf()
        detail = {
            "사건명": "Test Case Name",
            "사건번호": "2020do1234",
            "선고일자": "20200101",
            "법원명": "Supreme Court",
            "판시사항": "Holding text.",
            "판결요지": "Summary text.",
            "판례내용": "Full opinion text. " * 200,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "out.pdf")
            save_detail_as_pdf(detail, path, font_path=font_path)
            self.assertTrue(os.path.exists(path))
            self.assertGreater(os.path.getsize(path), 0)
            with open(path, "rb") as f:
                self.assertEqual(f.read(4), b"%PDF")

    def test_handles_missing_fields_gracefully(self):
        font_path = _find_any_ttf()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "out.pdf")
            save_detail_as_pdf({}, path, font_path=font_path)
            self.assertTrue(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()
