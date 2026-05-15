"""Phase 0b 施策1: Google CSE ページネーションテスト

修正内容: _fetch_hits_google_cse に start ループ追加（最大3ページ = 30件）
- start=1, 11, 21 の3回リクエスト
- seen_urls で重複URL除外
- ページ間スリープ 1.5秒
- 1ページ目が0件 or エラーの場合は早期終了
"""
import unittest
from unittest.mock import patch, MagicMock, call

import sys
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agents.search_agent import _fetch_hits_google_cse


def _make_cse_response(links: list[str], status: int = 200) -> MagicMock:
    """Google CSE API レスポンスのモック"""
    mock_resp = MagicMock()
    mock_resp.status_code = status
    mock_resp.json.return_value = {
        "items": [
            {"link": link, "title": f"title_{i}", "snippet": f"snippet_{i}"}
            for i, link in enumerate(links)
        ] if links else []
    }
    return mock_resp


def _empty_response() -> MagicMock:
    """0件レスポンスのモック"""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {}  # "items" キーなし
    return mock_resp


# ─────────────────────────────────────────────────────────────
# 単体テスト: ページネーション基本動作
# ─────────────────────────────────────────────────────────────

class TestFetchHitsGoogleCsePagination(unittest.TestCase):
    """_fetch_hits_google_cse のページネーション動作検証"""

    def _patch_env(self):
        """APIキーとCXを設定済みにするパッチ"""
        return patch(
            "agents.search_agent._fetch_hits_google_cse.__globals__",
            {},  # 使わない、config モックで代替
        )

    def _run(self, side_effects, query="テストクエリ", tbs="qdr:m3", num=50):
        """指定の side_effects で requests.get をモックして実行"""
        with patch("agents.search_agent.requests.get", side_effect=side_effects) as mock_get, \
             patch("agents.search_agent.time.sleep"), \
             patch("config.GOOGLE_CSE_API_KEY", "test_key"), \
             patch("config.GOOGLE_CSE_CX", "test_cx"):
            result = _fetch_hits_google_cse(query, tbs, num)
        return result, mock_get

    def test_three_pages_requested_when_all_return_results(self):
        """全ページで結果がある場合、start=1, 11, 21 の3回リクエストが発生する"""
        page1 = _make_cse_response([f"https://example{i}.co.jp" for i in range(10)])
        page2 = _make_cse_response([f"https://example{i}.co.jp" for i in range(10, 20)])
        page3 = _make_cse_response([f"https://example{i}.co.jp" for i in range(20, 30)])

        result, mock_get = self._run([page1, page2, page3])

        self.assertEqual(mock_get.call_count, 3)
        starts = [c.kwargs["params"]["start"] for c in mock_get.call_args_list]
        self.assertEqual(starts, [1, 11, 21])

    def test_results_merged_across_all_pages(self):
        """各ページの結果が合算される（30件返る）"""
        page1 = _make_cse_response([f"https://example{i}.co.jp" for i in range(10)])
        page2 = _make_cse_response([f"https://example{i}.co.jp" for i in range(10, 20)])
        page3 = _make_cse_response([f"https://example{i}.co.jp" for i in range(20, 30)])

        result, _ = self._run([page1, page2, page3])

        self.assertEqual(len(result), 30)
        urls = [r["href"] for r in result]
        self.assertIn("https://example0.co.jp", urls)
        self.assertIn("https://example15.co.jp", urls)
        self.assertIn("https://example29.co.jp", urls)

    def test_duplicate_urls_excluded_by_seen_urls(self):
        """ページ間で重複するURLは seen_urls で除外される"""
        dup_url = "https://duplicate.co.jp"
        page1 = _make_cse_response(["https://unique1.co.jp", dup_url])
        # page2 に page1 と同じ URL が含まれる
        page2 = _make_cse_response([dup_url, "https://unique2.co.jp"])
        page3 = _make_cse_response([])  # 早期終了

        result, _ = self._run([page1, page2, page3])

        hrefs = [r["href"] for r in result]
        # dup_url は1件のみ（重複除外）
        self.assertEqual(hrefs.count(dup_url), 1)
        self.assertIn("https://unique1.co.jp", hrefs)
        self.assertIn("https://unique2.co.jp", hrefs)
        self.assertEqual(len(result), 3)

    def test_early_exit_when_page1_returns_zero_items(self):
        """1ページ目で結果0件 → 2ページ目以降リクエストしない（早期終了）"""
        page1 = _empty_response()

        result, mock_get = self._run([page1])

        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(result, [])

    def test_early_exit_when_page2_returns_zero_items(self):
        """2ページ目で結果0件 → 3ページ目リクエストしない（早期終了）"""
        page1 = _make_cse_response(["https://example0.co.jp"])
        page2 = _empty_response()

        result, mock_get = self._run([page1, page2])

        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(len(result), 1)

    def test_page1_error_returns_empty_list(self):
        """1ページ目でAPIエラー → 空リスト返却（DDGフォールバックさせる）"""
        page1_error = _make_cse_response([], status=429)

        result, mock_get = self._run([page1_error])

        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(result, [])

    def test_page2_error_returns_page1_results_only(self):
        """2ページ目でAPIエラー → 1ページ目の結果のみ返却"""
        page1 = _make_cse_response(["https://example0.co.jp", "https://example1.co.jp"])
        page2_error = _make_cse_response([], status=500)

        result, mock_get = self._run([page1, page2_error])

        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(len(result), 2)
        hrefs = [r["href"] for r in result]
        self.assertIn("https://example0.co.jp", hrefs)
        self.assertIn("https://example1.co.jp", hrefs)

    def test_exception_on_page1_returns_empty_list(self):
        """1ページ目で例外 → 空リスト返却"""
        with patch("agents.search_agent.requests.get", side_effect=Exception("接続エラー")), \
             patch("agents.search_agent.time.sleep"), \
             patch("config.GOOGLE_CSE_API_KEY", "test_key"), \
             patch("config.GOOGLE_CSE_CX", "test_cx"):
            result = _fetch_hits_google_cse("テスト", "qdr:m3", 50)

        self.assertEqual(result, [])

    def test_exception_on_page2_returns_page1_results_only(self):
        """2ページ目で例外 → 1ページ目の結果のみ返却"""
        page1 = _make_cse_response(["https://example0.co.jp"])
        with patch("agents.search_agent.requests.get", side_effect=[page1, Exception("タイムアウト")]), \
             patch("agents.search_agent.time.sleep"), \
             patch("config.GOOGLE_CSE_API_KEY", "test_key"), \
             patch("config.GOOGLE_CSE_CX", "test_cx"):
            result = _fetch_hits_google_cse("テスト", "qdr:m3", 50)

        self.assertEqual(len(result), 1)


