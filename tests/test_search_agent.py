import unittest

from agents import search_agent


class TestSearchAgent(unittest.TestCase):
    def test_looks_like_company_url_cojp_always_true(self):
        self.assertTrue(
            search_agent._looks_like_company_url(
                "https://example.co.jp", "", ""
            )
        )

    def test_looks_like_company_url_com_requires_signal(self):
        # タイトルに株式会社があれば通る
        self.assertTrue(
            search_agent._looks_like_company_url(
                "https://example.com", "株式会社テスト", ""
            )
        )

        # パスに会社概要系が含まれていれば通る
        self.assertTrue(
            search_agent._looks_like_company_url(
                "https://example.com/about", "", ""
            )
        )

        # スニペットに会社概要ワードが含まれていれば通る
        self.assertTrue(
            search_agent._looks_like_company_url(
                "https://example.com/anything", "", "当社の会社概要はこちら"
            )
        )

        # 企業っぽいワードが1つもない場合は落ちる
        self.assertFalse(
            search_agent._looks_like_company_url(
                "https://example.com", "最新ニュースサイト", "ニュース速報"
            )
        )

    def test_looks_like_company_url_other_tld_needs_two_signals(self):
        # .biz は追加シグナルが2つ必要（タイトルとスニペット）
        self.assertFalse(
            search_agent._looks_like_company_url(
                "https://example.biz", "株式会社テスト", ""
            )
        )
        self.assertTrue(
            search_agent._looks_like_company_url(
                "https://example.biz", "株式会社テスト", "会社概要 はこちら"
            )
        )

    def test_detect_media_domain(self):
        # configにある媒体名が含まれていたらドメインが返る
        self.assertEqual(
            search_agent.detect_media_domain("KENJA GLOBAL 株式会社"),
            "kenja.tv",
        )
        # 含まれない場合は空文字
        self.assertEqual(
            search_agent.detect_media_domain("まったく別の検索キーワード"),
            "",
        )


if __name__ == "__main__":
    unittest.main()
