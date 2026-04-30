"""Phase 2 リスト条件全面見直しの単体テスト（49社分析からの加点・減点判定）。

TDD: このテストを最初に書く → 関数未実装で全失敗 →
rank_agent.py に評価関数を追加して全PASSにする。

参照: Phase2_実装計画.md
"""

import unittest

from agents.rank_agent import (
    # ===== Phase 2で新規追加する関数（まだ存在しない・失敗する）=====
    classify_industry_profit,
    classify_industry_turnover,
    classify_industry_category,
    classify_location,
    count_recruit_media,
    is_founder_owner,
    is_parent_prime_subsidiary_v2,
    evaluate_useful_conditions,
    evaluate_negative_conditions,
    evaluate_rank_v2,
)


# ============================================================
# A. マッピング判定テスト（10件）
# ============================================================


class TestClassifyIndustryProfit(unittest.TestCase):
    """業界利益率マッピング判定."""

    def test_finance_is_high(self):
        """金融は利益率「高」."""
        self.assertEqual(classify_industry_profit("金融サービス"), "high")

    def test_law_is_high(self):
        """弁護士は利益率「高」."""
        self.assertEqual(classify_industry_profit("弁護士法人"), "high")

    def test_trading_is_medium_high(self):
        """商社/卸売は利益率「中-高」."""
        self.assertEqual(classify_industry_profit("総合卸売業"), "medium-high")

    def test_si_is_medium(self):
        """受託SIは利益率「中」(レッドオーシャン)."""
        self.assertEqual(classify_industry_profit("受託開発SI業"), "medium")

    def test_logistics_is_low(self):
        """運送・物流は利益率「低」."""
        self.assertEqual(classify_industry_profit("運送業"), "low")

    def test_unknown_returns_unknown(self):
        """マッピングにない業種は不明."""
        self.assertEqual(classify_industry_profit("その他特殊業界"), "unknown")


class TestClassifyIndustryTurnover(unittest.TestCase):
    """業界離職率マッピング判定."""

    def test_finance_is_low(self):
        """金融は離職率「低」."""
        self.assertEqual(classify_industry_turnover("証券会社"), "low")

    def test_manufacturing_is_medium(self):
        """製造業は離職率「中」."""
        self.assertEqual(classify_industry_turnover("自動車部品メーカー"), "medium")

    def test_logistics_is_medium(self):
        """物流は離職率「中」."""
        self.assertEqual(classify_industry_turnover("物流センター"), "medium")


class TestClassifyIndustryCategory(unittest.TestCase):
    """業種カテゴリ判定."""

    def test_trading(self):
        """商社/卸売判定."""
        self.assertEqual(classify_industry_category("総合商社"), "商社/卸売")

    def test_finance(self):
        """金融判定."""
        self.assertEqual(classify_industry_category("証券会社"), "金融")

    def test_education_software(self):
        """教育ソフト判定."""
        self.assertEqual(classify_industry_category("eラーニングシステム提供"), "教育ソフト")

    def test_law(self):
        """士業判定."""
        self.assertEqual(classify_industry_category("税理士法人サンプル"), "士業")

    def test_manufacturing(self):
        """製造業判定."""
        self.assertEqual(classify_industry_category("精密機械工業"), "製造業")

    def test_it_telecom(self):
        """IT/通信判定."""
        self.assertEqual(classify_industry_category("通信ソリューション"), "IT/通信")

    def test_consulting(self):
        """コンサル・サービス判定."""
        self.assertEqual(classify_industry_category("経営コンサルティング"), "コンサル・サービス")

    def test_unknown(self):
        """マッピング外は None."""
        self.assertIsNone(classify_industry_category("特殊技術サービス"))


class TestClassifyLocation(unittest.TestCase):
    """住所による立地判定."""

    def test_chiyoda_is_prime(self):
        """千代田区は都心一等地."""
        self.assertEqual(classify_location("東京都千代田区丸の内1-1-1"), "prime")

    def test_minato_is_prime(self):
        """港区は都心一等地."""
        self.assertEqual(classify_location("東京都港区六本木3-2-1"), "prime")

    def test_umeda_is_prime(self):
        """大阪梅田は都心一等地."""
        self.assertEqual(classify_location("大阪府大阪市北区梅田1-1-1"), "prime")

    def test_iwate_is_local(self):
        """岩手県は地方."""
        self.assertEqual(classify_location("岩手県盛岡市盛岡駅前1-1"), "local")

    def test_unknown_address_is_neither(self):
        """都心でも地方でもない場合は neither."""
        self.assertEqual(classify_location("東京都品川区西品川1-1"), "neither")

    def test_empty_address(self):
        """住所空の場合は unknown."""
        self.assertEqual(classify_location(""), "unknown")


