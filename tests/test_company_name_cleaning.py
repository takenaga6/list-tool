# -*- coding: utf-8 -*-
"""
agents/scraper_agent.py の会社名クリーニング関数のユニットテスト

テスト対象:
  _remove_noise_phrases  - 末尾ノイズ語除去
  _truncate_at_separator - セパレータ以降切り捨て（法人格優先）
  _dedupe_consecutive    - 同一連続除去
  _clean_company_name    - 上記3つ + 既存ロジックの統合
"""
import logging

import pytest
from agents.scraper_agent import (
    _remove_noise_phrases,
    _truncate_at_separator,
    _dedupe_consecutive,
    _clean_company_name,
)


# ── 1. _remove_noise_phrases ─────────────────────────────────────────────────

class TestRemoveNoisePhrases:
    def test_homepage_suffix(self):
        assert _remove_noise_phrases("株式会社日米商会ホームページ") == "株式会社日米商会"

    def test_toppage_suffix(self):
        assert _remove_noise_phrases("株式会社ABC トップページ") == "株式会社ABC"

    def test_web_site_uppercase(self):
        assert _remove_noise_phrases("南薩食鳥株式会社WEBサイト") == "南薩食鳥株式会社"

    def test_web_site_mixed_case(self):
        assert _remove_noise_phrases("南薩食鳥株式会社Webサイト") == "南薩食鳥株式会社"

    def test_web_site_lowercase(self):
        assert _remove_noise_phrases("南薩食鳥株式会社webサイト") == "南薩食鳥株式会社"

    def test_official_site(self):
        assert _remove_noise_phrases("株式会社ABC公式サイト") == "株式会社ABC"

    def test_official_hp(self):
        assert _remove_noise_phrases("株式会社ABC公式HP") == "株式会社ABC"

    def test_official_homepage(self):
        assert _remove_noise_phrases("株式会社ABC公式ホームページ") == "株式会社ABC"

    # ── 削除しないケース ──
    def test_homepage_in_middle_preserved(self):
        # 「ホームページ」が末尾でなければ除去しない
        assert _remove_noise_phrases("株式会社○○ホームページ製作所") == "株式会社○○ホームページ製作所"

    def test_clean_name_unchanged(self):
        assert _remove_noise_phrases("株式会社仁平電設") == "株式会社仁平電設"

    def test_empty_string(self):
        assert _remove_noise_phrases("") == ""


# ── 2. _truncate_at_separator ────────────────────────────────────────────────

