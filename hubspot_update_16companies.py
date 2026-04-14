"""
HubSpot 16社 登録・更新スクリプト
"""

import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/projects/list_tool/.env"))
TOKEN = os.getenv("HUBSPOT_TOKEN")

if not TOKEN:
    print("エラー: HUBSPOT_TOKEN が .env に見つかりません")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}
BASE_URL = "https://api.hubapi.com"

EXISTING_COMPANIES = [
    {"name": "株式会社八千代ポートリー", "domain": "yachiyo-egg.com"},
    {"name": "ミカワリコピー販売株式会社", "domain": "mrnet.co.jp"},
    {"name": "株式会社石井工機", "domain": "ishii-kouki.co.jp"},
    {"name": "株式会社加藤組", "domain": "katou-gumi.co.jp"},
    {"name": "株式会社足利技研", "domain": "ashigi.co.jp"},
    {"name": "乃村工藝社", "domain": "nomurakougei.co.jp"},
]

NEW_COMPANIES = [
    {"name": "太成二葉産業株式会社", "domain": "tims-net.co.jp"},
    {"name": "SBIエステートファイナンス", "domain": "sbi-efinance.co.jp"},
    {"name": "株式会社ホンシュ", "domain": "honshu-ltd.co.jp"},
    {"name": "SBIリクイティディ・マーケット", "domain": "sbilm.co.jp"},
    {"name": "株式会社北海道クラウン", "domain": "hokkaido-crown.jp"},
    {"name": "武内製薬", "domain": "takeuchi-corp.jp"},
    {"name": "Wix.com Japan株式会社", "domain": "wix.com"},
    {"name": "ビット", "domain": "bit-corp.co.jp"},
    {"name": "株式会社CB JAPAN", "domain": "cb-j.com"},
    {"name": "SBIアルヒ", "domain": "sbiaruhi-group.jp"},
]

def search_company_by_domain(domain):
    url = f"{BASE_URL}/crm/v3/objects/companies/search"
    payload = {
        "filterGroups": [{"filters": [{"propertyName": "domain", "operator": "EQ", "value": domain}]}],
        "properties": ["name", "domain"],
        "limit": 1,
    }
    resp = requests.post(url, headers=HEADERS, json=payload)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return results[0]["id"] if results else None

def update_company(company_id, properties):
    url = f"{BASE_URL}/crm/v3/objects/companies/{company_id}"
    resp = requests.patch(url, headers=HEADERS, json={"properties": properties})
    resp.raise_for_status()

def create_company(properties):
    url = f"{BASE_URL}/crm/v3/objects/companies"
    resp = requests.post(url, headers=HEADERS, json={"properties": properties})
    resp.raise_for_status()
    return resp.json()["id"]

def main():
    print("=" * 60)
    print("HubSpot 16社 登録・更新スクリプト")
    print("=" * 60)
    success = 0
    errors = 0

    print("\n登録済み6社の更新")
    for c in EXISTING_COMPANIES:
        try:
            cid = search_company_by_domain(c["domain"])
            if cid:
                update_company(cid, {"apurochinaiyou": "社長アポ"})
                print(f"  更新完了: {c['name']} (ID: {cid})")
            else:
                nid = create_company({"name": c["name"], "domain": c["domain"], "apurochinaiyou": "社長アポ"})
                print(f"  未登録のため新規作成: {c['name']} (ID: {nid})")
            success += 1
        except Exception as e:
            print(f"  エラー: {c['name']} -> {e}")
            errors += 1

    print("\n新規10社の登録")
    for c in NEW_COMPANIES:
        try:
            cid = search_company_by_domain(c["domain"])
            if cid:
                update_company(cid, {"apurochinaiyou": "社長アポ"})
                print(f"  既に登録済み -> 更新: {c['name']} (ID: {cid})")
            else:
                nid = create_company({"name": c["name"], "domain": c["domain"], "apurochinaiyou": "社長アポ"})
                print(f"  新規作成: {c['name']} (ID: {nid})")
            success += 1
        except Exception as e:
            print(f"  エラー: {c['name']} -> {e}")
            errors += 1

    print(f"\n完了: 成功 {success} 件 / エラー {errors} 件")

if __name__ == "__main__":
    main()
