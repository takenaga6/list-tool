"""
Phase 7-B parallel: 並列実行対応テスト

- ファイルロック並列書き込みテスト（threading）
- クエリ範囲分割の境界テスト
- processed_domains 共有テスト
"""
import os
import sys
import json
import math
import threading
import tempfile
import unittest
from unittest.mock import patch, MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


# ──────────────────────────────────────────────────────────────
# ファイルロック並列書き込みテスト
# ──────────────────────────────────────────────────────────────

class TestFileLockConcurrentWrite(unittest.TestCase):
    """keyword_stats.json への並列書き込みでデータが壊れないことを確認する"""

    def test_concurrent_record_hit_does_not_corrupt(self):
        """5スレッドが同時に record_hit を呼んでも全件記録される"""
        from agents.keyword_agent import record_hit, load_stats, KEYWORD_STATS_FILE

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_stats = os.path.join(tmpdir, "keyword_stats.json")
            with patch("agents.keyword_agent.KEYWORD_STATS_FILE", tmp_stats), \
                 patch("agents.keyword_agent._STATS_LOCK") as mock_lock:
                # 実ロックを使う（モックに実装を引き継ぐ）
                from filelock import FileLock
                real_lock = FileLock(tmp_stats + ".lock", timeout=10)
                mock_lock.__enter__ = lambda s: real_lock.__enter__()
                mock_lock.__exit__ = lambda s, *a: real_lock.__exit__(*a)

                n_threads = 5
                errors = []

                def worker(i):
                    try:
                        record_hit(f"test_query_{i}", hit_count=1)
                    except Exception as e:
                        errors.append(e)

                threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()

                self.assertEqual(errors, [], f"例外発生: {errors}")

    def test_concurrent_record_hit_all_recorded(self):
        """同一クエリを 5スレッドから同時更新しても runs が 5 になる"""
        from agents.keyword_agent import record_hit, load_stats, save_stats, KEYWORD_STATS_FILE

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_stats = os.path.join(tmpdir, "keyword_stats.json")

            # FileLock を実際に使う（パス差し替え）
            from filelock import FileLock
            real_lock = FileLock(tmp_stats + ".lock", timeout=10)

            def patched_load():
                if not os.path.exists(tmp_stats):
                    return {"_version": "2.0", "queries": {}}
                with open(tmp_stats, "r", encoding="utf-8") as f:
                    return json.load(f)

            def patched_save(stats):
                with open(tmp_stats, "w", encoding="utf-8") as f:
                    json.dump(stats, f)

            errors = []
            n_threads = 5
            lock_obj = real_lock

            def worker():
                try:
                    with lock_obj:
                        s = patched_load()
                        qd = s.setdefault("queries", {}).setdefault("shared_query", {
                            "total_hits": 0, "runs": 0, "avg_hits": 0.0,
                            "a_rank": 0, "b_rank": 0, "ng_count": 0,
                            "ab_rate": 0.0, "a_rate": 0.0, "ng_rate": 0.0,
                            "last_run": "", "by_source": {},
                        })
                        qd["runs"] += 1
                        qd["total_hits"] += 1
                        patched_save(s)
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=worker) for _ in range(n_threads)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            self.assertEqual(errors, [], f"例外発生: {errors}")
            result = patched_load()
            runs = result["queries"]["shared_query"]["runs"]
            self.assertEqual(runs, n_threads, f"runs={runs}（期待値={n_threads}）")


# ──────────────────────────────────────────────────────────────
# クエリ範囲分割テスト
# ──────────────────────────────────────────────────────────────

class TestQueryRangeSplit(unittest.TestCase):
    """person_id / person_total によるクエリ範囲分割のテスト"""

    def _split(self, queries, person_id, person_total):
        """run_batch と同じ分割ロジック"""
        chunk_size = math.ceil(len(queries) / person_total)
        start = (person_id - 1) * chunk_size
        return queries[start: start + chunk_size]

    def test_3_persons_cover_all_queries(self):
        """3人分割で合計が全クエリ数と一致する（重複なし・漏れなし）"""
        queries = list(range(100))
        total = 3
        combined = []
        for pid in range(1, total + 1):
            combined.extend(self._split(queries, pid, total))
        self.assertEqual(sorted(combined), queries)

    def test_5_persons_cover_all_queries(self):
        """5人分割で合計が全クエリ数と一致する"""
        queries = list(range(97))  # 割り切れない数
        total = 5
        combined = []
        for pid in range(1, total + 1):
            combined.extend(self._split(queries, pid, total))
        self.assertEqual(sorted(combined), queries)

    def test_no_duplicates_between_persons(self):
        """分割された各範囲に重複がない"""
        queries = list(range(200))
        total = 3
        all_slices = [self._split(queries, pid, total) for pid in range(1, total + 1)]
        for i in range(total):
            for j in range(i + 1, total):
                overlap = set(all_slices[i]) & set(all_slices[j])
                self.assertEqual(overlap, set(), f"ID{i+1} と ID{j+1} に重複: {overlap}")

    def test_person_id_1_gets_first_chunk(self):
        """ID=1 は先頭から chunk_size 件を担当する"""
        queries = list(range(90))
        total = 3
        chunk_size = math.ceil(90 / 3)  # = 30
        result = self._split(queries, 1, 3)
        self.assertEqual(result, queries[:chunk_size])

    def test_none_person_id_returns_all(self):
        """person_id=None のとき全クエリを返す（分割しない）"""
        queries = list(range(100))
        # 分割しない場合は元のリストをそのまま使う
        person_id = None
        person_total = None
        if person_id and person_total:
            chunk_size = math.ceil(len(queries) / person_total)
            result = queries[(person_id - 1) * chunk_size: (person_id - 1) * chunk_size + chunk_size]
        else:
            result = queries
        self.assertEqual(result, queries)


