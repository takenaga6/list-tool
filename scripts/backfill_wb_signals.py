#!/usr/bin/env python3
"""回収トラック: 実績企業（アポ・受注）に wb_* 構造化シグナルをバックフィルする。

list-rank-validation の core。アポ獲得（Deal保有）・受注（顧客）企業に対して:
  1. HubSpot の「説明(description)」から リストアップ元（媒体）と流入経路を逆引き
     → wb_lead_source_type（list/紹介/inbound/手動）を判定。紹介・FAX・インバウンドは
       「非リスト経由」として検証から除外できるようタグ付け。
  2. 企業HPを再スクレイプ → evaluate_rank_v2 で再ランク → S1〜S10 シグナルを算出。
  3. wb_sig_s1〜s10 / wb_sig_score / wb_rank_version / wb_ranked_at /
     wb_lead_source_type を HubSpot に書き戻す。
  4. 媒体別・シグナル別の受注率（lift）レポートを出力。

これで初めて「実績（受注）× シグナル」の検証データが成立する（README: 問題A）。

使い方（Render Shell 推奨: デプロイ済みコード + HUBSPOT_TOKEN + スクレイプ網がある）:
    export HUBSPOT_TOKEN=<private-app-token>
    python scripts/backfill_wb_signals.py --dry-run            # 書き込まずプレビュー
    python scripts/backfill_wb_signals.py --no-scrape          # 媒体/流入の分類のみ（高速）
    python scripts/backfill_wb_signals.py --limit 10           # 先頭10社だけ本実行
    python scripts/backfill_wb_signals.py                      # 全件 本実行

注意:
  - wb_* プロパティが HubSpot に作成済みであること（scripts/create_wb_properties.py）。
  - 受注の定義は lifecyclestage == "customer"（README準拠）。
  - 再ランクは現在のHP本文に基づくため、登録当時と差異が出る場合がある（v1の割り切り）。
"""

import os
import re
import sys
import csv
import time
import argparse
from collections import Counter
from datetime import datetime
from urllib.parse import urlparse

import requests

# リポジトリルートを import パスに追加（scripts/ から agents・config を読む）
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from config import (
    MEDIA_NAME_TO_DOMAIN,
    HEALTH_CERT_DOMAINS,
    LARGE_COMPANY_DOMAINS,
    RANK_LOGIC_VERSION,
    OUTPUT_DIR,
)
from agents.rank_agent import evaluate_rank_v2
from agents.scraper_agent import scrape_company_info

# 副作用の無効化:
# scrape_company_info はスクレイプ失敗時に config.record_domain_fail() を呼び、
# 本番の learned_exclude.json（3回失敗で自動除外）にドメインを記録する。
# バックフィルは実績企業の再スクレイプを伴うため、これを呼ぶと実績ドメインを
# 誤って本番の除外リストへ載せうる。分析目的なので no-op に差し替える。
# （scrape_company_info は実行時に `from config import record_domain_fail` する
#   ため、config モジュール属性の差し替えで確実に無効化される。）
import config as _config
_config.record_domain_fail = lambda *a, **k: None

BASE_URL = "https://api.hubapi.com"

# ── 媒体逆引き（ドメイン → 媒体名）─────────────────────────────
# config の既存マップを再利用。検証対象外の業界メディアも参考表示用に追加。
DOMAIN_TO_MEDIA: dict[str, str] = {}
for _name, _dom in MEDIA_NAME_TO_DOMAIN.items():
    DOMAIN_TO_MEDIA.setdefault(_dom, _name)
for _dom in HEALTH_CERT_DOMAINS:
    DOMAIN_TO_MEDIA.setdefault(_dom, "健康経営優良法人")
# 検証対象媒体ではないが説明に頻出する参照元（レポート用・lead_source は list 扱いしない）
NON_TARGET_MEDIA = {
    "weekly-net.co.jp": "物流ウィークリー",
    "kyoukaikenpo.or.jp": "協会けんぽ",
    "kokoro.mhlw.go.jp": "厚労省こころ",
    "bosei-navi.mhlw.go.jp": "厚労省母性",
}

