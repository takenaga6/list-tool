"""
検索エージェント
DuckDuckGoで検索し、媒体名クエリの場合は媒体サイトのURLのみに絞り込む
"""

import time
import random
import logging
from urllib.parse import urlparse
from ddgs import DDGS
from config import MEDIA_NAME_TO_DOMAIN, load_exclude_list_csv

logger = logging.getLogger(__name__)

# 明らかな海外TLD（日本企業ではありえないドメイン）
FOREIGN_TLDS = [
    ".us", ".uk", ".au", ".de", ".fr", ".cn", ".kr", ".tw",
    ".sg", ".hk", ".ca", ".eu", ".ru", ".in", ".br", ".mx",
    ".it", ".es", ".nl", ".se", ".no", ".fi", ".dk", ".pl",
]

# 検索結果から除外するドメイン（媒体サイト自体・SNS・ECなど）
EXCLUDE_DOMAINS = [
    "google.com", "google.co.jp",
    "youtube.com", "wikipedia.org",
    "amazon.co.jp", "amazon.com",
    "rakuten.co.jp", "twitter.com", "x.com",
    "facebook.com", "instagram.com", "linkedin.com",
    "note.com", "prtimes.jp", "atpress.ne.jp",
    "infbs.net", "hellowork.mhlw.go.jp",
    # 求人媒体
    "doda.jp", "mynavi.jp", "en-japan.com",
    "type.jp", "indeed.com", "en-gage.net", "bene-fits.jp",
    # 中国・海外SNS・掲示板（Bingノイズ）
    "zhihu.com", "baidu.com", "weibo.com", "bilibili.com",
    "ruliweb.com", "naver.com", "daum.net",
    "bing.com", "msn.com",
    # ニュース・雑誌・メディアサイト（企業HPではない）
    "jbpress.ismedia.jp", "toyokeizai.net", "nikkei.com",
    "diamond.jp", "president.jp", "gendai.media",
    "bunshun.jp", "fujisan.co.jp", "docomo.ne.jp",
    "nhk.or.jp", "asahi.com", "yomiuri.co.jp", "mainichi.jp",
    "sankei.com", "businessinsider.jp", "newspicks.com",
    "mag2.com", "itmedia.co.jp", "techcrunch.com",
    "forbes.com", "huffpost.com",
    # 企業DB・ポータル系
    "corporatedb.jp", "houjin.info", "baseconnect.in",
    "jobcatalog.yahoo.co.jp",
]

# ドメインにこのキーワードが含まれる場合はメディア・ポータル等と判断して除外
NG_DOMAIN_KEYWORDS = [
    "news", "media", "books", "journal", "magazine",
    "catalog", "corporatedb", "jobcatalog",
    "bestcar", "bestmoto",
    # 企業DB・検索サービス
    "research", "houjin", "kaisha", "company-db", "companydb",
    "navi", "ranking", "review",
]

# ファイルURLで除外するTLD（官公庁・団体のリストファイルは対象外）
BLOCKED_FILE_TLDS = [".go.jp", ".or.jp", ".ac.jp", ".lg.jp", ".ed.jp"]

# 期間フィルターの変換（DuckDuckGo形式）
TBS_TO_DDG = {
    "qdr:w":  "w",
    "qdr:w2": "w",
    "qdr:m":  "m",
    "qdr:m2": "m",
    "qdr:m3": "m",
    "qdr:m6": "y",
    "qdr:m9": "y",
    "qdr:y":  "y",
}


def _looks_like_company_url(url: str, title: str, snippet: str) -> bool:
    """
    URLが企業の公式HPである可能性を判定する（ポジティブシグナル検証）。

    設計:
      - .co.jp → 日本法人専用ドメインのため無条件通過
      - .com / .net / .jp → 追加シグナル1件以上あれば通過
      - その他TLD → 追加シグナル必須

    追加シグナル（部分一致）:
      ① タイトルに株式会社 / 有限会社
      ② URLパスに会社概要系セグメント（/company, /about 等）
      ③ スニペットに企業HP定番ワード（日本語・英語・カタカナ）
    """
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    path   = parsed.path.lower()
    combined = (title + " " + snippet).lower()

    # .co.jp は日本法人専用 → 無条件通過
    if domain.endswith(".co.jp"):
        return True

    # 追加シグナルを評価
    signals = 0

    # ① タイトルに法人格
    if "株式会社" in title or "有限会社" in title:
        signals += 1

    # ② URLパスに会社概要系セグメント
    COMPANY_PATHS = [
        "/company", "/about", "/corporate", "/profile",
        "/gaiyou", "/kaisya", "/kaisha", "/aboutus",
        "/service", "/services", "/product", "/products",
        "/business", "/service-info", "/company-info",
    ]
    if any(kw in path for kw in COMPANY_PATHS):
        signals += 1

    # ③ スニペット・タイトルに企業HP定番ワード（部分一致・大文字小文字無視）
    CORP_KEYWORDS = [
        # 日本語
        "会社概要", "代表取締役", "事業内容", "資本金", "設立",
        "お問い合わせ", "アクセス", "採用情報", "採用", "リクルート",
        "サービス", "製品", "製品情報", "事業案内", "会社案内",
        # 英語（部分一致なので "ceo" "founded" 等でも検知）
        "company profile", "representative", "ceo", "founded",
        "capital", "employees", "about us", "contact", "services",
        "products", "business", "company", "corporate",
        # カタカナ
        "コーポレート", "プロフィール",
    ]
    if any(kw in combined for kw in CORP_KEYWORDS):
        signals += 1

    # .com / .net / .jp はシグナル1件以上で通過
    if domain.endswith((".com", ".net", ".jp")) and signals >= 1:
        return True

    # その他TLDはシグナル2件以上必要
    return signals >= 2


