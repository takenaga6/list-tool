"""fix/period-selection-bug: 期間選択バグ修正テスト

修正内容: run_batch() の periods_to_use = periods[:1] を periods に変更。
UIで複数期間を選択した時、全期間が実際に検索される。
"""
import math
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


# ──────────────────────────────────────────────────────────────
# search_tasks 構築ロジックの仕様テスト
# ──────────────────────────────────────────────────────────────

class TestSearchTasksConstruction(unittest.TestCase):
    """
    run_batch() の search_tasks 構築ロジックを仕様として検証する。
    修正後: periods_to_use = periods（全期間使用）
    修正前: periods_to_use = periods[:1]（最初の1期間のみ）
    """

    @staticmethod
    def _build(periods, query_list):
        """run_batch の search_tasks 構築ロジック（修正後）"""
        periods_to_use = periods
        return [(kw, lbl, tbs) for kw in query_list for lbl, tbs in periods_to_use]

    def test_two_periods_both_appear_in_tasks(self):
        """2期間選択時、両方の tbs が search_tasks に含まれる"""
        periods = [("1週間", "qdr:w"), ("3カ月以内", "qdr:m3")]
        tasks = self._build(periods, ["クエリA", "クエリB"])
        tbs_list = [tbs for _, _, tbs in tasks]
        self.assertIn("qdr:w",  tbs_list)
        self.assertIn("qdr:m3", tbs_list)

    def test_task_count_equals_queries_times_periods(self):
        """search_tasks の件数 = クエリ数 × 期間数"""
        periods = [("1週間", "qdr:w"), ("3カ月以内", "qdr:m3"), ("1年以内", "qdr:y")]
        queries = ["Q1", "Q2", "Q3", "Q4"]
        tasks = self._build(periods, queries)
        self.assertEqual(len(tasks), len(queries) * len(periods))  # 4 × 3 = 12

    def test_three_periods_all_appear(self):
        """3期間選択時、全期間が search_tasks に含まれる"""
        periods = [("1週間", "qdr:w"), ("3カ月以内", "qdr:m3"), ("1年以内", "qdr:y")]
        tasks = self._build(periods, ["クエリA"])
        tbs_list = [tbs for _, _, tbs in tasks]
        self.assertIn("qdr:w",  tbs_list)
        self.assertIn("qdr:m3", tbs_list)
        self.assertIn("qdr:y",  tbs_list)
        self.assertEqual(len(tasks), 3)

    def test_single_period_still_works(self):
        """1期間選択時でも正常に search_tasks が作られる（回帰確認）"""
        periods = [("3カ月以内", "qdr:m3")]
        tasks = self._build(periods, ["クエリA"])
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0][2], "qdr:m3")

    def test_old_slice_would_break_multi_period(self):
        """periods[:1] だと2期間目が消えることを確認（旧バグの再現）"""
        periods = [("1週間", "qdr:w"), ("3カ月以内", "qdr:m3")]
        # バグ再現: periods[:1] を使った場合
        periods_broken = periods[:1]
        tasks_broken = [(kw, lbl, tbs) for kw in ["クエリA"] for lbl, tbs in periods_broken]
        tbs_broken = [tbs for _, _, tbs in tasks_broken]
        # 旧バグでは3カ月以内が消える
        self.assertNotIn("qdr:m3", tbs_broken)
        self.assertIn("qdr:w", tbs_broken)


# ──────────────────────────────────────────────────────────────
# run_batch() の統合テスト
# ──────────────────────────────────────────────────────────────

class TestRunBatchMultiPeriod(unittest.TestCase):
    """run_batch() が選択した全期間で search_google を呼ぶことを確認"""

    def _run_and_capture_tbs(self, period_keys: list[str]) -> list[str]:
        """指定の period_keys で run_batch を実行し、search_google に渡された tbs を返す"""
        called_tbs = []

        def fake_search(query, tbs, num=10):
            called_tbs.append(tbs)
            return []  # 空 → 企業処理なし、全タスク消化で終了

        mock_hubspot = MagicMock()
        mock_hubspot.check_duplicate.return_value = False

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_results    = os.path.join(tmpdir, "results.csv")
            tmp_results_wq = os.path.join(tmpdir, "results_with_query.csv")

            with patch("main.search_google",   side_effect=fake_search), \
                 patch("main.HubSpotAgent",     return_value=mock_hubspot), \
                 patch("main.get_sorted_queries", return_value=["テスト株式会社"]), \
                 patch("main.MEDIA_LIST_URLS",  []), \
                 patch("main.startup_cleanup"), \
                 patch("main.print_progress"), \
                 patch("main.print_header"), \
                 patch("main.print_ng_suggestions"), \
                 patch("main.RESULTS_FILE",            tmp_results), \
                 patch("main.RESULTS_WITH_QUERY_FILE", tmp_results_wq):
                from main import run_batch
                run_batch(
                    keywords=[],
                    period_keys=period_keys,
                    auto_mode=True,
                    target_count=9999,  # 未達成のまま全タスク消化
                )
        return called_tbs

    def test_two_periods_both_searched(self):
        """period_keys=["1","5"] → 1週間(qdr:w) と 3カ月以内(qdr:m3) の両方で検索される

        TIME_PERIODS: "1"→"1週間"→qdr:w / "5"→"3カ月以内"→qdr:m3
        """
        called_tbs = self._run_and_capture_tbs(["1", "5"])
        self.assertIn("qdr:w",  called_tbs, "1週間(qdr:w) の検索が実行されていない")
        self.assertIn("qdr:m3", called_tbs, "3カ月以内(qdr:m3) の検索が実行されていない")

    def test_single_period_still_works(self):
        """period_keys=["5"] → 3カ月以内のみ実行（単一期間の回帰確認）"""
        called_tbs = self._run_and_capture_tbs(["5"])
        self.assertIn("qdr:m3", called_tbs)
        self.assertNotIn("qdr:w", called_tbs)

    def test_three_periods_all_searched(self):
        """period_keys=["1","5","8"] → 1週間・3カ月以内・1年以内の3期間すべてで検索される

        TIME_PERIODS: "1"→qdr:w / "5"→qdr:m3 / "8"→qdr:y
        """
        called_tbs = self._run_and_capture_tbs(["1", "5", "8"])
        self.assertIn("qdr:w",  called_tbs, "1週間(qdr:w) の検索が実行されていない")
        self.assertIn("qdr:m3", called_tbs, "3カ月以内(qdr:m3) の検索が実行されていない")
        self.assertIn("qdr:y",  called_tbs, "1年以内(qdr:y) の検索が実行されていない")
        self.assertEqual(len(set(called_tbs)), 3)


if __name__ == "__main__":
    unittest.main()
