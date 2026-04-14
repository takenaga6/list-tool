"""
HubSpot 業種・従業員数 追加書き込みスクリプト
CSVのドメインで企業を検索し、industry と numberofemployees を更新する
"""

import csv
import re
import os
import sys
import time
import logging
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger()


def clean_domain(raw):
    if not raw:
        return ""
    if re.search(r'[\u3000-\u9fff]', raw):
        return ""
    raw = raw.strip()
    raw = re.sub(r'^https?://', '', raw)
    raw = re.sub(r'^www\.', '', raw)
    raw = raw.split('/')[0]
    if '.' not in raw:
        return ""
    return raw


def search_by_domain(domain):
    resp = requests.post(
        f"{BASE_URL}/crm/v3/objects/companies/search",
        headers=HEADERS,
        json={
            "filterGroups": [{"filters": [{"propertyName": "domain", "operator": "EQ", "value": domain}]}],
            "properties": ["name", "domain"],
            "limit": 1,
        },
        timeout=15,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return results[0]["id"] if results else None


def update_company(company_id, properties):
    resp = requests.patch(
        f"{BASE_URL}/crm/v3/objects/companies/{company_id}",
        headers=HEADERS,
        json={"properties": properties},
        timeout=15,
    )
    resp.raise_for_status()


def clean_employee_count(raw):
    """従業員数を数値に変換"""
    if not raw:
        return ""
    # 数字だけ抽出
    nums = re.findall(r'\d+', raw.replace(',', ''))
    if nums:
        return nums[0]
    return ""


def main():
    csv_path = os.path.expanduser("~/projects/list_tool/approach_list.csv")
    if not os.path.exists(csv_path):
        print(f"エラー: CSVファイルが見つかりません: {csv_path}")
        sys.exit(1)

    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader)
        for row in reader:
            if len(row) > 3 and row[3].strip():
                rows.append(row)

    print(f"=" * 60)
    print(f"HubSpot 業種・従業員数 追加書き込み")
    print(f"対象: {len(rows)} 社")
    print(f"=" * 60)

    updated = 0
    skipped = 0
    errors = 0
    no_domain = 0
    not_found = 0

    for i, row in enumerate(rows):
        domain_raw = row[4].strip() if len(row) > 4 else ""
        domain = clean_domain(domain_raw)
        gyoushu = row[17].strip() if len(row) > 17 else ""
        juugyouin_raw = row[18].strip() if len(row) > 18 else ""
        juugyouin = clean_employee_count(juugyouin_raw)
        company_name = row[3].strip() if len(row) > 3 else ""

        # 業種も従業員数もなければスキップ
        if not gyoushu and not juugyouin:
            skipped += 1
            continue

        # ドメインなしはスキップ
        if not domain:
            no_domain += 1
            continue

        props = {}
        if gyoushu:
            props["gyoushukasutamu"] = gyoushu
        if juugyouin:
            props["numberofemployees"] = juugyouin

        try:
            company_id = search_by_domain(domain)
            if company_id:
                update_company(company_id, props)
                updated += 1
            else:
                not_found += 1
        except requests.HTTPError as e:
            status = e.response.status_code if e.response else 0
            if status == 429:
                logger.warning("レート制限 → 10秒待機")
                time.sleep(10)
                try:
                    company_id = search_by_domain(domain)
                    if company_id:
                        update_company(company_id, props)
                        updated += 1
                except:
                    errors += 1
            else:
                errors += 1
        except Exception as e:
            errors += 1

        if (i + 1) % 100 == 0:
            print(f"  進捗: {i+1}/{len(rows)} (更新:{updated} スキップ:{skipped} エラー:{errors})")

        if (i + 1) % 10 == 0:
            time.sleep(0.5)

    print(f"\n{'=' * 60}")
    print(f"完了")
    print(f"  更新:       {updated} 件")
    print(f"  スキップ:   {skipped} 件（業種・従業員数なし）")
    print(f"  ドメインなし: {no_domain} 件")
    print(f"  未発見:     {not_found} 件")
    print(f"  エラー:     {errors} 件")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