class TestCountRecruitMedia(unittest.TestCase):
    """HP本文から採用媒体数を判定."""

    def test_three_media(self):
        """リクナビ・マイナビ・doda 3つ → 3."""
        text = "弊社は現在、リクナビ・マイナビ・dodaにて募集しています。"
        self.assertEqual(count_recruit_media(text), 3)

    def test_one_media(self):
        """リクナビのみ → 1."""
        text = "リクナビで募集中です。"
        self.assertEqual(count_recruit_media(text), 1)

    def test_zero_media(self):
        """媒体記載なし → 0."""
        text = "弊社は健康経営に注力しています。"
        self.assertEqual(count_recruit_media(text), 0)

    def test_engage_and_indeed(self):
        """engage と Indeed 2媒体 → 2."""
        text = "engageとIndeedで採用活動中。"
        self.assertEqual(count_recruit_media(text), 2)


class TestIsFounderOwner(unittest.TestCase):
    """創業家オーナー判定."""

    def test_founder_family(self):
        """創業家キーワードあり → True."""
        text = "弊社は創業家が筆頭株主の同族経営です。"
        self.assertTrue(is_founder_owner(text))

    def test_no_founder(self):
        """キーワードなし → False."""
        text = "創業1948年。独立系の中堅企業として歩んできました。"
        self.assertFalse(is_founder_owner(text))


class TestIsParentPrimeSubsidiaryV2(unittest.TestCase):
    """大手プライム子会社判定（v2）."""

    def test_itochu_subsidiary(self):
        """伊藤忠商事の連結子会社."""
        self.assertTrue(is_parent_prime_subsidiary_v2(
            "当社は伊藤忠商事の連結子会社です。"
        ))

    def test_explicit_prime(self):
        """東証プライム上場の親会社."""
        self.assertTrue(is_parent_prime_subsidiary_v2(
            "東証プライム上場の親会社のもとで事業を展開"
        ))

    def test_independent_company(self):
        """独立系企業 → False."""
        self.assertFalse(is_parent_prime_subsidiary_v2(
            "独立系の中堅企業として運営"
        ))


# ============================================================
# B. 加点ロジックテスト（10件）
# ============================================================


_STD_PAGE_TEXT = (
    "私たちは健康経営を推進しています。健康経営優良法人2024に認定。"
    "従業員の健康を大切にし、ストレスチェック・産業医面談を実施。"
    "採用情報はこちら。新卒採用・中途採用ともに募集中。"
    "福利厚生として人間ドック、マッサージ、社員旅行、リフレッシュ休暇を提供。"
)


class TestEvaluateUsefulConditions(unittest.TestCase):
    """加点条件の評価."""

    def test_trading_company_plus_2(self):
        """商社/卸売 → +2点."""
        company_info = {
            "company_name": "サンプル商事株式会社",
            "industry": "総合卸売",
            "address": "東京都中央区",
        }
        score, reasons = evaluate_useful_conditions(company_info, _STD_PAGE_TEXT)
        # +2(商社/卸売) +2(利益率中-高) +1(都心一等地) +1(健康経営認定推定) +1(法定外福利) +1(採用媒体記載なしだが本文に「採用」あり)
        self.assertGreaterEqual(score, 2)
        self.assertTrue(any("商社" in r or "卸売" in r for r in reasons))

    def test_finance_plus_2(self):
        """金融 → +2点."""
        company_info = {
            "company_name": "サンプル証券",
            "industry": "証券業",
            "address": "東京都中央区日本橋",
        }
        score, reasons = evaluate_useful_conditions(company_info, _STD_PAGE_TEXT)
        self.assertGreaterEqual(score, 2)
        self.assertTrue(any("金融" in r for r in reasons))

    def test_three_recruit_media_plus_2(self):
        """採用媒体3つ → +2点."""
        company_info = {
            "company_name": "テスト株式会社",
            "industry": "サービス業",
            "address": "東京都新宿区",
        }
        text = _STD_PAGE_TEXT + " 当社はリクナビ・マイナビ・dodaで採用中です。"
        score, reasons = evaluate_useful_conditions(company_info, text)
        self.assertTrue(any("採用媒体3" in r or "採用媒体3つ" in r for r in reasons))

    def test_one_recruit_media_plus_1(self):
        """採用媒体1つ → +1点."""
        company_info = {
            "company_name": "テスト株式会社",
            "industry": "サービス業",
            "address": "東京都新宿区",
        }
        text = _STD_PAGE_TEXT + " 当社はリクナビで募集中。"
        score, reasons = evaluate_useful_conditions(company_info, text)
        self.assertTrue(any("採用媒体1" in r for r in reasons))

    def test_prime_location_plus_1(self):
        """都心一等地 → +1点."""
        company_info = {
            "company_name": "テスト株式会社",
            "industry": "サービス業",
            "address": "東京都港区六本木1-1-1",
        }
        score, reasons = evaluate_useful_conditions(company_info, _STD_PAGE_TEXT)
        self.assertTrue(any("都心" in r or "立地" in r for r in reasons))

    def test_high_profit_plus_2(self):
        """業界利益率「高」 → +2点."""
        company_info = {
            "company_name": "サンプル銀行",
            "industry": "銀行業",
            "address": "東京都中央区",
        }
        score, reasons = evaluate_useful_conditions(company_info, _STD_PAGE_TEXT)
        self.assertTrue(any("利益率" in r and "高" in r for r in reasons))


