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


if __name__ == "__main__":
    unittest.main()