# 流入経路の判定キーワード
_REFERRAL_RE = re.compile(r"紹介")
_INBOUND_RE = re.compile(r"FAX|ＦＡＸ|チラシ|流入|問い?合わせ|インバウンド|問合")

# 受注の定義
WON_STAGE = "customer"


def classify_lead_source(description: str, domain: str) -> tuple[str, str, bool]:
    """説明文と自社ドメインから (lead_source_type, media_name, is_big) を返す。

    lead_source_type: "list" / "紹介" / "inbound" / "手動"
    media_name: list の場合の媒体名（無ければ ""）
    is_big: 大手ドメイン（到達不可で検証除外対象）か
    """
    desc = description or ""
    is_big = any(big in (domain or "") for big in LARGE_COMPANY_DOMAINS)

    # 1. 紹介（最優先・非リスト）
    if _REFERRAL_RE.search(desc):
        return "紹介", "", is_big
    # 2. FAX・チラシ・流入・問い合わせ（インバウンド・非リスト）
    if _INBOUND_RE.search(desc):
        return "inbound", "", is_big
    # 3. 説明に媒体ドメインが含まれる → リスト経由
    for dom, media in DOMAIN_TO_MEDIA.items():
        if dom in desc:
            return "list", media, is_big
    for dom, media in NON_TARGET_MEDIA.items():
        if dom in desc:
            # 業界メディア等。リスト生成ツールの対象媒体ではないので list 扱いしない
            return "手動", media, is_big
    # 4. それ以外（生スクレイプ文・手動取り込み等）
    return "手動", "", is_big


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def fetch_target_companies(token: str) -> list[dict]:
    """Deal保有 または 顧客 の企業を全件取得（ページング）。"""
    url = f"{BASE_URL}/crm/v3/objects/companies/search"
    props = ["name", "domain", "website", "description", "industry",
             "numberofemployees", "lifecyclestage", "num_associated_deals",
             "a_12", "address", "city", "state", "zip", "wb_rank_version"]
    results: list[dict] = []
    after = None
    while True:
        payload = {
            "filterGroups": [
                {"filters": [{"propertyName": "num_associated_deals", "operator": "GT", "value": "0"}]},
                {"filters": [{"propertyName": "lifecyclestage", "operator": "EQ", "value": WON_STAGE}]},
            ],
            "properties": props,
            "limit": 100,
        }
        if after:
            payload["after"] = after
        resp = requests.post(url, json=payload, headers=_headers(token), timeout=20)
        resp.raise_for_status()
        data = resp.json()
        results.extend(data.get("results", []))
        after = data.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
        time.sleep(0.2)
    return results


def rerank_company(company: dict) -> tuple[dict | None, str, int]:
    """企業HPを再スクレイプ → evaluate_rank_v2。

    URLは自社ドメイン(domain)を優先する。HubSpot の website には媒体URL
    （voice-report 等）や末尾タイプミス（例: mabuchist.co.jpl）が混入しており、
    それを掴むと再ランクに失敗するため。

    Returns: (rank_result | None, reason, page_chars)
      reason: "ok" / "empty_page" / "no_domain" /
              "no_company_url" / "scrape_error:<type>"
    """
    props = company.get("properties", {})
    domain = (props.get("domain") or "").strip()
    website = (props.get("website") or "").strip()
    base = domain or website  # 自社ドメイン優先
    if not base:
        return None, "no_domain", 0
    url = base if base.startswith("http") else "https://" + base
    try:
        info = scrape_company_info(url)
    except Exception as e:
        return None, f"scrape_error:{type(e).__name__}", 0
    if not info.get("company_url"):
        return None, "no_company_url", 0
    # HubSpot 側の業種・従業員数で補完（スクレイプで取れない場合の保険）
    info.setdefault("industry", props.get("industry", "") or "")
    if not info.get("employee_count"):
        info["employee_count"] = props.get("numberofemployees", "") or ""
    if not info.get("address"):
        info["address"] = props.get("address", "") or ""

    page_text = info.get("_page_text", "")
    # 媒体ソースを search_results に渡して S1/S2 を正しく与える
    media_dom = ""
    desc = props.get("description", "") or ""
    for dom in list(DOMAIN_TO_MEDIA.keys()):
        if dom in desc:
            media_dom = dom
            break
    search_results = [{
        "url": info["company_url"],
        "source_list_url": f"https://{media_dom}/" if media_dom else "",
        "search_query": "",
    }]
    result = evaluate_rank_v2(info, search_results, page_text=page_text)
    return result, ("ok" if page_text else "empty_page"), len(page_text)


