"""
スクレイピングエージェント
・媒体記事ページ → 掲載企業のURLを抽出
・企業サイト → 会社名・代表者・住所・電話・従業員数・業種・郵便番号を抽出
"""

import re
import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

ABOUT_PAGE_PATHS = [
    "/company", "/company/", "/company.html",
    "/company/profile", "/company/profile/", "/company/about",
    "/about", "/about/", "/about.html", "/aboutus", "/aboutus/",
    "/about-us", "/about_us",
    "/corporate", "/corporate/", "/corporate/profile",
    "/profile", "/profile/",
    "/gaiyou", "/gaiyou.html", "/gaiyou/",
    "/outline", "/outline/",
    "/kaisya", "/kaisya/",
    "/info", "/info/company",
]

REP_PATTERNS = [
    r"代表取締役(?:社長|CEO|COO)?\s*[：:]\s*([^\s\n\r<「」]{2,20})",
    r"代表者?\s*[：:]\s*([^\s\n\r<「」]{2,20})",
    r"社長\s*[：:]\s*([^\s\n\r<「」]{2,20})",
    r"CEO\s*[：:]\s*([^\s\n\r<「」]{2,15})",
    r"代表取締役\s+([^\s<]{2,6})\s{0,3}([^\s<]{1,6})",
]

PHONE_PATTERNS = [
    r"(?:TEL|Tel|tel|電話番号?|T\.E\.L|お電話)[.：:./\s]*([0-9０-９\-ー－・\(\)（）\s]{10,18})",
    r"(0\d{1,4}[-－ー・/]\d{2,4}[-－ー・/]\d{3,4})",
    r"(\d{2,4}[-－ー]\d{2,4}[-－ー]\d{3,4})",
]

# 全都道府県リスト（誤検知防止）
ALL_PREFECTURES = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県",
    "岐阜県", "静岡県", "愛知県", "三重県",
    "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県",
    "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県",
    "福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
]

ADDRESS_PATTERNS = [
    r"〒\s*\d{3}[-ー]\d{4}\s*([^\n\r<]{5,60}(?:都|道|府|県)[^\n\r<]{3,30}(?:市|区|町|村)[^\n\r<]{0,30})",
    r"(?:所在地|住所|本社住所|本店所在地)\s*[：:]\s*([^\n\r<]{5,60}(?:都|道|府|県)[^\n\r<]{3,30}(?:市|区|町|村)[^\n\r<]{0,30})",
]

COMPANY_NAME_PATTERNS = [
    r"((?:株式会社|合同会社|有限会社|一般社団法人|NPO法人)[^\s「」【】\n\r<]{1,30})",
    r"([^\s「」【】\n\r<]{1,30}(?:株式会社|合同会社|有限会社))",
]

EMPLOYEE_PATTERNS = [
    r"従業員[数人]?\s*[：:\s]*(\d+)\s*名",
    r"社員[数人]?\s*[：:\s]*(\d+)\s*名",
    r"スタッフ[数人]?\s*[：:\s]*(\d+)\s*名",
    r"(\d+)\s*名(?:のスタッフ|の社員|の従業員)",
]

# 業種キーワードマップ（テキストから業種を推定）
INDUSTRY_MAP = [
    (["IT", "システム", "ソフトウェア", "DX", "SaaS", "クラウド", "AI", "アプリ"], "情報通信"),
    (["製造", "メーカー", "工場", "製品"], "製造"),
    (["人材", "派遣", "採用", "HR", "求人", "転職"], "人材サービス"),
    (["社労士", "社会保険労務士", "労務"], "社会保険労務士"),
    (["会計", "税理士", "経理", "財務", "コンサル"], "コンサルティング・士業"),
    (["不動産", "賃貸", "マンション", "物件"], "不動産"),
    (["金融", "保険", "証券", "ファイナンス", "投資", "モーゲージ"], "金融・保険"),
    (["広告", "マーケティング", "PR", "メディア", "デザイン", "クリエイティブ"], "広告・マーケティング"),
    (["商社", "卸売", "輸入", "輸出", "貿易"], "商社・卸売"),
    (["教育", "研修", "スクール", "塾", "セミナー"], "教育"),
    (["医療", "クリニック", "病院", "歯科", "薬"], "医療"),
    (["福祉", "介護", "障害", "支援"], "福祉・介護"),
    (["飲食", "レストラン", "カフェ", "食品"], "飲食・食品"),
    (["小売", "販売", "ショップ", "店舗"], "小売"),
]


