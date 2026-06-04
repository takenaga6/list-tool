"""Phase 6.7: 学習機構の整理と早期打ち切り テスト

Phase 6.7A: is_dead_query / get_sorted_queries(exclude_dead)
Phase 6.7A.2: main.py の while 条件による早期打ち切り
Phase 6.7B: has_media_hit_history / generate_all_queries のセクション9削減
2026-06-04: 判定3（A/B無→永久死）廃止・復活機構（RECOVERY_DAYS）追加
"""
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from agents.keyword_agent import (
    is_dead_query,
    has_media_hit_history,
    get_sorted_queries,
    generate_all_queries,
    get_producing_queries,
    RECOVERY_DAYS,
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


class TestCriterion3Removed(unittest.TestCase):
    """2026-06-04: 旧・判定3（5回+ヒット有+A/B無+NG有→永久死）の廃止確認"""

    def test_hits_but_no_ab_with_ng_is_alive(self):
        """ヒットは出るがA/Bゼロ・NG有 → 旧判定3では死だが、廃止後は生存"""
        stats = {
            "runs": 20, "total_hits": 56,  # ヒット率は十分高い
            "a_rank": 0, "b_rank": 0, "ng_count": 5,
            "last_run": "2026-06-01 03:44",
        }
        self.assertFalse(is_dead_query(stats, now=datetime(2026, 6, 4, 0, 0)))

    def test_hits_no_ab_no_ng_is_alive(self):
        """ヒット有・A/Bゼロ・NGゼロ → 当然生存（ヒットしている）"""
        stats = {
            "runs": 10, "total_hits": 30,
            "a_rank": 0, "b_rank": 0, "ng_count": 0,
            "last_run": "2026-06-03 10:00",
        }
        self.assertFalse(is_dead_query(stats, now=datetime(2026, 6, 4, 0, 0)))

    def test_zero_hits_still_dead(self):
        """検索ヒットそのものが出ない（判定1）は引き続き死（最近実行）"""
        stats = {"runs": 5, "total_hits": 0, "last_run": "2026-06-03 10:00"}
        self.assertTrue(is_dead_query(stats, now=datetime(2026, 6, 4, 0, 0)))


class TestRecoveryMechanism(unittest.TestCase):
    """RECOVERY_DAYS による死んだクエリの復活確認"""

    def test_dead_query_resurrected_after_recovery_days(self):
        """ヒット0で死んでいても、RECOVERY_DAYS以上前なら復活（生存扱い）"""
        old = (datetime(2026, 6, 4) - timedelta(days=RECOVERY_DAYS + 1)).strftime("%Y-%m-%d %H:%M")
        stats = {"runs": 5, "total_hits": 0, "last_run": old}
        self.assertFalse(is_dead_query(stats, now=datetime(2026, 6, 4, 0, 0)))

    def test_dead_query_stays_dead_within_recovery_window(self):
        """RECOVERY_DAYS 未満なら死んだまま"""
        recent = (datetime(2026, 6, 4) - timedelta(days=RECOVERY_DAYS - 1)).strftime("%Y-%m-%d %H:%M")
        stats = {"runs": 5, "total_hits": 0, "last_run": recent}
        self.assertTrue(is_dead_query(stats, now=datetime(2026, 6, 4, 0, 0)))

    def test_empty_last_run_no_recovery(self):
        """last_run が空 → 復活判定対象外、死んだまま（既存挙動の後方互換）"""
        stats = {"runs": 5, "total_hits": 0, "last_run": ""}
        self.assertTrue(is_dead_query(stats, now=datetime(2026, 6, 4, 0, 0)))

    def test_malformed_last_run_no_recovery(self):
        """last_run が不正形式 → 復活判定対象外、死んだまま"""
        stats = {"runs": 5, "total_hits": 0, "last_run": "不正な日付"}
        self.assertTrue(is_dead_query(stats, now=datetime(2026, 6, 4, 0, 0)))


class TestProducingQueries(unittest.TestCase):
    """get_producing_queries(): A/B成功記録の可視化"""

    def test_only_ab_producing_queries_returned(self):
        """A/Bを出したクエリだけが返り、AB件数降順に並ぶ"""
        mock_stats = _make_stats(
            **{
                "勝ちクエリ": {"a_rank": 2, "b_rank": 1, "ng_count": 5, "runs": 10, "total_hits": 30, "last_run": ""},
                "B少しクエリ": {"a_rank": 0, "b_rank": 1, "ng_count": 3, "runs": 5, "total_hits": 12, "last_run": ""},
                "無成果クエリ": {"a_rank": 0, "b_rank": 0, "ng_count": 8, "runs": 9, "total_hits": 20, "last_run": ""},
            }
        )
        with patch("agents.keyword_agent.load_stats", return_value=mock_stats):
            rows = get_producing_queries()
        self.assertEqual([r["query"] for r in rows], ["勝ちクエリ", "B少しクエリ"])
        self.assertEqual(rows[0]["AB"], 3)


# ─────────────────────────────────────────────
# Phase 6.7A: get_sorted_queries の exclude_dead
# ─────────────────────────────────────────────

class TestGetSortedQueriesDeadExclusion(unittest.TestCase):
    """get_sorted_queries(exclude_dead=True) で死んだクエリが除外される"""

    def test_get_sorted_queries_excludes_dead(self):
        """死んだクエリ（runs=5, hits=0）は結果に含まれない"""
        from config import NG_INDUSTRY_SUFFIX
        dead_query = f"B-PLUS 株式会社{NG_INDUSTRY_SUFFIX}"
        # stats は normalize_query_key() で正規化されたキー（NG suffix なし）で保存される
        dead_key = "B-PLUS 株式会社"
        mock_stats = _make_stats(**{dead_key: _make_query_data(runs=5, total_hits=0)})
        with patch("agents.keyword_agent.load_stats", return_value=mock_stats):
            result = get_sorted_queries(exclude_dead=True)
        self.assertNotIn(dead_query, result)

    def test_get_sorted_queries_keeps_alive(self):
        """生きているクエリは残る"""
        from config import NG_INDUSTRY_SUFFIX
        alive_query = f"B-PLUS 株式会社{NG_INDUSTRY_SUFFIX}"
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
        from config import NG_INDUSTRY_SUFFIX
        dead_query = f"B-PLUS 株式会社{NG_INDUSTRY_SUFFIX}"
        mock_stats = _make_stats(**{dead_query: _make_query_data(runs=5, total_hits=0)})
        with patch("agents.keyword_agent.load_stats", return_value=mock_stats):
            result = get_sorted_queries(exclude_dead=False)
        self.assertIn(dead_query, result)

    def test_get_sorted_queries_default_excludes_dead(self):
        """exclude_dead のデフォルト値は True（引数省略で死んだクエリ除外）"""
        from config import NG_INDUSTRY_SUFFIX
        dead_query = f"B-PLUS 株式会社{NG_INDUSTRY_SUFFIX}"
        # stats は normalize_query_key() で正規化されたキー（NG suffix なし）で保存される
        dead_key = "B-PLUS 株式会社"
        mock_stats = _make_stats(**{dead_key: _make_query_data(runs=5, total_hits=0)})
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
        from config import SEARCH_REGIONS, NG_INDUSTRY_SUFFIX
        non_priority = [r for r in SEARCH_REGIONS if r not in PRIORITY_PREFECTURES]
        target_media = PR_MEDIA[0]  # "KENJA GLOBAL"

        with patch("agents.keyword_agent.load_stats", return_value=EMPTY_STATS):
            queries = generate_all_queries()

        # 主要5都道府県は含まれる
        for region in PRIORITY_PREFECTURES:
            self.assertIn(f"{target_media} {region} 株式会社{NG_INDUSTRY_SUFFIX}", queries)

        # 非主要都道府県は含まれない
        for region in non_priority:
            self.assertNotIn(
                f"{target_media} {region} 株式会社{NG_INDUSTRY_SUFFIX}", queries,
                f"履歴なし媒体で非主要都道府県 {region} が生成されている"
            )

    def test_known_media_generates_all_prefectures(self):
        """ヒット実績ある媒体は全47都道府県生成"""
        from config import SEARCH_REGIONS, NG_INDUSTRY_SUFFIX
        target_media = PR_MEDIA[0]  # "KENJA GLOBAL"
        mock_stats = _make_stats(**{
            f"{target_media} 東京都 株式会社{NG_INDUSTRY_SUFFIX}": _make_query_data(runs=3, total_hits=5)
        })

        with patch("agents.keyword_agent.load_stats", return_value=mock_stats):
            queries = generate_all_queries()

        for region in SEARCH_REGIONS:
            self.assertIn(
                f"{target_media} {region} 株式会社{NG_INDUSTRY_SUFFIX}", queries,
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
