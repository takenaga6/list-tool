"""従業員数抽出パーサー拡張の単体テスト（2026-06-26）。

背景: ファネル実測で全候補の約8割が check_company_fields の「従業員数未取得」で
脱落しており、その多くは「名」以外の書き方（人/単位なし/連結括弧/総数/約/範囲/英語）を
旧パーサーが読めない偽陰性だった。extract_employee_count を拡張して取りこぼしを救う。

サイズ帯ロジック（EMPLOYEE_RANGE_CONFIG）は一切変更していない。
"""

import unittest

from agents.scraper_agent import extract_employee_count


class TestEmployeeExtractionPositive(unittest.TestCase):
    """様々な書き方から人数を取得できること。"""

    def test_basic_mei(self):
        for text, expected in [
            ("従業員数：50名", "50"),
            ("従業員数 50名", "50"),
            ("従業員 50名", "50"),
            ("社員数 100名", "100"),
            ("スタッフ30名", "30"),
            ("30名のスタッフ", "30"),
        ]:
            with self.subTest(text=text):
                self.assertEqual(extract_employee_count(text), expected)

    def test_nin_unit(self):
        """「人」単位（名以外）も取得する。"""
        for text, expected in [
            ("従業員数：50人", "50"),
            ("従業員 50人", "50"),
            ("従業員数:1,234人", "1234"),
        ]:
            with self.subTest(text=text):
                self.assertEqual(extract_employee_count(text), expected)

    def test_parenthetical_renketsu(self):
        """（連結）（単体）など括弧が挟まっても取得する。"""
        self.assertEqual(extract_employee_count("従業員数（連結）500名"), "500")
        self.assertEqual(extract_employee_count("従業員数（単体）120名"), "120")

    def test_sou_and_zaiseki(self):
        """総数・在籍・人員などの言い回し。"""
        self.assertEqual(extract_employee_count("従業員総数 300名"), "300")
        self.assertEqual(extract_employee_count("在籍人数 30名"), "30")
        self.assertEqual(extract_employee_count("人員 40名"), "40")
        self.assertEqual(extract_employee_count("正社員数：80名"), "80")

    def test_approx_and_range(self):
        """約・範囲（下限採用）。"""
        self.assertEqual(extract_employee_count("従業員数 約50名"), "50")
        self.assertEqual(extract_employee_count("従業員数 50〜60名"), "50")

    def test_no_unit_with_countword(self):
        """カウント語(数/総数)があれば単位なしでも取得する。"""
        self.assertEqual(extract_employee_count("従業員数 50"), "50")

    def test_fullwidth_and_comma(self):
        """全角数字・カンマを正規化する。"""
        self.assertEqual(extract_employee_count("従業員数　５０名"), "50")
        self.assertEqual(extract_employee_count("従業員数：１２０名"), "120")
        self.assertEqual(extract_employee_count("従業員数：1,200名"), "1200")

    def test_english(self):
        self.assertEqual(extract_employee_count("Employees: 50"), "50")
        self.assertEqual(extract_employee_count("Number of employees: 120"), "120")


class TestEmployeeExtractionFalsePositiveGuard(unittest.TestCase):
    """人数でない数字を誤って拾わないこと（空を返す）。"""

    def test_not_employee_numbers(self):
        for text in [
            "従業員満足度 95%",
            "資本金 5,000万円",
            "設立 1998年",
            "従業員の約8割が女性",
            "売上高 50億円",
            "従業員数 1000万円",
            "本社 50階",
            "電話 03-1234-5678",
            "年商 50億",
        ]:
            with self.subTest(text=text):
                self.assertEqual(extract_employee_count(text), "")

    def test_out_of_range(self):
        """1〜10000 の範囲外は採用しない。"""
        self.assertEqual(extract_employee_count("従業員数 0名"), "")
        self.assertEqual(extract_employee_count("従業員数 99999名"), "")

    def test_no_employee_info(self):
        self.assertEqual(extract_employee_count("当社はサービス企業です。"), "")


if __name__ == "__main__":
    unittest.main()
