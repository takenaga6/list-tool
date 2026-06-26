"""回収トラック（list-rank-validation）: 構造化シグナル永続化の単体テスト。

カバー範囲:
  1. evaluate_rank_v2 が構造化シグナル(S1〜S10)+ rank_version を返すこと
     （Finding-2 のバグ修正: 以前は "signals" を返さず main.py で常に空だった）
  2. evaluate_useful_conditions の return_signals オプション
  3. build_wb_signal_props 純粋関数（wb_sig_* props 組み立て）
  4. ENABLE_WB_SIGNALS のデフォルトが OFF であること（本番安全性）
"""

import re
import unittest

from agents.rank_agent import evaluate_rank_v2, evaluate_useful_conditions
from agents.hubspot_agent import build_wb_signal_props


# 健康経営 + ISO + SDGs + 福利厚生 を含む、非NG・複数シグナル該当のHP本文
_RICH_PAGE_TEXT = (
    "私たちは健康経営を推進し、健康経営優良法人2024に認定されています。"
    "ISO9001を取得しています。SDGsへの取り組みを推進しています。"
    "福利厚生として人間ドックを提供しています。"
)


class TestEvaluateRankV2Signals(unittest.TestCase):
    """evaluate_rank_v2 が構造化シグナルを返すことを確認（Finding-2 バグ修正）。"""

    def _eval(self):
        company_info = {
            "company_name": "株式会社テスト",
            "industry": "サービス業",
            "employee_count": "80",
            "address": "東京都千代田区丸の内1-1-1",
        }
        search_results = [{"url": "https://test.co.jp", "title": "", "snippet": ""}]
        return evaluate_rank_v2(company_info, search_results, page_text=_RICH_PAGE_TEXT)

    def test_v2_returns_signals_dict_with_s1_to_s10(self):
        """戻り値に S1〜S10 をすべて含む signals dict がある."""
        result = self._eval()
        self.assertIn("signals", result, "evaluate_rank_v2 が signals を返していない（旧バグ）")
        for i in range(1, 11):
            self.assertIn(f"S{i}", result["signals"], f"S{i} が signals に含まれない")
        for v in result["signals"].values():
            self.assertIsInstance(v, bool)

    def test_v2_detects_expected_signals(self):
        """ISO(S7)・SDGs(S8)・健康経営(S4) が True として表面化する."""
        result = self._eval()
        sig = result["signals"]
        self.assertTrue(sig["S7"], "ISO認定(S7)が検出されなかった")
        self.assertTrue(sig["S8"], "SDGs(S8)が検出されなかった")
        self.assertTrue(sig["S4"], "健康経営(S4)が検出されなかった")
        self.assertNotEqual(result["rank"], "NG")

    def test_v2_includes_rank_version(self):
        """rank_version が含まれる（wb_rank_version 用）."""
        from config import RANK_LOGIC_VERSION
        result = self._eval()
        self.assertEqual(result["rank_version"], RANK_LOGIC_VERSION)

    def test_v2_ng_path_still_returns_signals(self):
        """NG企業でも signals(全False)+rank_version を返す（書き込み側が落ちない）."""
        company_info = {
            "company_name": "テストメディア株式会社",
            "industry": "デジタルマーケティング",   # Phase1 NG業種（残存5語の1つ）
            "employee_count": "80",
        }
        search_results = [{"url": "https://ng.co.jp", "title": "", "snippet": ""}]
        result = evaluate_rank_v2(company_info, search_results, page_text=_RICH_PAGE_TEXT)
        self.assertEqual(result["rank"], "NG")
        self.assertIn("signals", result)
        self.assertEqual(len(result["signals"]), 10)
        self.assertTrue(all(v is False for v in result["signals"].values()))


class TestEvaluateUsefulConditionsReturnSignals(unittest.TestCase):
    """evaluate_useful_conditions の return_signals オプション."""

    def test_default_returns_two_tuple(self):
        """後方互換: return_signals 省略時は (score, reasons) の2要素."""
        out = evaluate_useful_conditions({"industry": "サービス業"}, _RICH_PAGE_TEXT)
        self.assertEqual(len(out), 2)
        score, reasons = out
        self.assertIsInstance(score, int)
        self.assertIsInstance(reasons, list)

    def test_return_signals_returns_three_tuple(self):
        """return_signals=True で (score, reasons, signals) の3要素."""
        out = evaluate_useful_conditions(
            {"industry": "サービス業"}, _RICH_PAGE_TEXT, return_signals=True
        )
        self.assertEqual(len(out), 3)
        _, _, signals = out
        self.assertIn("s7_iso", signals)
        self.assertTrue(signals["s7_iso"])


class TestBuildWbSignalProps(unittest.TestCase):
    """build_wb_signal_props 純粋関数."""

    def _sample(self):
        return {
            "signals": {
                "S1": True, "S2": False, "S3": True, "S4": True, "S5": False,
                "S6": False, "S7": True, "S8": True, "S9": False, "S10": False,
            },
            "score": 7,
            "rank_version": "2026-06",
        }

    def test_bool_signals_to_string(self):
        props = build_wb_signal_props(self._sample())
        self.assertEqual(props["wb_sig_s1"], "true")
        self.assertEqual(props["wb_sig_s2"], "false")
        self.assertEqual(props["wb_sig_s7"], "true")

    def test_score_and_version(self):
        props = build_wb_signal_props(self._sample())
        self.assertEqual(props["wb_sig_score"], "7")
        self.assertEqual(props["wb_rank_version"], "2026-06")

    def test_lead_source_defaults_to_list(self):
        props = build_wb_signal_props(self._sample())
        self.assertEqual(props["wb_lead_source_type"], "list")

    def test_lead_source_override(self):
        data = self._sample()
        data["wb_lead_source_type"] = "紹介"
        props = build_wb_signal_props(data)
        self.assertEqual(props["wb_lead_source_type"], "紹介")

    def test_ranked_at_is_iso_date(self):
        props = build_wb_signal_props(self._sample())
        self.assertRegex(props["wb_ranked_at"], r"^\d{4}-\d{2}-\d{2}$")

    def test_missing_signals_omitted(self):
        """signals が欠けたキーは props に出さない（None スキップ）."""
        props = build_wb_signal_props({"signals": {"S1": True}, "score": 1})
        self.assertIn("wb_sig_s1", props)
        self.assertNotIn("wb_sig_s2", props)

    def test_empty_company_data_uses_defaults(self):
        """signals/score なしでも例外を出さず、version/source/date は埋まる."""
        from config import RANK_LOGIC_VERSION
        props = build_wb_signal_props({})
        self.assertEqual(props["wb_rank_version"], RANK_LOGIC_VERSION)
        self.assertEqual(props["wb_lead_source_type"], "list")
        self.assertNotIn("wb_sig_score", props)


class TestFeatureFlagSafety(unittest.TestCase):
    """本番安全性: wb_* 書き込みはデフォルト OFF。"""

    def test_enable_wb_signals_default_off(self):
        """環境変数未設定時、ENABLE_WB_SIGNALS は False（プロパティ未作成のため）."""
        import os
        if os.environ.get("ENABLE_WB_SIGNALS"):
            self.skipTest("ENABLE_WB_SIGNALS が環境にセットされているためスキップ")
        import importlib
        import config
        importlib.reload(config)
        self.assertFalse(config.ENABLE_WB_SIGNALS)


if __name__ == "__main__":
    unittest.main()
