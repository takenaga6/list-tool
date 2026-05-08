# -*- coding: utf-8 -*-
"""
Phase 7-C D1: [FUNNEL] ログ検証テスト

process_one_company (main.py) の FUNNEL ログ 5 種類と
scrape_company_info (agents/scraper_agent.py) の FUNNEL ログ 2 種類が
正しく出力されることを確認する。
"""
import logging
import sys
import os
from unittest.mock import patch, MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import main
from agents.scraper_agent import scrape_company_info


# ── テストデータ生成ヘルパー ────────────────────────────────────────────────────

def _sr(url="http://test.co.jp/", search_query="テストクエリ"):
    """最小限の search_result dict を返す"""
    return {
        "url": url,
        "search_query": search_query,
        "is_media_page": False,
        "file_type": "",
        "title": "テスト株式会社",
        "snippet": "",
    }


def _info(company_url="http://test.co.jp", company_name="テスト株式会社"):
    """スクレイプ成功後の最小限の company_info を返す"""
    return {
        "company_url": company_url,
        "company_name": company_name,
        "representative": "山田 太郎",
        "phone": "03-1234-5678",
        "zip_code": "100-0001",
        "prefecture": "東京都",
        "address": "東京都千代田区1-1",
        "industry": "IT",
        "employee_count": "50",
        "_page_text": "健康経営 採用 福利厚生",
        "_confidence": 3,
    }


def _rank(rank="A", score=5, ng_reason=""):
    """最小限の rank_result dict を返す"""
    return {
        "rank": rank,
        "score": score,
        "ng_reason": ng_reason,
        "reasons": ["テスト理由"],
        "signals": {},
    }


def _hub(register_ok=True):
    hub = MagicMock()
    hub.check_duplicate.return_value = False
    hub.register_company.return_value = register_ok
    return hub


def _funnel_messages(caplog):
    """caplog から [FUNNEL] メッセージだけを抽出して返す"""
    return [r.message for r in caplog.records if "[FUNNEL]" in r.message]


# ── main.py の [FUNNEL] ログ検証 ─────────────────────────────────────────────

class TestFunnelLoggingMainPy:
    """process_one_company の FUNNEL ログ 5 種類を検証する"""

    def test_screener_ng_emits_funnel_log(self, caplog):
        """pre_screen が (False, reason) → [FUNNEL] screener_ng が 1 件出力される"""
        with caplog.at_level(logging.INFO, logger="main"), \
             patch("main.pre_screen", return_value=(False, "大手企業")), \
             patch("main.record_ng"):
            result = main.process_one_company(_sr(), _hub(), MagicMock(), set())

        assert result == "ng"
        msgs = _funnel_messages(caplog)
        assert len(msgs) == 1
        assert "screener_ng" in msgs[0]
        assert "大手企業" in msgs[0]
        assert "http://test.co.jp/" in msgs[0]

    def test_rank_ng_emits_funnel_log(self, caplog):
        """evaluate_rank_v2 が NG → [FUNNEL] rank_ng が 1 件出力される"""
        with caplog.at_level(logging.INFO, logger="main"), \
             patch("main.pre_screen", return_value=(True, "")), \
             patch("main.scrape_company_info", return_value=_info()), \
             patch("main.is_excluded_company", return_value=False), \
             patch("main.extract_domain", return_value="test.co.jp"), \
             patch("main.evaluate_rank_v2", return_value=_rank(rank="NG", score=0, ng_reason="広告業種")), \
             patch("main.record_ng"), \
             patch("main.add_to_excluded_companies"):
            result = main.process_one_company(_sr(), _hub(), MagicMock(), set())

        assert result == "ng"
        msgs = _funnel_messages(caplog)
        assert len(msgs) == 1
        assert "rank_ng" in msgs[0]
        assert "広告業種" in msgs[0]

    def test_low_score_emits_funnel_log(self, caplog):
        """score < MIN_REGISTER_SIGNALS → [FUNNEL] low_score が 1 件出力される"""
        with caplog.at_level(logging.INFO, logger="main"), \
             patch("main.pre_screen", return_value=(True, "")), \
             patch("main.scrape_company_info", return_value=_info()), \
             patch("main.is_excluded_company", return_value=False), \
             patch("main.extract_domain", return_value="test.co.jp"), \
             patch("main.evaluate_rank_v2", return_value=_rank(rank="C", score=2)), \
             patch("agents.rank_agent.is_parent_prime_subsidiary", return_value=False), \
             patch("main.find_media_article_url", return_value=""), \
             patch("main.record_ng"), \
             patch("main.add_to_excluded_companies"):
            result = main.process_one_company(_sr(), _hub(), MagicMock(), set())

        assert result == "ng"
        msgs = _funnel_messages(caplog)
        assert len(msgs) == 1
        assert "low_score" in msgs[0]
        assert "score=2" in msgs[0]

    def test_registered_emits_funnel_log(self, caplog):
        """register_company が True → [FUNNEL] registered が 1 件出力される"""
        with caplog.at_level(logging.INFO, logger="main"), \
             patch("main.pre_screen", return_value=(True, "")), \
             patch("main.scrape_company_info", return_value=_info()), \
             patch("main.is_excluded_company", return_value=False), \
             patch("main.extract_domain", return_value="test.co.jp"), \
             patch("main.evaluate_rank_v2", return_value=_rank(rank="A", score=5)), \
             patch("agents.rank_agent.is_parent_prime_subsidiary", return_value=False), \
             patch("main.find_media_article_url", return_value=""), \
             patch("main.record_rank_result"), \
             patch("main.record_ng"):
            result = main.process_one_company(_sr(), _hub(register_ok=True), MagicMock(), set())

        assert result == "success"
        msgs = _funnel_messages(caplog)
        assert len(msgs) == 1
        assert "registered" in msgs[0]
        assert "A" in msgs[0]
        assert "5" in msgs[0]

    def test_pending_emits_funnel_log(self, caplog):
        """register_company が False かつ pending_list あり → [FUNNEL] pending が 1 件出力される"""
        pending = []
        with caplog.at_level(logging.INFO, logger="main"), \
             patch("main.pre_screen", return_value=(True, "")), \
             patch("main.scrape_company_info", return_value=_info()), \
             patch("main.is_excluded_company", return_value=False), \
             patch("main.extract_domain", return_value="test.co.jp"), \
             patch("main.evaluate_rank_v2", return_value=_rank(rank="A", score=5)), \
             patch("agents.rank_agent.is_parent_prime_subsidiary", return_value=False), \
             patch("main.find_media_article_url", return_value=""), \
             patch("main.record_rank_result"), \
             patch("main.record_ng"):
            result = main.process_one_company(
                _sr(), _hub(register_ok=False), MagicMock(), set(), pending_list=pending
            )

        assert result == "pending"
        assert len(pending) == 1
        msgs = _funnel_messages(caplog)
        assert len(msgs) == 1
        assert "pending" in msgs[0]
        assert "A" in msgs[0]


