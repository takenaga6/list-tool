"""Phase 6.1: 企業名抽出バグ修正のテスト

バグB: HTMLタイトルそのまま採取（extract_company_name）
バグA-1: 先頭ノイズ（ほか/また/数字）
バグA-2: 説明文を企業名として採取
正常系: 正当な企業名を誤って除外しないこと
"""
import unittest
from bs4 import BeautifulSoup

from agents.scraper_agent import (
    _clean_company_name,
    _is_descriptive_text,
    extract_company_name,
)
from agents.list_page_agent import extract_company_names_from_text


def _soup_with_title(title_text: str) -> BeautifulSoup:
    """<title> のみを持つ最小HTMLからBeautifulSoupを生成"""
    return BeautifulSoup(
        f"<html><head><title>{title_text}</title></head></html>",
        "html.parser",
    )


class TestBugB_TitleExtraction(unittest.TestCase):
    """バグB: タイトルタグの最短法人格セグメントを選ぶ"""

    def test_home_dash_company(self):
        # NG例: "ホーム - 株式会社マベック" → 全体をそのまま返していた
        result = extract_company_name(_soup_with_title("Home - 株式会社マベック"), "")
        self.assertEqual(result, "株式会社マベック")

    def test_company_dash_google_profile(self):
        # NG例: "株式会社ZEROBASE - Google ビジネスプロフィール" → 全体を返していた
        result = extract_company_name(
            _soup_with_title("株式会社ZEROBASE - Google ビジネスプロフィール"), ""
        )
        self.assertEqual(result, "株式会社ZEROBASE")

    def test_mixed_separators(self):
        # セパレータが複数混在するケース（｜と - が両方ある）
        # 1回の反復では "Home - 株式会社タナック" で止まるが、
        # 絞り込みループで更に " - " で割って "株式会社タナック" を選ぶ
        result = extract_company_name(
            _soup_with_title("Home - 株式会社タナック｜住宅部材・各種建材、住宅機器"), ""
        )
        self.assertEqual(result, "株式会社タナック")

    def test_pipe_separator(self):
        # 「| お知らせ」は除外されて会社名のみ返る
        result = extract_company_name(
            _soup_with_title("株式会社サンプル | お知らせ"), ""
        )
        self.assertEqual(result, "株式会社サンプル")

    def test_no_title_falls_back_to_text(self):
        # titleタグなし → textのCOMPANY_NAME_PATTERNSフォールバック
        soup = BeautifulSoup("<html><head></head></html>", "html.parser")
        result = extract_company_name(soup, "株式会社フォールバック テスト")
        self.assertEqual(result, "株式会社フォールバック")

    def test_og_site_name_fallback(self):
        # titleなし → og:site_nameフォールバック
        soup = BeautifulSoup(
            '<html><head>'
            '<meta property="og:site_name" content="株式会社OGテスト"/>'
            "</head></html>",
            "html.parser",
        )
        result = extract_company_name(soup, "")
        self.assertEqual(result, "株式会社OGテスト")


class TestBugA1_PrefixNoise(unittest.TestCase):
    """バグA-1: 先頭ノイズ（ほか/また/数字プレフィックス）の除去"""

    def test_hoka_prefix_removed(self):
        # リストページで「ほかAiロボティクス株式会社」が抽出されるケース
        result = _clean_company_name("ほかAiロボティクス株式会社")
        self.assertEqual(result, "Aiロボティクス株式会社")

    def test_mata_prefix_removed(self):
        result = _clean_company_name("また株式会社サンプル")
        self.assertEqual(result, "株式会社サンプル")

    def test_digit_prefix_removed(self):
        # 番号付きリスト「2フンドーダイ株式会社」
        result = _clean_company_name("2フンドーダイ株式会社")
        self.assertEqual(result, "フンドーダイ株式会社")

    def test_full_width_digit_prefix_removed(self):
        result = _clean_company_name("２株式会社テスト")
        self.assertEqual(result, "株式会社テスト")

    def test_sarani_prefix_removed(self):
        result = _clean_company_name("さらに株式会社ABC")
        self.assertEqual(result, "株式会社ABC")


