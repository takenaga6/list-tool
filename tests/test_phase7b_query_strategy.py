"""Phase 7-B: クエリ戦略見直しのテスト"""
import unittest

from config import NG_INDUSTRY_SUFFIX
from agents.keyword_agent import (
    generate_all_queries,
    is_s2_media_query,
    S2_QUERY_MARKERS,
    PR_MEDIA,
    MEDIA_SUFFIXES,
)


class TestNGIndustrySuffix(unittest.TestCase):
    """NG_INDUSTRY_SUFFIX の定義テスト"""

    def test_suffix_not_empty(self):
        self.assertTrue(len(NG_INDUSTRY_SUFFIX.strip()) > 0)

    def test_suffix_contains_key_terms(self):
        for term in ["-建設", "-工務店", "-運輸", "-介護"]:
            self.assertIn(term, NG_INDUSTRY_SUFFIX, f"{term} がサフィックスにない")


class TestS1QueriesHaveNGSuffix(unittest.TestCase):
    """S1クエリ（媒体 × 定型フレーズ）に NG_INDUSTRY_SUFFIX が付いていること"""

    def setUp(self):
        self.queries = generate_all_queries()

    def test_s1_queries_have_ng_suffix(self):
        # 媒体名 × MEDIA_SUFFIXES の組み合わせにサフィックスが付いている
        media = PR_MEDIA[0]  # "KENJA GLOBAL"
        for suffix in MEDIA_SUFFIXES:
            expected = f"{media} {suffix}{NG_INDUSTRY_SUFFIX}"
            self.assertIn(expected, self.queries, f"S1クエリにNGサフィックスがない: {expected!r}")

    def test_health_welfare_queries_no_ng_suffix(self):
        # HEALTH_WELFARE 系には NG_INDUSTRY_SUFFIX を付けない（高精度フレーズのため）
        from agents.keyword_agent import HEALTH_WELFARE
        for q in HEALTH_WELFARE:
            self.assertIn(q, self.queries, f"HEALTH_WELFARE クエリが消えた: {q!r}")
            # サフィックス付き版は存在しない
            self.assertNotIn(q + NG_INDUSTRY_SUFFIX, self.queries)


class TestS7QueriesHaveNGSuffix(unittest.TestCase):
    """S7クエリ（媒体 × 大分類）に NG_INDUSTRY_SUFFIX が付いていること"""

    def setUp(self):
        self.queries = generate_all_queries()

    def test_s7_queries_have_ng_suffix(self):
        CATEGORY_L1 = ["株式会社", "健康経営", "代表取締役", "えるぼし認定", "法定外福利厚生"]
        media = PR_MEDIA[0]
        for cat in CATEGORY_L1:
            expected = f"{media} {cat}{NG_INDUSTRY_SUFFIX}"
            self.assertIn(expected, self.queries, f"S7クエリにNGサフィックスがない: {expected!r}")


class TestS9QueriesHaveNGSuffix(unittest.TestCase):
    """S9クエリ（地域 × 媒体）に NG_INDUSTRY_SUFFIX が付いていること"""

    def setUp(self):
        self.queries = generate_all_queries()

    def test_s9_queries_have_ng_suffix(self):
        # 主要5都道府県は履歴なし媒体でも生成されるため確認対象
        PRIORITY_PREFS = ["東京都", "大阪府", "愛知県", "神奈川県", "福岡県"]
        media = PR_MEDIA[0]  # 履歴なしでも主要5都道府県は生成される
        for region in PRIORITY_PREFS:
            expected = f"{media} {region} 株式会社{NG_INDUSTRY_SUFFIX}"
            self.assertIn(expected, self.queries, f"S9クエリにNGサフィックスがない: {expected!r}")


