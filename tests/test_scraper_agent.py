import unittest

from agents import scraper_agent


class TestScraperAgent(unittest.TestCase):
    def test_check_company_fields_requires_employee_count(self):
        # 社名/住所/電話/代表者などが揃っていても従業員数が含まれていない場合は除外
        text = (
            "株式会社テスト 代表取締役: 田中太郎 事業内容: 健康サポート "
            "〒123-4567 東京都新宿区新宿1-1-1 TEL: 03-1234-5678 "
            + "あいうえお" * 20
        )
        is_company, missing = scraper_agent.check_company_fields(text)
        self.assertFalse(is_company)
        self.assertIn("従業員数", missing)

    def test_check_company_fields_excludes_listed_ir_pages(self):
        text = (
            "株式会社テスト 代表取締役: 田中太郎 事業内容: 健康サポート "
            "東証グロース市場上場 / 投資家情報(IR)をご覧ください "
            "〒123-4567 東京都新宿区新宿1-1-1 TEL: 03-1234-5678 "
            "従業員数: 50名 "
            + "あいうえお" * 20
        )
        is_company, missing = scraper_agent.check_company_fields(text)
        self.assertFalse(is_company)
        self.assertIn("上場/IR情報あり", missing)

    def test_check_company_fields_all_good(self):
        text = (
            "株式会社テスト 代表取締役: 田中太郎 事業内容: 健康サポート "
            "〒123-4567 東京都新宿区新宿1-1-1 TEL: 03-1234-5678 "
            "従業員数: 50名 "
            + "あいうえお" * 20
        )
        is_company, missing = scraper_agent.check_company_fields(text)
        self.assertTrue(is_company)
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