def check_company_fields(all_text: str) -> tuple[bool, list[str]]:
    """
    スクレイプ後のテキストでマスト項目の有無を確認する。

    除外条件:
      - 「運営会社」の記載あり → サービスサイト（SaaS等）であり企業HPではない

    マスト5項目（トップページ記載でもOK）:
      ① 法人格（株式会社/合同会社/有限会社）
      ② 代表取締役 / 代表者
      ③ 事業内容 / Company / About / 企業情報 など
      ④ 〒住所 または 都道府県+市区町村
      ⑤ TEL / 電話番号

    5項目中3つ以上あれば企業HPと判定。

    Returns:
        (is_company_page, missing_fields_list)
    """
    # 日本語ページ判定（ひらがな・カタカナが50文字未満 → 海外企業・英語サイト）
    japanese_chars = len(re.findall(r'[\u3040-\u309F\u30A0-\u30FF]', all_text[:3000]))
    if japanese_chars < 50:
        return False, ["日本語ページではない（海外企業・英語サイト）"]

    # サービスページ除外（「運営会社」= SaaS・プロダクトサイトの特徴的な表現のみ対象）
    # ※「利用規約」「プライバシーポリシー」は企業HPにも普通に存在するため除外しない
    if re.search(r"運営会社|運営元|このサービスについて|本サービスの運営", all_text[:3000]):
        return False, ["運営会社記載（サービスページ）"]

    # 上場・IR情報が含まれているページは除外
    # ※「株式会社」は株式の一部文字列を含むため、特定の表現に絞る
    if re.search(
        r"IR情報|投資家情報|株主(?:総会|向け)?|株式(?:公開|上場|情報|投資|譲渡|市場)|"
        r"上場企業|証券コード|東証|プライム市場|スタンダード市場|グロース市場|TSE[:：]|JPX",
        all_text,
    ):
        return False, ["上場/IR情報あり"]

    checks = {
        "法人格":   bool(re.search(r"株式会社|合同会社|有限会社|一般社団法人", all_text)),
        "代表者":   bool(re.search(r"代表取締役|代表者|社長\s*[：:]|CEO\s*[：:]|President", all_text)),
        "事業内容": bool(re.search(
            r"事業内容|サービス内容|主な事業|業務内容|企業情報|会社情報|会社概要"
            r"|Company|About\s*Us|Our\s*Business|About\s*Company",
            all_text
        )),
        "住所":     bool(re.search(r"〒\s*\d{3}[-ー]\d{4}|[^\s]{2,4}[都道府県][^\s]{2,6}[市区町村]", all_text)),
        "TEL":      bool(re.search(r"TEL|電話番号|Tel\.|0\d{1,4}[-－ー]\d{2,4}[-－ー]\d{3,4}", all_text)),
    }

    # 従業員数が記載されていない企業はリストアップ対象外
    # ※求人サイト等で「100名以上」といった曖昧表現だけのケースも除外
    employee_count = extract_employee_count(all_text)
    if not employee_count:
        missing = ["従業員数"]
        # 既存のチェック不足と組み合わせる
        missing += [k for k, v in checks.items() if not v]
        return False, missing

    missing = [k for k, v in checks.items() if not v]
    present_count = sum(checks.values())
    is_company = present_count >= 3
    return is_company, missing


