# -*- coding: utf-8 -*-
"""
scripts/repair_data_apply.py のユニットテスト（Phase 7-A Step 4c）

テスト対象:
  build_patch_props  - 差分プロパティ組み立て
  _patch_company     - PATCH実行（リトライロジック含む）
  init_log_file      - ヘッダー書き込み（新規時のみ）
  append_log_row     - 即書き込み（追記モード）
  main               - 確認プロンプト / ループ内即書き込み検証
"""
import csv
import io
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, call, patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from scripts.repair_data_apply import (
    _LOG_FIELDS,
    _SKIP_IDS,
    _patch_company,
    append_log_row,
    build_patch_props,
    init_log_file,
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


# ── 5. 即書き込み検証 ─────────────────────────────────────────────────────────

class TestImmediateLogWrite(unittest.TestCase):
    """ログが1件ごとに即書き込みされることを検証する。"""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._log_path = os.path.join(self._tmpdir, "repair_apply_log.csv")

    def _patch_out_log(self, mod):
        """OUT_LOG_CSV をテンポラリパスに差し替えるコンテキストマネージャを返す。"""
        return patch.object(mod, "OUT_LOG_CSV", self._log_path)

    def test_init_log_file_creates_header(self):
        """ファイルが存在しない → ヘッダー行が書き込まれる"""
        from scripts import repair_data_apply as mod
        with self._patch_out_log(mod):
            init_log_file()
        with open(self._log_path, encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            header = next(reader)
        self.assertEqual(header, _LOG_FIELDS)

    def test_init_log_file_no_overwrite(self):
        """ファイルが既存 → 上書きしない（既存内容を保持）"""
        # 先にダミー内容を書き込む
        with open(self._log_path, "w", encoding="utf-8-sig") as f:
            f.write("existing content\n")
        from scripts import repair_data_apply as mod
        with self._patch_out_log(mod):
            init_log_file()
        with open(self._log_path, encoding="utf-8-sig") as f:
            content = f.read()
        self.assertEqual(content, "existing content\n")

    def test_append_log_row_writes_correct_columns(self):
        """append_log_row が正しいカラム値を書き込む"""
        # ヘッダーを先に作成
        with open(self._log_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_LOG_FIELDS)
            writer.writeheader()

        row = _make_row(
            hubspot_id="999",
            name_old="株式会社テスト WEB", name_new="株式会社テスト",
            pref_old="東京都", pref_new="大阪府",
            addr_old="東京都渋谷区", addr_new="",
        )
        from scripts import repair_data_apply as mod
        with self._patch_out_log(mod):
            append_log_row(row, result="OK", status=200, note="")

        with open(self._log_path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["hubspot_id"],   "999")
        self.assertEqual(r["会社名_元"],     "株式会社テスト WEB")
        self.assertEqual(r["会社名_新"],     "株式会社テスト")
        self.assertEqual(r["都道府県_元"],   "東京都")
        self.assertEqual(r["都道府県_新"],   "大阪府")
        self.assertEqual(r["所在地_元"],     "東京都渋谷区")
        self.assertEqual(r["所在地_新"],     "")
        self.assertEqual(r["適用結果"],      "OK")
        self.assertEqual(r["HTTPステータス"], "200")
        self.assertEqual(r["備考"],          "")
        # 実行日時は ISO 形式の文字列として存在する
        self.assertTrue(r["実行日時"])

    def test_append_log_row_accumulates(self):
        """複数回 append_log_row を呼ぶと行が積み上がる（バッチ書き込みではない）"""
        with open(self._log_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_LOG_FIELDS)
            writer.writeheader()

        row1 = _make_row(hubspot_id="001", pref_old="東京都", pref_new="大阪府")
        row2 = _make_row(hubspot_id="002", pref_old="千葉県", pref_new="埼玉県")
        from scripts import repair_data_apply as mod
        with self._patch_out_log(mod):
            append_log_row(row1, result="OK",     status=200, note="")
            append_log_row(row2, result="failed", status=404, note="not found")

        with open(self._log_path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["hubspot_id"], "001")
        self.assertEqual(rows[0]["適用結果"],    "OK")
        self.assertEqual(rows[1]["hubspot_id"], "002")
        self.assertEqual(rows[1]["適用結果"],    "failed")

    @patch("scripts.repair_data_apply.time.sleep")
    @patch("scripts.repair_data_apply.requests.patch")
    @patch("builtins.input", return_value="yes")
    @patch("scripts.repair_data_apply.load_dryrun_csv")
    @patch.dict(os.environ, {"HUBSPOT_TOKEN": "dummy_token_for_test"})
    def test_main_writes_log_per_record(self, mock_load, mock_input, mock_req, mock_sleep):
        """main() が PATCH 1件ごとに append_log_row を即呼び出しすること"""
        row1 = _make_row(hubspot_id="001", pref_old="東京都", pref_new="大阪府")
        row2 = _make_row(hubspot_id="002", pref_old="千葉県", pref_new="埼玉県")
        mock_load.return_value = [row1, row2]

        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.ok = True
        ok_resp.text = ""
        mock_req.return_value = ok_resp

        from scripts import repair_data_apply as mod

        # os.path.exists は IN_CSV(/dummy/path.csv) のみ True を返し、
        # それ以外（ログファイル等）は実際のファイルシステムを参照する
        _real_exists = os.path.exists
        def _selective_exists(path: str) -> bool:
            if path == "/dummy/path.csv":
                return True
            return _real_exists(path)

        with self._patch_out_log(mod):
            with patch.object(mod, "IN_CSV", "/dummy/path.csv"):
                with patch("os.path.exists", side_effect=_selective_exists):
                    mod.main()

        with open(self._log_path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["hubspot_id"], "001")
        self.assertEqual(rows[0]["適用結果"],    "OK")
        self.assertEqual(rows[1]["hubspot_id"], "002")
        self.assertEqual(rows[1]["適用結果"],    "OK")

    @patch("scripts.repair_data_apply.time.sleep")
    @patch("scripts.repair_data_apply.requests.patch")
    @patch("builtins.input", return_value="yes")
    @patch("scripts.repair_data_apply.load_dryrun_csv")
    @patch.dict(os.environ, {"HUBSPOT_TOKEN": "dummy_token_for_test"})
    def test_main_logs_before_exception(self, mock_load, mock_input, mock_req, mock_sleep):
        """
        1件目成功後に2件目でキーボード割り込み → ループ中断前の1件がログ済みであること。
        （バッチ書き込みなら0件になるが、即書き込みなら1件残る）

        KeyboardInterrupt は BaseException のため _patch_company 内の
        except Exception では捕捉されず、確実にループを中断する。
        """
        row1 = _make_row(hubspot_id="001", pref_old="東京都", pref_new="大阪府")
        row2 = _make_row(hubspot_id="002", pref_old="千葉県", pref_new="埼玉県")
        mock_load.return_value = [row1, row2]

        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.ok = True
        ok_resp.text = ""
        # 1件目成功、2件目で KeyboardInterrupt（BaseException → except Exception に捕捉されない）
        mock_req.side_effect = [ok_resp, KeyboardInterrupt()]

        _real_exists = os.path.exists
        def _selective_exists(path: str) -> bool:
            if path == "/dummy/path.csv":
                return True
            return _real_exists(path)

        from scripts import repair_data_apply as mod
        with self._patch_out_log(mod):
            with patch.object(mod, "IN_CSV", "/dummy/path.csv"):
                with patch("os.path.exists", side_effect=_selective_exists):
                    with self.assertRaises(KeyboardInterrupt):
                        mod.main()

        with open(self._log_path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        # 1件目のログは即書き込みされているので残っている（バッチなら0件）
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["hubspot_id"], "001")
        self.assertEqual(rows[0]["適用結果"],    "OK")


if __name__ == "__main__":
    unittest.main()
