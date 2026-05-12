# -*- coding: utf-8 -*-
"""
utils/company_name_validator.py のユニットテスト（Phase 7-B C2）

テスト対象:
  _is_valid_company_name  - 会社名有効性判定（ルール1〜3）
  _dedupe_consecutive     - スペース区切り重複除去（拡張後）
"""
import pytest
from utils.company_name_validator import _is_valid_company_name
from agents.scraper_agent import _dedupe_consecutive


# ── _is_valid_company_name ───────────────────────────────────────────────────

class TestIsValidCompanyName:

    # ── 有効と判定されるべきケース ────────────────────────────────────────
    def test_valid_authority_creative(self):
        assert _is_valid_company_name("株式会社AUTHORITY CREATIVE Works") is True

    def test_valid_katakana_prefix(self):
        assert _is_valid_company_name("シオヤユニテック株式会社") is True

    def test_valid_katakana_short(self):
        assert _is_valid_company_name("ジェイカス株式会社") is True

    def test_valid_latin_prefix(self):
        assert _is_valid_company_name("Fit株式会社") is True

    def test_valid_no_particles(self):
        """助詞ゼロの英数混在名は通過する"""
        assert _is_valid_company_name("ABC株式会社") is True

    def test_valid_particle_count_2(self):
        """助詞2個以下は通過する（「なかのエスアイ」等）"""
        assert _is_valid_company_name("なかのエスアイ株式会社") is True

    def test_valid_kokokoro_clinic(self):
        """閾値4: と+の+の = 3個 → 通過する"""
        assert _is_valid_company_name("株式会社こころとからだのクリニック") is True

    def test_valid_nodoka_home(self):
        """の=1個 → 通過する"""
        assert _is_valid_company_name("のどかホーム株式会社") is True

    def test_valid_kotono_ha(self):
        """ノ=カタカナ（U+30CE）≠ の（U+306E）→ 助詞0個 → 通過する"""
        assert _is_valid_company_name("コトノハ株式会社") is True

    # ── ルール1: 句読点・感嘆符 ────────────────────────────────────────────
    def test_invalid_exclamation_with_location(self):
        """感嘆符を含む → False"""
        assert _is_valid_company_name("ばねのことならおまかせください！兵庫県豊岡市") is False

    def test_invalid_exclamation_long_text(self):
        """感嘆符を含む長文 → False"""
        assert _is_valid_company_name(
            "特急対応を叶えてくれる！仕上がりの早い深穴加工業者ガイド"
        ) is False

    def test_invalid_period(self):
        """句点を含む → False"""
        assert _is_valid_company_name("株式会社の登録商標です。") is False

    def test_invalid_question_mark(self):
        """疑問符を含む → False"""
        assert _is_valid_company_name("会社名？不明") is False

    def test_invalid_comma(self):
        """読点（U+3001）を含む → False"""
        assert _is_valid_company_name("株式会社、テスト") is False

    def test_invalid_fullwidth_comma(self):
        """全角カンマ U+FF0C「，」を含む → False（文字コード違い対策）"""
        assert _is_valid_company_name("株式会社，テスト") is False

    def test_invalid_halfwidth_comma(self):
        """半角カンマ U+002C「,」を含む → False（文字コード違い対策）"""
        assert _is_valid_company_name("株式会社,テスト") is False

    def test_invalid_pattern1_real_case(self):
        """5/9走行で発覚したパターン1の実例: 読点含む長文 → False"""
        assert _is_valid_company_name(
            "株式会社東豊精工は、1957年（昭和32年）コウノトリ舞う豊かな自然"
        ) is False

    # ── ルール2: 法人格の直後が助詞 ──────────────────────────────────────
    def test_invalid_legal_form_followed_by_no(self):
        """株式会社 + の → False（句読点なしバージョンも除外）"""
        assert _is_valid_company_name("株式会社のサービス案内") is False

    def test_invalid_legal_form_followed_by_wo(self):
        """株式会社 + を → False"""
        assert _is_valid_company_name("株式会社を検索する") is False

    def test_invalid_limited_followed_by_particle(self):
        """有限会社 + の → False"""
        assert _is_valid_company_name("有限会社のサービス") is False

    def test_valid_legal_form_at_end(self):
        """法人格が末尾 → 直後なし → True（ルール2発動せず）"""
        assert _is_valid_company_name("テスト株式会社") is True

    # ── ルール3: 助詞4個以上 ──────────────────────────────────────────────
    def test_invalid_particles_4_or_more(self):
        """の+と+な+だ = 4個 → False"""
        assert _is_valid_company_name("これはとてもながいせつめいぶんのテスト") is False

    def test_invalid_sentence_like(self):
        """「ばね...」の ！なし版は助詞3個（閾値4未満）→ True（ルール1に委ねる設計）"""
        assert _is_valid_company_name("ばねのことならおまかせください兵庫県豊岡市") is True

    def test_invalid_many_particles(self):
        """がをのには = 5個 → False"""
        assert _is_valid_company_name("がをのにはたくさんある会社名") is False

    # ── 空文字・None ─────────────────────────────────────────────────────
    def test_empty_string(self):
        assert _is_valid_company_name("") is False


# ── _dedupe_consecutive のスペース区切り拡張 ──────────────────────────────────

class TestDedupeConsecutiveSpaceExtension:

    def test_space_duplicate_full(self):
        """半角スペース区切りの完全重複 → 前半を返す"""
        assert _dedupe_consecutive("株式会社フレームマン 株式会社フレームマン") == "株式会社フレームマン"

    def test_fullwidth_space_duplicate(self):
        """全角スペース区切りの完全重複 → 前半を返す"""
        assert _dedupe_consecutive("A　A") == "A"

    def test_mixed_space_duplicate(self):
        """半角+全角スペース混在の完全重複 → 前半を返す"""
        assert _dedupe_consecutive("A 　A") == "A"

    def test_different_parts_unchanged(self):
        """内容が異なる場合は変更しない"""
        assert _dedupe_consecutive("A B") == "A B"

    def test_separator_duplicate_unchanged(self):
        """既存のセパレータ区切り重複は引き続き機能する"""
        assert _dedupe_consecutive("株式会社ABC│株式会社ABC") == "株式会社ABC"

    def test_no_duplicate_unchanged(self):
        """重複なしは変更しない"""
        assert _dedupe_consecutive("株式会社フレームマン") == "株式会社フレームマン"

    def test_three_parts_unchanged(self):
        """3つの部分は重複扱いしない（前半と後半だけを比較）"""
        assert _dedupe_consecutive("A B C") == "A B C"