def build_patch_props(lead_source: str, rank_result: dict | None) -> dict:
    props: dict = {"wb_lead_source_type": lead_source}
    if rank_result:
        sig = rank_result.get("signals", {})
        for i in range(1, 11):
            v = sig.get(f"S{i}")
            if v is not None:
                props[f"wb_sig_s{i}"] = "true" if v else "false"
        score = rank_result.get("score")
        if score is not None:
            props["wb_sig_score"] = str(score)
        props["wb_rank_version"] = rank_result.get("rank_version") or RANK_LOGIC_VERSION
        props["wb_ranked_at"] = datetime.now().strftime("%Y-%m-%d")
    return props


def patch_company(token: str, company_id: str, props: dict) -> bool:
    url = f"{BASE_URL}/crm/v3/objects/companies/{company_id}"
    resp = requests.patch(url, json={"properties": props}, headers=_headers(token), timeout=20)
    if resp.ok:
        return True
    print(f"    PATCH失敗: {resp.status_code} {resp.text[:160]}")
    return False


def _won(props: dict) -> bool:
    return (props.get("lifecyclestage") or "") == WON_STAGE


def print_report(rows: list[dict]) -> None:
    """媒体別・シグナル別の受注率（lift）レポート。rows は処理済み企業のメタ。"""
    print("\n" + "=" * 64)
    print("【レポート】")
    total = len(rows)
    print(f"対象企業: {total}社")

    # 流入経路の分布
    print("\n■ 流入経路（wb_lead_source_type）の分布")
    by_src: dict[str, list[dict]] = {}
    for r in rows:
        by_src.setdefault(r["lead_source"], []).append(r)
    for src, rs in sorted(by_src.items(), key=lambda x: -len(x[1])):
        won = sum(1 for r in rs if r["won"])
        print(f"  {src:6} {len(rs):3}社  受注{won:3}社  受注率 {won/len(rs)*100:5.1f}%")

    # list 経由のみで検証
    listed = [r for r in rows if r["lead_source"] == "list"]
    print(f"\n■ リスト経由のみ（検証対象）: {len(listed)}社")

    # 媒体別 受注率
    print("\n■ 媒体別 受注率（リスト経由）")
    by_media: dict[str, list[dict]] = {}
    for r in listed:
        by_media.setdefault(r["media"] or "(媒体不明)", []).append(r)
    for media, rs in sorted(by_media.items(), key=lambda x: -len(x[1])):
        won = sum(1 for r in rs if r["won"])
        print(f"  {media:24} {len(rs):3}社  受注{won:3}社  受注率 {won/len(rs)*100:5.1f}%")

    # シグナル別 lift（リスト経由・再ランク済みのみ）
    ranked = [r for r in listed if r.get("signals")]
    print(f"\n■ シグナル別 lift（リスト経由・再ランク済 {len(ranked)}社）")
    if not ranked:
        print("  （再ランク済み企業なし。--no-scrape を外して実行すると算出されます）")
    else:
        print(f"  {'シグナル':16} {'あり社数':>6} {'受注率(あり)':>12} {'受注率(なし)':>12} {'lift':>6}")
        for i in range(1, 11):
            key = f"S{i}"
            has = [r for r in ranked if r["signals"].get(key)]
            non = [r for r in ranked if not r["signals"].get(key)]
            wr_has = (sum(1 for r in has if r["won"]) / len(has)) if has else 0.0
            wr_non = (sum(1 for r in non if r["won"]) / len(non)) if non else 0.0
            lift = (wr_has / wr_non) if wr_non > 0 else float("inf") if wr_has > 0 else 0.0
            lift_s = "∞" if lift == float("inf") else f"{lift:.2f}"
            print(f"  {key:16} {len(has):6} {wr_has*100:11.1f}% {wr_non*100:11.1f}% {lift_s:>6}")
    print("=" * 64)


