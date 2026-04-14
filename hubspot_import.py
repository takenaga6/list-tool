"""
HubSpot 一括インポートスクリプト
スプレッドシートのアプローチリスト → HubSpot企業レコード
"""

import csv
import re
import os
import sys
import time
import logging
from dotenv import load_dotenv
import requests

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

# ─── マッピング定義 ───

# 苗字 → フルネーム
NAME_MAP = {
    "近野": "近野凌太",
    "松本": "松本力哉",
    "中井": "中井伸次朗",
    "nakai": "中井伸次朗",
    "橋爪": "橋爪伶侍",
    "野村": "野村行",
    "渡辺": "渡辺大輔",
    "渡邊": "渡辺大輔",
    "中尾": "中尾英聖",
    "山口": "山口滉太郎",
    "小谷": "小谷空輝",
    "安保": "安保菜々音",
    "峰尾": "峰尾慶章",
    "ミネオ": "峰尾慶章",
    "坂上": "坂上寛歩",
    "黛": "黛直汰朗",
    "天田": "天田莉子",
    "堤": "堤亮太",
    "小山": "小山優希",
    "神元": "神元葉月",
    "中西": "中西海斗",
    "宮": "宮侑次郎",
    "金子": "金子生佑",
    "塩澤": "塩澤耕太",
    "大澤": "大澤美咲",
    "前岡": "前岡",
    "櫻井": "櫻井",
    "河野": "河野",
    "仲山": "仲山",
}

# アプローチ内容の変換
APPROACH_MAP = {
    "受付NG": "受付NG",
    "担当NG": "担当NG",
    "社長NG": "社長NG",
    "取材NG": "取材NG",
    "追客": "追客",
    "社長アポ": "社長アポ",
    "担当アポ": "担当アポ",
    "資料送付": "資料送付",
    "不通リスト": "不通リスト",
    "追わない": "追わない",
    # CSV独自の値を変換
    "アポ獲得": "社長アポ",
    "ガチャぎり": "受付NG",
    "ナーチャリング": "追客",
    "日程調整中": "社長アポ",
    "触るな危険！": "追わない",
    "追客, ナーチャリング": "追客",
    "追客, 不通リスト": "追客",
}


def search_by_domain(domain):
    """ドメインでHubSpot企業を検索"""
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
    """既存企業を更新"""
    resp = requests.patch(
        f"{BASE_URL}/crm/v3/objects/companies/{company_id}",
        headers=HEADERS,
        json={"properties": properties},
        timeout=15,
    )
    resp.raise_for_status()


