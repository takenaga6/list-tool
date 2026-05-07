"""Phase 6.7: 学習機構の整理と早期打ち切り テスト

Phase 6.7A: is_dead_query / get_sorted_queries(exclude_dead)
Phase 6.7A.2: main.py の while 条件による早期打ち切り
Phase 6.7B: has_media_hit_history / generate_all_queries のセクション9削減
"""
import unittest
from unittest.mock import patch

from agents.keyword_agent import (
    is_dead_query,
    has_media_hit_history,
    get_sorted_queries,
    generate_all_queries,
    PRIORITY_PREFECTURES,
    PR_MEDIA,
)

EMPTY_STATS = {"_version": "2.0", "queries": {}}


def _make_stats(**query_stats: dict) -> dict:
    """テスト用の stats オブジェクトを生成するヘルパー"""
    return {"_version": "2.0", "queries": query_stats}


def _make_query_data(runs: int, total_hits: int) -> dict:
    return {
        "runs": runs, "total_hits": total_hits, "avg_hits": total_hits / max(runs, 1),
        "a_rank": 0, "b_rank": 0, "ng_count": 0,
        "ab_rate": 0.0, "a_rate": 0.0, "ng_rate": 0.0,
        "last_run": "", "by_source": {},
    }


# ─────────────────────────────────────────────
# Phase 6.7A: is_dead_query
# ─────────────────────────────────────────────

class TestIsDeadQuery(unittest.TestCase):
    """is_dead_query() の判定ロジック確認"""

    def test_dead_query_runs_3_zero_hits(self):
        """3回試行で0件 → 死んでいる"""
        self.assertTrue(is_dead_query({"runs": 3, "total_hits": 0}))

    def test_alive_query_runs_2_zero_hits(self):
        """2回試行で0件 → まだ判定材料不足（生きている）"""
        self.assertFalse(is_dead_query({"runs": 2, "total_hits": 0}))

    def test_alive_query_5_runs_1_hit(self):
        """5回試行で1件（20%） → 効率良好、生きている"""
        self.assertFalse(is_dead_query({"runs": 5, "total_hits": 1}))

    def test_dead_query_10_runs_zero_hits(self):
        """10回試行で0件 → 完全に死んでいる"""
        self.assertTrue(is_dead_query({"runs": 10, "total_hits": 0}))

    def test_dead_query_low_efficiency(self):
        """100回試行で4件（4%） → ヒット率5%未満、効率悪すぎ"""
        self.assertTrue(is_dead_query({"runs": 100, "total_hits": 4}))

    def test_alive_boundary_efficiency(self):
        """100回試行で5件（5%） → 閾値ちょうどなので生きている"""
        self.assertFalse(is_dead_query({"runs": 100, "total_hits": 5}))

    def test_alive_query_no_history(self):
        """履歴なし → 初回試行するので死んでいない"""
        self.assertFalse(is_dead_query({}))

    def test_alive_query_runs_1_zero_hits(self):
        """1回試行で0件 → まだ判定できない"""
        self.assertFalse(is_dead_query({"runs": 1, "total_hits": 0}))


# ─────────────────────────────────────────────
# Phase 6.7A: get_sorted_queries の exclude_dead
# ─────────────────────────────────────────────

