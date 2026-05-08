# -*- coding: utf-8 -*-
"""
scripts/repair_data_dryrun.py のユニットテスト（Phase 7-A Step 3c）

テスト対象:
  _is_malformed_phone       - 電話番号フォーマット異常チェック
  repair_record             - 1件再判定ロジック（都道府県・会社名・所在地）
  fetch_list_tool_companies - HubSpot API 取得（requests.post をモック）
"""
from unittest.mock import MagicMock, patch

import pytest

from scripts.repair_data_dryrun import (
    _is_malformed_phone,
    fetch_list_tool_companies,
    repair_record,
)


# ── ヘルパー ──────────────────────────────────────────────────────────────────

def _make_record(
    hubspot_id: str,
    name: str = "",
    state: str = "",
    zip_code: str = "",
    phone: str = "",
    address: str = "",
    website: str = "",
) -> dict:
    return {
        "id": hubspot_id,
        "properties": {
            "name": name,
            "state": state,
            "zip": zip_code,
            "phone": phone,
            "address": address,
            "website": website,
            "a_12": "value",
        },
    }


# ── 1. _is_malformed_phone ───────────────────────────────────────────────────

class TestIsMalformedPhone:
    def test_normal_phone_ok(self):
        assert _is_malformed_phone("024-567-6367") is False

    def test_six_digits_malformed(self):
        # 6桁 < 9桁 → 異常
        assert _is_malformed_phone("033582") is True

    def test_eight_digits_malformed(self):
        assert _is_malformed_phone("02456763") is True

    def test_nine_digits_ok(self):
        assert _is_malformed_phone("024567636") is False

    def test_empty_not_malformed(self):
        assert _is_malformed_phone("") is False

    def test_freephone_ok(self):
        # フリーダイヤルは9桁以上あるので形式異常とは判定しない
        assert _is_malformed_phone("0120-123-456") is False


# ── 2. repair_record ─────────────────────────────────────────────────────────

class TestRepairRecordReturnShape:
    """返却 dict の構造チェック"""

    def test_all_required_keys_present(self):
        rec = _make_record("9999", name="テスト株式会社", state="東京都")
        result = repair_record(rec)
        required = {
            "hubspot_id", "会社名_元", "会社名_新",
            "都道府県_元", "都道府県_新",
            "所在地_元", "所在地_新",
            "変更フラグ", "修正理由",
        }
        assert required.issubset(result.keys())

    def test_hubspot_id_preserved(self):
        rec = _make_record("5678", name="株式会社テスト", state="東京都")
        assert repair_record(rec)["hubspot_id"] == "5678"

    def test_changed_flag_is_bool(self):
        rec = _make_record("1", name="株式会社テスト", state="東京都")
        assert isinstance(repair_record(rec)["変更フラグ"], bool)


class TestRepairRecordKnownBugs:
    """過去に誤登録された3社の修正案検証"""

    def test_shioya_unitec_pref_fixed_to_fukushima(self):
        # シオヤユニテック: 北海道(誤) → 福島県(正)
        rec = _make_record(
            "1001",
            name="シオヤユニテック",
            state="北海道",
            zip_code="960-1232",
            phone="024-567-6367",
            address="北海道○○市1-1",
        )
        result = repair_record(rec)
        assert result["都道府県_新"] == "福島県"
        assert result["変更フラグ"] is True

    def test_shioya_unitec_address_cleared(self):
        # 都道府県変更 + 所在地が「北海道」始まり → クリア
        rec = _make_record(
            "1001",
            name="シオヤユニテック",
            state="北海道",
            zip_code="960-1232",
            phone="024-567-6367",
            address="北海道○○市1-1",
        )
        assert repair_record(rec)["所在地_新"] == ""

    def test_fit_pref_fixed_to_tokyo(self):
        # Fit: 埼玉県(誤) → 東京都(正)
        rec = _make_record(
            "1002",
            name="Fit（フィット株式会社）",
            state="埼玉県",
            zip_code="186-0013",
            phone="042-521-2785",
            address="埼玉県さいたま市1-1",
        )
        result = repair_record(rec)
        assert result["都道府県_新"] == "東京都"
        assert result["変更フラグ"] is True

    def test_excelsior_pref_fixed_to_osaka(self):
        # エクセルシオ: 東京都(誤) → 大阪府(正)
        rec = _make_record(
            "1003",
            name="エクセルシオ株式会社│エクセルシオ株式会社",
            state="東京都",
            zip_code="531-0072",
            phone="06-6949-8546",
            address="東京都港区1-1",
        )
        result = repair_record(rec)
        assert result["都道府県_新"] == "大阪府"
        assert result["変更フラグ"] is True

    def test_excelsior_name_deduped(self):
        # 重複社名（A│A 形式）→ 単一社名
        rec = _make_record(
            "1003",
            name="エクセルシオ株式会社│エクセルシオ株式会社",
            state="東京都",
            zip_code="531-0072",
            phone="06-6949-8546",
        )
        assert repair_record(rec)["会社名_新"] == "エクセルシオ株式会社"


