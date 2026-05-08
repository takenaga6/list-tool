# -*- coding: utf-8 -*-
"""
scripts/repair_data_apply.py のユニットテスト（Phase 7-A Step 4c）

テスト対象:
  build_patch_props  - 差分プロパティ組み立て
  _patch_company     - PATCH実行（リトライロジック含む）
  main               - 確認プロンプト "no" → 終了
"""
import csv
import io
import os
import sys
import time
import unittest
from unittest.mock import MagicMock, call, patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from scripts.repair_data_apply import (
    _SKIP_IDS,
    _patch_company,
    build_patch_props,
    load_dryrun_csv,
)


# ── テスト用ダミーデータ ──────────────────────────────────────────────────────

def _make_row(
    hubspot_id="111",
    name_old="株式会社A",
    name_new="株式会社A",
    pref_old="東京都",
    pref_new="東京都",
    addr_old="東京都渋谷区",
    addr_new="東京都渋谷区",
    changed=True,
) -> dict:
    return {
        "hubspot_id": hubspot_id,
        "会社名_元":   name_old,
        "会社名_新":   name_new,
        "都道府県_元": pref_old,
        "都道府県_新": pref_new,
        "所在地_元":   addr_old,
        "所在地_新":   addr_new,
        "変更フラグ":  str(changed),
        "修正理由":    "テスト",
    }


# ── 1. スキップリスト ────────────────────────────────────────────────────────

class TestSkipList(unittest.TestCase):
    def test_skip_id_present(self):
        """東豊精工のhubspot_idがスキップリストに含まれる"""
        self.assertIn("321669733093", _SKIP_IDS)

    def test_skip_id_is_string(self):
        """スキップリストの要素は文字列型"""
        for sid in _SKIP_IDS:
            self.assertIsInstance(sid, str)


# ── 2. 変更フラグ False はPATCHされない ──────────────────────────────────────

class TestBuildPatchProps(unittest.TestCase):
    def test_no_change_returns_empty_dict(self):
        """全フィールドが同一 → 空dictを返す"""
        row = _make_row()
        self.assertEqual(build_patch_props(row), {})

    def test_name_changed_only(self):
        """会社名だけ変わった → name のみ含む"""
        row = _make_row(name_old="株式会社A WEBサイト", name_new="株式会社A")
        props = build_patch_props(row)
        self.assertEqual(props, {"name": "株式会社A"})
        self.assertNotIn("state",   props)
        self.assertNotIn("address", props)

    def test_pref_changed_only(self):
        """都道府県だけ変わった → state のみ含む"""
        row = _make_row(pref_old="東京都", pref_new="大阪府")
        props = build_patch_props(row)
        self.assertEqual(props, {"state": "大阪府"})

    def test_address_cleared(self):
        """都道府県変更に伴い所在地がクリアされる → address="" が含まれる"""
        row = _make_row(
            pref_old="東京都", pref_new="大阪府",
            addr_old="東京都渋谷区", addr_new="",
        )
        props = build_patch_props(row)
        self.assertIn("address", props)
        self.assertEqual(props["address"], "")  # 空文字で明示クリア

    def test_city_never_in_props(self):
        """city は絶対にpropに含まれない"""
        row = _make_row(
            name_old="株式会社A WEBサイト", name_new="株式会社A",
            pref_old="東京都", pref_new="大阪府",
            addr_old="東京都渋谷区", addr_new="",
        )
        props = build_patch_props(row)
        self.assertNotIn("city", props)

    def test_all_three_changed(self):
        """名前・都道府県・所在地すべて変更 → 3フィールド含む"""
        row = _make_row(
            name_old="兵庫県西宮市｜ジェイカス株式会社",
            name_new="ジェイカス株式会社",
            pref_old="東京都", pref_new="兵庫県",
            addr_old="東京都江戸川区", addr_new="",
        )
        props = build_patch_props(row)
        self.assertEqual(set(props.keys()), {"name", "state", "address"})


# ── 3. リトライロジック ───────────────────────────────────────────────────────