def main() -> int:
    parser = argparse.ArgumentParser(description="実績企業に wb_* をバックフィル")
    parser.add_argument("--dry-run", action="store_true", help="HubSpotに書き込まない")
    parser.add_argument("--no-scrape", action="store_true", help="再スクレイプ/再ランクせず流入分類のみ")
    parser.add_argument("--limit", type=int, default=0, help="処理する社数の上限（0=全件）")
    parser.add_argument("--sleep", type=float, default=1.0, help="スクレイプ間の待機秒")
    parser.add_argument("--rerank-all", action="store_true",
                        help="list 経由だけでなく全企業を再ランク（手動/紹介も signals 取得）")
    args = parser.parse_args()

    token = os.environ.get("HUBSPOT_TOKEN", "")
    if not token:
        print("ERROR: HUBSPOT_TOKEN が未設定です。", file=sys.stderr)
        return 1

    print("対象企業を取得中…")
    companies = fetch_target_companies(token)
    print(f"取得: {len(companies)}社" + ("（dry-run）" if args.dry_run else ""))
    if args.limit:
        companies = companies[: args.limit]
        print(f"--limit により先頭 {len(companies)}社のみ処理")

    rows: list[dict] = []
    written = 0
    rerank_reasons: Counter = Counter()
    for idx, comp in enumerate(companies, 1):
        cid = comp["id"]
        props = comp.get("properties", {})
        name = props.get("name", "")
        domain = props.get("domain", "")
        desc = props.get("description", "") or ""
        lead_source, media, is_big = classify_lead_source(desc, domain)
        won = _won(props)

        rank_result = None
        if not args.no_scrape and (lead_source == "list" or args.rerank_all):
            rank_result, reason, _chars = rerank_company(comp)
            rerank_reasons[reason] += 1
            if rank_result is None:
                print(f"    再ランク不能: {reason}")
            time.sleep(args.sleep)

        patch = build_patch_props(lead_source, rank_result)
        status = "DRY" if args.dry_run else ("OK" if patch_company(token, cid, patch) else "ERR")
        if status == "OK":
            written += 1

        score = rank_result.get("score") if rank_result else ""
        rank = rank_result.get("rank") if rank_result else ""
        print(f"[{idx}/{len(companies)}] {status} {name} "
              f"src={lead_source} media={media or '-'} won={'Y' if won else '-'} "
              f"rank={rank or '-'}({score})")

        rows.append({
            "id": cid, "name": name, "lead_source": lead_source, "media": media,
            "is_big": is_big, "won": won,
            "signals": rank_result.get("signals") if rank_result else None,
            "score": score, "rank": rank,
        })

    # CSV 保存
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    csv_path = os.path.join(OUTPUT_DIR, "backfill_wb_report.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "lead_source", "media", "is_big", "won", "rank", "score"]
                   + [f"S{i}" for i in range(1, 11)])
        for r in rows:
            sig = r.get("signals") or {}
            w.writerow([r["id"], r["name"], r["lead_source"], r["media"], r["is_big"],
                        r["won"], r["rank"], r["score"]]
                       + [int(bool(sig.get(f"S{i}"))) if sig else "" for i in range(1, 11)])

    print(f"\n書き込み: {written}社" + ("（dry-run のため0）" if args.dry_run else ""))
    print(f"明細CSV: {csv_path}")
    if rerank_reasons:
        print("\n■ 再ランク結果の内訳（原因可視化）")
        for reason, n in rerank_reasons.most_common():
            print(f"  {reason:28} {n}社")
    print_report(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
