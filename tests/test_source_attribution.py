"""source不一致バグ修正の検証（2026-06-04）

バグ: record_hit は source="search:期間" 付きだが、record_ng / record_rank_result は
source 無し（デフォルト "search"）で記録されていた。ヒットと A/B・NG が別バケツに入り、
get_media_stats() が媒体別 A率 を正しく出せなかった。

修正: main.py で各 result に _source を刻み、record_hit / record_ng / record_rank_result の
source を一致させる。本テストは「同一 source で記録すれば get_media_stats が
1エントリに集約され A率/NG率が正しく出る」という不変条件を保証する。
"""
import os
import tempfile
import unittest

from filelock import FileLock

import agents.keyword_agent as ka


class TestSourceAttribution(unittest.TestCase):
    def setUp(self):
        # stats ファイルを一時ファイルにリダイレクト（実データを汚さない）
        self._tmp = tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w", encoding="utf-8"
        )
        self._tmp.write('{"_version": "2.0", "queries": {}}')
        self._tmp.close()
        self._orig_file = ka.KEYWORD_STATS_FILE
        self._orig_lock = ka._STATS_LOCK
        ka.KEYWORD_STATS_FILE = self._tmp.name
        ka._STATS_LOCK = FileLock(self._tmp.name + ".lock", timeout=10)

    def tearDown(self):
        ka.KEYWORD_STATS_FILE = self._orig_file
        ka._STATS_LOCK = self._orig_lock
        for p in (self._tmp.name, self._tmp.name + ".lock"):
            if os.path.exists(p):
                os.remove(p)

    def test_consistent_source_aggregates_into_one_media_entry(self):
        """hit / rank / ng を同一 source で記録 → get_media_stats が1エントリに集約"""
        src = "search:1週間"
        ka.record_hit("健康経営 株式会社", 10, source=src)
        ka.record_rank_result("健康経営 株式会社", "A", source=src)
        ka.record_ng("健康経営 株式会社", source=src)

        media = ka.get_media_stats()
        self.assertEqual(len(media), 1, "同一 source なら媒体エントリは1つに集約されるはず")
        m = media[0]
        self.assertEqual(m["source"], src)
        self.assertEqual(m["total_hits"], 10)
        self.assertEqual(m["a_rank"], 1)
        self.assertEqual(m["ng_count"], 1)
        # A率 = a_rank / (a+b+ng) = 1 / (1+0+1) = 0.5
        self.assertAlmostEqual(m["a_rate"], 0.5)

    def test_split_source_reproduces_old_bug(self):
        """旧バグ再現: hit と rank/ng が別 source → 媒体エントリが分裂し A率が出ない

        修正後コードはこの分裂を起こさないが、データモデル上「別 source で記録すると
        分裂する」ことを明示し、回帰時に気づけるようにする。
        """
        ka.record_hit("健康経営 株式会社", 10, source="search:1週間")
        ka.record_rank_result("健康経営 株式会社", "A", source="search")  # 旧バグ相当
        ka.record_ng("健康経営 株式会社", source="search")

        media = {m["source"]: m for m in ka.get_media_stats()}
        # ヒットだけの "search:1週間" と、ランク/NGだけの "search" に分裂する
        self.assertIn("search:1週間", media)
        self.assertIn("search", media)
        self.assertEqual(media["search:1週間"]["a_rank"], 0)   # ヒット側にA率情報がない
        self.assertEqual(media["search:1週間"]["a_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
