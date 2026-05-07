"""Phase 6.1.5: list_page_agent.py の _safe_add によるゴミ除去テスト

extract_company_names_from_text / extract_company_names_from_html が
_safe_add 経由で _clean_company_name を呼び出し、「ほか〜」などのノイズを除去することを確認する。
"""
import unittest
from bs4 import BeautifulSoup

from agents.list_page_agent import (
    extract_company_names_from_text,
    extract_company_names_from_html,
    _safe_add,
)


class TestSafeAdd(unittest.TestCase):
    """_safe_add ヘルパーの単体テスト"""

    def test_safe_add_removes_hoka_prefix(self):
        names: set = set()
        _safe_add(names, "ほか株式会社テスト")
        self.assertIn("株式会社テスト", names)
        self.assertNotIn("ほか株式会社テスト", names)

    def test_safe_add_removes_hoka_with_real_name(self):
        names: set = set()
        _safe_add(names, "ほかエイベックス株式会社")
        self.assertIn("エイベックス株式会社", names)

    def test_safe_add_strips_whitespace(self):
        names: set = set()
        _safe_add(names, "  株式会社サンプル  ")
        self.assertIn("株式会社サンプル", names)

    def test_safe_add_ignores_empty_after_clean(self):
        """クリーン後に空文字になるものは追加しない"""
        names: set = set()
        _safe_add(names, "ほか")
        self.assertEqual(len(names), 0)

    def test_safe_add_normal_name_passes(self):
        names: set = set()
        _safe_add(names, "株式会社テスト商事")
        self.assertIn("株式会社テスト商事", names)


class TestExtractCompanyNamesFromTextClean(unittest.TestCase):
    """extract_company_names_from_text がゴミを除去して返すこと"""

    def test_hoka_prefix_removed(self):
        text = "受賞企業：ほか株式会社テスト 様"
        results = extract_company_names_from_text(text)
        for name in results:
            self.assertFalse(
                name.startswith("ほか"),
                f"「ほか」プレフィックスが残っている: {name!r}"
            )

    def test_normal_name_extracted(self):
        text = "健康経営優良法人：株式会社サンプルテクノロジー"
        results = extract_company_names_from_text(text)
        self.assertIn("株式会社サンプルテクノロジー", results)

    def test_descriptive_text_excluded(self):
        """説明文が企業名として混入しない（既存フィルタとの連携確認）"""
        text = "弊社の健康経営の取り組みを支援する株式会社Aのサービス"
        results = extract_company_names_from_text(text)
        for name in results:
            self.assertNotIn("の取り組みを支援する", name)


class TestExtractCompanyNamesFromHtmlClean(unittest.TestCase):
    """extract_company_names_from_html がゴミを除去して返すこと"""

    def test_table_hoka_removed(self):
        html = """
        <table>
          <tr><td>ほか株式会社エイベックス</td></tr>
          <tr><td>株式会社ソニー</td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        results = extract_company_names_from_html(soup)
        for name in results:
            self.assertFalse(
                name.startswith("ほか"),
                f"テーブルで「ほか」プレフィックスが残っている: {name!r}"
            )

    def test_list_hoka_removed(self):
        html = """
        <ul>
          <li>ほか株式会社ミュージック</li>
          <li>合同会社テストA</li>
        </ul>
        """
        soup = BeautifulSoup(html, "html.parser")
        results = extract_company_names_from_html(soup)
        for name in results:
            self.assertFalse(
                name.startswith("ほか"),
                f"リストで「ほか」プレフィックスが残っている: {name!r}"
            )

    def test_normal_company_preserved(self):
        html = "<ul><li>株式会社テストシステムズ</li></ul>"
        soup = BeautifulSoup(html, "html.parser")
        results = extract_company_names_from_html(soup)
        self.assertIn("株式会社テストシステムズ", results)


if __name__ == "__main__":
    unittest.main()
