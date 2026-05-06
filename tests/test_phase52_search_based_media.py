"""Phase 5.2: 検索クエリ逆引き S2 取得のテスト"""
import unittest
from unittest.mock import patch

from agents.search_agent import (
    get_companies_from_search_queries,
    _extract_company_name_from_title,
    extract_domain,
)


# search_google が返すダミー結果のファクトリ
def _make_hit(url, title="株式会社テスト", snippet="健康経営に取り組む企業", is_media=False):
    return {
        "url": url,
        "title": title,
        "snippet": snippet,
        "search_query": "テストクエリ",
        "is_media_page": is_media,
        "media_domain": "",
        "file_type": "",
    }


class TestExtractCompanyNameFromTitle(unittest.TestCase):
    """_extract_company_name_from_title のユニットテスト"""

    def test_pipe_separator(self):
        title = "株式会社サンプル | 健康経営推進 | 採用情報"
        result = _extract_company_name_from_title(title, "https://sample.co.jp")
        self.assertEqual(result, "株式会社サンプル")

    def test_jp_pipe_separator(self):
        title = "合同会社テック｜サービス紹介"
        result = _extract_company_name_from_title(title, "https://tech.co.jp")
        self.assertEqual(result, "合同会社テック")

    def test_dash_separator(self):
        title = "一般社団法人ヘルス - 活動報告"
        result = _extract_company_name_from_title(title, "https://health.or.jp")
        self.assertEqual(result, "一般社団法人ヘルス")

    def test_no_separator_with_legal_keyword(self):
        title = "有限会社フジサン企業サイト"
        result = _extract_company_name_from_title(title, "https://fujisan.co.jp")
        self.assertEqual(result, "有限会社フジサン企業サイト")

    def test_fallback_to_domain(self):
        # 法人格なし・区切りなし → ドメイン先頭セグメント
        title = "About Us - Our Company"
        result = _extract_company_name_from_title(title, "https://example.co.jp")
        self.assertEqual(result, "example")

    def test_company_name_fallback_to_domain_when_empty_title(self):
        result = _extract_company_name_from_title("", "https://mycompany.co.jp")
        self.assertEqual(result, "mycompany")


class TestGetCompaniesFromSearchQueries(unittest.TestCase):
    """get_companies_from_search_queries のテスト"""

    @patch("agents.search_agent.search_google")
    def test_extract_companies_from_search_results(self, mock_search):
        """通常の企業URLを正しく取得できる"""
        mock_search.return_value = [
            _make_hit("https://alpha.co.jp/health"),
            _make_hit("https://beta.co.jp/about"),
        ]
        results = get_companies_from_search_queries(["Voice Report 掲載されました"], "voice_report")
        self.assertEqual(len(results), 2)
        # source_confirmed_s2 フラグが付与されていること
        for r in results:
            self.assertTrue(r["source_confirmed_s2"])

    @patch("agents.search_agent.search_google")
    def test_news_site_domains_excluded(self, mock_search):
        """NEWS_SITE_DOMAINS のドメインは除外される"""
        mock_search.return_value = [
            _make_hit("https://digitalpr.jp/r/12345"),          # ニュース配信
            _make_hit("https://prtimes.jp/main/html/rd/1"),     # PRTimes
            _make_hit("https://goodcompany.co.jp/health"),      # 正常な企業HP
        ]
        results = get_companies_from_search_queries(["DAIDO KENCO AWARD 受賞"], "daido_kenco")
        self.assertEqual(len(results), 1)
        self.assertIn("goodcompany.co.jp", results[0]["url"])

    @patch("agents.search_agent.search_google")
    def test_media_pages_excluded(self, mock_search):
        """is_media_page=True のURLは除外される"""
        mock_search.return_value = [
            _make_hit("https://voice-report.jp/article/123", is_media=True),
            _make_hit("https://realcompany.co.jp/"),
        ]
        results = get_companies_from_search_queries(["Voice Report 掲載"], "voice_report")
        self.assertEqual(len(results), 1)
        self.assertNotIn("voice-report.jp", results[0]["url"])

    @patch("agents.search_agent.search_google")
    def test_duplicate_domains_removed(self, mock_search):
        """同一ドメインが複数クエリにまたがって出現しても1件のみ"""
        mock_search.side_effect = [
            [_make_hit("https://dupcompany.co.jp/page1")],  # クエリ1
            [_make_hit("https://dupcompany.co.jp/page2")],  # クエリ2
        ]
        results = get_companies_from_search_queries(
            ["クエリA", "クエリB"], "test_media"
        )
        domains = [extract_domain(r["url"]) for r in results]
        self.assertEqual(len(domains), len(set(domains)), "ドメイン重複あり")

    @patch("agents.search_agent.search_google")
    def test_company_name_extracted_from_title(self, mock_search):
        """タイトルから会社名が抽出される"""
        mock_search.return_value = [
            _make_hit(
                "https://wellness.co.jp/",
                title="株式会社ウェルネス | 健康経営優良法人認定",
            )
        ]
        results = get_companies_from_search_queries(["ウェルネス 掲載"], "test")
        self.assertEqual(results[0]["company_name"], "株式会社ウェルネス")

    @patch("agents.search_agent.search_google")
    def test_empty_queries_returns_empty(self, mock_search):
        """空クエリリストは空リストを返す"""
        results = get_companies_from_search_queries([], "test")
        self.assertEqual(results, [])
        mock_search.assert_not_called()

    @patch("agents.search_agent.search_google")
    def test_source_confirmed_s2_flag_set(self, mock_search):
        """全件に source_confirmed_s2=True が付与される"""
        mock_search.return_value = [
            _make_hit("https://comp1.co.jp/"),
            _make_hit("https://comp2.co.jp/"),
            _make_hit("https://comp3.co.jp/"),
        ]
        results = get_companies_from_search_queries(["テストクエリ"], "media")
        self.assertTrue(all(r.get("source_confirmed_s2") for r in results))


if __name__ == "__main__":
    unittest.main()
