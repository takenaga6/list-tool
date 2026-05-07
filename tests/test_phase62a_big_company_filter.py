"""Phase 6.2A + 6.3: 大手企業ドメイン除外・S10加点修正・Phase5.2無効化テスト"""
import unittest

from agents.rank_agent import pre_screen
from config import (
    PROFITABLE_INDUSTRY_KEYWORDS,
    LARGE_COMPANY_DOMAINS,
    BIG_COMPANY_DOMAINS,
    ENABLE_PHASE_5_2,
)


def _make_result(url: str, title: str = "テスト株式会社", snippet: str = "健康経営に取り組む企業") -> dict:
    return {
        "url": url,
        "title": title,
        "snippet": snippet,
        "search_query": "test",
        "is_media_page": False,
    }


class TestBigCompanyDomainFilter(unittest.TestCase):
    """Phase 6.2A.3: 大手ドメインが pre_screen() で NG 判定される"""

    def test_axa_rejected(self):
        passed, reason = pre_screen(_make_result("https://www.axa.co.jp/about/"))
        self.assertFalse(passed)
        self.assertIn("大企業ドメイン", reason)

    def test_sojitz_logitech_rejected(self):
        passed, reason = pre_screen(_make_result("https://www.sojitz-logitech.com/company/"))
        self.assertFalse(passed)
        self.assertIn("大企業ドメイン", reason)

    def test_polus_rejected(self):
        passed, reason = pre_screen(_make_result("https://www.polus.co.jp/"))
        self.assertFalse(passed)
        self.assertIn("大企業ドメイン", reason)

    def test_sompo_japan_rejected(self):
        passed, reason = pre_screen(_make_result("https://www.sompo-japan.co.jp/"))
        self.assertFalse(passed)
        self.assertIn("大企業ドメイン", reason)

    def test_nomura_rejected(self):
        passed, reason = pre_screen(_make_result("https://www.nomura.co.jp/"))
        self.assertFalse(passed)
        self.assertIn("大企業ドメイン", reason)

    def test_normal_company_passes(self):
        # 中小企業は通過する
        passed, _ = pre_screen(_make_result("https://example.co.jp/"))
        self.assertTrue(passed)

    def test_small_insurance_agency_passes(self):
        # 中小保険代理店は通過する（業種で除外しない）
        passed, _ = pre_screen(_make_result(
            "https://example-hoken.co.jp/",
            snippet="保険代理店として地域の皆様に寄り添います 従業員30名"
        ))
        self.assertTrue(passed)

    def test_regional_bank_passes(self):
        # 地方銀行（除外リストになければ）通過する
        passed, _ = pre_screen(_make_result("https://example-bank.co.jp/"))
        self.assertTrue(passed)


class TestBigCompanyDomainsConfig(unittest.TestCase):
    """BIG_COMPANY_DOMAINS と LARGE_COMPANY_DOMAINS の構成確認"""

    def test_axa_in_big_company_domains(self):
        self.assertIn("axa.co.jp", BIG_COMPANY_DOMAINS)

    def test_sojitz_logitech_in_big_company_domains(self):
        self.assertIn("sojitz-logitech.com", BIG_COMPANY_DOMAINS)

    def test_polus_in_big_company_domains(self):
        self.assertIn("polus.co.jp", BIG_COMPANY_DOMAINS)

    def test_big_company_domains_merged_into_large_company_domains(self):
        for domain in BIG_COMPANY_DOMAINS:
            self.assertIn(domain, LARGE_COMPANY_DOMAINS, f"{domain} が LARGE_COMPANY_DOMAINS にない")

    def test_original_domains_preserved(self):
        self.assertIn("fanuc.co.jp", LARGE_COMPANY_DOMAINS)
        self.assertIn("rizapgroup.com", LARGE_COMPANY_DOMAINS)


class TestS10ProfitableKeywords(unittest.TestCase):
    """Phase 6.2A.2: 保険・金融が S10 加点リストから除外されている"""

    def test_hoken_removed(self):
        self.assertNotIn("保険", PROFITABLE_INDUSTRY_KEYWORDS)

    def test_hoken_dairi_removed(self):
        self.assertNotIn("保険代理店", PROFITABLE_INDUSTRY_KEYWORDS)

    def test_kinyu_service_removed(self):
        self.assertNotIn("金融サービス", PROFITABLE_INDUSTRY_KEYWORDS)

    def test_shoken_removed(self):
        self.assertNotIn("証券", PROFITABLE_INDUSTRY_KEYWORDS)

    def test_consulting_remains(self):
        # コンサルティング系は残っていること
        self.assertIn("コンサルティング", PROFITABLE_INDUSTRY_KEYWORDS)
        self.assertIn("経営コンサル", PROFITABLE_INDUSTRY_KEYWORDS)
        self.assertIn("戦略コンサル", PROFITABLE_INDUSTRY_KEYWORDS)

    def test_investment_remains(self):
        # 投資・運用系は残っていること（大手保険会社と関係ない）
        self.assertIn("投資", PROFITABLE_INDUSTRY_KEYWORDS)
        self.assertIn("アセットマネジメント", PROFITABLE_INDUSTRY_KEYWORDS)

    def test_saas_it_remains(self):
        self.assertIn("SaaS", PROFITABLE_INDUSTRY_KEYWORDS)
        self.assertIn("クラウドサービス", PROFITABLE_INDUSTRY_KEYWORDS)


class TestPhase52Flag(unittest.TestCase):
    """Phase 6.3: ENABLE_PHASE_5_2 フラグで Phase 5.2 が無効化されている"""

    def test_phase52_disabled_by_default(self):
        self.assertFalse(ENABLE_PHASE_5_2, "ENABLE_PHASE_5_2 は False であること")

    def test_phase52_flag_is_bool(self):
        self.assertIsInstance(ENABLE_PHASE_5_2, bool)


if __name__ == "__main__":
    unittest.main()
