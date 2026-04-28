"""Phase 1 本命条件チェックの単体テスト（57社分析からの追加判定）。"""

import unittest

from agents.rank_agent import (
    check_phase1_must_conditions,
    evaluate_rank,
    is_parent_prime_subsidiary,
    is_special_industry,
    pre_screen,
)


# 健康経営・採用・福利厚生をすべて満たす標準的なHP本文
_STD_PAGE_TEXT = (
    "私たちは健康経営を推進しています。健康経営優良法人2024に認定。"
    "従業員の健康を大切にし、ストレスチェック・産業医面談を実施。"
    "採用情報はこちら。新卒採用・中途採用ともに募集中。"
    "福利厚生として人間ドック、マッサージ、社員旅行、リフレッシュ休暇を提供。"
)


class TestSpecialIndustry(unittest.TestCase):
    def test_law_firm_is_special(self):
        self.assertTrue(is_special_industry("○○法律事務所 弁護士法人"))

    def test_vc_is_special(self):
        self.assertTrue(is_special_industry("ベンチャーキャピタル ファンド運営"))

    def test_normal_company_is_not_special(self):
        self.assertFalse(is_special_industry("製造業 機械部品メーカー"))


class TestParentPrimeSubsidiary(unittest.TestCase):
    def test_itochu_subsidiary_detected(self):
        self.assertTrue(is_parent_prime_subsidiary(
            "当社は伊藤忠商事の連結子会社として..."
        ))

    def test_explicit_prime_phrase_detected(self):
        self.assertTrue(is_parent_prime_subsidiary(
            "東証プライム上場の親会社のもとで事業を展開"
        ))

    def test_unrelated_company_not_detected(self):
        self.assertFalse(is_parent_prime_subsidiary(
            "創業1948年、独立系の中堅企業として..."
        ))


