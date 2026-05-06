"""Phase 5.1 英語サイト事前フィルタのテスト。

対象:
  - config.count_japanese_chars()
  - agents.search_agent._is_english_site()
"""
import unittest

from config import count_japanese_chars, JAPANESE_MIN_CHARS_IN_SNIPPET
from agents.search_agent import _is_english_site


class TestCountJapaneseChars(unittest.TestCase):
    """count_japanese_chars の単体テスト。"""

    def test_hiragana_counted(self):
        self.assertEqual(count_japanese_chars("ひらがな"), 4)

    def test_katakana_counted(self):
        self.assertEqual(count_japanese_chars("カタカナ"), 4)

    def test_kanji_counted(self):
        self.assertEqual(count_japanese_chars("漢字テスト"), 5)

    def test_prolonged_sound_mark_counted(self):
        # ー（長音符）はカタカナ語に必須
        self.assertEqual(count_japanese_chars("コーヒー"), 4)

    def test_english_zero(self):
        self.assertEqual(count_japanese_chars("The Best Antivirus Software for 2024"), 0)

    def test_full_width_punctuation_excluded(self):
        # 「・」「：」「「」「」」は全角記号 → 0文字扱い
        self.assertEqual(count_japanese_chars("・：「」"), 0)

    def test_mixed_japanese_english(self):
        # 「株式会社ABC」の 株式会社 = 4漢字
        self.assertEqual(count_japanese_chars("ABC株式会社"), 4)

    def test_empty_string(self):
        self.assertEqual(count_japanese_chars(""), 0)

    def test_japanese_min_chars_constant(self):
        # 定数が 1 以上であること（後で調整可能）
        self.assertGreaterEqual(JAPANESE_MIN_CHARS_IN_SNIPPET, 1)


class TestIsEnglishSiteExclusion(unittest.TestCase):
    """英語サイト（pcmag.com 等）が除外されること。"""

    def test_pcmag_style_excluded(self):
        # pcmag.com 風: タイトル・スニペットともに英語
        result = _is_english_site(
            "https://www.pcmag.com/picks/best-antivirus",
            "The Best Antivirus Software for 2024 | PCMag",
            "We test and review antivirus software so you can keep your computer safe.",
        )
        self.assertTrue(result, "pcmag.com 風の英語サイトは除外されるべき")

    def test_expertinsights_style_excluded(self):
        # expertinsights.com 風
        result = _is_english_site(
            "https://expertinsights.com/insights/best-antivirus",
            "The 10 Best Antivirus Software Solutions",
            "We compare the top antivirus tools for business and personal use.",
        )
        self.assertTrue(result, "expertinsights.com 風の英語サイトは除外されるべき")

    def test_comparitech_style_excluded(self):
        result = _is_english_site(
            "https://www.comparitech.com/antivirus/best-antivirus-software/",
            "Best Antivirus Software 2024: Our Top Picks",
            "Compare antivirus software options for Windows, Mac, and mobile.",
        )
        self.assertTrue(result, "comparitech.com 風の英語サイトは除外されるべき")

    def test_geekflare_style_excluded(self):
        result = _is_english_site(
            "https://geekflare.com/best-antivirus-software/",
            "10 Best Antivirus Software for PC and Mac in 2024",
            "Geekflare editors test and recommend the best antivirus software.",
        )
        self.assertTrue(result, "geekflare.com 風の英語サイトは除外されるべき")


class TestIsEnglishSitePassthrough(unittest.TestCase):
    """日本企業・日本語スニペットが通過すること。"""

    def test_japanese_snippet_passes(self):
        # スニペットに日本語あり → 通過
        result = _is_english_site(
            "https://example.com/",
            "Health Corp",
            "健康経営に注力する企業です。従業員の健康を第一に考えています。",
        )
        self.assertFalse(result, "日本語スニペットがある場合は通過すべき")

    def test_kabushiki_in_title_passes(self):
        # タイトルに「株式会社」あり（スニペットは英語のみ）→ 通過
        result = _is_english_site(
            "https://abc-corp.com/",
            "ABC株式会社",
            "Health management solutions for your business.",
        )
        self.assertFalse(result, "タイトルに法人格がある場合は通過すべき")

    def test_all_legal_keywords_pass(self):
        # 法人格キーワード7種それぞれでテスト
        legal_names = [
            "XYZ有限会社",
            "ABC合同会社",
            "○○一般社団法人",
            "△△一般財団法人",
            "□□学校法人",
            "◇◇医療法人",
        ]
        for name in legal_names:
            with self.subTest(title=name):
                result = _is_english_site(
                    "https://example.com/",
                    name,
                    "Company providing health management services.",
                )
                self.assertFalse(result, f"法人格「{name}」があれば通過すべき")

    def test_co_jp_domain_always_passes(self):
        # .co.jp ドメインは問答無用で通過
        result = _is_english_site(
            "https://example.co.jp/",
            "Example Company",
            "This is an English snippet with no Japanese characters.",
        )
        self.assertFalse(result, ".co.jp は無条件通過すべき")

    def test_single_japanese_char_passes(self):
        # 日本語1文字（境界値）→ 通過
        result = _is_english_site(
            "https://abc.com/",
            "ABC Corp の",  # 「の」が1文字の日本語
            "English snippet only.",
        )
        self.assertFalse(result, "日本語1文字あれば通過すべき（境界値）")


class TestIsEnglishSiteBoundary(unittest.TestCase):
    """境界値テスト。"""

    def test_zero_japanese_no_legal_excluded(self):
        # 日本語0文字 + 法人格なし → 除外（仕様通り）
        result = _is_english_site(
            "https://mercari-inc.com/",
            "Mercari, Inc.",  # 法人格なし（Incは _JP_LEGAL_KEYWORDSに含まれない）
            "Online marketplace platform.",
        )
        self.assertTrue(result, "日本語0文字・法人格なし → 除外されるべき（境界値）")

    def test_full_width_symbols_only_excluded(self):
        # 全角記号のみ（「・」「：」）→ 日本語0文字扱い → 法人格なしなら除外
        result = _is_english_site(
            "https://example.com/",
            "Example: Services・Solutions",  # ・は除外対象の約物
            "Global services company.",
        )
        self.assertTrue(result, "全角記号のみで法人格なし → 除外すべき（境界値）")


if __name__ == "__main__":
    unittest.main()