class TestBugA2_DescriptiveText(unittest.TestCase):
    """バグA-2: 説明文・キャッチコピーの除外"""

    def test_description_before_company_blocked(self):
        # 「誠実さと真心が魅力の屋根・雨漏りの修理会社株式会社」
        # prefix に助詞「の」「が」が2種 → 説明文と判定
        result = _clean_company_name("誠実さと真心が魅力の屋根・雨漏りの修理会社株式会社")
        self.assertEqual(result, "")

    def test_rental_space_description_blocked(self):
        # 「地域の憩いの場になるレンタルスペース運営ジョルダンスペース／株式会社」
        # prefix に「の」「に」が2種 → 説明文と判定
        result = _clean_company_name(
            "地域の憩いの場になるレンタルスペース運営ジョルダンスペース／株式会社"
        )
        self.assertEqual(result, "")

    def test_repair_company_redundant_suffix_blocked(self):
        # 法人格の直前が「社」で終わる（修理会社株式会社 など）
        result = _is_descriptive_text("屋根修理会社株式会社")
        self.assertTrue(result)

    def test_is_descriptive_direct_check(self):
        # _is_descriptive_text の直接テスト
        self.assertTrue(_is_descriptive_text("誠実さと真心が魅力の屋根修理会社株式会社"))
        self.assertFalse(_is_descriptive_text("株式会社みんなのリビング"))
        self.assertFalse(_is_descriptive_text("株式会社サイベックコーポレーション"))

    def test_company_name_followed_by_sentence_edge_case(self):
        # 「株式会社ネットマーケティングの完全子会社化と今後の成長戦略」
        # prefix=""（法人格が先頭）→ _is_descriptive_text は False → 現状は文章ごと返る
        # ※ この edge case は Phase 6.1 の修正範囲外（prefix チェック方式の限界）
        result = _clean_company_name("株式会社ネットマーケティングの完全子会社化と今後の成長戦略")
        # 文章ごと返る（"" でも "株式会社ネットマーケティング" でもない）
        self.assertEqual(
            result,
            "株式会社ネットマーケティングの完全子会社化と今後の成長戦略",
            "prefix=空の場合はis_descriptiveが効かないため文章ごと返る（既知の限界）",
        )


class TestNormalCases(unittest.TestCase):
    """正常系: 正当な企業名を誤って除外しないこと"""

    def test_long_katakana_company_name(self):
        result = _clean_company_name("株式会社サイベックコーポレーション")
        self.assertEqual(result, "株式会社サイベックコーポレーション")

    def test_company_name_with_single_no_particle(self):
        # 「の」が1個だけ → 除外しない（助詞2種類未満）
        result = _clean_company_name("株式会社みんなのリビング")
        self.assertEqual(result, "株式会社みんなのリビング")

    def test_legal_keyword_only_excluded_by_list_agent(self):
        # list_page_agent の extract_company_names_from_text は「株式会社」単体を除外する（既存動作）
        result = extract_company_names_from_text("株式会社")
        self.assertEqual(result, [])

    def test_conjunction_still_excluded(self):
        # 既存の「及び」除外が壊れていないこと
        result = _clean_company_name("株式会社A及び株式会社B")
        self.assertEqual(result, "")

    def test_suffix_hoka_still_removed(self):
        # 既存の末尾「ほか」除去が壊れていないこと
        result = _clean_company_name("株式会社テストほか2社")
        self.assertEqual(result, "株式会社テスト")

    def test_normal_company_without_noise(self):
        for name in ["株式会社ABC", "合同会社テック", "有限会社フジサン"]:
            with self.subTest(name=name):
                self.assertEqual(_clean_company_name(name), name)


if __name__ == "__main__":
    unittest.main()
