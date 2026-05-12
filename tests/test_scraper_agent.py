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


class TestCheckCompanyFieldsPhase0aC1(unittest.TestCase):
    """Phase 0a C1: 代表者・住所を必須から外し、TEL をハード必須に昇格"""

    _PADDING = "あいうえお" * 20  # 日本語判定用（50文字以上）

    def _text(self, employee=True, tel="TEL: 03-1234-5678", legal=True, business=True,
              rep=False, addr=False):
        parts = []
        if employee:
            parts.append("従業員数 50名")
        if tel:
            parts.append(tel)
        if legal:
            parts.append("株式会社テスト")
        if business:
            parts.append("事業内容: 健康サポート")
        if rep:
            parts.append("代表取締役: 田中太郎")
        if addr:
            parts.append("〒123-4567 東京都新宿区新宿1-1-1")
        parts.append(self._PADDING)
        return " ".join(parts)

    # ── TEL キーワード拡張テスト ──────────────────────────────────

    def test_tel_denwa_only_keyword_hits(self):
        """「電話」単体キーワード → TEL ハードチェックでヒット"""
        text = self._text(tel="電話 03-1234-5678")
        is_company, missing = scraper_agent.check_company_fields(text)
        self.assertNotIn("TEL", missing)
        self.assertTrue(is_company)

    def test_tel_lowercase_dot_hits(self):
        """「tel.」小文字 → TEL ハードチェックでヒット"""
        text = self._text(tel="tel. 03-1234-5678")
        is_company, missing = scraper_agent.check_company_fields(text)
        self.assertNotIn("TEL", missing)
        self.assertTrue(is_company)

    def test_tel_number_format_only_hits(self):
        """番号フォーマット「03-1234-5678」だけでも → TEL ハードチェックでヒット"""
        text = self._text(tel="03-1234-5678")
        is_company, missing = scraper_agent.check_company_fields(text)
        self.assertNotIn("TEL", missing)
        self.assertTrue(is_company)

    # ── 緩和後の通過条件テスト ─────────────────────────────────────

    def test_passes_with_legal_only_no_business(self):
        """TEL + 法人格のみ（事業内容なし） → 通過"""
        is_company, missing = scraper_agent.check_company_fields(self._text(business=False))
        self.assertTrue(is_company)
        self.assertIn("事業内容", missing)

    def test_passes_with_business_only_no_legal(self):
        """TEL + 事業内容のみ（法人格なし） → 通過"""
        is_company, missing = scraper_agent.check_company_fields(self._text(legal=False))
        self.assertTrue(is_company)
        self.assertIn("法人格", missing)

    def test_fails_without_tel(self):
        """TEL なし → スキップ（ハード必須）"""
        is_company, missing = scraper_agent.check_company_fields(self._text(tel=None))
        self.assertFalse(is_company)
        self.assertIn("TEL", missing)

    def test_passes_without_representative_and_address(self):
        """代表者・住所なし、TEL+法人格+事業内容のみ → 通過"""
        is_company, missing = scraper_agent.check_company_fields(
            self._text(rep=False, addr=False)
        )
        self.assertTrue(is_company)
        self.assertEqual(missing, [])

    def test_fails_without_legal_and_business(self):
        """TEL のみ（法人格なし・事業内容なし） → スキップ"""
        is_company, missing = scraper_agent.check_company_fields(
            self._text(legal=False, business=False)
        )
        self.assertFalse(is_company)
        self.assertIn("法人格", missing)
        self.assertIn("事業内容", missing)


class TestHasMinFieldsSpec(unittest.TestCase):
    """
    main.py の has_min_fields ロジックの仕様テスト（Phase 0a C1 変更後）。
    住所は不問。電話番号のみで判定。
    has_min_fields は main.py 内のインラインコードのため、同一ロジックを再現して検証する。
    """

    @staticmethod
    def _has_min_fields(info: dict) -> bool:
        # main.py:652 の has_min_fields と同一ロジック（Phase 0a C1 変更後）
        return bool(info.get("company_name")) and bool(info.get("phone"))

    def test_name_and_phone_passes(self):
        """会社名 + 電話番号 → 通過"""
        self.assertTrue(self._has_min_fields(
            {"company_name": "株式会社A", "phone": "03-1234-5678"}
        ))

    def test_name_and_address_only_fails(self):
        """会社名 + 住所のみ（電話番号なし）→ スキップ（Phase 0a C1 仕様変更）"""
        self.assertFalse(self._has_min_fields(
            {"company_name": "株式会社A", "address": "東京都新宿区"}
        ))

    def test_name_only_fails(self):
        """会社名のみ → スキップ"""
        self.assertFalse(self._has_min_fields({"company_name": "株式会社A"}))


if __name__ == "__main__":
    unittest.main()
