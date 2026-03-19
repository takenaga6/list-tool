import unittest

from agents.rank_agent import pre_screen


class TestRankAgentPreScreen(unittest.TestCase):
    def test_pre_screen_rejects_large_company_domain(self):
        # domain listed in config.LARGE_COMPANY_DOMAINS should be rejected immediately
        result, reason = pre_screen({
            "url": "https://www.rizapgroup.com/", 
            "title": "RIZAPグループ", 
            "snippet": "" 
        })
        self.assertFalse(result)
        self.assertIn("大企業ドメイン", reason)

    def test_pre_screen_rejects_small_company_domain(self):
        # domain listed in config.SMALL_COMPANY_DOMAINS should be rejected immediately
        result, reason = pre_screen({
            "url": "https://nagata-sho.com/", 
            "title": "株式会社長田商会", 
            "snippet": "" 
        })
        self.assertFalse(result)
        self.assertIn("小規模ドメイン", reason)

    def test_pre_screen_accepts_regular_company(self):
        # A normal SMB-like company should pass the pre-screen (no obvious large signals)
        result, reason = pre_screen({
            "url": "https://example.co.jp/", 
            "title": "株式会社テスト", 
            "snippet": "" 
        })
        self.assertTrue(result)
        self.assertEqual(reason, "")


if __name__ == "__main__":
    unittest.main()
