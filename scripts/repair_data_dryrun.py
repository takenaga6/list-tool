# -*- coding: utf-8 -*-
"""
HubSpot登録済み企業の修復ドライランスクリプト（Phase 7-A Step 3）

- HubSpot API から list-tool 登録企業を全件取得（READ ONLY）
- Phase 7-A Step 1-2 の修正ロジックで都道府県・会社名を再判定
- 修正案を CSV / MD で出力（HubSpot への書き込みは一切行わない）

実行: python scripts/repair_data_dryrun.py
"""
import csv
import logging
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv
load_dotenv()

import requests

from utils.prefecture_resolver import extract_prefecture_with_voting
from agents.scraper_agent import _clean_company_name

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ── 定数 ──────────────────────────────────────────────────────────────────────
HUBSPOT_BASE = "https://api.hubapi.com"
OUT_CSV = os.path.join(ROOT, "output", "repair_dryrun_report.csv")
OUT_MD  = os.path.join(ROOT, "output", "repair_dryrun_summary.md")

# list-tool 開始日（2026-03-27 00:00:00 UTC）のUnixミリ秒
_LIST_TOOL_START_MS = str(int(datetime(2026, 3, 27, tzinfo=timezone.utc).timestamp() * 1000))

# ── HubSpot取得 ───────────────────────────────────────────────────────────────

def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def fetch_list_tool_companies(token: str) -> list[dict]:
    """
    HubSpotから list-tool 登録企業を全件取得する（READ ONLY）。

    フィルター: country=Japan + a_12 HAS_PROPERTY + createdate >= 2026-03-27
    ページネーション: 100件/ページ、after カーソルで順次取得。
    """
    url = f"{HUBSPOT_BASE}/crm/v3/objects/companies/search"
    properties = [
        "name", "state", "city", "phone", "zip", "address", "website", "a_12", "createdate",
    ]
    payload: dict = {
        "filterGroups": [{"filters": [
            {"propertyName": "country",    "operator": "EQ",           "value": "Japan"},
            {"propertyName": "a_12",       "operator": "HAS_PROPERTY"},
            {"propertyName": "createdate", "operator": "GTE",          "value": _LIST_TOOL_START_MS},
        ]}],
        "properties": properties,
        "limit": 100,
        "sorts": [{"propertyName": "createdate", "direction": "ASCENDING"}],
    }

    results: list[dict] = []
    after: str | None = None

    while True:
        if after:
            payload["after"] = after
        try:
            resp = requests.post(url, json=payload, headers=_headers(token), timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"HubSpot API エラー: {e}")
            break

        batch = data.get("results", [])
        results.extend(batch)
        logger.info(f"  取得済み: {len(results)} 件")

        after = (data.get("paging") or {}).get("next", {}).get("after")
        if not after:
            break

    return results


# ── 再判定ロジック ────────────────────────────────────────────────────────────

def _is_malformed_phone(phone: str) -> bool:
    """電話番号フォーマット異常チェック（数字のみで9桁未満 かつ 空文字でない）"""
    if not phone:
        return False
    digits = re.sub(r"[^\d]", "", phone)
    return len(digits) < 9


