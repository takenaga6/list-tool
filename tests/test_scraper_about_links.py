"""会社概要リンク追従（固定パス当てずっぽう → リンク実URL追従）の単体テスト。

背景: 旧スクレイパーは /company 等の固定パスを当てずっぽうで叩くだけで、
サイト独自URL（例: /pages/2/）の会社概要に到達できず従業員数を取りこぼしていた。
find_about_links で実リンクを辿る方式へ変更（2026-06-26）。
"""

import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

from agents.scraper_agent import find_about_links, scrape_company_info


class TestFindAboutLinks(unittest.TestCase):
    def _links(self, html, base="https://ex.co.jp"):
        return find_about_links(BeautifulSoup(html, "html.parser"), base)

    def test_picks_company_overview_link(self):
        """会社概要リンクの実URLを返す（固定パスに無い /pages/2/ も拾える）."""
        html = '<a href="/pages/2/">会社概要</a><a href="/news">お知らせ</a>'
        links = self._links(html)
        self.assertIn("https://ex.co.jp/pages/2/", links)

    def test_priority_japanese_first(self):
        """「会社概要」は「about」より高優先で先頭に来る."""
        html = '<a href="/about">About</a><a href="/x/outline.html">会社概要</a>'
        links = self._links(html)
        self.assertEqual(links[0], "https://ex.co.jp/x/outline.html")

    def test_excludes_external_and_non_http(self):
        """外部ドメイン・mailto・tel・#アンカーは除外する."""
        html = (
            '<a href="https://twitter.com/x">company</a>'
            '<a href="https://other.com/company">会社概要</a>'
            '<a href="mailto:a@b.com">会社概要</a>'
            '<a href="tel:0312345678">会社概要</a>'
            '<a href="#top">会社概要</a>'
            '<a href="/company/">会社案内</a>'
        )
        links = self._links(html)
        self.assertEqual(links, ["https://ex.co.jp/company/"])

    def test_excludes_non_about_links(self):
        """会社概要系でないリンク（採用・お問い合わせ等）は拾わない."""
        html = '<a href="/recruit">採用情報</a><a href="/contact">お問い合わせ</a>'
        self.assertEqual(self._links(html), [])

    def test_none_soup(self):
        self.assertEqual(find_about_links(None, "https://ex.co.jp"), [])

    def test_limit(self):
        html = "".join(f'<a href="/c{i}">会社概要{i}</a>' for i in range(10))
        self.assertEqual(len(self._links(html)), 6)


class TestLinkFollowingRecoversEmployeeCount(unittest.TestCase):
    """統合: 固定パスに無いリンク先の従業員数を、リンク追従で回収する."""

    def test_recovers_via_non_guessable_link(self):
        # トップ: TEL・法人格・代表者はあるが従業員数なし + /pages/2/ への会社概要リンク
        top_html = (
            '<html><body>株式会社テスト 代表取締役 山田太郎 '
            'TEL: 03-1234-5678 事業内容はソフトウェア開発です。'
            '会社案内をご覧ください。'
            '<a href="/pages/2/">会社概要</a></body></html>'
        )
        # 会社概要ページ（固定パスには存在しないURL）に従業員数
        about_html = (
            "<html><body>会社概要 従業員数 40名 資本金1000万円 "
            "本社は東京都千代田区にあります。</body></html>"
        )

        def fake_get_page_text(url, timeout=8):
            u = url.rstrip("/")
            if u.endswith("/pages/2"):
                soup = BeautifulSoup(about_html, "html.parser")
                return soup.get_text(" ", strip=True), soup
            if u.endswith("example.co.jp"):
                soup = BeautifulSoup(top_html, "html.parser")
                return soup.get_text(" ", strip=True), soup
            return "", None  # 固定パス当てずっぽう（/company 等）は空

        with patch("agents.scraper_agent.get_page_text", side_effect=fake_get_page_text), \
             patch("agents.scraper_agent.extract_company_name", return_value="株式会社テスト"), \
             patch("agents.scraper_agent.estimate_industry", return_value="IT"), \
             patch("agents.scraper_agent.extract_address_parts",
                   return_value=("100-0001", "東京都", "東京都千代田区1-1")), \
             patch("agents.scraper_agent.extract_prefecture_with_voting", return_value="東京都"), \
             patch("agents.scraper_agent.extract_notable_links", return_value=[]), \
             patch("agents.list_page_agent.find_file_links", return_value=[]):
            info = scrape_company_info("http://example.co.jp", minimal=False)

        # 固定パスでは到達できないリンク先から従業員数40名を回収できている
        self.assertEqual(info["employee_count"], "40")
        self.assertTrue(info.get("company_url"))  # check_company_fields を通過している


if __name__ == "__main__":
    unittest.main()
