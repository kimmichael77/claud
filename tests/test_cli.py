import json
import os
import tempfile
import unittest
from unittest.mock import patch

from judgment_search.cli import main


class CompareCliTest(unittest.TestCase):
    def _search_precedents_all_side_effect(self, query, **kwargs):
        if "촬영" in query:
            items = [
                {"판례일련번호": "1", "사건명": "성폭력처벌법위반(카메라등이용촬영·반포등)"},
                {"판례일련번호": "2", "사건명": "성폭력처벌법위반(카메라등이용촬영·반포등)"},
                {"판례일련번호": "99", "사건명": "성폭력처벌법위반(카메라등이용촬영등),성폭력처벌법위반(허위영상물편집·반포등)"},
            ]
        else:
            items = [
                {"판례일련번호": "3", "사건명": "성폭력처벌법위반(허위영상물편집·반포등)"},
                {"판례일련번호": "99", "사건명": "성폭력처벌법위반(카메라등이용촬영등),성폭력처벌법위반(허위영상물편집·반포등)"},
            ]
        return {"total_count": len(items), "items": items}

    def test_compare_writes_separate_files_and_reports_overlap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = os.path.join(tmpdir, "out")
            with patch(
                "judgment_search.cli.LawGoKrClient.search_precedents_all",
                side_effect=self._search_precedents_all_side_effect,
            ), patch("judgment_search.cli.LawGoKrClient.__init__", return_value=None):
                main(["compare", "--out-dir", out_dir])

            label1_file = [f for f in os.listdir(out_dir) if "카메라" in f]
            label2_file = [f for f in os.listdir(out_dir) if "허위영상물" in f]
            self.assertEqual(len(label1_file), 1)
            self.assertEqual(len(label2_file), 1)

            with open(os.path.join(out_dir, label1_file[0]), encoding="utf-8") as f:
                group1 = json.load(f)
            with open(os.path.join(out_dir, label2_file[0]), encoding="utf-8") as f:
                group2 = json.load(f)

            self.assertEqual({item["판례일련번호"] for item in group1}, {"1", "2", "99"})
            self.assertEqual({item["판례일련번호"] for item in group2}, {"3", "99"})

    def test_compare_with_pdf_flag_saves_one_pdf_per_item(self):
        saved_paths = []

        def fake_save_pdf(detail, path, font_path=None):
            saved_paths.append(path)
            with open(path, "w", encoding="utf-8") as f:
                f.write("fake-pdf")

        def fake_get_detail(self, prec_id):
            return {"사건번호": f"case-{prec_id}", "사건명": "테스트"}

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = os.path.join(tmpdir, "out")
            with patch(
                "judgment_search.cli.LawGoKrClient.search_precedents_all",
                side_effect=self._search_precedents_all_side_effect,
            ), patch(
                "judgment_search.cli.LawGoKrClient.__init__", return_value=None
            ), patch(
                "judgment_search.cli.LawGoKrClient.get_precedent_detail", fake_get_detail
            ), patch(
                "judgment_search.cli.save_detail_as_pdf", side_effect=fake_save_pdf
            ):
                main(["compare", "--out-dir", out_dir, "--pdf"])

            pdf_dirs = [d for d in os.listdir(out_dir) if d.endswith("_pdf")]
            self.assertEqual(len(pdf_dirs), 2)
            all_pdfs = []
            for d in pdf_dirs:
                all_pdfs.extend(os.listdir(os.path.join(out_dir, d)))
            # 그룹1(3건: 1,2,99) + 그룹2(2건: 3,99) = 5개 PDF
            self.assertEqual(len(all_pdfs), 5)
            self.assertEqual(len(saved_paths), 5)


class DetailCliTest(unittest.TestCase):
    def test_detail_with_pdf_option_calls_pdf_writer(self):
        saved = {}

        def fake_save_pdf(detail, path, font_path=None):
            saved["path"] = path
            saved["detail"] = detail

        def fake_get_detail(self, prec_id):
            return {"사건명": "테스트 사건", "판례내용": "본문"}

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = os.path.join(tmpdir, "result.pdf")
            with patch(
                "judgment_search.cli.LawGoKrClient.__init__", return_value=None
            ), patch(
                "judgment_search.cli.LawGoKrClient.get_precedent_detail", fake_get_detail
            ), patch(
                "judgment_search.cli.save_detail_as_pdf", side_effect=fake_save_pdf
            ):
                main(["detail", "123", "--pdf", pdf_path])

            self.assertEqual(saved["path"], pdf_path)
            self.assertEqual(saved["detail"]["사건명"], "테스트 사건")


if __name__ == "__main__":
    unittest.main()
