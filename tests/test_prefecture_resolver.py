# -*- coding: utf-8 -*-
"""utils/prefecture_resolver.py のユニットテスト"""
import logging
import pytest

from utils.prefecture_resolver import (
    postal_code_to_prefecture,
    phone_to_prefecture,
    extract_prefecture_with_voting,
)


# ── 1. postal_code_to_prefecture ────────────────────────────────────────────

class TestPostalCodeToPrefecture:
    def test_fukushima(self):
        assert postal_code_to_prefecture("960-1232") == "福島県"

    def test_tokyo(self):
        assert postal_code_to_prefecture("186-0013") == "東京都"

    def test_osaka(self):
        assert postal_code_to_prefecture("531-0072") == "大阪府"

    def test_hokkaido_low_range(self):
        # 001-009 range: ゼロ埋め3桁キーで正しく引けること
        assert postal_code_to_prefecture("001-0000") == "北海道"

    def test_tokyo_chiyoda(self):
        assert postal_code_to_prefecture("100-0001") == "東京都"

    def test_hokkaido_sapporo(self):
        assert postal_code_to_prefecture("060-0001") == "北海道"

    # ── 不正入力（エラーで落ちない・None返却）──
    def test_empty_string(self):
        assert postal_code_to_prefecture("") is None

    def test_non_digit_only(self):
        assert postal_code_to_prefecture("abc-defg") is None

    def test_too_short(self):
        assert postal_code_to_prefecture("12") is None

    def test_long_input_no_crash(self):
        # 長すぎる入力でもエラーにならないこと
        result = postal_code_to_prefecture("1234567890")
        assert result is None or isinstance(result, str)


# ── 2. phone_to_prefecture ──────────────────────────────────────────────────

class TestPhoneToPrefecture:
    def test_tokyo_03(self):
        assert phone_to_prefecture("03-1234-5678") == "東京都"

    def test_osaka_06(self):
        assert phone_to_prefecture("06-1234-5678") == "大阪府"

    def test_fukushima_024(self):
        assert phone_to_prefecture("024-567-6367") == "福島県"

    def test_tokyo_042(self):
        assert phone_to_prefecture("042-521-2785") == "東京都"

    def test_osaka_06_full(self):
        assert phone_to_prefecture("06-6949-8546") == "大阪府"

    # ── フリーダイヤル/IP電話スキップ ──
    def test_freephone_0120(self):
        assert phone_to_prefecture("0120-123-456") is None

    def test_freephone_0800(self):
        assert phone_to_prefecture("0800-123-4567") is None

    def test_ip_phone_050(self):
        assert phone_to_prefecture("050-1234-5678") is None

    # ── 不正入力（エラーで落ちない・None返却）──
    def test_empty_string(self):
        assert phone_to_prefecture("") is None

    def test_japanese_text(self):
        assert phone_to_prefecture("電話なし") is None

    def test_alphabet_only(self):
        assert phone_to_prefecture("abc") is None

    def test_too_short_digits(self):
        assert phone_to_prefecture("12345") is None


# ── 3. extract_prefecture_with_voting ───────────────────────────────────────