class TestTruncateAtSeparator:
    def test_fullwidth_pipe(self):
        assert _truncate_at_separator("エクセルシオ株式会社｜エクセルシオ株式会社") == "エクセルシオ株式会社"

    def test_box_drawing_vertical(self):
        # │ (U+2502 罫線縦) は旧来 _TITLE_SEPARATORS に含まれていなかった
        assert _truncate_at_separator("エクセルシオ株式会社│エクセルシオ株式会社") == "エクセルシオ株式会社"

    def test_em_dash(self):
        assert _truncate_at_separator("株式会社ABC — 業種説明") == "株式会社ABC"

    def test_en_dash(self):
        assert _truncate_at_separator("株式会社ABC – 業種説明") == "株式会社ABC"

    def test_horizontal_bar(self):
        assert _truncate_at_separator("株式会社ABC―業種説明") == "株式会社ABC"

    def test_halfwidth_pipe_with_spaces(self):
        assert _truncate_at_separator("株式会社A | 業種") == "株式会社A"

    def test_ideographic_space_before_pipe(self):
        # 全角スペース + 半角パイプ + 全角スペース のパターン
        assert _truncate_at_separator("株式会社A　|　業種") == "株式会社A"

    def test_hyphen_with_spaces(self):
        assert _truncate_at_separator("株式会社仁平電設 - 福島県白河市") == "株式会社仁平電設"

    def test_multiple_separators_takes_first(self):
        assert _truncate_at_separator("株式会社A｜B｜C") == "株式会社A"

    # ── 削除しないケース ──
    def test_hyphen_without_spaces_preserved(self):
        # 社名内ハイフン（前後スペースなし）は除去しない
        assert _truncate_at_separator("株式会社A-B商事") == "株式会社A-B商事"

    def test_clean_name_unchanged(self):
        assert _truncate_at_separator("株式会社仁平電設") == "株式会社仁平電設"

    def test_empty_string(self):
        assert _truncate_at_separator("") == ""

    # ── 法人格優先ロジック（Phase 7-A Step 2-fix）──
    def test_prefix_toppage_legal_in_suffix(self):
        # 先頭がノイズ語でも後半に法人格があれば後半を採用
        assert _truncate_at_separator("トップページ - 株式会社仁平電設｜福島県白河市") == "株式会社仁平電設"

    def test_prefix_location_legal_in_suffix(self):
        # 先頭が地名でも後半に法人格があれば後半を採用
        assert _truncate_at_separator("兵庫県西宮市｜ジェイカス株式会社") == "ジェイカス株式会社"

    def test_prefix_description_legal_in_suffix(self):
        # 先頭が説明文でも後半に法人格があれば後半を採用
        assert _truncate_at_separator("情報社会に、新しいジャンルを創る。 ｜ リングロー株式会社") == "リングロー株式会社"

    def test_multiple_legal_forms_takes_first(self):
        # 法人格が複数ある場合は最初に出現したものを採用
        assert _truncate_at_separator("A株式会社 - B株式会社") == "A株式会社"

    def test_no_legal_form_generic_fallback(self):
        # 法人格なし → 先頭採用
        assert _truncate_at_separator("Fit | フィット") == "Fit"

    def test_no_legal_form_falls_back_to_first(self):
        # 法人格なしのフォールバック仕様固定（Phase 7-B で精度向上を検討）
        # TODO Phase 7-B: 法人格なしケースの精度向上
        result = _truncate_at_separator(
            "ばねのことならおまかせ下さい！兵庫県豊岡市｜東豊精工 | バネのことならおまかせ"
        )
        assert result == "ばねのことならおまかせ下さい！兵庫県豊岡市"  # 現時点の仕様

    def test_long_name_legal_warning(self, caplog):
        # 法人格優先で採用した部分が100文字超 → LEGAL 警告ログ
        long_part = "あ" * 98 + "株式会社"  # 102文字
        name = "前置きノイズ | " + long_part
        with caplog.at_level(logging.WARNING, logger="agents.scraper_agent"):
            result = _truncate_at_separator(name)
        assert result == long_part
        assert "[LONG_COMPANY_NAME_LEGAL]" in caplog.text

    def test_long_name_fallback_warning(self, caplog):
        # 法人格なしのフォールバックが100文字超 → FALLBACK 警告ログ
        long_first = "ほ" * 101  # 101文字、法人格なし
        name = long_first + "｜テスト"
        with caplog.at_level(logging.WARNING, logger="agents.scraper_agent"):
            result = _truncate_at_separator(name)
        assert result == long_first
        assert "[LONG_COMPANY_NAME_FALLBACK]" in caplog.text


# ── 3. _dedupe_consecutive ───────────────────────────────────────────────────

class TestDedupeConsecutive:
    def test_fullwidth_pipe_dedup(self):
        assert _dedupe_consecutive("エクセルシオ株式会社｜エクセルシオ株式会社") == "エクセルシオ株式会社"

    def test_box_drawing_dedup(self):
        assert _dedupe_consecutive("エクセルシオ株式会社│エクセルシオ株式会社") == "エクセルシオ株式会社"

    def test_halfwidth_pipe_dedup(self):
        assert _dedupe_consecutive("株式会社ABC|株式会社ABC") == "株式会社ABC"

    def test_different_parts_unchanged(self):
        # A と B が異なる場合はそのまま（truncate 側が担当）
        assert _dedupe_consecutive("株式会社A｜福島県") == "株式会社A｜福島県"

    def test_clean_name_unchanged(self):
        assert _dedupe_consecutive("株式会社仁平電設") == "株式会社仁平電設"

    def test_empty_string(self):
        assert _dedupe_consecutive("") == ""


# ── 4. _clean_company_name（統合テスト）─────────────────────────────────────

