"""
検索エージェント
Google Custom Search API（優先）またはDuckDuckGoで検索する。
媒体ドメインのURLは is_media_page=True として通し、企業特集記事から企業HPを抽出する。
"""

import time
import random
import logging
import requests
from urllib.parse import urlparse
from ddgs import DDGS
from config import MEDIA_NAME_TO_DOMAIN, load_exclude_list_csv, count_japanese_chars, JAPANESE_MIN_CHARS_IN_SNIPPET

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


# 法人格キーワード（タイトル内にあれば日本企業の可能性大）
_JP_LEGAL_KEYWORDS = [
    "株式会社", "有限会社", "合同会社",
    "一般社団法人", "一般財団法人",
    "学校法人", "医療法人",
]


def _is_english_site(url: str, title: str, snippet: str) -> bool:
    """
    タイトル＋スニペットの日本語文字がゼロかつ法人格なしの場合に True（英語サイトと判定）。

    条件（AND）:
      1. title + snippet の日本語文字（ひらがな・カタカナ・漢字）が
         JAPANESE_MIN_CHARS_IN_SNIPPET 未満
      2. title に法人格（株式会社・有限会社・合同会社等）が含まれない

    .co.jp は日本法人専用ドメインなので常に通過（False を返す）。
    """
    from urllib.parse import urlparse as _up
    if _up(url).netloc.lower().endswith(".co.jp"):
        return False

    # 条件1: 日本語文字数チェック
    combined = title + " " + snippet
    if count_japanese_chars(combined) >= JAPANESE_MIN_CHARS_IN_SNIPPET:
        return False

    # 条件2: タイトルに法人格キーワードがあれば日本企業の可能性大 → 通過させる
    if any(kw in title for kw in _JP_LEGAL_KEYWORDS):
        return False

    return True


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


def _fetch_hits_google_cse(query: str, tbs: str, num: int) -> list[dict]:
    """
    Google Custom Search APIでヒットを取得する。
    APIキー未設定またはエラー時は空リストを返す。
    """
    from config import GOOGLE_CSE_API_KEY, GOOGLE_CSE_CX
    if not GOOGLE_CSE_API_KEY or not GOOGLE_CSE_CX:
        return []
    # tbs → dateRestrict パラメータ変換
    date_restrict_map = {
        "qdr:w":  "d7",
        "qdr:w2": "d14",
        "qdr:m":  "m1",
        "qdr:m2": "m2",
        "qdr:m3": "m3",
        "qdr:m6": "m6",
        "qdr:m9": "m9",
        "qdr:y":  "y1",
    }
    params = {
        "key": GOOGLE_CSE_API_KEY,
        "cx": GOOGLE_CSE_CX,
        "q": query,
        "lr": "lang_ja",
        "gl": "jp",
        "num": min(num * 2, 10),
    }
    dr = date_restrict_map.get(tbs)
    if dr:
        params["dateRestrict"] = dr
    try:
        resp = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params=params,
            timeout=10,
        )
        if resp.status_code != 200:
            logger.debug(f"Google CSE APIエラー: {resp.status_code}")
            return []
        items = resp.json().get("items", [])
        # DuckDuckGo形式に統一
        return [
            {
                "href": item.get("link", ""),
                "title": item.get("title", ""),
                "body": item.get("snippet", ""),
            }
            for item in items if item.get("link")
        ]
    except Exception as e:
        logger.debug(f"Google CSE例外: {e}")
        return []


def _fetch_hits_ddgs(query: str, tbs: str, num: int) -> list[dict]:
    """DuckDuckGoでヒットを取得する（フォールバック）。"""
    timelimit = TBS_TO_DDG.get(tbs, "y")
    try:
        with DDGS() as ddgs:
            hits = ddgs.text(
                query,
                region="jp-jp",
                safesearch="off",
                timelimit=timelimit,
                max_results=num * 2,
            )
            return list(hits) if hits else []
    except Exception as e:
        logger.debug(f"DuckDuckGo例外: {e}")
        return []