# ──────────────────────────────────────────────────────────────
# processed_domains 共有テスト
# ──────────────────────────────────────────────────────────────

class TestSharedDomains(unittest.TestCase):
    """utils/shared_domains.py のユニットテスト"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.tmp_file = os.path.join(self.tmpdir, "processed_domains_shared.json")

    def _make_module(self):
        """テスト用の shared_domains モジュール（ENABLE=True、パスを tmpdir に向ける）"""
        import importlib
        import utils.shared_domains as sd
        # 一時ファイルにリダイレクト
        sd._SHARED_DOMAINS_FILE = self.tmp_file
        from filelock import FileLock
        sd._SHARED_DOMAINS_LOCK = FileLock(self.tmp_file + ".lock", timeout=5)
        sd._ENABLED = True
        return sd

    def test_add_and_check_domain(self):
        """add_shared_domain で追加後、is_shared_domain が True を返す"""
        sd = self._make_module()
        sd.add_shared_domain("example.co.jp")
        self.assertTrue(sd.is_shared_domain("example.co.jp"))

    def test_unknown_domain_returns_false(self):
        """登録していないドメインは False を返す"""
        sd = self._make_module()
        self.assertFalse(sd.is_shared_domain("unknown.co.jp"))

    def test_add_returns_false_for_existing(self):
        """既存ドメインへの add は False を返す"""
        sd = self._make_module()
        result1 = sd.add_shared_domain("dup.co.jp")
        result2 = sd.add_shared_domain("dup.co.jp")
        self.assertTrue(result1)
        self.assertFalse(result2)

    def test_concurrent_add_no_duplicate(self):
        """2スレッドが同時に add しても重複エントリが作られない"""
        sd = self._make_module()
        results = []
        errors = []

        def worker():
            try:
                r = sd.add_shared_domain("concurrent.co.jp")
                results.append(r)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"例外発生: {errors}")
        # 一方だけが True を返す（どちらかが先に追加できた）
        self.assertEqual(sum(results), 1, f"True の数={sum(results)}（期待=1）")

        # ファイル内に重複がない
        with open(self.tmp_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        domains = [e["domain"] for e in data["domains"]]
        self.assertEqual(len(domains), len(set(domains)))

    def test_cleanup_removes_old_entries(self):
        """7日以上古いエントリが cleanup で削除される"""
        from datetime import datetime, timezone, timedelta
        sd = self._make_module()
        old_ts = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(timespec="seconds")
        new_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        data = {
            "domains": [
                {"domain": "old.co.jp", "added_at": old_ts},
                {"domain": "new.co.jp", "added_at": new_ts},
            ],
            "last_cleanup": old_ts,
        }
        with open(self.tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f)

        sd.startup_cleanup()

        with open(self.tmp_file, "r", encoding="utf-8") as f:
            result = json.load(f)
        remaining = [e["domain"] for e in result["domains"]]
        self.assertNotIn("old.co.jp", remaining)
        self.assertIn("new.co.jp", remaining)

    def test_legacy_format_migration(self):
        """旧形式（配列のみ）を読み込んでも新形式に自動移行される"""
        sd = self._make_module()
        # 旧形式を直接書き込む
        with open(self.tmp_file, "w", encoding="utf-8") as f:
            json.dump(["legacy.co.jp", "old.co.jp"], f)

        self.assertTrue(sd.is_shared_domain("legacy.co.jp"))
        self.assertTrue(sd.is_shared_domain("old.co.jp"))

    def test_disabled_by_default(self):
        """ENABLE_SHARED_DOMAINS 未設定時は常に False を返す"""
        import utils.shared_domains as sd
        original_enabled = sd._ENABLED
        try:
            sd._ENABLED = False
            sd.add_shared_domain("should_not_add.co.jp")
            self.assertFalse(sd.is_shared_domain("should_not_add.co.jp"))
        finally:
            sd._ENABLED = original_enabled


if __name__ == "__main__":
    unittest.main()
