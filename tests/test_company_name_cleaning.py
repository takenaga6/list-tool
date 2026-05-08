# -*- coding: utf-8 -*-
"""
agents/scraper_agent.py の会社名クリーニング関数のユニットテスト

テスト対象:
  _remove_noise_phrases  - 末尾ノイズ語除去
  _truncate_at_separator - セパレータ以降切り捨て
  _dedupe_consecutive    - 同一連続除去
  _clean_company_name    - 上記3つ + 既存ロジックの統合
"""
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