class TestRepairRecordNoChange:
    """変更不要なレコードのチェック"""

    def test_correct_record_flag_false(self):
        # 都道府県・会社名ともに正しい → 変更フラグ=False
        rec = _make_record(
            "1004",
            name="株式会社仁平電設",
            state="福島県",
            zip_code="960-1232",
            phone="024-567-6367",
            address="福島県白河市1-1",
        )
        assert repair_record(rec)["変更フラグ"] is False

    def test_address_preserved_when_pref_unchanged(self):
        # 都道府県変更なし → 所在地はそのまま
        rec = _make_record(
            "2001",
            name="テスト株式会社",
            state="福島県",
            zip_code="960-1232",
            phone="024-567-6367",
            address="福島県郡山市1-1",
        )
        assert repair_record(rec)["所在地_新"] == "福島県郡山市1-1"

    def test_address_preserved_when_already_starts_with_new_pref(self):
        # 都道府県変更あり・所在地が新都道府県で始まる → クリアしない
        rec = _make_record(
            "2002",
            name="テスト株式会社",
            state="北海道",
            zip_code="531-0072",
            phone="06-6949-8546",
            address="大阪府大阪市北区1-1",
        )
        result = repair_record(rec)
        assert result["都道府県_新"] == "大阪府"
        assert result["所在地_新"] == "大阪府大阪市北区1-1"


class TestRepairRecordEdgeCases:
    """電話番号異常・判定不能などの境界ケース"""

    def test_malformed_phone_in_reason(self):
        # 電話番号フォーマット異常 → 修正理由に記録
        rec = _make_record(
            "1005",
            name="テスト株式会社",
            state="東京都",
            zip_code="100-0001",
            phone="033582",
        )
        assert "電話番号フォーマット異常" in repair_record(rec)["修正理由"]

    def test_no_zip_no_phone_keeps_existing_pref(self):
        # 郵便+電話なし → 判定不能 → 既存都道府県維持・フラグFalse
        rec = _make_record(
            "1006",
            name="テスト株式会社",
            state="大阪府",
            zip_code="",
            phone="",
        )
        result = repair_record(rec)
        assert result["都道府県_新"] == "大阪府"
        assert result["変更フラグ"] is False
        assert "判定不能" in result["修正理由"]

    def test_empty_name_not_overwritten(self):
        # _clean_company_name が空文字 → 既存値を維持（安全ガード）
        rec = _make_record("7001", name="", state="東京都", zip_code="100-0001")
        result = repair_record(rec)
        assert result["会社名_新"] == ""


# ── 3. fetch_list_tool_companies — HubSpot API モック ─────────────────────

class TestFetchListToolCompanies:

    @staticmethod
    def _mock_response(results: list, after: str | None = None) -> MagicMock:
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        data: dict = {"results": results}
        if after:
            data["paging"] = {"next": {"after": after}}
        resp.json.return_value = data
        return resp

    def test_single_page(self):
        companies = [{"id": "1", "properties": {"name": "テスト株式会社"}}]
        with patch("scripts.repair_data_dryrun.requests.post") as mock_post:
            mock_post.return_value = self._mock_response(companies)
            result = fetch_list_tool_companies("dummy_token")
        assert len(result) == 1
        assert result[0]["id"] == "1"

    def test_pagination_all_pages_fetched(self):
        # 1ページ目: 100件 + cursor → 2ページ目: 50件
        page1 = [{"id": str(i), "properties": {}} for i in range(100)]
        page2 = [{"id": str(i), "properties": {}} for i in range(100, 150)]
        with patch("scripts.repair_data_dryrun.requests.post") as mock_post:
            mock_post.side_effect = [
                self._mock_response(page1, after="cursor_abc"),
                self._mock_response(page2, after=None),
            ]
            result = fetch_list_tool_companies("dummy_token")
        assert len(result) == 150

    def test_api_error_returns_empty_list(self):
        # API エラー時はクラッシュせずリストを返す
        resp = MagicMock()
        resp.raise_for_status.side_effect = Exception("500 Server Error")
        with patch("scripts.repair_data_dryrun.requests.post") as mock_post:
            mock_post.return_value = resp
            result = fetch_list_tool_companies("dummy_token")
        assert isinstance(result, list)

    def test_empty_results(self):
        with patch("scripts.repair_data_dryrun.requests.post") as mock_post:
            mock_post.return_value = self._mock_response([])
            result = fetch_list_tool_companies("dummy_token")
        assert result == []
