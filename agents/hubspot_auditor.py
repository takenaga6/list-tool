"""
HubSpot登録済み企業の事後バリデーション

優先度順にチェック（重いほど後回し）:
  1. ドメインキーワード（即時）
  2. 会社名 vs ドメイン一致（即時）
  3. 軽量スクレイプ + check_company_fields（最後だけ）

NG企業:
  - HubSpotの説明フィールドに「【要確認】」を追記
  - ドメインを exclude_list.csv に追加（学習）
"""

import logging
import re
import time
import requests
from urllib.parse import urlparse

from config import add_to_exclude_csv, HUBSPOT_TOKEN
from agents.search_agent import NG_DOMAIN_KEYWORDS, EXCLUDE_DOMAINS

logger = logging.getLogger(__name__)

BASE_URL = "https://api.hubapi.com"
HEADERS = {
    "Authorization": f"Bearer {HUBSPOT_TOKEN}",
    "Content-Type": "application/json",
}

# ─────────────────────────────────────────────
# HubSpot API
# ─────────────────────────────────────────────

def _get_all_companies(limit: int = 100) -> list[dict]:
    """HubSpotから全企業を取得（website / name / description）"""
    companies = []
    after = None
    while True:
        params = {
            "limit": limit,
            "properties": "name,website,description",
        }
        if after:
            params["after"] = after
        resp = requests.get(
            f"{BASE_URL}/crm/v3/objects/companies",
            headers=HEADERS, params=params, timeout=15
        )
        if resp.status_code != 200:
            logger.error(f"HubSpot取得失敗: {resp.status_code}")
            break
        data = resp.json()
        companies.extend(data.get("results", []))
        paging = data.get("paging", {}).get("next", {})
        after = paging.get("after")
        if not after:
            break
        time.sleep(0.3)
    return companies


def _flag_company(company_id: str, reason: str):
    """HubSpotの説明フィールドに【要確認】タグを追記"""
    url = f"{BASE_URL}/crm/v3/objects/companies/{company_id}"
    # 現在の説明を取得
    resp = requests.get(url, headers=HEADERS, params={"properties": "description"}, timeout=10)
    current_desc = ""
    if resp.status_code == 200:
        current_desc = resp.json().get("properties", {}).get("description", "") or ""

    if "【要確認】" in current_desc:
        return  # 既にフラグ済み

    new_desc = f"【要確認】{reason}\n{current_desc}".strip()
    requests.patch(url, json={"properties": {"description": new_desc}}, headers=HEADERS, timeout=10)


# ─────────────────────────────────────────────
# チェックロジック
# ─────────────────────────────────────────────

def _check_domain_keywords(domain: str) -> str:
    """ドメインキーワードで即時NG判定。NG理由を返す（OKなら空文字）"""
    for kw in NG_DOMAIN_KEYWORDS:
        if kw in domain:
            return f"NGキーワード({kw})がドメインに含まれる: {domain}"
    for ex in EXCLUDE_DOMAINS:
        if ex in domain:
            return f"除外ドメイン一致: {domain}"
    return ""


def _check_name_vs_domain(company_name: str, domain: str) -> str:
    """会社名コアとドメインの一致チェック。NG理由を返す（OKなら空文字）"""
    # 法人格を除去してコア名を取得
    core = re.sub(
        r'(株式会社|合同会社|有限会社|一般社団法人|NPO法人)', '', company_name
    ).strip().lower()

    if not core or len(core) < 2:
        return ""  # 判定不能

    # ローマ字・カタカナトークンを抽出
    tokens = re.findall(r'[a-zA-Z]{2,}|[ァ-ヶー]{2,}|[一-龯]{2,}', core)
    if not tokens:
        return ""

    domain_lower = domain.lower()
    matched = sum(1 for t in tokens if t.lower() in domain_lower)

    # 全トークンが一致しない、かつドメインに会社名の痕跡がゼロの場合のみNG
    # （緩めに判定 → 疑わしいもののみフラグ）
    if matched == 0 and len(tokens) >= 2:
        return f"会社名({company_name})とドメイン({domain})が不一致"
    return ""


def _quick_scrape_check(url: str) -> str:
    """軽量スクレイプで企業HP必須項目チェック。NG理由を返す（OKなら空文字）"""
    try:
        from agents.scraper_agent import check_company_fields
        resp = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        if resp.status_code != 200:
            return f"HTTP {resp.status_code}"
        resp.encoding = resp.apparent_encoding or "utf-8"
        text = resp.text[:5000]  # 先頭5000文字で十分
        ok, missing = check_company_fields(text)
        if not ok:
            return f"企業HP項目不足: {missing}"
    except Exception as e:
        return f"取得エラー: {e}"
    return ""


# ─────────────────────────────────────────────
# メイン
# ─────────────────────────────────────────────

def audit_hubspot(scrape_borderline: bool = False) -> dict:
    """
    HubSpot登録済み企業を検証し、NGをフラグ立て・学習データに追加する。

    Args:
        scrape_borderline: Trueの場合、ドメインチェックを通過した企業もスクレイプ検証

    Returns:
        {"total": N, "ng": N, "flagged": [...]}
    """
    logger.info("HubSpot監査開始...")
    companies = _get_all_companies()
    logger.info(f"取得: {len(companies)}社")

    ng_list = []

    for c in companies:
        props = c.get("properties", {})
        name = props.get("name", "") or ""
        website = props.get("website", "") or ""
        company_id = c["id"]

        if not website:
            continue

        domain = urlparse(website if website.startswith("http") else f"https://{website}").netloc
        domain = domain.replace("www.", "")

        reason = ""

        # ① ドメインキーワード（即時・無コスト）
        reason = _check_domain_keywords(domain)

        # ② 会社名 vs ドメイン（即時・無コスト）
        if not reason:
            reason = _check_name_vs_domain(name, domain)

        # ③ 軽量スクレイプ（オプション or ②でグレーだった場合）
        if not reason and scrape_borderline:
            reason = _quick_scrape_check(website)
            time.sleep(0.5)

        if reason:
            logger.info(f"[NG] {name} ({domain}): {reason}")
            _flag_company(company_id, reason)
            add_to_exclude_csv(domain, f"監査NG: {reason}")
            ng_list.append({"name": name, "domain": domain, "reason": reason})

    result = {"total": len(companies), "ng": len(ng_list), "flagged": ng_list}
    logger.info(f"監査完了: {len(companies)}社中 {len(ng_list)}社をNG判定")
    return result
