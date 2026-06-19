#!/usr/bin/env python3
"""PR #12（従業員数抽出パターン拡張）の実データ検証スクリプト。

CLAUDE.md のコア判定ロジック変更ルールに基づくマージ前検証。
既存のランク付き企業（= 既存OK企業）を再スクレイプし、
旧パターン・新パターンの抽出値を突き合わせ、HubSpot 登録値（正解の目安）と比較する。

確認したいこと:
  1. 回収: 旧では取れず新で取れた（recovered）= 歩留まり改善の実数
  2. 退行: 旧と新で抽出値が食い違う（changed）= 誤抽出/規模判定崩れの危険（要目視）
  3. 整合: 新の抽出値が HubSpot 登録値と大きく乖離しないか（mismatch）

読み取り＋スクレイプのみ。HubSpot への書き込み・learned_exclude への記録はしない。

使い方:
    export HUBSPOT_TOKEN=<token>
    python scripts/verify_employee_extraction.py --limit 40
"""

import os
import re
import sys
import time
import argparse

import requests

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# 副作用無効化（スクレイプ失敗を本番 learned_exclude に記録しない）
import config as _config
_config.record_domain_fail = lambda *a, **k: None

from agents.scraper_agent import get_page_text

BASE_URL = "https://api.hubapi.com"

# 新 EMPLOYEE_PATTERNS（PR #12）— scraper の版に依存せず内蔵する。
# こうすることで PR #12 をマージする前（＝現在の本番デプロイ）でも検証できる。
NEW_PATTERNS = [
    r"(?:従業員|社員|スタッフ|職員|人員)(?:数|人数)?\s*(?:[（(][^）)]*[）)])?\s*[：:\s]*約?\s*([\d,]+)\s*[名人]",
    r"([\d,]+)\s*[名人](?:のスタッフ|の社員|の従業員|の職員)",
    r"(?:総勢|総従業員数|グループ従業員数)\s*[：:\s]*約?\s*([\d,]+)\s*[名人]",
]

# 旧 EMPLOYEE_PATTERNS（PR #12 以前）— 比較用に固定で持つ
OLD_PATTERNS = [
    r"従業員[数人]?\s*[：:\s]*(\d+)\s*名",
    r"社員[数人]?\s*[：:\s]*(\d+)\s*名",
    r"スタッフ[数人]?\s*[：:\s]*(\d+)\s*名",
    r"(\d+)\s*名(?:のスタッフ|の社員|の従業員)",
]

SUB_PATHS = ["/company", "/company/profile", "/company/outline",
             "/about", "/profile", "/outline", "/company-info"]


def extract_with(patterns: list[str], text: str) -> str:
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            raw = m.group(1).replace(",", "").replace("，", "")
            if raw.isdigit():
                n = int(raw)
                if 1 <= n <= 10000:
                    return str(n)
    return ""


def fetch_text(domain: str) -> str:
    """トップ＋会社概要系サブページを連結して返す（scraper の取得を模倣）。"""
    if not domain:
        return ""
    base = domain if domain.startswith("http") else "https://" + domain
    base = base.rstrip("/")
    texts = []
    t, _ = get_page_text(base)
    if t:
        texts.append(t)
    # トップで取れなければサブページも見る
    if not extract_with(NEW_PATTERNS, " ".join(texts)):
        for p in SUB_PATHS:
            t, _ = get_page_text(base + p)
            if t:
                texts.append(t)
            if extract_with(NEW_PATTERNS, " ".join(texts)):
                break
    return " ".join(texts)


def fetch_sample(token: str, limit: int) -> list[dict]:
    """a_12（ランク）付き＝既存OK企業を取得。"""
    url = f"{BASE_URL}/crm/v3/objects/companies/search"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "filterGroups": [{"filters": [{"propertyName": "a_12", "operator": "HAS_PROPERTY"}]}],
        "properties": ["name", "domain", "website", "numberofemployees", "a_12"],
        "limit": min(limit, 100),
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.json().get("results", [])


def _to_int(s) -> int | None:
    s = re.sub(r"\D", "", str(s or ""))
    return int(s) if s else None


def main() -> int:
    parser = argparse.ArgumentParser(description="従業員数抽出パターンの実データ検証")
    parser.add_argument("--limit", type=int, default=40, help="検証社数")
    parser.add_argument("--sleep", type=float, default=1.0)
    args = parser.parse_args()

    token = os.environ.get("HUBSPOT_TOKEN", "")
    if not token:
        print("ERROR: HUBSPOT_TOKEN 未設定", file=sys.stderr)
        return 1

    companies = fetch_sample(token, args.limit)
    print(f"検証対象（a_12付き既存企業）: {len(companies)}社\n")

    recovered, changed, mismatch, agree, both_empty = [], [], [], [], []
    print(f"{'会社名':24} {'HS登録':>7} {'旧':>5} {'新':>5}  判定")
    for comp in companies:
        p = comp.get("properties", {})
        name = (p.get("name") or "")[:24]
        domain = p.get("domain") or p.get("website") or ""
        hs_emp = _to_int(p.get("numberofemployees"))

        text = fetch_text(domain)
        old = extract_with(OLD_PATTERNS, text)
        new = extract_with(NEW_PATTERNS, text)
        time.sleep(args.sleep)

        tag = ""
        if not old and new:
            tag = "★回収"
            recovered.append((name, new, hs_emp))
        elif old and new and old != new:
            tag = "⚠️退行?"
            changed.append((name, old, new, hs_emp))
        elif new and hs_emp and abs(int(new) - hs_emp) > max(5, hs_emp * 0.5):
            tag = "△HS乖離"
            mismatch.append((name, new, hs_emp))
        elif not old and not new:
            both_empty.append(name)
        else:
            agree.append(name)

        print(f"{name:24} {str(hs_emp or '-'):>7} {old or '-':>5} {new or '-':>5}  {tag}")

    print("\n" + "=" * 60)
    print("【検証サマリ】")
    print(f"  ★回収（旧×→新○）   : {len(recovered)}社  ← 歩留まり改善の実数")
    print(f"  ⚠️退行?（旧≠新）     : {len(changed)}社  ← 要目視（誤抽出/規模判定崩れの危険）")
    print(f"  △HS登録値と乖離      : {len(mismatch)}社  ← 要目視")
    print(f"  一致/変化なし        : {len(agree)}社")
    print(f"  両方取れず           : {len(both_empty)}社")

    if changed:
        print("\n⚠️ 退行候補（旧→新で値が変わった社・必ず目視）:")
        for name, old, new, hs in changed:
            print(f"    {name}: 旧{old} → 新{new}（HS登録{hs or '-'}）")
    if mismatch:
        print("\n△ HS登録値と乖離（新抽出が登録値と大きく違う社）:")
        for name, new, hs in mismatch:
            print(f"    {name}: 新{new}（HS登録{hs}）")
    if recovered:
        print("\n★ 回収サンプル（最大10社）:")
        for name, new, hs in recovered[:10]:
            print(f"    {name}: 新{new}（HS登録{hs or '-'}）")
    print("=" * 60)
    print("\n判断目安: ⚠️退行?・△乖離 が無い/少なく説明可能なら、誤抽出リスクは低い。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