# ============================================================
# C. 減点ロジックテスト（5件）
# ============================================================


class TestEvaluateNegativeConditions(unittest.TestCase):
    """減点条件の評価."""

    def test_manufacturing_minus_2(self):
        """製造業 → -2点."""
        company_info = {
            "company_name": "サンプル製作所",
            "industry": "金属加工メーカー",
            "address": "東京都大田区",
        }
        score, reasons = evaluate_negative_conditions(company_info, _STD_PAGE_TEXT)
        self.assertLessEqual(score, -2)
        self.assertTrue(any("製造業" in r for r in reasons))

    def test_it_telecom_minus_2(self):
        """IT/通信 → -2点."""
        company_info = {
            "company_name": "テスト通信",
            "industry": "情報通信業",
            "address": "東京都新宿区",
        }
        score, reasons = evaluate_negative_conditions(company_info, _STD_PAGE_TEXT)
        self.assertTrue(any("IT" in r or "通信" in r for r in reasons))

    def test_consulting_minus_2(self):
        """コンサル・サービス → -2点."""
        company_info = {
            "company_name": "テストコンサル",
            "industry": "経営コンサルティング",
            "address": "東京都港区",
        }
        score, reasons = evaluate_negative_conditions(company_info, _STD_PAGE_TEXT)
        self.assertTrue(any("コンサル" in r for r in reasons))

    def test_redocean_minus_2(self):
        """業界利益率「中」（受託SI）→ -2点."""
        company_info = {
            "company_name": "テストシステム",
            "industry": "受託開発SI",
            "address": "東京都新宿区",
        }
        score, reasons = evaluate_negative_conditions(company_info, _STD_PAGE_TEXT)
        self.assertTrue(any("レッドオーシャン" in r or "中" in r for r in reasons))

    def test_founder_owner_minus_1(self):
        """創業家オーナー → -1点."""
        company_info = {
            "company_name": "テスト商事",
            "industry": "卸売業",
            "address": "東京都江東区",
        }
        text = _STD_PAGE_TEXT + " 弊社は創業家が筆頭株主の同族経営です。"
        score, reasons = evaluate_negative_conditions(company_info, text)
        self.assertTrue(any("創業家" in r for r in reasons))


# ============================================================
# D. evaluate_rank_v2 統合テスト（49社代表企業で検証）
# ============================================================


class TestEvaluateRankV2Integration(unittest.TestCase):
    """49社シミュレーションの主要結果を統合テストで検証."""

    def test_mabuchi_is_a_or_b(self):
        """マブチエスアンドティー（継続社）→ A or B 判定.

        49社シミュレーションでは A判定（5点）.
        商社・業界利益率中-高・創業家オーナー-1 = +5点
        """
        company_info = {
            "company_name": "マブチエスアンドティー株式会社",
            "industry": "商社",
            "employee_count": "70",
            "address": "東京都中央区",
        }
        text = _STD_PAGE_TEXT + " 当社は創業者一族が代々経営しております。"
        result = evaluate_rank_v2(
            company_info,
            [{"url": "", "title": "", "snippet": "", "search_query": ""}],
            page_text=text,
        )
        self.assertIn(result["rank"], ["A", "B"])

    def test_advertising_is_ng(self):
        """広告代理店 → NG（必須条件違反）."""
        company_info = {
            "company_name": "サンプル広告株式会社",
            "industry": "広告代理店",
            "employee_count": "100",
            "address": "東京都港区",
        }
        result = evaluate_rank_v2(
            company_info,
            [{"url": "", "title": "", "snippet": "", "search_query": ""}],
            page_text=_STD_PAGE_TEXT,
        )
        self.assertEqual(result["rank"], "NG")

    def test_blank_zone_is_ng(self):
        """200-499名（空白帯）→ NG."""
        company_info = {
            "company_name": "テスト商事",
            "industry": "卸売",
            "employee_count": "300",
            "address": "東京都中央区",
        }
        result = evaluate_rank_v2(
            company_info,
            [{"url": "", "title": "", "snippet": "", "search_query": ""}],
            page_text=_STD_PAGE_TEXT,
        )
        self.assertEqual(result["rank"], "NG")

    def test_finance_with_signals_is_a(self):
        """金融 + 健康経営記載 → A判定."""
        company_info = {
            "company_name": "サンプルファイナンス",
            "industry": "金融サービス",
            "employee_count": "50",
            "address": "東京都中央区日本橋",
        }
        text = _STD_PAGE_TEXT + " リクナビ・マイナビ・dodaで採用中。"
        result = evaluate_rank_v2(
            company_info,
            [{"url": "", "title": "", "snippet": "", "search_query": ""}],
            page_text=text,
        )
        self.assertEqual(result["rank"], "A")


if __name__ == "__main__":
    unittest.main()
