import unittest
from unittest.mock import MagicMock

from agents import scraper_agent
from agents.scraper_agent import extract_company_name_from_media_page


class TestExtractCompanyNameFromMediaPage(unittest.TestCase):
    """extract_company_name_from_media_page が _clean_company_name を経由することを確認"""

    def _make_soup_with_h1(self, text: str):
        from bs4 import BeautifulSoup
        html = f"<html><body><h1>{text}</h1></body></html>"
        return BeautifulSoup(html, "html.parser")

    def test_valid_name_returned(self):
        """正常な会社名はそのまま返す"""
        soup = self._make_soup_with_h1("株式会社テスト")
        result = extract_company_name_from_media_page(soup, "株式会社テスト")
        assert result == "株式会社テスト"

    def test_pattern1_real_case_filtered(self):
        """5/9走行で発覚したパターン1: 「、」含む長文はバリデーションで除外される"""
        text = "株式会社東豊精工は、1957年（昭和32年）コウノトリ舞う豊かな自然"
        soup = self._make_soup_with_h1(text)
        result = extract_company_name_from_media_page(soup, text)
        assert result == ""

    def test_fullwidth_comma_filtered(self):
        """全角カンマ「，」含む文字列も除外される"""
        text = "株式会社テスト，詳しくはこちら"
        soup = self._make_soup_with_h1(text)
        result = extract_company_name_from_media_page(soup, text)
        assert result == ""

    def test_text_fallback_also_filtered(self):
        """h1/h2にマッチなし・テキストフォールバックでも _clean_company_name が効く"""
        text = "株式会社東豊精工は、1957年（昭和32年）コウノトリ舞う豊かな自然"
        soup = MagicMock()
        soup.find_all.return_value = []
        result = extract_company_name_from_media_page(soup, text)
        assert result == ""


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
