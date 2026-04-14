"""
担当リスト自動整理スクリプト
- アプローチ日から1ヶ月経過 → 担当者を外す
- アプローチ日から2ヶ月経過 → 別の担当者にランダム再配布
- 「追わない」ステータスは対象外

毎日自動実行する想定（Windowsタスクスケジューラ）
"""

import os
import sys
import random
import logging
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/projects/list_tool/.env"))
TOKEN = os.getenv("HUBSPOT_TOKEN")
MEMBERS_RAW = os.getenv("MEMBERS", "")
MEMBERS = [m.strip() for m in MEMBERS_RAW.split(",") if m.strip()]

if not TOKEN:
    print("エラー: HUBSPOT_TOKEN が .env に見つかりません")
    sys.exit(1)

if not MEMBERS:
    # kaden-toolの.envからも試行
    load_dotenv(os.path.expanduser("~/projects/kaden-tool/.env"), override=True)
    MEMBERS_RAW = os.getenv("MEMBERS", "")
    MEMBERS = [m.strip() for m in MEMBERS_RAW.split(",") if m.strip()]

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}
BASE_URL = "https://api.hubapi.com"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger()

TODAY = datetime.now()
ONE_MONTH_AGO = (TODAY - timedelta(days=30)).strftime("%Y-%m-%d")
TWO_MONTHS_AGO = (TODAY - timedelta(days=60)).strftime("%Y-%m-%d")


def hs_search(filter_groups, properties, limit=100, after=""):
    body = {
        "filterGroups": filter_groups,
        "properties": properties,
        "limit": limit,
    }
    if after:
        body["after"] = after
    resp = requests.post(
        f"{BASE_URL}/crm/v3/objects/companies/search",
        headers=HEADERS,
        json=body,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def hs_patch(company_id, properties):
    resp = requests.patch(
        f"{BASE_URL}/crm/v3/objects/companies/{company_id}",
        headers=HEADERS,
        json={"properties": properties},
        timeout=15,
    )
    resp.raise_for_status()


def get_all_companies(filter_groups, properties):
    """ページネーションで全件取得"""
    all_results = []
    after = ""
    while True:
        data = hs_search(filter_groups, properties, limit=100, after=after)
        all_results.extend(data.get("results", []))
        paging = data.get("paging", {})
        if paging.get("next"):
            after = paging["next"]["after"]
        else:
            break
    return all_results


def main():
    print(f"{'=' * 60}")
    print(f"担当リスト自動整理")
    print(f"実行日: {TODAY.strftime('%Y-%m-%d %H:%M')}")
    print(f"1ヶ月基準日: {ONE_MONTH_AGO}")
    print(f"2ヶ月基準日: {TWO_MONTHS_AGO}")
    print(f"{'=' * 60}")

    # ── 1. アプローチ日から2ヶ月経過 → 別の担当者に再配布 ──
    # （2ヶ月を先に処理。1ヶ月で外した企業が2ヶ月条件にも該当するため）
    print(f"\n--- 2ヶ月経過: 別の担当者に再配布 ---")
    
    # 担当者あり & アプローチ日が2ヶ月以上前 & 追わない以外
    two_month_companies = get_all_companies(
        filter_groups=[
            {
                "filters": [
                    {"propertyName": "kadentantoushamei", "operator": "HAS_PROPERTY"},
                    {"propertyName": "apurochibi", "operator": "LT", "value": TWO_MONTHS_AGO},
                    {"propertyName": "apurochinaiyou", "operator": "NEQ", "value": "追わない"},
                ]
            }
        ],
        properties=["name", "kadentantoushamei", "apurochibi", "apurochinaiyou"],
    )

    reassigned = 0
    for company in two_month_companies:
        props = company.get("properties", {})
        current_user = props.get("kadentantoushamei", "")
        
        # 現在の担当者以外からランダムに選ぶ
        candidates = [m for m in MEMBERS if m != current_user]
        if not candidates:
            candidates = MEMBERS
        new_user = random.choice(candidates)

        try:
            hs_patch(company["id"], {"kadentantoushamei": new_user})
            logger.info(f"再配布: {props.get('name', '')} | {current_user} → {new_user} | アプローチ日={props.get('apurochibi', '')}")
            reassigned += 1
        except Exception as e:
            logger.warning(f"再配布失敗: {props.get('name', '')} | {e}")

    print(f"再配布: {reassigned} 件")

    # ── 2. アプローチ日から1ヶ月経過 → 担当者を外す ──
    print(f"\n--- 1ヶ月経過: 担当者を外す ---")
    
    # 担当者あり & アプローチ日が1ヶ月以上前（2ヶ月未満） & 追わない以外
    one_month_companies = get_all_companies(
        filter_groups=[
            {
                "filters": [
                    {"propertyName": "kadentantoushamei", "operator": "HAS_PROPERTY"},
                    {"propertyName": "apurochibi", "operator": "LT", "value": ONE_MONTH_AGO},
                    {"propertyName": "apurochinaiyou", "operator": "NEQ", "value": "追わない"},
                ]
            }
        ],
        properties=["name", "kadentantoushamei", "apurochibi", "apurochinaiyou"],
    )

    # 2ヶ月以上経過した企業は既に再配布済みなので除外
    one_month_companies = [c for c in one_month_companies if (c.get("properties", {}).get("apurochibi", "") or "") >= TWO_MONTHS_AGO]

    removed = 0
    for company in one_month_companies:
        props = company.get("properties", {})
        try:
            hs_patch(company["id"], {"kadentantoushamei": ""})
            logger.info(f"担当外し: {props.get('name', '')} | 元担当={props.get('kadentantoushamei', '')} | アプローチ日={props.get('apurochibi', '')}")
            removed += 1
        except Exception as e:
            logger.warning(f"担当外し失敗: {props.get('name', '')} | {e}")

    print(f"担当外し: {removed} 件")

    # ── 結果サマリー ──
    print(f"\n{'=' * 60}")
    print(f"完了")
    print(f"  再配布（2ヶ月経過）: {reassigned} 件")
    print(f"  担当外し（1ヶ月経過）: {removed} 件")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