class TestPhase1MustConditions(unittest.TestCase):
    # テスト1: 既知の継続社「マブチエスアンドティー」想定
    # 業歴76年・商社・従業員70名・健康経営記載あり・採用情報あり
    def test_continued_smb_passes(self):
        company_info = {
            "company_name": "マブチエスアンドティー株式会社",
            "industry": "商社",
            "employee_count": "70",
        }
        ok, reason = check_phase1_must_conditions(company_info, _STD_PAGE_TEXT)
        self.assertTrue(ok, f"継続想定社がNGになった: {reason}")
        self.assertEqual(reason, "OK")

    # テスト2: 既知の非継続社「博報堂」想定 — 広告代理店NG
    def test_advertising_agency_ng(self):
        company_info = {
            "company_name": "株式会社博報堂",
            "industry": "広告代理店",
            "employee_count": "100",
        }
        ok, reason = check_phase1_must_conditions(company_info, _STD_PAGE_TEXT)
        self.assertFalse(ok)
        self.assertIn("NG業種(広告/メディア)", reason)

    # テスト3: 受託SI業者・従業員250名 — 業界利益率中NG（200-499名空白帯にも該当）
    def test_si_medium_size_ng(self):
        company_info = {
            "company_name": "株式会社サンプルシステムズ",
            "industry": "受託開発",
            "employee_count": "250",
        }
        ok, reason = check_phase1_must_conditions(company_info, _STD_PAGE_TEXT)
        self.assertFalse(ok)
        # レッドオーシャン業界 OR 空白帯規模 のどちらかで弾かれる
        self.assertTrue(
            "レッドオーシャン業界" in reason or "空白帯規模" in reason,
            f"想定外のNG理由: {reason}",
        )

    # 大手プライム子会社例外: 伊藤忠系の総合商社は救済される
    def test_prime_subsidiary_redocean_exception(self):
        company_info = {
            "company_name": "伊藤忠○○株式会社",
            "industry": "総合商社",
            "employee_count": "100",
        }
        page_text = _STD_PAGE_TEXT + " 当社は伊藤忠商事の連結子会社です。"
        ok, reason = check_phase1_must_conditions(company_info, page_text)
        self.assertTrue(ok, f"プライム子会社例外が効いていない: {reason}")

    # 健康経営記載なしNG
    def test_no_kenkokeiei_ng(self):
        company_info = {"company_name": "株式会社サンプル", "employee_count": "50"}
        page_text = "採用情報。福利厚生にマッサージ・人間ドック完備。"  # 健康経営記載なし
        ok, reason = check_phase1_must_conditions(company_info, page_text)
        self.assertFalse(ok)
        self.assertEqual(reason, "HP健康経営記載なし")

    # 採用ページなしNG
    def test_no_recruit_ng(self):
        company_info = {"company_name": "株式会社サンプル", "employee_count": "50"}
        page_text = "健康経営に注力。福利厚生にマッサージ・人間ドック。"  # 採用記載なし
        ok, reason = check_phase1_must_conditions(company_info, page_text)
        self.assertFalse(ok)
        self.assertEqual(reason, "HP採用情報なし")

    # 福利厚生なし・士業以外NG
    def test_no_welfare_non_special_ng(self):
        company_info = {
            "company_name": "株式会社サンプル",
            "industry": "製造業",
            "employee_count": "50",
        }
        page_text = "健康経営に注力。新卒採用・中途採用を実施中。"  # 福利厚生キーワードなし
        ok, reason = check_phase1_must_conditions(company_info, page_text)
        self.assertFalse(ok)
        self.assertEqual(reason, "福利厚生記載なし(士業以外)")

    # 士業は福利厚生記載なくてもOK
    def test_law_firm_no_welfare_ok(self):
        company_info = {
            "company_name": "○○法律事務所",
            "industry": "弁護士法人",
            "employee_count": "20",
        }
        page_text = "健康経営優良法人。新卒採用・中途採用を実施。"  # 福利厚生なし
        ok, reason = check_phase1_must_conditions(company_info, page_text)
        self.assertTrue(ok, f"士業の福利厚生例外が効いていない: {reason}")

    # 200-499名 空白帯NG
    def test_blank_zone_ng(self):
        company_info = {"company_name": "株式会社サンプル", "employee_count": "250"}
        ok, reason = check_phase1_must_conditions(company_info, _STD_PAGE_TEXT)
        self.assertFalse(ok)
        self.assertIn("空白帯規模", reason)

    # 6-9名 士業以外NG
    def test_micro_non_special_ng(self):
        company_info = {
            "company_name": "株式会社サンプル",
            "industry": "製造業",
            "employee_count": "8",
        }
        ok, reason = check_phase1_must_conditions(company_info, _STD_PAGE_TEXT)
        self.assertFalse(ok)
        self.assertIn("極小規模(8名)", reason)

    # 6-9名 士業はOK
    def test_micro_special_industry_ok(self):
        company_info = {
            "company_name": "○○税理士法人",
            "industry": "税理士事務所",
            "employee_count": "8",
        }
        ok, reason = check_phase1_must_conditions(company_info, _STD_PAGE_TEXT)
        self.assertTrue(ok, f"士業の極小規模例外が効いていない: {reason}")

    # 500名以上は大手プライム子会社のみOK
    def test_large_non_prime_ng(self):
        company_info = {
            "company_name": "株式会社サンプル",
            "industry": "製造業",
            "employee_count": "600",
        }
        ok, reason = check_phase1_must_conditions(company_info, _STD_PAGE_TEXT)
        self.assertFalse(ok)
        self.assertIn("大規模(600名)", reason)


class TestPreScreenPhase1(unittest.TestCase):
    """pre_screen のスニペット段階で広告/メディア業種・規模で弾けるか。"""

    def test_pre_screen_rejects_advertising(self):
        result, reason = pre_screen({
            "url": "https://example.co.jp/",
            "title": "株式会社サンプル広告代理店",
            "snippet": "総合広告サービスを提供",
        })
        self.assertFalse(result)
        self.assertIn("NG業種(広告/メディア)", reason)

    def test_pre_screen_rejects_blank_zone_employees(self):
        result, reason = pre_screen({
            "url": "https://example.co.jp/",
            "title": "株式会社サンプル",
            "snippet": "従業員数 350名の中堅企業",
        })
        self.assertFalse(result)
        # 既存の200名超チェック or Phase 1 空白帯のどちらかで弾かれる
        self.assertTrue(
            "200名超" in reason or "空白帯規模" in reason,
            f"想定外のNG理由: {reason}",
        )


class TestEvaluateRankIntegration(unittest.TestCase):
    """evaluate_rank() に必須条件チェックが組み込まれているか。"""

    def test_advertising_company_returns_ng(self):
        company_info = {
            "company_name": "株式会社サンプル広告",
            "industry": "広告代理店",
            "employee_count": "50",
        }
        result = evaluate_rank(
            company_info,
            [{"url": "", "title": "", "snippet": "", "search_query": ""}],
            page_text=_STD_PAGE_TEXT,
        )
        self.assertEqual(result["rank"], "NG")
        self.assertIn("Phase1必須条件NG", result["ng_reason"])


if __name__ == "__main__":
    unittest.main()
