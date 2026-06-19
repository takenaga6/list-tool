"""従業員数抽出の拡張テスト（B: 歩留まり改善 2026-06-19）。

本番ログで「従業員数だけ落ち」が約2.4万件＝歩留まり最大のボトルネックだった。
旧 EMPLOYEE_PATTERNS は「名」限定・カンマ非対応・「約」非対応で、
ごく一般的な表記を取りこぼしていた。その回収を検証する。

合わせて「誤った数字を拾わない」ことも確認（設立年・資本金・年商等）。
"""

import unittest

from agents.scraper_agent import extract_employee_count, check_company_fields


class TestEmployeeExtractionRecovered(unittest.TestCase):
    """旧パターンが取りこぼしていた、よくある表記を拾えること。"""

    def test_counter_nin(self):
        """カウンタ「人」: 従業員数 50人 → 50."""
        self.assertEqual(extract_employee_count("従業員数 50人"), "50")

    def test_counter_mei(self):
        """カウンタ「名」: 従業員数 50名 → 50（後方互換）."""
        self.assertEqual(extract_employee_count("従業員数 50名"), "50")

    def test_comma_separated(self):
        """カンマ区切り: 従業員数：1,200名 → 1200."""
        self.assertEqual(extract_employee_count("従業員数：1,200名"), "1200")

    def test_approx_prefix(self):
        """約: 従業員数 約80名 → 80."""
        self.assertEqual(extract_employee_count("従業員数 約80名"), "80")

    def test_shain_nin(self):
        """社員数 120人 → 120."""
        self.assertEqual(extract_employee_count("社員数 120人"), "120")

    def test_jin_in_label(self):
        """ラベル「人員」: 人員 30名 → 30."""
        self.assertEqual(extract_employee_count("人員 30名"), "30")

    def test_staff_suffix(self):
        """50名のスタッフ → 50（パターン2）."""
        self.assertEqual(extract_employee_count("50名のスタッフが在籍"), "50")

    def test_paren_separator(self):
        """従業員数（2024年現在）85名 → 85."""
        self.assertEqual(extract_employee_count("従業員数（2024年現在）85名"), "85")

    def test_fullwidth_digits(self):
        """全角数字: 従業員数 ５０名 → 50."""
        self.assertEqual(extract_employee_count("従業員数 ５０名"), "50")

    def test_total_label(self):
        """総勢 45名 → 45."""
        self.assertEqual(extract_employee_count("総勢 45名"), "45")


class TestEmployeeExtractionNoFalsePositive(unittest.TestCase):
    """誤った数字を拾わないこと（実データ検証の代替・回帰防止）。"""

    def test_founding_year_not_matched(self):
        """設立2024年 → 空（カウンタ無し）."""
        self.assertEqual(extract_employee_count("設立2024年 創業50年"), "")

    def test_capital_not_matched(self):
        """資本金5,000万円 → 空（名/人カウンタ無し）."""
        self.assertEqual(extract_employee_count("資本金5,000万円"), "")

    def test_revenue_not_matched(self):
        """年商50億円 → 空."""
        self.assertEqual(extract_employee_count("年商50億円"), "")

    def test_over_cap_returns_empty(self):
        """上限超(>10000): 従業員数 50,000名 → 空（巨大企業は拾わない）."""
        self.assertEqual(extract_employee_count("従業員数 50,000名"), "")

    def test_unrelated_mei_not_matched(self):
        """「ご予約は50名様まで」のような無関係文 → 空."""
        # ラベル(従業員/社員/…)が無いので拾わない
        self.assertEqual(extract_employee_count("ご予約は50名様まで承ります"), "")


class TestCheckCompanyFieldsRecovered(unittest.TestCase):
    """従業員数を「人」表記で拾えると check_company_fields を通過すること。"""

    def test_passes_with_nin_counter(self):
        text = (
            "株式会社テストの会社概要をご案内します。"
            "私たちは事業内容としてソフトウェア開発と受託システム開発を行っています。"
            "経営理念は社員の成長を第一に考えることです。"
            "従業員数 50人。お問い合わせは TEL 03-1234-5678 まで。"
        )
        is_company, missing = check_company_fields(text)
        self.assertTrue(is_company, f"従業員数(人)で通過しなかった: {missing}")
        self.assertNotIn("従業員数", missing)


if __name__ == "__main__":
    unittest.main()
