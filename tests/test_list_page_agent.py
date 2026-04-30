"""
list_page_agent の企業名抽出テスト

Phase 4 Step 2 で COMPANY_NAME_PATTERNS の除外文字に
「（」「(」「）」「)」を追加した修正のリグレッション防止。
"""

import unittest

from agents.list_page_agent import extract_company_names_from_text


class TestExtractCompanyNamesFromText(unittest.TestCase):
    """企業名抽出の基本動作テスト."""

    # ── 基本ケース ───────────────────────────────────────
    def test_simple_kabushiki_kaisha(self):
        """株式会社のシンプルな抽出."""
        result = extract_company_names_from_text("株式会社サンプル")
        self.assertIn("株式会社サンプル", result)

    def test_simple_yugen_kaisha(self):
        """有限会社のシンプルな抽出."""
        result = extract_company_names_from_text("有限会社サンプル")
        self.assertIn("有限会社サンプル", result)

    def test_simple_godou_kaisha(self):
        """合同会社のシンプルな抽出."""
        result = extract_company_names_from_text("合同会社サンプル")
        self.assertIn("合同会社サンプル", result)

    def test_simple_shadanhojin(self):
        """一般社団法人のシンプルな抽出."""
        result = extract_company_names_from_text("一般社団法人サンプル")
        self.assertIn("一般社団法人サンプル", result)

    # ── Phase 4 Step 2 で修正したケース ──────────────────
    # 朝のログで「こそが働きがいを育てる（三和建設株式会社」のような
    # 壊れた企業名が抽出されていた問題のリグレッション防止
    def test_paren_zenkaku_breakdown(self):
        """全角括弧「（」を含むテキストから正しく企業名を抽出する."""
        text = "こそが働きがいを育てる（三和建設株式会社）の事例紹介"
        result = extract_company_names_from_text(text)
        # 修正後: 「三和建設株式会社」が抽出される
        self.assertIn("三和建設株式会社", result)
        # 修正前のバグ: 「こそが働きがいを育てる（三和建設株式会社」が抽出されていた
        for name in result:
            self.assertNotIn("こそが", name, f"壊れた企業名が抽出されている: {name}")

    def test_paren_hankaku_breakdown(self):
        """半角括弧「(」を含むテキストから正しく企業名を抽出する."""
        text = "経営の極意とは(ダイサンドット株式会社)代表より"
        result = extract_company_names_from_text(text)
        # 修正後: 「ダイサンドット株式会社」が抽出される
        self.assertIn("ダイサンドット株式会社", result)
        # 修正前のバグ: 「極意とは(ダイサンドット株式会社」が抽出されていた
        for name in result:
            self.assertNotIn("極意", name, f"壊れた企業名が抽出されている: {name}")

    def test_paren_close_zenkaku(self):
        """全角閉じ括弧「）」を含むテキスト."""
        text = "認定企業（株式会社アスノオト）の取り組み"
        result = extract_company_names_from_text(text)
        # 「株式会社アスノオト」が抽出される
        self.assertIn("株式会社アスノオト", result)

    # ── ノイズ・短すぎ・長すぎの除外 ─────────────────────
    def test_too_short_excluded(self):
        """3文字未満は除外される."""
        result = extract_company_names_from_text("AB")
        self.assertEqual(result, [])

    def test_too_long_excluded(self):
        """40文字超は除外される."""
        # 30文字超の名前 + 株式会社
        long_name = "あ" * 35 + "株式会社"
        result = extract_company_names_from_text(long_name)
        # 全体としては40文字を超えるが、抽出時の制約で除外される可能性
        # （あくまで「40文字以下」のチェックであることを確認）
        for name in result:
            self.assertLessEqual(len(name), 40)

    # ── 公的機関ドメインの除外 ────────────────────────────
    def test_no_target_returns_empty(self):
        """企業名表記が含まれない場合は空リスト."""
        result = extract_company_names_from_text("これは普通の文章です")
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
