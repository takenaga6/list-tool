"""
リストページエージェント
指定URL（健康経営優良法人リスト等）から企業名を一括抽出する。

対応形式:
  - HTML（テーブル・リスト）
  - PDF
  - Word (.docx)
  - Excel (.xlsx)

抽出した企業名 → DuckDuckGoで公式HP検索 → search_agent 形式の結果として返す
"""

import io
import re
import time
import random
import logging
import requests
from urllib.parse import urlparse, urljoin

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

COMPANY_NAME_PATTERNS = [
    r"((?:株式会社|合同会社|有限会社|一般社団法人|NPO法人)[^\s「」【】\n\r<、。,]{1,30})",
    r"([^\s「」【】\n\r<、。,]{1,30}(?:株式会社|合同会社|有限会社))",
]

# ファイルリンク拡張子
FILE_EXTENSIONS = {
    ".pdf":  "pdf",
    ".docx": "docx",
    ".xlsx": "xlsx",
    ".xls":  "xlsx",
}

# 除外する求人・SNS等ドメイン（完全一致・部分一致）
SKIP_DOMAINS = [
    "google", "youtube", "twitter", "x.com", "facebook",
    "instagram", "wikipedia", "amazon", "rakuten",
    "indeed", "doda", "mynavi", "en-japan", "type.jp",
    "zhihu", "baidu", "weibo", "bilibili", "ruliweb", "naver", "daum",
    "bing.com", "msn.com",
    # 求人・就職・人材ポータル（誤登録防止）
    "jinzaikakuho", "hellowork", "hello-work", "jsite.mhlw",
    "kyujin", "shushoku", "hataraku", "saiyo",
    "careerindex", "careerlink", "rikunabi", "wantedly",
    "green-japan", "offers.jp", "leverages-career",
    # ニュース・メディア系
    "nikkei.com", "toyokeizai", "diamond.jp", "itmedia",
    "president.jp", "nhk.or.jp", "asahi.com", "yomiuri",
    "pref.", ".go.jp", ".lg.jp",
]

# ドメインにこのキーワードが含まれる場合はメディア・ポータル等と判断して除外
NG_DOMAIN_KEYWORDS = [
    "news", "media", "books", "journal", "magazine", "press",
    "catalog", "navi", "portal", "corporatedb", "-db",
    "jobcatalog", "bestcar", "bestmoto",
]

# 大規模法人リストファイルを示すURLキーワード（除外対象）
DAIKIBO_KEYWORDS = ["daikibo", "大規模", "large"]


# ─────────────────────────────────────────────
# テキスト抽出（各ファイル形式）
# ─────────────────────────────────────────────

def _extract_from_pdf(content: bytes) -> str:
    """PDFバイト列からテキスト抽出"""
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            texts = []
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    texts.append(t)
            return "\n".join(texts)
    except Exception as e:
        logger.debug(f"PDF抽出エラー: {e}")
        return ""


