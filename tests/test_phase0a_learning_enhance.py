"""Phase 0a 候補1+2: 学習機能強化テスト

候補1: is_dead_query の質的ゼロ条件（runs>=5 & total_hits>0 & a_rank+b_rank=0 & ng_count>0）
       → 2026-06-04 に廃止。A/B発生率が約1%しかなく、1クエリの標本では
       「実力が悪い」と「運が悪い」を区別できず、良クエリまで永久追放して
       本番クエリ2630/2970件が壊滅したため。本クラスは「廃止後＝これらは生存」を確認する。
候補2: sort_key のグループ2を ab_rate >= AB_RATE_HIGH_QUALITY_THRESHOLD に絞り、低AB率はグループ3に降格（現役）
"""
import unittest
from unittest.mock import patch

from agents.keyword_agent import (
    is_dead_query,
    get_sorted_queries,
    AB_RATE_HIGH_QUALITY_THRESHOLD,
)

EMPTY_STATS = {"_version": "2.0", "queries": {}}


def _make_stats(**query_stats: dict) -> dict:
    return {"_version": "2.0", "queries": query_stats}


def _make_qd(runs: int, total_hits: int, a_rank: int = 0, b_rank: int = 0, ng_count: int = 0) -> dict:
    """テスト用クエリデータ（全フィールドを明示的に指定）"""
    total_ab = a_rank + b_rank
    total_processed = total_ab + ng_count
    ab_rate = total_ab / max(total_hits, 1) if total_hits > 0 else 0.0
    a_rate = a_rank / max(total_processed, 1)
    ng_rate = ng_count / max(total_processed, 1)
    avg_hits = total_hits / max(runs, 1)
    return {
        "runs": runs, "total_hits": total_hits, "avg_hits": avg_hits,
        "a_rank": a_rank, "b_rank": b_rank, "ng_count": ng_count,
        "ab_rate": ab_rate, "a_rate": a_rate, "ng_rate": ng_rate,
        "last_run": "", "by_source": {},
    }


# ─────────────────────────────────────────────
# 候補1: is_dead_query 質的ゼロ条件
# ─────────────────────────────────────────────

class TestIsDeadQueryPhase0aCandidate1(unittest.TestCase):
    """候補1（質的ゼロ条件）は 2026-06-04 に廃止。ヒットが出ていれば生存することを確認。"""

    def test_quality_zero_no_longer_excluded_at_runs5(self):
        """runs=5, total_hits=20, a_rank=0, b_rank=0, ng_count>0 → 廃止後は生存（旧仕様では除外）"""
        self.assertFalse(is_dead_query(_make_qd(runs=5, total_hits=20, ng_count=10)))

    def test_quality_zero_no_longer_excluded_many_runs(self):
        """大量実行・ヒット有・A/Bゼロでも生存（一方通行の永久死をやめた）"""
        self.assertFalse(is_dead_query(_make_qd(runs=30, total_hits=90, ng_count=50)))

    def test_existing_total_hits_zero_condition_still_works(self):
        """runs=5, total_hits=0 → 既存条件（ヒット数ゼロ）で除外（回帰確認）"""
        self.assertTrue(is_dead_query({"runs": 5, "total_hits": 0}))

    def test_low_hit_efficiency_still_dead(self):
        """runs=100, total_hits=4（4%）→ ヒット率5%未満で除外（判定2は現役）"""
        self.assertTrue(is_dead_query({"runs": 100, "total_hits": 4}))

    def test_a_rank_query_alive(self):
        """A実績あり → 当然生存"""
        self.assertFalse(is_dead_query(_make_qd(runs=5, total_hits=20, a_rank=1, ng_count=10)))

    def test_b_rank_query_alive(self):
        """B実績あり → 当然生存"""
        self.assertFalse(is_dead_query(_make_qd(runs=5, total_hits=20, b_rank=1, ng_count=10)))


# ─────────────────────────────────────────────
# 候補1: カスタムクエリ保護（get_sorted_queries）
# ─────────────────────────────────────────────

class TestCustomQueryProtectionPhase0aCandidate1(unittest.TestCase):
    """カスタムクエリは死亡条件（ヒット0）に該当しても除外されない"""

    def test_custom_query_not_excluded_even_if_dead(self):
        """ヒット0で死んでいるクエリもカスタム指定なら除外されない"""
        custom_q = "カスタムクエリ学習強化専用テスト"
        mock_stats = _make_stats(**{
            custom_q: _make_qd(runs=5, total_hits=0, ng_count=15)
        })
        with patch("agents.keyword_agent.load_stats", return_value=mock_stats):
            result = get_sorted_queries(
                custom_queries=[custom_q], exclude_dead=True
            )
        self.assertIn(custom_q, result)


# ─────────────────────────────────────────────
# 候補2: sort_key グループ2の閾値（AB_RATE_HIGH_QUALITY_THRESHOLD）
# ─────────────────────────────────────────────