def detect_media_domain(query: str) -> str:
    """
    クエリに媒体名が含まれる場合、その媒体ドメインを返す。
    含まれない場合は空文字を返す。
    """
    query_lower = query.lower()
    for media_name, domain in MEDIA_NAME_TO_DOMAIN.items():
        if media_name.lower() in query_lower:
            return domain
    return ""


def _record_rejected_url(url: str, title: str, snippet: str, query: str, reason: str) -> None:
    """検索候補として不採用になったURLをログとして残す（調査用）。"""
    try:
        # 過度な出力を防ぐため、最低限の項目だけ保存する
        from config import REJECTED_SEARCH_URLS_FILE
        import csv
        import os

        os.makedirs(os.path.dirname(REJECTED_SEARCH_URLS_FILE), exist_ok=True)
        file_exists = os.path.exists(REJECTED_SEARCH_URLS_FILE) and os.path.getsize(REJECTED_SEARCH_URLS_FILE) > 0
        with open(REJECTED_SEARCH_URLS_FILE, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["timestamp", "query", "url", "title", "snippet", "reason"],
            )
            if not file_exists:
                writer.writeheader()
            writer.writerow({
                "timestamp": datetime.now().isoformat(),
                "query": query,
                "url": url,
                "title": title,
                "snippet": snippet,
                "reason": reason,
            })
    except Exception:
        # 失敗しても本処理には影響させない
        pass


def search_google(query: str, tbs: str, num: int = 10) -> list[dict]:
    """
    DuckDuckGoで検索し結果を返す。

    媒体名クエリ（例: "KENJA GLOBAL 株式会社"）の場合:
      - DuckDuckGoは媒体に掲載された企業のページを返す
      - 媒体ドメイン自体・SNS・ECを除外し、企業ページとして処理
      - rank_agentがクエリ内の媒体名を検出して+2ボーナスを付与

    通常クエリの場合:
      - 媒体・SNS・ECを除いた企業URLを返す
    """
    results = []
    timelimit = TBS_TO_DDG.get(tbs, "y")
    media_domain = detect_media_domain(query)

    try:
        with DDGS() as ddgs:
            hits = ddgs.text(
                query,
                region="jp-jp",
                safesearch="off",
                timelimit=timelimit,
                max_results=num * 2,
            )

            for hit in hits:
                url = hit.get("href", "")
                if not url:
                    continue

                parsed = urlparse(url)
                domain = parsed.netloc.replace("www.", "")

                # 除外ドメインをスキップ（媒体・SNS・ECなど）
                if any(ex in domain for ex in EXCLUDE_DOMAINS):
                    continue
                # メディア・ポータル系ドメインキーワード除外
                if any(kw in domain for kw in NG_DOMAIN_KEYWORDS):
                    continue
                # 自動学習 + 手動追加の除外ドメインもスキップ
                learned = load_exclude_list_csv()
                if any(ex in domain for ex in learned):
                    continue
                # 海外TLDをスキップ（日本企業のみ対象）
                if any(domain.endswith(tld) for tld in FOREIGN_TLDS):
                    continue
                # 媒体ドメイン自体も除外（企業サイトのみ対象）
                if any(md in domain for md in MEDIA_NAME_TO_DOMAIN.values()):
                    continue

                # 企業HPポジティブシグナル検証（ポータル・ニュース記事の混入を防ぐ）
                title = hit.get("title", "")
                snippet = hit.get("body", "")
                if not _looks_like_company_url(url, title, snippet):
                    logger.debug(f"企業URL判定NG（シグナル不足）: {url}")
                    _record_rejected_url(url, title, snippet, query, "信号不足")
                    continue

                # ファイルURL判定（PDF/Excel/Word）
                path_lower = parsed.path.lower().split("?")[0]
                file_type = ""
                if path_lower.endswith(".pdf"):
                    file_type = "pdf"
                elif path_lower.endswith((".xlsx", ".xls")):
                    file_type = "xlsx"
                elif path_lower.endswith(".docx"):
                    file_type = "docx"

                # 官公庁・団体ドメインのファイルは除外（企業リストではなく行政文書）
                if file_type and any(domain.endswith(tld) for tld in BLOCKED_FILE_TLDS):
                    continue

                results.append({
                    "url": url,
                    "title": title,
                    "snippet": snippet,
                    "search_query": query,
                    "is_media_page": False,
                    "media_domain": "",
                    "file_type": file_type,  # "" なら通常HTML
                })

                if len(results) >= num:
                    break

    except Exception as e:
        logger.error(f"検索エラー [{query}]: {e}")

    logger.info(f"検索完了 [{query}]: {len(results)}件")
    time.sleep(random.uniform(1, 3))
    return results


def extract_domain(url: str) -> str:
    """URLからドメイン（www除去）を返す"""
    parsed = urlparse(url)
    domain = parsed.netloc
    if domain.startswith("www."):
        domain = domain[4:]
    return domain