class TestGetSortedQueriesDeadExclusion(unittest.TestCase):
    """get_sorted_queries(exclude_dead=True) で死んだクエリが除外される"""

    def test_get_sorted_queries_excludes_dead(self):
        """死んだクエリ（runs=5, hits=0）は結果に含まれない"""
        dead_query = "B-PLUS 株式会社"
        mock_stats = _make_stats(**{dead_query: _make_query_data(runs=5, total_hits=0)})
        with patch("agents.keyword_agent.load_stats", return_value=mock_stats):
            result = get_sorted_queries(exclude_dead=True)
        self.assertNotIn(dead_query, result)

    def test_get_sorted_queries_keeps_alive(self):
        """生きているクエリは残る"""
        alive_query = "B-PLUS 株式会社"
        mock_stats = _make_stats(**{alive_query: _make_query_data(runs=5, total_hits=10)})
        with patch("agents.keyword_agent.load_stats", return_value=mock_stats):
            result = get_sorted_queries(exclude_dead=True)
        self.assertIn(alive_query, result)

    def test_get_sorted_queries_keeps_custom_even_if_dead(self):
        """カスタムクエリは exclude_dead=True でも除外されない"""
        custom_query = "カスタム健康経営クエリ専用テスト用"
        mock_stats = _make_stats(**{custom_query: _make_query_data(runs=5, total_hits=0)})
        with patch("agents.keyword_agent.load_stats", return_value=mock_stats):
            result = get_sorted_queries(
                custom_queries=[custom_query], exclude_dead=True
            )
        self.assertIn(custom_query, result)

    def test_get_sorted_queries_backward_compat(self):
        """exclude_dead=False では死んだクエリも除外されない（後方互換）"""
        dead_query = "B-PLUS 株式会社"
        mock_stats = _make_stats(**{dead_query: _make_query_data(runs=5, total_hits=0)})
        with patch("agents.keyword_agent.load_stats", return_value=mock_stats):
            result = get_sorted_queries(exclude_dead=False)
        self.assertIn(dead_query, result)

    def test_get_sorted_queries_default_excludes_dead(self):
        """exclude_dead のデフォルト値は True（引数省略で死んだクエリ除外）"""
        dead_query = "B-PLUS 株式会社"
        mock_stats = _make_stats(**{dead_query: _make_query_data(runs=5, total_hits=0)})
        with patch("agents.keyword_agent.load_stats", return_value=mock_stats):
            result = get_sorted_queries()  # デフォルト引数で呼び出し
        self.assertNotIn(dead_query, result)

    def test_no_history_query_is_kept(self):
        """統計データのないクエリ（初回実行）は除外しない"""
        with patch("agents.keyword_agent.load_stats", return_value=EMPTY_STATS):
            result = get_sorted_queries(exclude_dead=True)
        # 生成クエリが1件以上あること
        self.assertGreater(len(result), 0)


# ─────────────────────────────────────────────
# Phase 6.7A.2: 早期打ち切り（静的確認）
# ─────────────────────────────────────────────

class TestEarlyTermination(unittest.TestCase):
    """Phase 6.7A.2: main.py の batch モードに早期打ち切り条件が存在する"""

    def test_early_termination_condition_in_batch_while(self):
        """バッチループの while 条件に target_count チェックが含まれること"""
        import pathlib
        main_text = pathlib.Path("main.py").read_text(encoding="utf-8")
        self.assertIn('while stats["success"] < target_count', main_text)

    def test_early_termination_log_added(self):
        """目標達成時のログ出力が main.py に含まれること"""
        import pathlib
        main_text = pathlib.Path("main.py").read_text(encoding="utf-8")
        self.assertIn("[早期終了]", main_text)


# ─────────────────────────────────────────────
# Phase 6.7B: has_media_hit_history
# ─────────────────────────────────────────────

class TestHasMediaHitHistory(unittest.TestCase):
    """has_media_hit_history() の判定ロジック確認"""

    def test_media_with_hit_history(self):
        """過去にヒット実績ある媒体 → True"""
        stats = {
            "B-PLUS 東京都 株式会社": {"total_hits": 5},
            "B-PLUS 大阪府 株式会社": {"total_hits": 0},
        }
        self.assertTrue(has_media_hit_history("B-PLUS", stats))

    def test_media_all_zero_hits(self):
        """全クエリでヒット0 → False"""
        stats = {
            "Newsweek WEB 東京都 株式会社": {"total_hits": 0},
            "Newsweek WEB 大阪府 株式会社": {"total_hits": 0},
        }
        self.assertFalse(has_media_hit_history("Newsweek WEB", stats))

    def test_media_no_history(self):
        """履歴なし（空dict） → False"""
        self.assertFalse(has_media_hit_history("B-PLUS", {}))

    def test_media_partial_match_excluded(self):
        """部分一致しない媒体は True にならない"""
        stats = {
            "B-PLUS 東京都 株式会社": {"total_hits": 5},
        }
        # "B-PLUS" を含まない媒体は False
        self.assertFalse(has_media_hit_history("KENJA GLOBAL", stats))

    def test_media_hit_exactly_1(self):
        """ヒット数1でも True（0より大きければOK）"""
        stats = {
            "SUPER CEO 東京都 株式会社": {"total_hits": 1},
        }
        self.assertTrue(has_media_hit_history("SUPER CEO", stats))


