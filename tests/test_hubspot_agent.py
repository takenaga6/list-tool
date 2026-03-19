import unittest
from unittest.mock import patch, MagicMock

from agents.hubspot_agent import HubSpotAgent


class TestHubSpotAgent(unittest.TestCase):
    def setUp(self):
        # ダミートークン / NGリストファイルはテスト用で実際には書き込まれない
        self.agent = HubSpotAgent(token="test-token", ng_list_file="output/ng_list_test.csv")

    def test_normalize_phone_common_patterns(self):
        cases = {
            "03-1234-5678": "+81312345678",
            "090-1234-5678": "+819012345678",
            "+81-90-1234-5678": "+819012345678",
            "03-1234-5678 内線123": "+81312345678 ext 123",
            "03-1234-5678 ext 123": "+81312345678 ext 123",
            "004-0821": "",  # 郵便番号なので電話としては送らない
            "061-1405": "",  # 郵便番号として除外
            "066-0012": "",  # 郵便番号として除外
        }

        for inp, expected in cases.items():
            with self.subTest(inp=inp):
                self.assertEqual(self.agent._normalize_phone(inp), expected)

    @patch("agents.hubspot_agent.requests.post")
    def test_register_company_retries_without_phone_on_invalid_phone(self, mock_post):
        # 1回目: HubSpotがINVALID_PHONE_NUMBERで400を返す
        failed_response = MagicMock()
        failed_response.ok = False
        failed_response.status_code = 400
        # HubSpotが INVALID_PHONE_NUMBER を返した場合の応答例
        failed_response.text = '{"status":"error","message":"Property values were not valid","errors":[{"error":"INVALID_PHONE_NUMBER"}]}'

        # 2回目: 正常応答
        success_response = MagicMock()
        success_response.ok = True
        success_response.json.return_value = {"id": "12345"}

        mock_post.side_effect = [failed_response, success_response]

        company_data = {
            "company_name": "テスト株式会社",
            "company_url": "https://example.com",
            "phone": "03-1234-5678",
        }

        result = self.agent.register_company(company_data)
        self.assertTrue(result)
        self.assertEqual(mock_post.call_count, 2, "電話番号エラーで再送が行われること")

    @patch("agents.hubspot_agent.requests.post")
    def test_register_company_fails_if_always_invalid_phone(self, mock_post):
        # 常にINVALID_PHONE_NUMBERを返す
        failed_response = MagicMock()
        failed_response.ok = False
        failed_response.status_code = 400
        failed_response.text = '{"status":"error","message":"Property values were not valid","errors":[{"error":"INVALID_PHONE_NUMBER"}]}'
        mock_post.return_value = failed_response

        company_data = {
            "company_name": "テスト株式会社",
            "company_url": "https://example.com",
            "phone": "03-1234-5678",
        }

        result = self.agent.register_company(company_data)
        self.assertFalse(result)
        self.assertEqual(mock_post.call_count, 2, "再送後も失敗なら2回呼ばれる")


if __name__ == "__main__":
    unittest.main()