class TestExtractPrefectureWithVoting:

    # ── 郵便+電話が一致 ──
    def test_postal_and_phone_match_fukushima(self):
        assert extract_prefecture_with_voting("960-1232", "024-567-6367", "") == "福島県"

    def test_postal_and_phone_match_tokyo(self):
        assert extract_prefecture_with_voting("186-0013", "042-521-2785", "") == "東京都"

    def test_postal_and_phone_match_osaka(self):
        assert extract_prefecture_with_voting("531-0072", "06-6949-8546", "") == "大阪府"

    # ── 郵便のみ ──
    def test_postal_only_tokyo(self):
        assert extract_prefecture_with_voting("100-0001", "", "") == "東京都"

    def test_postal_only_hokkaido(self):
        assert extract_prefecture_with_voting("060-0001", "", "") == "北海道"

    # ── 電話のみ ──
    def test_phone_only_tokyo(self):
        assert extract_prefecture_with_voting("", "03-1234-5678", "") == "東京都"

    def test_phone_only_osaka(self):
        assert extract_prefecture_with_voting("", "06-1234-5678", "") == "大阪府"

    # ── 矛盾ケース（郵便優先 + 警告ログ）──
    def test_conflict_postal_wins(self, caplog):
        with caplog.at_level(logging.WARNING, logger="utils.prefecture_resolver"):
            result = extract_prefecture_with_voting("100-0001", "06-1234-5678", "")
        assert result == "東京都"

    def test_conflict_emits_warning_log(self, caplog):
        with caplog.at_level(logging.WARNING, logger="utils.prefecture_resolver"):
            extract_prefecture_with_voting("100-0001", "06-1234-5678", "")
        assert "ADDRESS_CONFLICT" in caplog.text

    # ── フリーダイヤルがあっても郵便で正しく判定 ──
    def test_postal_wins_over_freephone(self):
        assert extract_prefecture_with_voting("100-0001", "0120-123-456", "") == "東京都"

    def test_postal_wins_over_ip_phone(self):
        assert extract_prefecture_with_voting("100-0001", "050-1234-5678", "") == "東京都"

    # ── フリーダイヤルのみ・郵便なし → 空文字 ──
    def test_freephone_only_returns_empty(self):
        assert extract_prefecture_with_voting("", "0120-123-456", "") == ""

    def test_ip_phone_only_returns_empty(self):
        assert extract_prefecture_with_voting("", "0800-123-4567", "") == ""

    def test_050_only_returns_empty(self):
        assert extract_prefecture_with_voting("", "050-1234-5678", "") == ""

    # ── HP本文フォールバック ──
    def test_hp_fallback_last_position_wins_on_tie(self):
        # 出現回数が同数の場合、後方（末尾＝本社住所フッター）を優先
        text = "北海道支店について詳しくはこちら。本社所在地：東京都港区"
        result = extract_prefecture_with_voting("", "", text)
        assert result == "東京都"

    def test_hp_fallback_most_frequent_wins(self):
        # 最頻出の都道府県を選ぶ
        text = "東京都渋谷区・東京都新宿区・東京都港区の3拠点。大阪府にも支店あり。"
        result = extract_prefecture_with_voting("", "", text)
        assert result == "東京都"

    def test_hp_fallback_no_prefecture_returns_empty(self):
        assert extract_prefecture_with_voting("", "", "本文に都道府県名なし") == ""


# ── 4. 再現テスト（バグ防止）─────────────────────────────────────────────────

class TestReproductionBugs:
    """旧バグ（北海道から線形検索）の再発を防ぐ回帰テスト"""

    def test_shioya_unitec_returns_fukushima(self):
        # HP本文に「北海道」言及があっても郵便+電話で福島県を返す
        hp_text = "北海道支店のご案内。本社：福島県郡山市。"
        result = extract_prefecture_with_voting("960-1232", "024-567-6367", hp_text)
        assert result == "福島県"

    def test_shioya_unitec_not_hokkaido(self):
        hp_text = "北海道支店のご案内。本社：福島県郡山市。"
        result = extract_prefecture_with_voting("960-1232", "024-567-6367", hp_text)
        assert result != "北海道"

    def test_fit_returns_tokyo(self):
        # HP本文に「埼玉県」言及があっても郵便+電話で東京都を返す
        hp_text = "埼玉県のお客様へ。本社所在地：東京都国立市。"
        result = extract_prefecture_with_voting("186-0013", "042-521-2785", hp_text)
        assert result == "東京都"

    def test_fit_not_saitama(self):
        hp_text = "埼玉県のお客様へ。本社所在地：東京都国立市。"
        result = extract_prefecture_with_voting("186-0013", "042-521-2785", hp_text)
        assert result != "埼玉県"

    def test_excelsior_returns_osaka(self):
        # HP本文に「東京都」言及があっても郵便+電話で大阪府を返す
        hp_text = "東京都のお客様も承ります。本社：大阪府大阪市北区。"
        result = extract_prefecture_with_voting("531-0072", "06-6949-8546", hp_text)
        assert result == "大阪府"

    def test_excelsior_not_tokyo(self):
        hp_text = "東京都のお客様も承ります。本社：大阪府大阪市北区。"
        result = extract_prefecture_with_voting("531-0072", "06-6949-8546", hp_text)
        assert result != "東京都"