# ─────────────────────────────────────────────────────────────
# 統合テスト（mock）: 上限・スリープ
# ─────────────────────────────────────────────────────────────

class TestFetchHitsGoogleCseIntegration(unittest.TestCase):
    """統合的な動作検証（上限カット・スリープ）"""

    def test_30_results_returned_when_all_3_pages_have_10_items(self):
        """全3ページが10件ずつ返す場合、合計30件が返る"""
        pages = [
            _make_cse_response([f"https://p{p}e{i}.co.jp" for i in range(10)])
            for p in range(3)
        ]
        with patch("agents.search_agent.requests.get", side_effect=pages), \
             patch("agents.search_agent.time.sleep"), \
             patch("config.GOOGLE_CSE_API_KEY", "test_key"), \
             patch("config.GOOGLE_CSE_CX", "test_cx"):
            result = _fetch_hits_google_cse("テスト", "qdr:m3", num=50)

        self.assertEqual(len(result), 30)

    def test_num_param_does_not_restrict_cse_fetch(self):
        """num=5 でも _fetch_hits_google_cse は全件返す（上限カットは search_google 側の責務）"""
        page1 = _make_cse_response([f"https://example{i}.co.jp" for i in range(10)])
        page2 = _empty_response()
        with patch("agents.search_agent.requests.get", side_effect=[page1, page2]), \
             patch("agents.search_agent.time.sleep"), \
             patch("config.GOOGLE_CSE_API_KEY", "test_key"), \
             patch("config.GOOGLE_CSE_CX", "test_cx"):
            result = _fetch_hits_google_cse("テスト", "qdr:m3", num=5)

        # _fetch_hits_google_cse は num で切らない（10件全部返す）
        self.assertEqual(len(result), 10)

    def test_page_sleep_called_between_pages(self):
        """ページ間スリープ time.sleep(1.5) がページ間で呼ばれる"""
        pages = [
            _make_cse_response([f"https://p{p}e{i}.co.jp" for i in range(10)])
            for p in range(3)
        ]
        with patch("agents.search_agent.requests.get", side_effect=pages), \
             patch("agents.search_agent.time.sleep") as mock_sleep, \
             patch("config.GOOGLE_CSE_API_KEY", "test_key"), \
             patch("config.GOOGLE_CSE_CX", "test_cx"):
            _fetch_hits_google_cse("テスト", "qdr:m3", num=50)

        # start=1→11 と start=11→21 の2回スリープ（最終ページ後はなし）
        self.assertEqual(mock_sleep.call_count, 2)
        for c in mock_sleep.call_args_list:
            self.assertEqual(c.args[0], 1.5)

    def test_no_sleep_when_page1_is_empty(self):
        """1ページ目が空の場合、スリープしない（早期終了）"""
        with patch("agents.search_agent.requests.get", return_value=_empty_response()), \
             patch("agents.search_agent.time.sleep") as mock_sleep, \
             patch("config.GOOGLE_CSE_API_KEY", "test_key"), \
             patch("config.GOOGLE_CSE_CX", "test_cx"):
            _fetch_hits_google_cse("テスト", "qdr:m3", num=50)

        mock_sleep.assert_not_called()

    def test_returns_empty_when_api_key_not_set(self):
        """APIキー未設定時は空リストを返す（既存動作の回帰確認）"""
        with patch("config.GOOGLE_CSE_API_KEY", ""), \
             patch("config.GOOGLE_CSE_CX", "test_cx"):
            result = _fetch_hits_google_cse("テスト", "qdr:m3", num=50)

        self.assertEqual(result, [])

    def test_date_restrict_passed_to_all_pages(self):
        """dateRestrict パラメータが全ページのリクエストに含まれる"""
        pages = [
            _make_cse_response([f"https://p{p}e{i}.co.jp" for i in range(10)])
            for p in range(3)
        ]
        with patch("agents.search_agent.requests.get", side_effect=pages) as mock_get, \
             patch("agents.search_agent.time.sleep"), \
             patch("config.GOOGLE_CSE_API_KEY", "test_key"), \
             patch("config.GOOGLE_CSE_CX", "test_cx"):
            _fetch_hits_google_cse("テスト", "qdr:m3", num=50)

        for c in mock_get.call_args_list:
            self.assertIn("dateRestrict", c.kwargs["params"])
            self.assertEqual(c.kwargs["params"]["dateRestrict"], "m3")

    def test_num_10_fixed_per_page_in_params(self):
        """各ページのリクエストに num=10 が含まれる（1ページあたり固定）"""
        page1 = _make_cse_response(["https://example0.co.jp"])
        page2 = _empty_response()
        with patch("agents.search_agent.requests.get", side_effect=[page1, page2]) as mock_get, \
             patch("agents.search_agent.time.sleep"), \
             patch("config.GOOGLE_CSE_API_KEY", "test_key"), \
             patch("config.GOOGLE_CSE_CX", "test_cx"):
            _fetch_hits_google_cse("テスト", "qdr:m3", num=50)

        for c in mock_get.call_args_list:
            self.assertEqual(c.kwargs["params"]["num"], 10)


if __name__ == "__main__":
    unittest.main()