def repair_record(record: dict) -> dict:
    """
    1件の HubSpot Company レコードを再判定し、修正案を返す。

    変更フラグ判定ルール:
      - 再判定後の都道府県が空文字 → 変更フラグ False、既存値を維持
      - _clean_company_name() が空文字 → 変更フラグ False、既存値を維持
    """
    hubspot_id = record.get("id", "")
    props = record.get("properties") or {}

    name_old    = (props.get("name")    or "").strip()
    pref_old    = (props.get("state")   or "").strip()
    address_old = (props.get("address") or "").strip()
    zip_code    = (props.get("zip")     or "").strip()
    phone       = (props.get("phone")   or "").strip()
    website     = (props.get("website") or "").strip()

    reasons: list[str] = []

    # ── 会社名 再判定 ──────────────────────────────────────────────────────
    name_cleaned = _clean_company_name(name_old) if name_old else ""
    # _clean_company_name が空文字を返した場合は安全のため既存値を保持
    name_new = name_cleaned if name_cleaned else name_old

    # ── 電話番号フォーマット確認 ────────────────────────────────────────────
    if _is_malformed_phone(phone):
        reasons.append("電話番号フォーマット異常")
        phone_for_voting = ""   # フォーマット異常は投票に使わない
    else:
        phone_for_voting = phone

    # ── 都道府県 再判定 ────────────────────────────────────────────────────
    pref_new = extract_prefecture_with_voting(zip_code, phone_for_voting, "", url=website)

    # 再判定が空文字 → 既存値を維持（Q2仕様: 空文字で上書きしない）
    if not pref_new:
        pref_new = pref_old
        if not _is_malformed_phone(phone):
            reasons.append("郵便・電話不足のため判定不能")

    # ── 所在地 クリア判定（Step 1 と同ロジック）─────────────────────────────
    if pref_new and pref_new != pref_old and address_old:
        if not address_old.startswith(pref_new):
            address_new = ""
            reasons.append(f"都道府県変更({pref_old}→{pref_new})に伴い所在地クリア")
        else:
            address_new = address_old
    else:
        address_new = address_old

    # ── 変更フラグ ────────────────────────────────────────────────────────
    name_changed = (name_new != name_old)
    pref_changed = (pref_new != pref_old)
    addr_changed = (address_new != address_old)
    changed = name_changed or pref_changed or addr_changed

    if name_changed:
        reasons.append("会社名体裁修正")
    if pref_changed:
        reasons.append(f"都道府県修正({pref_old}→{pref_new})")

    return {
        "hubspot_id":  hubspot_id,
        "会社名_元":   name_old,
        "会社名_新":   name_new,
        "都道府県_元": pref_old,
        "都道府県_新": pref_new,
        "所在地_元":   address_old,
        "所在地_新":   address_new,
        "変更フラグ":  changed,
        "修正理由":    " / ".join(reasons) if reasons else "変更なし",
        "_website":    website,
    }


# ── 出力 ──────────────────────────────────────────────────────────────────────

_CSV_FIELDS = [
    "hubspot_id", "会社名_元", "会社名_新",
    "都道府県_元", "都道府県_新",
    "所在地_元", "所在地_新",
    "変更フラグ", "修正理由",
]


def write_csv(rows: list[dict]) -> None:
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    logger.info(f"CSV出力: {OUT_CSV}")