def _extract_from_docx(content: bytes) -> str:
    """Wordバイト列からテキスト抽出"""
    try:
        from docx import Document
        doc = Document(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        logger.debug(f"Word抽出エラー: {e}")
        return ""


def _extract_from_xlsx(content: bytes) -> str:
    """Excelバイト列からテキスト抽出"""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        rows = []
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                row_text = " ".join(str(c) for c in row if c is not None)
                if row_text.strip():
                    rows.append(row_text)
        return "\n".join(rows)
    except Exception as e:
        logger.debug(f"Excel抽出エラー: {e}")
        return ""


# ─────────────────────────────────────────────
# 企業名抽出
# ─────────────────────────────────────────────

def extract_company_names_from_text(text: str) -> list[str]:
    """テキストから企業名（株式会社等）を全て抽出"""
    names = set()
    for pattern in COMPANY_NAME_PATTERNS:
        for m in re.finditer(pattern, text):
            name = m.group(1).strip()
            # 長すぎる・短すぎるものは除外
            if 3 <= len(name) <= 40:
                # ノイズ除去（数字・記号だけの場合を除外）
                if re.search(r'[ぁ-んァ-ン一-龯a-zA-Z]', name):
                    names.add(name)
    return sorted(names)


def extract_company_names_from_html(soup: BeautifulSoup) -> list[str]:
    """HTMLから企業名を抽出（テーブル・リスト優先）"""
    names = set()

    # テーブルから抽出
    for table in soup.find_all("table"):
        for td in table.find_all(["td", "th"]):
            cell = td.get_text(strip=True)
            for pattern in COMPANY_NAME_PATTERNS:
                m = re.search(pattern, cell)
                if m:
                    name = m.group(1).strip()
                    if 3 <= len(name) <= 40:
                        names.add(name)

    # リスト（ul/ol/li）から抽出
    for li in soup.find_all("li"):
        text = li.get_text(strip=True)
        for pattern in COMPANY_NAME_PATTERNS:
            m = re.search(pattern, text)
            if m:
                name = m.group(1).strip()
                if 3 <= len(name) <= 40:
                    names.add(name)

    # 全テキストからも抽出（上記で漏れたもの補完）
    full_text = soup.get_text(separator="\n", strip=True)
    names.update(extract_company_names_from_text(full_text))

    return sorted(names)


# ─────────────────────────────────────────────
# ファイルリンク検出・ダウンロード
# ─────────────────────────────────────────────

def find_file_links(soup: BeautifulSoup, base_url: str) -> list[tuple[str, str]]:
    """
    ページ内のPDF/Word/Excelリンクを返す
    Returns: [(url, file_type), ...]
    """
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href:
            continue
        full_url = urljoin(base_url, href)
        lower = href.lower().split("?")[0]
        # 大規模法人リストファイルは除外（中小企業のみ対象）
        if any(kw in lower for kw in DAIKIBO_KEYWORDS):
            logger.info(f"大規模法人ファイルをスキップ: {full_url}")
            continue
        for ext, ftype in FILE_EXTENSIONS.items():
            if lower.endswith(ext):
                links.append((full_url, ftype))
                break
    return links


def download_and_extract(url: str, file_type: str) -> str:
    """ファイルをダウンロードしてテキスト抽出"""
    try:
        logger.info(f"ファイルダウンロード: {url}")
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            return ""
        content = resp.content

        if file_type == "pdf":
            return _extract_from_pdf(content)
        elif file_type == "docx":
            return _extract_from_docx(content)
        elif file_type == "xlsx":
            return _extract_from_xlsx(content)
    except Exception as e:
        logger.debug(f"ダウンロードエラー: {url} - {e}")
    return ""


# ─────────────────────────────────────────────
# 企業HP検索
# ─────────────────────────────────────────────

def _is_likely_company_hp(company_name: str, hit: dict) -> bool:
    """
    検索ヒットが対象企業の公式HPである可能性を検証する。
    ポータルサイト（求人・地域ナビ等）への誤マッチを防ぐ。
    """
    title = hit.get("title", "")
    snippet = hit.get("body", "")
    url = hit.get("href", "")
    combined = (title + " " + snippet + " " + url).lower()

    # 法人格を除去してコアキーワードを取得
    core = re.sub(
        r'(株式会社|合同会社|有限会社|一般社団法人|NPO法人|社団法人|財団法人)',
        '', company_name
    ).strip()

    if not core or len(core) < 2:
        return True  # 判定不能なのでスキップしない

    # コア名がそのまま含まれていれば確実にOK
    if core.lower() in combined:
        return True

    # コア名をトークン分割して主要語が含まれるか確認
    # 例: "AGCディスプレイグラス米沢" → ["AGC", "ディスプレイグラス", "米沢"]
    tokens = re.findall(r'[A-Za-z]+|[ァ-ヶー]{2,}|[一-龯]{2,}', core)
    significant = [t for t in tokens if len(t) >= 2]

    if not significant:
        return True

    # 主要トークンのうち過半数が含まれていればOK
    matched = sum(1 for t in significant if t.lower() in combined)
    return matched >= max(1, len(significant) // 2)


def search_company_hp(company_name: str, source_url: str) -> dict | None:
    """
    企業名で公式HPをDuckDuckGo検索し、search_agent形式の結果を返す。
    ポータル・求人サイト等への誤マッチを防ぐため企業名の一致検証を行う。
    見つからない場合は None。
    """
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            hits = ddgs.text(
                f"{company_name} 公式サイト 会社概要",
                region="jp-jp",
                safesearch="off",
                max_results=5,
            )
            for hit in hits:
                url = hit.get("href", "")
                if not url:
                    continue
                domain = urlparse(url).netloc.replace("www.", "")

                # スキップ対象ドメイン
                if any(s in domain for s in SKIP_DOMAINS):
                    logger.debug(f"SKIP_DOMAINS除外: {domain}")
                    continue
                # メディア・ポータル系ドメインキーワード除外
                if any(kw in domain for kw in NG_DOMAIN_KEYWORDS):
                    logger.debug(f"NGキーワード除外: {domain}")
                    continue
                # 海外TLD除外
                foreign_tlds = [".us", ".uk", ".au", ".de", ".fr", ".cn", ".kr"]
                if any(domain.endswith(t) for t in foreign_tlds):
                    continue

                # 企業名一致検証（ポータルサイト誤マッチ防止）
                if not _is_likely_company_hp(company_name, hit):
                    logger.debug(
                        f"企業名不一致のためスキップ: {company_name} → {url} "
                        f"(title={hit.get('title', '')[:40]})"
                    )
                    continue

                logger.debug(f"HP発見: {company_name} → {url}")
                return {
                    "url": url,
                    "title": hit.get("title", company_name),
                    "snippet": hit.get("body", ""),
                    "search_query": f"[リストページ] {company_name}",
                    "is_media_page": False,
                    "media_domain": "",
                    "source_list_url": source_url,
                }
    except Exception as e:
        logger.debug(f"HP検索エラー: {company_name} - {e}")
    return None


# ─────────────────────────────────────────────
# メイン関数
# ─────────────────────────────────────────────

def scrape_company_list_page(list_url: str, max_companies: int = 200) -> list[dict]:
    """
    リストページURLから企業を一括取得し、search_agent形式のリストを返す。

    処理:
      1. HTMLページから企業名を抽出
      2. PDF/Word/Excelリンクを検出 → ダウンロード → 企業名抽出
      3. 各企業名でDuckDuckGo検索 → 公式HP URL を取得
      4. search_agent 形式の dict リストを返す

    Args:
        list_url: リストページURL（例: https://kenko-keiei.jp/houjin_list/）
        max_companies: 最大取得企業数

    Returns:
        [{"url": ..., "search_query": ..., ...}, ...]
    """
    logger.info(f"リストページ取得開始: {list_url}")
    company_names: set[str] = set()

    # ① HTMLページ取得
    try:
        resp = requests.get(list_url, headers=HEADERS, timeout=15)
        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        # HTMLから企業名抽出
        html_names = extract_company_names_from_html(soup)
        company_names.update(html_names)
        logger.info(f"HTML抽出: {len(html_names)}社")

        # ② PDF/Word/Excelリンクを処理
        file_links = find_file_links(soup, list_url)
        logger.info(f"ファイルリンク検出: {len(file_links)}件")

        for file_url, file_type in file_links:
            text = download_and_extract(file_url, file_type)
            if text:
                file_names = extract_company_names_from_text(text)
                company_names.update(file_names)
                logger.info(f"  {file_type.upper()}から{len(file_names)}社抽出: {file_url}")
            time.sleep(random.uniform(0.5, 1.5))

    except Exception as e:
        logger.error(f"リストページ取得エラー: {list_url} - {e}")
        return []

    logger.info(f"合計抽出企業名: {len(company_names)}社")

    if not company_names:
        logger.warning("企業名が抽出できませんでした")
        return []

    # ③ 各企業のHP検索
    results = []
    for i, name in enumerate(sorted(company_names)[:max_companies]):
        logger.info(f"HP検索 ({i+1}/{min(len(company_names), max_companies)}): {name}")
        result = search_company_hp(name, list_url)
        if result:
            results.append(result)
        # DuckDuckGoレート制限対策
        time.sleep(random.uniform(1.0, 2.5))

    logger.info(f"HP取得完了: {len(results)}/{min(len(company_names), max_companies)}社")
    return results