def create_company(properties):
    """新規企業を作成"""
    resp = requests.post(
        f"{BASE_URL}/crm/v3/objects/companies",
        headers=HEADERS,
        json={"properties": properties},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def resolve_tantou(raw):
    """担当者名を解決（カンマ区切りの場合は最初の人）"""
    if not raw or raw in ["リスト", "推薦リスト", "見込み"]:
        return ""
    first = raw.split(",")[0].strip()
    return NAME_MAP.get(first, first)



def clean_domain(raw):
    """ドメインをクリーニング（URL→ドメイン、日本語→空）"""
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

def resolve_approach(raw):
    """アプローチ内容を変換"""
    if not raw:
        return ""
    return APPROACH_MAP.get(raw.strip(), "")


def main():
    csv_path = os.path.expanduser("~/projects/list_tool/approach_list.csv")
    
    # アップロードされたCSVをコピーして使う場合のパスも対応
    if not os.path.exists(csv_path):
        # カレントディレクトリも確認
        alt = "approach_list.csv"
        if os.path.exists(alt):
            csv_path = alt
        else:
            print(f"エラー: CSVファイルが見つかりません: {csv_path}")
            print("CSVファイルを ~/projects/list_tool/approach_list.csv に置いてください")
            sys.exit(1)

    # CSV読み込み
    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader)
        for row in reader:
            if len(row) > 3 and row[3].strip():  # 会社名があるもののみ
                rows.append(row)

    print(f"=" * 60)
    print(f"HubSpot 一括インポート")
    print(f"対象: {len(rows)} 社")
    print(f"=" * 60)

    created = 0
    updated = 0
    skipped = 0
    errors = 0
    
    for i, row in enumerate(rows):
        company_name = row[3].strip() if len(row) > 3 else ""
        domain_raw = row[4].strip() if len(row) > 4 else ""
        domain = clean_domain(domain_raw)
        phone = row[8].strip() if len(row) > 8 else ""
        daihyou = row[9].strip() if len(row) > 9 else ""
        tantou_raw = row[1].strip() if len(row) > 1 else ""
        approach_raw = row[12].strip() if len(row) > 12 else ""
        rank = row[13].strip() if len(row) > 13 else ""
        bikou = row[14].strip() if len(row) > 14 else ""
        jikai = row[15].strip() if len(row) > 15 else ""
        chiiki = row[16].strip() if len(row) > 16 else ""
        gyoushu = row[17].strip() if len(row) > 17 else ""
        juugyouin = row[18].strip() if len(row) > 18 else ""

        # 変換
        tantou = resolve_tantou(tantou_raw)
        approach = resolve_approach(approach_raw)

        # HubSpotプロパティ組み立て
        props = {"name": company_name}
        if domain:
            props["domain"] = domain
        # 電話番号はHubSpotのフォーマット制約があるためスキップ
        # if phone:
        #     props["phone"] = phone
        if daihyou:
            props["daihyoumei"] = daihyou
        if tantou:
            props["kadentantoushamei"] = tantou
        if approach:
            props["apurochinaiyou"] = approach
        if rank in ["A", "B", "C"]:
            props["a_12"] = rank
        if bikou:
            props["apurochibikou"] = bikou
        if jikai:
            # 日付形式の正規化（2025/11/6 → 2025-11-06）
            try:
                parts = jikai.replace("以降", "").replace("中旬", "").strip().split("/")
                if len(parts) == 3:
                    jikai_fmt = f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
                    props["jikaiapurochibi"] = jikai_fmt
            except:
                pass

        try:
            if domain:
                existing_id = search_by_domain(domain)
                if existing_id:
                    update_company(existing_id, props)
                    updated += 1
                else:
                    create_company(props)
                    created += 1
            else:
                # ドメインなし → 新規作成のみ
                create_company(props)
                created += 1

        except requests.HTTPError as e:
            status = e.response.status_code if e.response else 0
            if status == 429:
                # レート制限 → 10秒待って再試行
                logger.warning(f"レート制限 → 10秒待機")
                time.sleep(10)
                try:
                    if domain:
                        existing_id = search_by_domain(domain)
                        if existing_id:
                            update_company(existing_id, props)
                            updated += 1
                        else:
                            create_company(props)
                            created += 1
                    else:
                        create_company(props)
                        created += 1
                except Exception as e2:
                    logger.error(f"再試行失敗 [{i+1}] {company_name}: {e2}")
                    errors += 1
            else:
                body = e.response.text[:200] if e.response else str(e)
                logger.error(f"エラー [{i+1}] {company_name}: {body[:200]}")
                errors += 1
        except Exception as e:
            logger.error(f"エラー [{i+1}] {company_name}: {e}")
            errors += 1

        # 進捗表示（100件ごと）
        if (i + 1) % 100 == 0:
            print(f"  進捗: {i+1}/{len(rows)} (作成:{created} 更新:{updated} エラー:{errors})")

        # レート制限対策: 10件ごとに0.5秒待機
        if (i + 1) % 10 == 0:
            time.sleep(0.5)

    print(f"\n{'=' * 60}")
    print(f"完了")
    print(f"  新規作成: {created} 件")
    print(f"  更新:     {updated} 件")
    print(f"  エラー:   {errors} 件")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