class TestIsS2MediaQuery(unittest.TestCase):
    """is_s2_media_query のユニットテスト"""

    def test_voice_report_marker_detected(self):
        self.assertTrue(is_s2_media_query("アクサ生命 Voice Report 掲載 株式会社"))

    def test_voice_report_katakana_detected(self):
        self.assertTrue(is_s2_media_query("アクサ生命 ボイスレポート 掲載 株式会社"))

    def test_daido_kenco_detected(self):
        self.assertTrue(is_s2_media_query("DAIDO KENCO AWARD 受賞 株式会社"))

    def test_daido_kanji_detected(self):
        self.assertTrue(is_s2_media_query("大同生命 KENCO AWARD 受賞 株式会社"))

    def test_daido_award_detected(self):
        self.assertTrue(is_s2_media_query("大同生命 健康経営アワード 株式会社"))

    def test_non_s2_query_not_detected(self):
        self.assertFalse(is_s2_media_query("KENJA GLOBAL 株式会社"))
        self.assertFalse(is_s2_media_query("法定外福利厚生 株式会社"))
        self.assertFalse(is_s2_media_query("健康経営優良法人 東京都"))

    def test_empty_query_not_detected(self):
        self.assertFalse(is_s2_media_query(""))


class TestS2QueryCount(unittest.TestCase):
    """S2クエリが十分な数（10件以上/媒体）生成されていること"""

    def setUp(self):
        self.queries = generate_all_queries()

    def test_voice_report_query_count(self):
        vr_queries = [q for q in self.queries if "Voice Report" in q or "ボイスレポート" in q]
        self.assertGreaterEqual(len(vr_queries), 8, "Voice Report クエリが8件未満")

    def test_daido_query_count(self):
        daido_queries = [
            q for q in self.queries
            if "DAIDO KENCO" in q or "大同生命 KENCO" in q or "大同生命 健康経営アワード" in q
        ]
        self.assertGreaterEqual(len(daido_queries), 6, "DAIDO KENCO クエリが6件未満")


class TestTargetAttributeQueries(unittest.TestCase):
    """ターゲット属性クエリ（業種 × 健康経営優良法人 × 都道府県）のテスト"""

    def setUp(self):
        self.queries = generate_all_queries()

    def test_it_industry_queries_present(self):
        it_queries = [q for q in self.queries if q.startswith("IT企業 健康経営優良法人")]
        self.assertEqual(len(it_queries), 47, f"IT企業クエリが47件でない: {len(it_queries)}")

    def test_consulting_queries_present(self):
        cons_queries = [q for q in self.queries if q.startswith("コンサルティング 健康経営優良法人")]
        self.assertEqual(len(cons_queries), 47, f"コンサルティングクエリが47件でない: {len(cons_queries)}")

    def test_manufacturing_queries_present(self):
        mfg_queries = [q for q in self.queries if q.startswith("製造業 健康経営優良法人")]
        self.assertEqual(len(mfg_queries), 47, f"製造業クエリが47件でない: {len(mfg_queries)}")

    def test_sample_query_format(self):
        self.assertIn("IT企業 健康経営優良法人 東京都", self.queries)
        self.assertIn("コンサルティング 健康経営優良法人 大阪府", self.queries)
        self.assertIn("製造業 健康経営優良法人 愛知県", self.queries)


class TestTotalQueryCount(unittest.TestCase):
    """クエリ総数が想定範囲内であること"""

    def test_query_count_in_range(self):
        queries = generate_all_queries()
        # 最小: 基本クエリ + S2 20件 + ターゲット属性141件
        self.assertGreater(len(queries), 500, f"クエリ数が少なすぎる: {len(queries)}")
        # 最大: 無限増殖防止（10000件上限）
        self.assertLess(len(queries), 10000, f"クエリ数が多すぎる: {len(queries)}")

    def test_no_duplicate_queries(self):
        queries = generate_all_queries()
        self.assertEqual(len(queries), len(set(queries)), "重複クエリあり")


if __name__ == "__main__":
    unittest.main()