def search_google(query: str, tbs: str, num: int = 10) -> list[dict]:
    """
    Google CSE（優先）またはDuckDuckGoで検索し結果を返す。

    媒体名クエリ（例: "KENJA GLOBAL 掲載"）の場合:
      - 媒体ドメインのURLは is_media_page=True として通す
      - scraper_agent が記事から企業URLを抽出し企業HPをスクレイプする
      - rank_agent がクエリ内の媒体名を検出して +2ボーナスを付与

    通常クエリの場合:
      - SNS・EC・求人サイト等を除外した企業URLを返す
    """
    results = []

    # Google CSE優先、失敗時はDuckDuckGo
    hits = _fetch_hits_google_cse(query, tbs, num)
    source = "Google CSE"
    if not hits:
        hits = _fetch_hits_ddgs(query, tbs, num)
        source = "DuckDuckGo"

    # 既知媒体ドメインのセット（is_media_page判定用）
    known_media_domains = set(MEDIA_NAME_TO_DOMAIN.values())
    learned = load_exclude_list_csv()

    for hit in hits:
        url = hit.get("href", "")
        if not url:
            continue

        parsed = urlparse(url)
        domain = parsed.netloc.replace("www.", "")

        # 絶対除外ドメイン（SNS・EC・求人・大手メディア）
        if any(ex in domain for ex in EXCLUDE_DOMAINS):
            continue
        # メディア・ポータル系キーワード除外（媒体ドメイン以外）
        is_known_media = any(md in domain for md in known_media_domains)
        if not is_known_media and any(kw in domain for kw in NG_DOMAIN_KEYWORDS):
            continue
        # 自動学習 + 手動追加の除外ドメイン
        if any(ex in domain for ex in learned):
            continue
        # 海外TLDをスキップ
        if any(domain.endswith(tld) for tld in FOREIGN_TLDS):
            continue

        title = hit.get("title", "")
        snippet = hit.get("body", "")

        # ファイルURL判定
        path_lower = parsed.path.lower().split("?")[0]
        file_type = ""
        if path_lower.endswith(".pdf"):
            file_type = "pdf"
        elif path_lower.endswith((".xlsx", ".xls")):
            file_type = "xlsx"
        elif path_lower.endswith(".docx"):
            file_type = "docx"

        # 官公庁ファイルは除外
        if file_type and any(domain.endswith(tld) for tld in BLOCKED_FILE_TLDS):
            continue

        # 媒体ドメインの場合は is_media_page=True で通す（企業特集記事として処理）
        if is_known_media:
            results.append({
                "url": url,
                "title": title,
                "snippet": snippet,
                "search_query": query,
                "is_media_page": True,
                "media_domain": domain,
                "file_type": file_type,
            })
            logger.debug(f"媒体記事URL検出 [{source}]: {url}")
        else:
            # 通常企業HP：シグナル検証
            if not _looks_like_company_url(url, title, snippet):
                logger.debug(f"企業URL判定NG（シグナル不足）: {url}")
                _record_rejected_url(url, title, snippet, query, "信号不足")
                continue
            if _is_english_site(url, title, snippet):
                logger.info(f"英語サイト判定（スニペット日本語0・法人格なし）→スキップ: {url}")
                _record_rejected_url(url, title, snippet, query, "英語サイト")
                continue
            results.append({
                "url": url,
                "title": title,
                "snippet": snippet,
                "search_query": query,
                "is_media_page": False,
                "media_domain": "",
                "file_type": file_type,
            })

        if len(results) >= num:
            break

    logger.info(f"検索完了 [{query}]({source}): {len(results)}件")
    time.sleep(random.uniform(1, 3))
    return results


def extract_domain(url: str) -> str:
    """URLからドメイン（www除去）を返す"""
    parsed = urlparse(url)
    domain = parsed.netloc
    if domain.startswith("www."):
        domain = domain[4:]
    return domain