class TestSortKeyPhase0aCandidate2(unittest.TestCase):
    """候補2: ab_rate >= 0.05 → グループ2、ab_rate < 0.05 → グループ3に降格"""

    def test_ab_rate_threshold_constant_value(self):
        """AB_RATE_HIGH_QUALITY_THRESHOLD は 0.05 であること"""
        self.assertEqual(AB_RATE_HIGH_QUALITY_THRESHOLD, 0.05)

    @patch("agents.keyword_agent.generate_all_queries")
    @patch("agents.keyword_agent.load_stats")
    def test_high_ab_rate_ranked_before_low_ab_rate(self, mock_load, mock_gen):
        """ab_rate=0.05 のクエリは ab_rate=0.04 のクエリより前に並ぶ（グループ2 vs グループ3）

        runs=4 を使用: runs>=5 の既存グループ4条件（A率低・実績十分 → 末尾手前）を
        回避して グループ2/3 の閾値分岐のみをテストする。
        """
        high_q = "高AB率クエリ_候補2テスト"
        low_q = "低AB率クエリ_候補2テスト"
        mock_gen.return_value = [low_q, high_q]  # 初期順序を逆にして逆転を確認
        mock_load.return_value = _make_stats(**{
            high_q: _make_qd(runs=4, total_hits=100, b_rank=5),   # ab_rate = 5/100 = 0.05
            low_q:  _make_qd(runs=4, total_hits=100, b_rank=4),   # ab_rate = 4/100 = 0.04
        })
        result = get_sorted_queries(exclude_dead=False)
        self.assertIn(high_q, result)
        self.assertIn(low_q, result)
        self.assertLess(result.index(high_q), result.index(low_q))

    @patch("agents.keyword_agent.generate_all_queries")
    @patch("agents.keyword_agent.load_stats")
    def test_zero_ab_rate_ranked_below_high_ab_query(self, mock_load, mock_gen):
        """ab_rate=0 のクエリは ab_rate=0.05 のクエリより後に並ぶ

        runs=4 を使用: runs>=5 の既存グループ4条件を回避してグループ2/3 の挙動をテスト。
        """
        ab_q = "AB率ありクエリ_候補2テスト"
        no_ab_q = "AB率なしクエリ_候補2テスト"
        mock_gen.return_value = [no_ab_q, ab_q]
        mock_load.return_value = _make_stats(**{
            ab_q:    _make_qd(runs=4, total_hits=100, b_rank=5),  # ab_rate = 0.05 → グループ2
            no_ab_q: _make_qd(runs=4, total_hits=100, b_rank=0),  # ab_rate = 0 → グループ3
        })
        result = get_sorted_queries(exclude_dead=False)
        self.assertLess(result.index(ab_q), result.index(no_ab_q))

    @patch("agents.keyword_agent.generate_all_queries")
    @patch("agents.keyword_agent.load_stats")
    def test_a_rank_still_gets_group1_above_group2(self, mock_load, mock_gen):
        """a_rank>0 のクエリは ab_rate>=0.05 のクエリより前に並ぶ（グループ1 > グループ2）"""
        a_q = "Aランクありクエリ_候補2テスト"
        b_q = "高AB率Bランククエリ_候補2テスト"
        mock_gen.return_value = [b_q, a_q]  # 初期順序を逆にして逆転を確認
        mock_load.return_value = _make_stats(**{
            a_q: _make_qd(runs=5, total_hits=100, a_rank=5, ng_count=20),   # a_rank > 0
            b_q: _make_qd(runs=5, total_hits=100, b_rank=10, ng_count=20),  # ab_rate = 0.10
        })
        result = get_sorted_queries(exclude_dead=False)
        self.assertLess(result.index(a_q), result.index(b_q))


# ─────────────────────────────────────────────
# 統合テスト: 候補1 + 候補2 の組み合わせ
# ─────────────────────────────────────────────

class TestIntegrationPhase0aLearningEnhance(unittest.TestCase):
    """死んだクエリ（ヒット0）は sort 対象から外れ、残りで ab_rate >= 0.05 が優先される"""

    @patch("agents.keyword_agent.generate_all_queries")
    @patch("agents.keyword_agent.load_stats")
    def test_dead_query_excluded_before_sorting(self, mock_load, mock_gen):
        """runs>=3 & total_hits=0（ヒットそのものが出ない）→ exclude_dead=True で除外"""
        dead_q = "死クエリ_統合テスト"
        mock_gen.return_value = [dead_q]
        mock_load.return_value = _make_stats(**{
            dead_q: _make_qd(runs=5, total_hits=0, ng_count=15)
        })
        result = get_sorted_queries(exclude_dead=True)
        self.assertNotIn(dead_q, result)

    @patch("agents.keyword_agent.generate_all_queries")
    @patch("agents.keyword_agent.load_stats")
    def test_high_ab_rate_prioritized_after_dead_excluded(self, mock_load, mock_gen):
        """除外後の残りクエリで ab_rate>=0.05 が ab_rate<0.05 より優先される

        dead_q: ヒット0で死亡 → 除外
        high_q/low_q: runs=4 でグループ4 条件を回避しグループ2/3 分岐をテスト
        """
        dead_q = "死クエリ_統合テスト2"
        high_q = "高AB率クエリ_統合テスト2"
        low_q  = "低AB率クエリ_統合テスト2"
        mock_gen.return_value = [dead_q, low_q, high_q]  # 初期順: dead→low→high
        mock_load.return_value = _make_stats(**{
            dead_q: _make_qd(runs=5, total_hits=0, ng_count=15),           # 除外される
            high_q: _make_qd(runs=4, total_hits=100, b_rank=5, ng_count=30),  # ab_rate=0.05
            low_q:  _make_qd(runs=4, total_hits=100, b_rank=4, ng_count=30),  # ab_rate=0.04
        })
        result = get_sorted_queries(exclude_dead=True)
        # 質的ゼロクエリは除外される
        self.assertNotIn(dead_q, result)
        # 残りクエリが含まれる
        self.assertIn(high_q, result)
        self.assertIn(low_q, result)
        # high_q が low_q より前に並ぶ
        self.assertLess(result.index(high_q), result.index(low_q))


if __name__ == "__main__":
    unittest.main()
