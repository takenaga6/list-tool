#!/usr/bin/env python3
"""HubSpot に回収トラック用の構造化シグナルプロパティ wb_* を作成する。

list-rank-validation（リストランク／シグナル検証）の回収トラックで、
rank_agent が判定した S1〜S10 / スコア / ランク版 / 流入経路を
HubSpot の構造化プロパティへ永続化するために必要なプロパティ定義を作る。

冪等: 既に存在するプロパティはスキップする（再実行しても二重作成しない）。
作成のみ・既存定義の変更や削除は行わない。

使い方:
    export HUBSPOT_TOKEN=<private-app-token>   # CRM プロパティ設定の権限が必要
    python scripts/create_wb_properties.py
    python scripts/create_wb_properties.py --dry-run   # 何が作られるか確認だけ

内部名は agents/hubspot_agent.build_wb_signal_props() / config と完全一致させること。
1文字でもズレると ENABLE_WB_SIGNALS=1 時に register_company が 400 で落ちる。
"""

import os
import sys
import json
import argparse

import requests

BASE_URL = "https://api.hubapi.com"
OBJECT_TYPE = "companies"
GROUP_NAME = "wellbody_signals"
GROUP_LABEL = "Well Body シグナル"

_BOOL_OPTIONS = [
    {"label": "はい", "value": "true", "displayOrder": 0, "hidden": False},
    {"label": "いいえ", "value": "false", "displayOrder": 1, "hidden": False},
]

_LEAD_SOURCE_OPTIONS = [
    {"label": "リスト（アウトバウンド）", "value": "list", "displayOrder": 0, "hidden": False},
    {"label": "紹介", "value": "紹介", "displayOrder": 1, "hidden": False},
    {"label": "インバウンド", "value": "inbound", "displayOrder": 2, "hidden": False},
    {"label": "手動", "value": "手動", "displayOrder": 3, "hidden": False},
]

# S1〜S10 のラベル（内部名は wb_sig_s1 〜 wb_sig_s10）
_SIGNAL_LABELS = {
    1: "S1 PR有料媒体掲載",
    2: "S2 健康経営メディア掲載",
    3: "S3 法定外福利厚生記載",
    4: "S4 健康経営注力",
    5: "S5 半年以内HPリニューアル",
    6: "S6 自社ビル保有",
    7: "S7 ISO認定",
    8: "S8 SDGs/サステナ",
    9: "S9 社長メッセージ健康記載",
    10: "S10 儲かる業界",
}


def _bool_prop(name: str, label: str) -> dict:
    return {
        "name": name,
        "label": label,
        "type": "bool",
        "fieldType": "booleancheckbox",
        "groupName": GROUP_NAME,
        "options": _BOOL_OPTIONS,
    }


def build_property_specs() -> list[dict]:
    specs: list[dict] = []
    for i in range(1, 11):
        specs.append(_bool_prop(f"wb_sig_s{i}", f"WBシグナル {_SIGNAL_LABELS[i]}"))
    specs.append({
        "name": "wb_sig_score", "label": "WBシグナル合計点",
        "type": "number", "fieldType": "number", "groupName": GROUP_NAME,
    })
    specs.append({
        "name": "wb_rank_version", "label": "WBランクロジック版",
        "type": "string", "fieldType": "text", "groupName": GROUP_NAME,
    })
    specs.append({
        "name": "wb_ranked_at", "label": "WBランク付与日",
        "type": "date", "fieldType": "date", "groupName": GROUP_NAME,
    })
    specs.append({
        "name": "wb_lead_source_type", "label": "WB流入経路",
        "type": "enumeration", "fieldType": "select", "groupName": GROUP_NAME,
        "options": _LEAD_SOURCE_OPTIONS,
    })
    return specs


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def ensure_group(token: str, dry_run: bool) -> None:
    """プロパティグループを作成（既存なら 409 を無視）。失敗しても致命的ではない。"""
    if dry_run:
        print(f"[dry-run] グループ確認/作成: {GROUP_NAME}")
        return
    url = f"{BASE_URL}/crm/v3/properties/{OBJECT_TYPE}/groups"
    resp = requests.post(
        url, headers=_headers(token),
        json={"name": GROUP_NAME, "label": GROUP_LABEL}, timeout=15,
    )
    if resp.ok:
        print(f"✅ グループ作成: {GROUP_NAME}")
    elif resp.status_code == 409 or "EXISTS" in resp.text.upper():
        print(f"➖ グループ既存: {GROUP_NAME}")
    else:
        print(f"⚠️ グループ作成失敗（続行）: {resp.status_code} {resp.text[:160]}")


def property_exists(token: str, name: str) -> bool:
    url = f"{BASE_URL}/crm/v3/properties/{OBJECT_TYPE}/{name}"
    resp = requests.get(url, headers=_headers(token), timeout=15)
    return resp.status_code == 200


def create_property(token: str, spec: dict, dry_run: bool) -> str:
    """1プロパティを作成。戻り値: 'created' / 'skipped' / 'error'。"""
    name = spec["name"]
    if property_exists(token, name):
        print(f"➖ 既存スキップ: {name}")
        return "skipped"
    if dry_run:
        print(f"[dry-run] 作成: {name} ({spec['type']}/{spec['fieldType']}) - {spec['label']}")
        return "created"
    url = f"{BASE_URL}/crm/v3/properties/{OBJECT_TYPE}"
    resp = requests.post(url, headers=_headers(token), json=spec, timeout=15)
    if resp.ok:
        print(f"✅ 作成: {name} - {spec['label']}")
        return "created"
    # 競合（並行実行・既存）は成功扱い
    if resp.status_code == 409 or "EXISTS" in resp.text.upper():
        print(f"➖ 既存スキップ(409): {name}")
        return "skipped"
    print(f"❌ 作成失敗: {name} - {resp.status_code} {resp.text[:200]}")
    return "error"


def main() -> int:
    parser = argparse.ArgumentParser(description="HubSpot wb_* プロパティ作成（冪等）")
    parser.add_argument("--dry-run", action="store_true", help="作成せず内容のみ表示")
    args = parser.parse_args()

    token = os.environ.get("HUBSPOT_TOKEN", "")
    if not token:
        print("ERROR: 環境変数 HUBSPOT_TOKEN が未設定です。", file=sys.stderr)
        print("  export HUBSPOT_TOKEN=<private-app-token> を設定して再実行してください。", file=sys.stderr)
        return 1

    specs = build_property_specs()
    print(f"対象オブジェクト: {OBJECT_TYPE} / プロパティ {len(specs)}件"
          + ("（dry-run）" if args.dry_run else ""))
    print("-" * 60)

    ensure_group(token, args.dry_run)

    counts = {"created": 0, "skipped": 0, "error": 0}
    for spec in specs:
        counts[create_property(token, spec, args.dry_run)] += 1

    print("-" * 60)
    print(f"結果: 作成 {counts['created']} / 既存スキップ {counts['skipped']} / 失敗 {counts['error']}")
    if counts["error"]:
        print("⚠️ 失敗があります。内部名・権限（プロパティ設定の編集）を確認してください。")
        return 2
    print("✅ 完了。次は Render に ENABLE_WB_SIGNALS=1 を設定して新規登録で wb_* が埋まるか確認。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