# ── agents/scraper_agent.py の [FUNNEL] ログ検証 ─────────────────────────────

class TestFunnelLoggingScraperAgent:
    """scrape_company_info の FUNNEL ログ 2 種類を検証する"""

    def test_scrape_success_minimal_emits_funnel_log(self, caplog):
        """minimal=True → [FUNNEL] scrape_success_minimal が 1 件出力される"""
        mock_soup = MagicMock()
        # 従業員数パターン "従業員数 50名" が EMPLOYEE_PATTERNS にマッチする
        page_text = "従業員数 50名\n03-1234-5678\n〒100-0001 東京都千代田区1-1"
        with caplog.at_level(logging.INFO, logger="agents.scraper_agent"), \
             patch("agents.scraper_agent.get_page_text", return_value=(page_text, mock_soup)), \
             patch("agents.scraper_agent.extract_company_name", return_value="テスト株式会社"), \
             patch("agents.scraper_agent.extract_prefecture_with_voting", return_value="東京都"):
            info = scrape_company_info("http://example.co.jp", minimal=True)

        assert info["company_name"] == "テスト株式会社"
        assert info["employee_count"] == "50"
        msgs = _funnel_messages(caplog)
        assert len(msgs) == 1
        assert "scrape_success_minimal" in msgs[0]
        assert "example.co.jp" in msgs[0]
        assert "テスト株式会社" in msgs[0]

    def test_scrape_success_full_emits_funnel_log(self, caplog):
        """minimal=False かつ check_company_fields OK → [FUNNEL] scrape_success が 1 件出力される"""
        mock_soup = MagicMock()
        page_text = "従業員数 50名\n03-1234-5678\n株式会社テスト 代表取締役 山田太郎"
        with caplog.at_level(logging.INFO, logger="agents.scraper_agent"), \
             patch("agents.scraper_agent.get_page_text", return_value=(page_text, mock_soup)), \
             patch("agents.scraper_agent.check_company_fields", return_value=(True, [])), \
             patch("agents.scraper_agent.validate_company_info", side_effect=lambda x: x), \
             patch("agents.scraper_agent.extract_company_name", return_value="テスト株式会社"), \
             patch("agents.scraper_agent.extract_representative", return_value="山田太郎"), \
             patch("agents.scraper_agent.extract_phone", return_value="03-1234-5678"), \
             patch("agents.scraper_agent.extract_address_parts",
                   return_value=("100-0001", "東京都", "東京都千代田区1-1")), \
             patch("agents.scraper_agent.extract_employee_count", return_value="50"), \
             patch("agents.scraper_agent.estimate_industry", return_value="IT"), \
             patch("agents.scraper_agent.extract_prefecture_with_voting", return_value="東京都"), \
             patch("agents.scraper_agent.extract_notable_links", return_value=[]), \
             patch("agents.list_page_agent.find_file_links", return_value=[]):
            info = scrape_company_info("http://example.co.jp", minimal=False)

        assert info["company_name"] == "テスト株式会社"
        assert info["employee_count"] == "50"
        msgs = _funnel_messages(caplog)
        assert len(msgs) == 1
        assert "scrape_success" in msgs[0]
        assert "scrape_success_minimal" not in msgs[0]
        assert "example.co.jp" in msgs[0]
        assert "テスト株式会社" in msgs[0]
