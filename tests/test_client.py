import unittest
from unittest.mock import MagicMock, patch

from judgment_search.client import LawGoKrClient, LawGoKrError


def _mock_response(json_data, status_ok=True):
    resp = MagicMock()
    resp.json.return_value = json_data
    if status_ok:
        resp.raise_for_status.return_value = None
    return resp


class LawGoKrClientTest(unittest.TestCase):
    def test_requires_oc(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(LawGoKrError):
                LawGoKrClient()

    def test_search_normalizes_single_dict_result_to_list(self):
        client = LawGoKrClient(oc="test")
        payload = {
            "PrecSearch": {
                "totalCnt": "1",
                "page": "1",
                "prec": {"판례일련번호": "123", "사건명": "테스트 사건"},
            }
        }
        with patch("judgment_search.client.requests.get", return_value=_mock_response(payload)):
            result = client.search_precedents("테스트")

        self.assertEqual(result["total_count"], 1)
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["판례일련번호"], "123")

    def test_search_keeps_multiple_results_as_list(self):
        client = LawGoKrClient(oc="test")
        payload = {
            "PrecSearch": {
                "totalCnt": "2",
                "page": "1",
                "prec": [
                    {"판례일련번호": "1"},
                    {"판례일련번호": "2"},
                ],
            }
        }
        with patch("judgment_search.client.requests.get", return_value=_mock_response(payload)):
            result = client.search_precedents("테스트")

        self.assertEqual(len(result["items"]), 2)

    def test_search_with_no_results(self):
        client = LawGoKrClient(oc="test")
        payload = {"PrecSearch": {"totalCnt": "0", "page": "1"}}
        with patch("judgment_search.client.requests.get", return_value=_mock_response(payload)):
            result = client.search_precedents("존재하지않는검색어")

        self.assertEqual(result["total_count"], 0)
        self.assertEqual(result["items"], [])

    def test_invalid_json_raises_law_go_kr_error(self):
        client = LawGoKrClient(oc="test")
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.side_effect = ValueError("no json")
        resp.text = "<html>error</html>"
        with patch("judgment_search.client.requests.get", return_value=resp):
            with self.assertRaises(LawGoKrError):
                client.search_precedents("테스트")

    def test_get_precedent_detail(self):
        client = LawGoKrClient(oc="test")
        payload = {"PrecService": {"사건명": "테스트 사건", "판례내용": "본문..."}}
        with patch("judgment_search.client.requests.get", return_value=_mock_response(payload)):
            detail = client.get_precedent_detail("123")

        self.assertEqual(detail["사건명"], "테스트 사건")


if __name__ == "__main__":
    unittest.main()