def write_summary(rows: list[dict]) -> None:
    total   = len(rows)
    changed = [r for r in rows if r["変更フラグ"]]
    unch    = [r for r in rows if not r["変更フラグ"]]

    pref_only = [r for r in changed
                 if r["都道府県_元"] != r["都道府県_新"] and r["会社名_元"] == r["会社名_新"]]
    name_only = [r for r in changed
                 if r["都道府県_元"] == r["都道府県_新"] and r["会社名_元"] != r["会社名_新"]]
    both      = [r for r in changed
                 if r["都道府県_元"] != r["都道府県_新"] and r["会社名_元"] != r["会社名_新"]]

    pref_changes = Counter(
        f"{r['都道府県_元']} → {r['都道府県_新']}"
        for r in changed if r["都道府県_元"] != r["都道府県_新"]
    )
    name_patterns = Counter()
    for r in changed:
        if r["会社名_元"] != r["会社名_新"]:
            removed = r["会社名_元"].replace(r["会社名_新"], "").strip()
            if removed:
                name_patterns[removed[:30]] += 1

    cnt_malformed  = sum(1 for r in rows if "電話番号フォーマット異常" in r["修正理由"])
    cnt_no_data    = sum(1 for r in rows if "判定不能" in r["修正理由"])

    lines = [
        "# 修復ドライラン結果",
        "",
        f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 全体サマリー",
        f"- 対象レコード数: {total}件",
        f"- 変更あり: {len(changed)}件 ({len(changed)/max(total,1)*100:.0f}%)",
        f"- 変更なし: {len(unch)}件",
        "- 内訳:",
        f"  - 都道府県のみ変更: {len(pref_only)}件",
        f"  - 会社名のみ変更: {len(name_only)}件",
        f"  - 両方変更: {len(both)}件",
        "",
        "## 重大事故レコード Top 10",
        "（都道府県変更ありを優先した上位10件）",
        "",
        "| # | hubspot_id | 会社名(元) | 都道府県 変更 | 所在地 | 修正理由 |",
        "|---|-----------|-----------|-------------|--------|---------|",
    ]

    top10 = sorted(
        changed,
        key=lambda r: (
            r["都道府県_元"] != r["都道府県_新"],
            r["所在地_元"] != r["所在地_新"],
        ),
        reverse=True,
    )[:10]
    for i, r in enumerate(top10, 1):
        pref_ch = (f"{r['都道府県_元']}→{r['都道府県_新']}"
                   if r["都道府県_元"] != r["都道府県_新"] else "-")
        addr_ch = ("クリア" if r["所在地_新"] == "" and r["所在地_元"] != ""
                   else ("-" if r["所在地_元"] == r["所在地_新"] else "変更あり"))
        lines.append(
            f"| {i} | {r['hubspot_id']} | {r['会社名_元'][:25]} "
            f"| {pref_ch} | {addr_ch} | {r['修正理由'][:40]} |"
        )

    lines += [
        "",
        "## 変更内容の傾向",
        "",
        "### 都道府県の変更パターン（Before → After）",
    ]
    if pref_changes:
        for pat, cnt in pref_changes.most_common():
            lines.append(f"- {pat}: {cnt}件")
    else:
        lines.append("- 都道府県変更なし")

    lines += [
        "",
        "### 会社名の変更パターン（除去された語）",
    ]
    if name_patterns:
        for pat, cnt in name_patterns.most_common():
            lines.append(f"- `{pat}`: {cnt}件")
    else:
        lines.append("- 会社名変更なし")

    lines += [
        "",
        "## 注意事項",
        f"- 電話番号フォーマット異常: {cnt_malformed}件（Phase 7-B で対応予定）",
        f"- 郵便・電話不足で判定不能: {cnt_no_data}件（都道府県は既存値を維持）",
        "",
        "## 次のステップ",
        "- Step 4: このレポートの hubspot_id を使って HubSpot に PATCH を適用",
        f"- 修正対象: {len(changed)} 件",
        "- コマンド: `python scripts/repair_data_apply.py`（Step 4 で作成予定）",
    ]

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    logger.info(f"サマリー出力: {OUT_MD}")


# ── メイン ────────────────────────────────────────────────────────────────────

def main() -> None:
    # 1. 環境確認
    token = os.environ.get("HUBSPOT_TOKEN", "")
    if not token:
        logger.error("HUBSPOT_TOKEN が未設定です。.env を確認するか、"
                     "Render の環境変数からローカルに持ってきてください。")
        sys.exit(1)
    logger.info(f"HUBSPOT_TOKEN: 確認OK（長さ {len(token)} 文字）")

    # 2. HubSpot から全件取得
    logger.info("HubSpot から list-tool 登録企業を取得中...")
    companies = fetch_list_tool_companies(token)
    logger.info(f"取得完了: {len(companies)} 件")

    if not companies:
        logger.warning("取得件数が 0 件です。フィルター条件を確認してください。")
        sys.exit(0)

    # 3. 再判定
    rows = [repair_record(c) for c in companies]

    # 4. 出力
    write_csv(rows)
    write_summary(rows)

    changed_count = sum(1 for r in rows if r["変更フラグ"])
    print(f"\n== ドライラン完了 ==")
    print(f"対象: {len(rows)} 件")
    print(f"変更あり: {changed_count} 件 ({changed_count / max(len(rows), 1) * 100:.0f}%)")
    print(f"CSV: {OUT_CSV}")
    print(f"サマリー: {OUT_MD}")


if __name__ == "__main__":
    main()