def find_media_article_url(company_name: str, search_query: str = "") -> str:
    """
    企業の「媒体掲載記事URL」を取得する。HubSpot説明欄に記載するために使用。

    ① クエリに媒体名が含まれる場合 → その媒体で企業名検索
    ② 含まれない場合 → 全PR媒体を横断して企業名検索（最初にヒットした記事を返す）

    これにより、どの検索クエリ経由で発見した企業でも、
    媒体掲載記事URL（=リストアップ根拠）を説明欄に記載できる。
    """
    from config import MEDIA_NAME_TO_DOMAIN
    if not company_name:
        return ""

    # ① クエリに媒体名が含まれる場合は該当媒体に絞る
    query_lower = search_query.lower()
    prioritized_media = {}
    for media_name, domain in MEDIA_NAME_TO_DOMAIN.items():
        if media_name.lower() in query_lower:
            prioritized_media[media_name] = domain
            break  # 最初にマッチした媒体のみ

    # ② マッチなし → 全媒体を横断（代表的な媒体のみ、負荷軽減のため上位5件）
    if not prioritized_media:
        items = list(MEDIA_NAME_TO_DOMAIN.items())[:5]
        prioritized_media = dict(items)

    try:
        from ddgs import DDGS
        for media_name, media_domain in prioritized_media.items():
            with DDGS() as ddgs:
                hits = ddgs.text(
                    f"{media_name} {company_name}",
                    region="jp-jp",
                    safesearch="off",
                    max_results=5,
                )
                for hit in hits:
                    url = hit.get("href", "")
                    if not url:
                        continue
                    parsed = urlparse(url)
                    domain_hit = parsed.netloc.replace("www.", "")
                    # 媒体ドメインのURLかつトップページでない
                    if media_domain in domain_hit and parsed.path not in ("", "/", "/index.html"):
                        logger.debug(f"媒体記事URL発見: {company_name} → {url} ({media_name})")
                        return url
    except Exception as e:
        logger.debug(f"媒体記事URL検索エラー: {e}")
    return ""


def extract_notable_links(soup: BeautifulSoup, base_url: str, max_links: int = 5) -> list[str]:
    """
    企業ページ内の注目リンクを抽出する。
    HubSpot説明欄に「なぜリストアップしたか」の根拠として記載する。

    対象:
      - プレスリリース（prtimes, atpress等）
      - 健康経営・認定・受賞関連ページ
      - 媒体掲載記事（社長インタビュー等）
      - ニュース・お知らせページ内の外部リンク

    除外:
      - 自社ドメイン内リンク（ナビ・フッター）
      - SNS・YouTube等
    """
    if not soup:
        return []

    parsed_base = urlparse(base_url)
    own_domain = parsed_base.netloc.replace("www.", "")

    # 注目ラベルキーワード（アンカーテキストに含まれる場合に優先）
    NOTABLE_LABELS = [
        "健康経営", "優良法人", "認定", "受賞", "表彰", "プレスリリース",
        "ニュース", "お知らせ", "メディア", "掲載", "インタビュー", "取材",
        "健康", "ウェルネス", "福利厚生", "社長", "代表", "受賞歴",
    ]

    # 外部リンクとして優先するドメイン
    PRIORITY_DOMAINS = [
        "prtimes.jp", "atpress.ne.jp", "kenko-keiei.jp",
        "meti.go.jp", "mhlw.go.jp",  # 認定ページとして許容
    ]

    SKIP_DOMAINS = [
        "google", "youtube", "twitter", "x.com", "facebook",
        "instagram", "linkedin", "amazon", "rakuten",
    ]

    found = []
    seen_urls = set()

    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue

        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        if parsed.scheme not in ("http", "https"):
            continue

        domain = parsed.netloc.replace("www.", "")

        # 自社ドメインは除外
        if own_domain and own_domain in domain:
            continue
        # SNS等は除外
        if any(s in domain for s in SKIP_DOMAINS):
            continue
        # 重複除外
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        label = a.get_text(strip=True)
        is_priority_domain = any(pd in domain for pd in PRIORITY_DOMAINS)
        has_notable_label = any(kw in label for kw in NOTABLE_LABELS)

        if is_priority_domain or has_notable_label:
            found.insert(0, full_url)  # 優先URLは先頭に
        elif label and len(label) > 5:
            found.append(full_url)

    # 重複を保ちつつ上位を返す
    seen = set()
    result = []
    for u in found:
        if u not in seen:
            seen.add(u)
            result.append(u)
        if len(result) >= max_links:
            break

    return result