class TestPatchCompanyRetry(unittest.TestCase):

    def _make_resp(self, status: int, text: str = "") -> MagicMock:
        r = MagicMock()
        r.status_code = status
        r.ok = (200 <= status < 300)
        r.text = text
        return r

    @patch("scripts.repair_data_apply.requests.patch")
    def test_success_200(self, mock_patch):
        """200 → (200, "") を返す"""
        mock_patch.return_value = self._make_resp(200)
        status, err = _patch_company("tok", "123", {"name": "A"})
        self.assertEqual(status, 200)
        self.assertEqual(err, "")
        self.assertEqual(mock_patch.call_count, 1)

    @patch("scripts.repair_data_apply.time.sleep")
    @patch("scripts.repair_data_apply.requests.patch")
    def test_429_retries_once(self, mock_patch, mock_sleep):
        """429 → 2秒スリープ後1回リトライ、2回目成功 → OK"""
        mock_patch.side_effect = [
            self._make_resp(429),
            self._make_resp(200),
        ]
        status, err = _patch_company("tok", "123", {"name": "A"})
        # sleep(2) が呼ばれた
        mock_sleep.assert_called_once_with(2)
        self.assertEqual(status, 200)
        self.assertEqual(err, "")
        self.assertEqual(mock_patch.call_count, 2)

    @patch("scripts.repair_data_apply.requests.patch")
    def test_4xx_no_retry(self, mock_patch):
        """404 → リトライなし、エラー返却"""
        mock_patch.return_value = self._make_resp(404, "not found")
        status, err = _patch_company("tok", "123", {"name": "A"})
        self.assertEqual(status, 404)
        self.assertIn("not found", err)
        self.assertEqual(mock_patch.call_count, 1)  # リトライなし

    @patch("scripts.repair_data_apply.requests.patch")
    def test_5xx_retries_once(self, mock_patch):
        """500 → 1回リトライ、2回目成功 → OK"""
        mock_patch.side_effect = [
            self._make_resp(500, "internal error"),
            self._make_resp(200),
        ]
        status, err = _patch_company("tok", "123", {"name": "A"})
        self.assertEqual(status, 200)
        self.assertEqual(err, "")
        self.assertEqual(mock_patch.call_count, 2)

    @patch("scripts.repair_data_apply.requests.patch")
    def test_timeout_retries_once(self, mock_patch):
        """タイムアウト例外 → 1回リトライ、2回目成功 → OK"""
        import requests as req_module
        mock_patch.side_effect = [
            req_module.Timeout(),
            self._make_resp(200),
        ]
        status, err = _patch_company("tok", "123", {"name": "A"})
        self.assertEqual(status, 200)
        self.assertEqual(err, "")
        self.assertEqual(mock_patch.call_count, 2)

    @patch("scripts.repair_data_apply.requests.patch")
    def test_timeout_both_fail(self, mock_patch):
        """タイムアウト2回連続 → (None, エラーメッセージ)"""
        import requests as req_module
        mock_patch.side_effect = [req_module.Timeout(), req_module.Timeout()]
        status, err = _patch_company("tok", "123", {"name": "A"})
        self.assertIsNone(status)
        self.assertIn("タイムアウト", err)


# ── 4. 確認プロンプト "no" → sys.exit ────────────────────────────────────────

class TestMainPromptCancel(unittest.TestCase):

    def _make_csv_content(self) -> str:
        fields = [
            "hubspot_id", "会社名_元", "会社名_新",
            "都道府県_元", "都道府県_新", "所在地_元", "所在地_新",
            "変更フラグ", "修正理由",
        ]
        rows = [
            {
                "hubspot_id": "999", "会社名_元": "株式会社テスト",
                "会社名_新": "株式会社テスト修正",
                "都道府県_元": "東京都", "都道府県_新": "大阪府",
                "所在地_元": "東京都渋谷区", "所在地_新": "",
                "変更フラグ": "True", "修正理由": "テスト",
            }
        ]
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        return buf.getvalue()

    @patch("builtins.input", return_value="no")
    @patch("scripts.repair_data_apply.load_dryrun_csv")
    @patch.dict(os.environ, {"HUBSPOT_TOKEN": "dummy_token_for_test"})
    def test_no_answer_exits(self, mock_load, mock_input):
        """確認プロンプトに "no" → SystemExit(0)"""
        mock_load.return_value = [
            {
                "hubspot_id": "999",
                "会社名_元": "株式会社テスト",
                "会社名_新": "株式会社テスト修正",
                "都道府県_元": "東京都",
                "都道府県_新": "大阪府",
                "所在地_元": "東京都渋谷区",
                "所在地_新": "",
                "変更フラグ": "True",
                "修正理由": "テスト",
            }
        ]

        from scripts import repair_data_apply as mod
        with patch.object(mod, "load_dryrun_csv", mock_load):
            with patch.object(mod, "IN_CSV", "/dummy/path.csv"):
                with patch("os.path.exists", return_value=True):
                    with self.assertRaises(SystemExit) as ctx:
                        mod.main()
        self.assertEqual(ctx.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