class TestCleanCompanyName:

    # ── 正常系（修正後の期待値）──
    def test_jinhei_densetsu_full_title(self):
        # トップページ → extract_company_name が処理するが、安全網として確認
        # セパレータで分割後の残骸が来るケース
        assert _clean_company_name("株式会社仁平電設｜福島県白河市") == "株式会社仁平電設"

    def test_nansatsu_shokucho_web(self):
        assert _clean_company_name("南薩食鳥株式会社WEBサイト") == "南薩食鳥株式会社"

    def test_nichibei_shokai_homepage(self):
        assert _clean_company_name("株式会社日米商会ホームページ") == "株式会社日米商会"

    def test_excelsior_duplicate(self):
        assert _clean_company_name("エクセルシオ株式会社│エクセルシオ株式会社") == "エクセルシオ株式会社"

    def test_toppage_separator_chain(self):
        # セパレータ連鎖後に法人格が来るケース
        assert _clean_company_name("株式会社仁平電設｜福島県白河市｜電気工事一式") == "株式会社仁平電設"

    # ── 削除しないケース（重要）──
    def test_hyphen_in_name_preserved(self):
        assert _clean_company_name("株式会社A-B商事") == "株式会社A-B商事"

    def test_parenthesis_pattern_preserved(self):
        # 括弧パターンはスコープ外
        assert _clean_company_name("Fit（フィット株式会社）") == "Fit（フィット株式会社）"

    def test_homepage_factory_preserved(self):
        # 「ホームページ」が社名の一部（末尾でない）は除去しない
        assert _clean_company_name("株式会社○○ホームページ製作所") == "株式会社○○ホームページ製作所"

    # ── エッジケース ──
    def test_fullwidth_space_before_pipe(self):
        assert _clean_company_name("株式会社A　|　業種") == "株式会社A"

    def test_multiple_separators(self):
        assert _clean_company_name("株式会社A｜B｜C") == "株式会社A"

    def test_empty_string(self):
        assert _clean_company_name("") == ""

    def test_none_like_empty(self):
        # 呼び出し元では None を渡さないが、空文字は常に安全に処理
        assert _clean_company_name("") == ""

    # ── トップページ PREFIX（セパレータなし）の挙動確認 ──
    def test_toppage_prefix_no_separator_behavior(self):
        # 将来の拡張ポイント: セパレータなし PREFIX は現時点で除去対象外
        # extract_company_name() がセパレータで先に処理するため実運用では発生しない
        result = _clean_company_name("トップページ株式会社仁平電設")
        # 「トップページ株式会社仁平電設」がそのまま返るか、何らかの形で返ることを確認
        # （エラーで落ちないことが最低条件）
        assert isinstance(result, str)

    # ── 既存ロジックとの共存確認 ──
    def test_conjunction_still_excluded(self):
        # 既存: 「及び」を含む → 空文字
        assert _clean_company_name("株式会社A及び株式会社B") == ""

    def test_suffix_noise_still_removed(self):
        # 既存: 末尾「など」→ 切り捨て
        assert _clean_company_name("株式会社ABCなど各種サービス") == "株式会社ABC"

    def test_prefix_digit_still_removed(self):
        # 既存: 先頭数字1-2桁 → 除去
        assert _clean_company_name("1株式会社ABC") == "株式会社ABC"

    # ── 法人格優先ロジック（Phase 7-A Step 2-fix）統合確認 ──
    def test_toppage_prefix_legal_in_body(self):
        # ドライラン再現: 仁平電設（トップページ - 法人名｜地名）
        assert _clean_company_name("トップページ - 株式会社仁平電設｜福島県白河市") == "株式会社仁平電設"

    def test_location_prefix_legal_in_body(self):
        # ドライラン再現: ジェイカス（地名｜法人名）
        assert _clean_company_name("兵庫県西宮市｜ジェイカス株式会社") == "ジェイカス株式会社"

    def test_toppage_legal_homepage_suffix(self):
        # ドライラン再現: 日米商会（トップページ｜法人名ホームページ）
        # ※ 「ホームページ」は _remove_noise_phrases が先に処理して除去
        assert _clean_company_name("トップページ｜株式会社日米商会ホームページ") == "株式会社日米商会"

    def test_description_legal_in_body(self):
        # ドライラン再現: リングロー（説明文｜法人名）
        assert _clean_company_name("情報社会に、新しいジャンルを創る。 ｜ リングロー株式会社") == "リングロー株式会社"