# ─────────────────────────────────────────────
# Phase 6.7B: generate_all_queries のクエリ削減
# ─────────────────────────────────────────────

class TestGenerateAllQueriesMediaHistory(unittest.TestCase):
    """Phase 6.7B: generate_all_queries がヒット履歴に応じてクエリ数を絞る"""

    def test_new_media_generates_only_priority_prefectures(self):
        """履歴ない媒体は主要5都道府県のみクエリ生成"""
        from config import SEARCH_REGIONS
        non_priority = [r for r in SEARCH_REGIONS if r not in PRIORITY_PREFECTURES]
        target_media = PR_MEDIA[0]  # "KENJA GLOBAL"

        with patch("agents.keyword_agent.load_stats", return_value=EMPTY_STATS):
            queries = generate_all_queries()

        # 主要5都道府県は含まれる
        for region in PRIORITY_PREFECTURES:
            self.assertIn(f"{target_media} {region} 株式会社", queries)

        # 非主要都道府県は含まれない
        for region in non_priority:
            self.assertNotIn(
                f"{target_media} {region} 株式会社", queries,
                f"履歴なし媒体で非主要都道府県 {region} が生成されている"
            )

    def test_known_media_generates_all_prefectures(self):
        """ヒット実績ある媒体は全47都道府県生成"""
        from config import SEARCH_REGIONS
        target_media = PR_MEDIA[0]  # "KENJA GLOBAL"
        mock_stats = _make_stats(**{
            f"{target_media} 東京都 株式会社": _make_query_data(runs=3, total_hits=5)
        })

        with patch("agents.keyword_agent.load_stats", return_value=mock_stats):
            queries = generate_all_queries()

        for region in SEARCH_REGIONS:
            self.assertIn(
                f"{target_media} {region} 株式会社", queries,
                f"ヒット実績あり媒体で {region} が生成されていない"
            )

    def test_query_count_reduced_without_history(self):
        """全媒体が未知の場合、セクション9のクエリ数が大幅削減される"""
        from config import SEARCH_REGIONS

        with patch("agents.keyword_agent.load_stats", return_value=EMPTY_STATS):
            queries = generate_all_queries()

        # 全媒体 × 全47都道府県の組み合わせは生成されないはず
        all_media_x_all_regions = len(PR_MEDIA) * len(SEARCH_REGIONS)  # 44 × 47 = 2068
        # 実際のセクション9クエリ数 = len(PR_MEDIA) × 5 (主要5都道府県)
        expected_section9 = len(PR_MEDIA) * len(PRIORITY_PREFECTURES)  # 44 × 5 = 220

        section9_queries = [
            q for q in queries
            if any(media in q for media in PR_MEDIA)
            and "株式会社" in q
            and any(region in q for region in SEARCH_REGIONS)
        ]
        # 全47都道府県 × 全媒体数より少ないこと（削減されていること）
        self.assertLess(len(section9_queries), all_media_x_all_regions)

    def test_priority_prefectures_count(self):
        """PRIORITY_PREFECTURES は5件であること"""
        self.assertEqual(len(PRIORITY_PREFECTURES), 5)

    def test_priority_prefectures_content(self):
        """PRIORITY_PREFECTURES に主要5都市が含まれること"""
        for expected in ["東京都", "大阪府", "愛知県", "神奈川県", "福岡県"]:
            self.assertIn(expected, PRIORITY_PREFECTURES)


if __name__ == "__main__":
    unittest.main()