def get_page_text(url: str, timeout: int = 8) -> tuple[str, BeautifulSoup | None]:
    """URLのページテキストとBeautifulSoupを返す"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)

        # エンコーディング: まずUTF-8を試みる（apparent_encodingは誤検知が多い）
        for enc in ["utf-8", resp.apparent_encoding or "utf-8", "cp932", "euc-jp"]:
            try:
                resp.encoding = enc
                text_candidate = resp.text
                # 日本語が30文字以上あれば正常と判断
                ja_count = len(re.findall(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', text_candidate[:3000]))
                if ja_count >= 30 or enc == "utf-8":
                    break
            except Exception:
                continue

        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return soup.get_text(separator=" ", strip=True), soup
    except Exception as e:
        logger.debug(f"ページ取得失敗: {url} - {e}")
        return "", None


def _search_company_url_by_name(company_name: str) -> str:
    """企業名でDuckDuckGo検索して公式HPのURLを探す（フォールバック用）"""
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            hits = ddgs.text(
                f"{company_name} 公式サイト",
                region="jp-jp",
                safesearch="off",
                max_results=5,
            )
            skip = [
                "google", "youtube", "twitter", "x.com", "facebook",
                "instagram", "wikipedia", "amazon", "rakuten",
                "indeed", "doda", "mynavi", "en-japan", "type.jp",
                "wantedly", "rikunabi", "careerindex", "careerlink",
                "nikkei.com", "toyokeizai", "diamond.jp", "itmedia",
                "president.jp", "nhk.or.jp", "asahi.com", "yomiuri",
                "pref.", ".go.jp", ".lg.jp",
            ]
            for hit in hits:
                url = hit.get("href", "")
                domain = urlparse(url).netloc.replace("www.", "")
                if any(s in domain for s in skip):
                    continue
                # 会社名をドメインに含むか、.co.jpのもの優先
                parsed = urlparse(url)
                top_url = f"{parsed.scheme}://{parsed.netloc}"
                logger.debug(f"DuckDuckGo検索で企業URL発見: {company_name} → {top_url}")
                return top_url
    except Exception as e:
        logger.debug(f"企業URL検索エラー: {e}")
    return ""


def extract_company_name_from_media_page(soup: BeautifulSoup, text: str) -> str:
    """媒体記事ページから掲載企業名を抽出する"""
    # h1・h2タグから企業名を探す
    for tag in (soup.find_all("h1") + soup.find_all("h2"))[:5]:
        tag_text = tag.get_text(strip=True)
        for pattern in COMPANY_NAME_PATTERNS:
            match = re.search(pattern, tag_text)
            if match:
                return match.group(1).strip()[:40]

    # テキスト全体から企業名パターンを探す（先頭1500文字）
    for pattern in COMPANY_NAME_PATTERNS:
        match = re.search(pattern, text[:1500])
        if match:
            return match.group(1).strip()[:40]

    return ""


def extract_company_url_from_media_page(media_url: str) -> tuple[str, str]:
    """
    媒体記事ページから掲載企業のURL・企業名を抽出する。

    手順:
    1. 記事内の外部リンク（公式サイトラベル優先）を探す
    2. 見つからなければ記事から企業名を取得してDuckDuckGoで検索

    Returns:
        (company_url, company_name)  どちらも空文字の場合は取得失敗
    """
    text, soup = get_page_text(media_url)
    if not soup:
        return "", ""

    parsed_media = urlparse(media_url)
    media_domain = parsed_media.netloc.replace("www.", "")

    skip_domains = [
        "google", "youtube", "twitter", "x.com", "facebook",
        "instagram", "linkedin", "amazon", "rakuten", "wikipedia",
        "note.com", "prtimes", "atpress",
        "nikkei.com", "toyokeizai", "diamond.jp", "itmedia",
        "president.jp", "nhk.or.jp", "asahi.com", "yomiuri",
        "indeed", "doda", "mynavi", "en-japan", "wantedly",
        "jinzaikakuho", "pref.", ".go.jp", ".lg.jp",
    ]

    priority_labels = [
        "公式サイト", "ホームページ", "公式hp", "会社hp", "会社サイト",
        "オフィシャル", "official", "website", "web site", "詳細はこちら",
        "会社情報", "企業サイト",
    ]

    candidate_urls = []

    for a_tag in soup.find_all("a", href=True):
        href = a_tag.get("href", "")
        if not href.startswith("http"):
            href = urljoin(media_url, href)
        if not href.startswith("http"):
            continue

        parsed = urlparse(href)
        domain = parsed.netloc.replace("www.", "")

        if media_domain in domain:
            continue
        if any(s in domain for s in skip_domains):
            continue
        if not any(tld in domain for tld in [".co.jp", ".com", ".jp", ".net", ".org"]):
            continue

        label = a_tag.get_text(strip=True).lower()
        is_priority = any(pl in label for pl in priority_labels)

        top_url = f"{parsed.scheme}://{parsed.netloc}"
        if is_priority:
            candidate_urls.insert(0, top_url)
        else:
            candidate_urls.append(top_url)

    # ① 記事内リンクから企業URLを取得
    if candidate_urls:
        best_url = candidate_urls[0]
        logger.debug(f"記事内リンクから企業URL: {media_url} → {best_url}")
        return best_url, ""

    # ② フォールバック：記事から企業名を取得 → DuckDuckGoで検索
    company_name = extract_company_name_from_media_page(soup, text)
    if company_name:
        logger.info(f"フォールバック検索: {company_name}")
        found_url = _search_company_url_by_name(company_name)
        return found_url, company_name

    logger.debug(f"企業URL・企業名の取得失敗: {media_url}")
    return "", ""


def extract_company_name(soup: BeautifulSoup, text: str) -> str:
    if soup:
        title_tag = soup.find("title")
        if title_tag:
            title_text = title_tag.get_text(strip=True)
            for sep in ["|", "｜", " - ", "–", "—", "　"]:
                for part in title_text.split(sep):
                    part = part.strip()
                    if any(kw in part for kw in ["株式会社", "合同会社", "有限会社", "一般社団法人"]):
                        return part[:40]
        og = soup.find("meta", property="og:site_name")
        if og and og.get("content"):
            return og["content"].strip()[:40]

    for pattern in COMPANY_NAME_PATTERNS:
        match = re.search(pattern, text[:500])
        if match:
            return match.group(1).strip()[:40]
    return ""


def extract_representative(text: str) -> str:
    for pattern in REP_PATTERNS:
        match = re.search(pattern, text)
        if match:
            name = match.group(1).strip()
            name = re.sub(r"[　\s]{2,}", " ", name)
            name = name.replace("さん", "").replace("氏", "").strip()
            if 2 <= len(name) <= 20:
                return name
    return ""


def extract_phone(text: str, soup: BeautifulSoup = None) -> str:
    # ① tel: リンクから優先取得（最も確実）
    if soup:
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if href.startswith("tel:"):
                phone = href[4:].strip()
                # 全角→半角変換
                phone = phone.translate(str.maketrans("０１２３４５６７８９ー－", "0123456789--"))
                phone = re.sub(r"\s+", "", phone)
                phone = re.sub(r"[^\d\-]", "", phone)
                if 10 <= len(phone) <= 13:
                    return phone

    # ② テキストパターンから抽出
    for pattern in PHONE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            phone = match.group(1).strip()
            phone = phone.translate(str.maketrans("０１２３４５６７８９ー－", "0123456789--"))
            phone = re.sub(r"\s+", "", phone)
            if 10 <= len(phone) <= 15:
                return phone
    return ""


def extract_address_parts(text: str) -> tuple[str, str, str]:
    """
    住所から (郵便番号, 都道府県, 「都道府県+市区町村」) を返す
    """
    zip_code = ""
    prefecture = ""
    full_address = ""

    # 文字化け行を除去（非CJK・非ASCII比率が高い行はスキップ）
    clean_lines = []
    for line in text.splitlines():
        valid = len(re.findall(r'[\u0020-\u007E\u3000-\u9FFF\uFF00-\uFFEF]', line))
        total = len(line)
        if total == 0 or valid / total >= 0.5:
            clean_lines.append(line)
    clean_text = " ".join(clean_lines)

    # 郵便番号
    zip_match = re.search(r"〒\s*(\d{3}[-ー]\d{4})", clean_text)
    if zip_match:
        zip_code = zip_match.group(1).replace("ー", "-")

    # 都道府県（全47都道府県リストで正確にマッチ）
    for pref in ALL_PREFECTURES:
        if pref in clean_text:
            prefecture = pref
            break

    # 「都道府県+市区町村」まで抽出
    if prefecture:
        # 都道府県以降のテキストから市区町村を取得
        pref_idx = clean_text.find(prefecture)
        after_pref = clean_text[pref_idx:pref_idx + 60]
        city_match = re.search(
            r"(" + re.escape(prefecture) + r"[^\s\n\r<]{2,20}?(?:市|区|町|村))",
            after_pref
        )
        if city_match:
            full_address = city_match.group(1).strip()

    # 郵便番号付き住所パターンでも試みる
    if not full_address:
        for pattern in ADDRESS_PATTERNS:
            match = re.search(pattern, clean_text)
            if match:
                addr = match.group(1) if match.lastindex and match.lastindex >= 1 else match.group(0)
                addr = re.sub(r"\s+", "", addr).strip()
                # 都道府県+市区町村の範囲に絞る
                city_end = re.search(r"(?:市|区|町|村)", addr)
                if city_end:
                    addr = addr[:city_end.end()]
                if 5 <= len(addr) <= 40:
                    full_address = addr
                    # 都道府県が未確定なら住所から取得
                    if not prefecture:
                        for pref in ALL_PREFECTURES:
                            if pref in addr:
                                prefecture = pref
                                break
                break

    return zip_code, prefecture, full_address


def extract_employee_count(text: str) -> str:
    for pattern in EMPLOYEE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            count = int(match.group(1))
            if 1 <= count <= 10000:
                return str(count)
    return ""


def estimate_industry(text: str, company_name: str = "") -> str:
    combined = (text[:1000] + " " + company_name).lower()
    for keywords, industry in INDUSTRY_MAP:
        if any(kw.lower() in combined for kw in keywords):
            return industry
    return ""


def validate_company_info(info: dict) -> dict:
    """
    スクレイピング結果の各フィールドを検証し、明らかな誤りを自動クリアする。
    また信頼度スコア（_confidence: 0〜4）を付与する。

    - 電話番号: 数字10〜11桁でなければクリア
    - 従業員数: 数値かつ1〜999の範囲でなければクリア
    - 会社名: 法人格あり + 60文字以内なら信頼度+1
    - 都道府県: 47都道府県に一致すれば信頼度+1
    """
    confidence = 0

    # 電話番号: 数字のみで10〜11桁
    phone = info.get("phone", "")
    if phone:
        digits = re.sub(r"\D", "", phone)
        if 10 <= len(digits) <= 11:
            confidence += 1
        else:
            logger.debug(f"電話番号形式NG→クリア: {phone}")
            info["phone"] = ""

    # 会社名: 法人格あり + 60文字以内
    name = info.get("company_name", "")
    if name and re.search(r"株式会社|合同会社|有限会社|一般社団法人", name) and len(name) <= 60:
        confidence += 1

    # 従業員数: 数値かつ1〜999の範囲
    emp = info.get("employee_count", "")
    if emp:
        digits_emp = re.sub(r"\D", "", str(emp))
        if digits_emp and 1 <= int(digits_emp) <= 999:
            confidence += 1
        else:
            logger.debug(f"従業員数範囲外→クリア: {emp}")
            info["employee_count"] = ""

    # 都道府県: 47都道府県リストに一致
    prefecture = info.get("prefecture", "")
    if prefecture and prefecture in ALL_PREFECTURES:
        confidence += 1

    info["_confidence"] = confidence  # 0〜4点
    return info


def scrape_company_info(url: str, is_media_page: bool = False, media_domain: str = "", search_snippet: str = "") -> dict:
    """
    企業情報を取得する。

    is_media_page=True の場合:
      まず媒体記事から企業URLを取得し、その企業サイトをスクレイピングする。

    Returns:
        {
            company_name, company_url, representative,
            address, zip_code, prefecture, phone,
            employee_count, industry,
            source_url (媒体記事URL)
        }
    """
    info = {
        "company_name": "",
        "company_url": "",
        "representative": "",
        "address": "",
        "zip_code": "",
        "prefecture": "",
        "phone": "",
        "employee_count": "",
        "industry": "",
        "source_url": url,  # 検索でヒットした元URL
    }

    # 媒体ページの場合は企業URLを先に抽出
    if is_media_page:
        company_url, found_name = extract_company_url_from_media_page(url)
        if not company_url:
            logger.debug(f"媒体記事から企業URL取得失敗: {url}")
            return info
        target_url = company_url
        # 記事から企業名が取れていたら先にセット（サイトから取れなかった場合の保険）
        if found_name:
            info["company_name"] = found_name
    else:
        parsed = urlparse(url)
        target_url = f"{parsed.scheme}://{parsed.netloc}"

    # 官公庁・団体・大学ドメイン除外（株式会社ではありえないドメイン）
    target_domain = urlparse(target_url).netloc.replace("www.", "")
    BLOCKED_TLDS = [".go.jp", ".or.jp", ".ac.jp", ".ed.jp", ".lg.jp"]
    if any(target_domain.endswith(tld) for tld in BLOCKED_TLDS):
        logger.info(f"官公庁・団体ドメイン除外: {target_url}")
        return info  # company_url = "" のまま返す

    info["company_url"] = target_url

    # 企業サイトをスクレイピング（トップ + 会社概要ページ）
    pages_to_visit = [target_url] + [target_url + path for path in ABOUT_PAGE_PATHS[:5]]
    all_text = ""
    main_soup = None

    for page_url in pages_to_visit[:6]:
        text, soup = get_page_text(page_url)
        if not text:
            continue
        if not main_soup:
            main_soup = soup
            if soup:
                # トップページでファイルリンクを検出してinfoに記録（自動処理用）
                from agents.list_page_agent import find_file_links
                found_files = find_file_links(soup, page_url)
                if found_files:
                    info["found_file_links"] = found_files
                    logger.info(f"ページ内ファイルリンク検出: {len(found_files)}件 @ {page_url}")
                # 注目リンク収集（プレスリリース・認定・掲載記事等）
                info["notable_links"] = extract_notable_links(soup, page_url)
        all_text += " " + text
        if not info["company_name"] and soup:
            info["company_name"] = extract_company_name(soup, text)
        if info["representative"] and info["phone"] and info["address"]:
            break

    if not all_text.strip():
        # JSレンダリングサイト等でテキスト0文字の場合、検索スニペットで補完
        if search_snippet:
            logger.info(f"JSレンダリングサイト → 検索スニペットで補完: {target_url}")
            all_text = search_snippet
        else:
            logger.warning(f"コンテンツ取得失敗: {target_url}")
            return info

    # マスト項目チェック（全ページ取得後に判定）
    # is_media_page=True でも target_url は企業HP（媒体記事から抽出済み）なので必ず検証する
    is_company, missing = check_company_fields(all_text)
    if not is_company:
        logger.info(f"企業HP項目不足（未取得: {missing}）→スキップ: {target_url}")
        info["company_url"] = ""  # 株式会社と確認できないURLはクリア
        # 失敗ドメインを学習データに記録（3回失敗で自動除外）
        from config import record_domain_fail
        record_domain_fail(target_domain)
        return info
    if missing:
        logger.debug(f"企業HP確認OK（未取得: {missing}）: {target_url}")

    if not info["representative"]:
        info["representative"] = extract_representative(all_text)
    if not info["phone"]:
        info["phone"] = extract_phone(all_text, main_soup)

    zip_code, prefecture, full_address = extract_address_parts(all_text)
    info["zip_code"] = zip_code
    info["prefecture"] = prefecture
    info["address"] = full_address

    info["employee_count"] = extract_employee_count(all_text)
    info["industry"] = estimate_industry(all_text, info["company_name"])

    # フィールドバリデーション（明らかな誤りをクリア + 信頼度スコア付与）
    info = validate_company_info(info)

    logger.debug(
        f"スクレイプ完了: {info['company_name'] or target_url} "
        f"| 代表:{bool(info['representative'])} TEL:{bool(info['phone'])} "
        f"| 住所:{bool(info['address'])} 従業員:{info['employee_count']} "
        f"| 信頼度:{info.get('_confidence', 0)}/4"
    )
    return info
