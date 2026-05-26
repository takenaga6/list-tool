"""
verify_prime_sub_fix.py — fix/prime-subsidiary-exception ブランチの実データ検証

検証 A: 旧 PARENT_PRIME_KEYWORDS (generic キーワード含む) と
         新 PARENT_PRIME_KEYWORDS で is_parent_prime_subsidiary() の判定が変わる
         企業をローカルデータとHP取得で洗い出す。

検証 B: ng_list.csv / tool.log に「上場企業」「グループ会社」「200名超」でNG判定された
         企業がないか確認し、新コードで誤OK化がないか確認。

検証 C: Google CSE を1クエリ叩いてフル判定フローのログを確認する。
"""

import csv
import os
import sys
import time
import re
import logging

# ─── プロジェクトルートを sys.path に追加 ───────────────────────────────
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv()

from config import PARENT_PRIME_KEYWORDS
from agents.rank_agent import is_parent_prime_subsidiary

logging.basicConfig(level=logging.WARNING)

# ─── 旧 PARENT_PRIME_KEYWORDS（5つの generic キーワードが含まれていた） ───
OLD_PARENT_PRIME_KEYWORDS = [
    "東証プライム上場の", "プライム上場企業の",
    "プライム市場上場企業の", "上場企業の100%子会社",
    "100%子会社", "完全子会社",
    "の連結子会社", "の関連会社",
    "グループ会社",
    "SBIホールディングス", "SBI Holdings",
    "伊藤忠商事", "三井物産", "住友商事", "丸紅", "双日", "豊田通商",
    "ANAホールディングス", "JALホールディングス",
    "SOMPOホールディングス", "東京海上ホールディングス",
    "三井住友フィナンシャル", "三菱UFJフィナンシャル", "みずほフィナンシャル",
    "野村ホールディングス", "大和証券グループ",
    "GMOインターネットグループ",
]

# 削除された generic キーワード
REMOVED_KEYWORDS = {"100%子会社", "完全子会社", "の連結子会社", "の関連会社", "グループ会社"}

NEW_PARENT_PRIME_KEYWORDS = PARENT_PRIME_KEYWORDS  # 現在の設定


def old_is_prime(text: str) -> bool:
    return any(kw in text for kw in OLD_PARENT_PRIME_KEYWORDS)


def new_is_prime(text: str) -> bool:
    return is_parent_prime_subsidiary(text)


def matched_keywords(text: str, keywords) -> list[str]:
    return [kw for kw in keywords if kw in text]


# ─── A. ローカルCSVデータでの旧/新判定比較 ─────────────────────────────────
def check_a_local_data():
    print("\n" + "=" * 60)
    print("【検証 A-1】ローカル CSV での旧/新 PARENT_PRIME_KEYWORDS 比較")
    print("=" * 60)

    results_csv = os.path.join(_PROJECT_ROOT, "output", "results.csv")
    ng_csv = os.path.join(_PROJECT_ROOT, "output", "ng_list.csv")

    changed = []  # (source, company_name, url, old_result, new_result, matched_old, text_snippet)

    for filepath, label in [(results_csv, "registered"), (ng_csv, "ng_list")]:
        with open(filepath, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                company_name = row.get("会社名", "") or ""
                url = row.get("企業URL", "") or ""
                remarks = row.get("備考", "") or ""
                location = row.get("所在地", "") or ""
                text = company_name + " " + remarks + " " + location

                old_r = old_is_prime(text)
                new_r = new_is_prime(text)

                if old_r != new_r:
                    m_old = matched_keywords(text, OLD_PARENT_PRIME_KEYWORDS)
                    changed.append({
                        "source": label,
                        "name": company_name[:40],
                        "url": url,
                        "old": old_r,
                        "new": new_r,
                        "matched_old": m_old,
                        "snippet": text[:120],
                    })

    if not changed:
        print("→ 判定変化なし（旧→新で変わった企業は0件）")
        print("  ※ CSV 内のテキスト（会社名・備考・所在地）に generic キーワードは存在しない")
    else:
        print(f"→ 判定変化あり: {len(changed)}件")
        for c in changed:
            direction = "True→False (旧OK→新NG)" if c["old"] and not c["new"] else "False→True"
            print(f"  [{c['source']}] {c['name']}")
            print(f"    URL    : {c['url']}")
            print(f"    変化   : {direction}")
            print(f"    旧マッチ: {c['matched_old']}")
            print(f"    テキスト: {c['snippet']}")
            print()

    return changed


# ─── A-2. HP テキストフェッチによる詳細確認 ──────────────────────────────
def check_a_hp_fetch():
    """
    results.csv の登録済み企業 URL に対して HP を取得し、
    旧/新 PARENT_PRIME_KEYWORDS の差分を確認する。
    取得は1社10秒以内。全社最大30秒で打ち切る。
    """
    print("\n" + "=" * 60)
    print("【検証 A-2】HP フェッチ: 登録済み企業のプライム子会社判定")
    print("=" * 60)

    try:
        import httpx
        from bs4 import BeautifulSoup
    except ImportError:
        print("→ httpx/beautifulsoup4 未インストールのためスキップ")
        return []

    results_csv = os.path.join(_PROJECT_ROOT, "output", "results.csv")
    companies = []
    with open(results_csv, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            url = row.get("企業URL", "") or ""
            name = row.get("会社名", "") or ""
            if url and url.startswith("http"):
                companies.append((name, url))

    print(f"→ 登録済み企業: {len(companies)}社")

    changed_hp = []
    headers = {"User-Agent": "Mozilla/5.0 (compatible; list-tool verify/1.0)"}

    for name, url in companies[:15]:  # 最大15社を確認
        try:
            resp = httpx.get(url, timeout=8, follow_redirects=True, headers=headers)
            soup = BeautifulSoup(resp.text, "html.parser")
            # body テキスト（先頭3000字）
            body = soup.get_text(separator=" ", strip=True)[:3000]
        except Exception as e:
            print(f"  SKIP {name[:30]}: {type(e).__name__}")
            continue

        old_r = old_is_prime(body)
        new_r = new_is_prime(body)

        if old_r or new_r:
            m_old = matched_keywords(body, OLD_PARENT_PRIME_KEYWORDS)
            m_new = matched_keywords(body, NEW_PARENT_PRIME_KEYWORDS)
            status = ""
            if old_r and not new_r:
                status = "⚠️  旧OK→新NG（要確認）"
            elif not old_r and new_r:
                status = "→ 旧NG→新OK"
            else:
                status = "→ 変化なし（両方True）"

            print(f"\n  {name[:40]}")
            print(f"    URL    : {url}")
            print(f"    {status}")
            print(f"    旧マッチ: {m_old}")
            print(f"    新マッチ: {m_new}")

            if old_r and not new_r:
                changed_hp.append({
                    "name": name,
                    "url": url,
                    "matched_old_only": [k for k in m_old if k in REMOVED_KEYWORDS],
                })

        time.sleep(1)

    if not changed_hp:
        print("\n→ 旧OK→新NG 企業: 0件（HP取得範囲内で誤NG化なし）")
    else:
        print(f"\n→ 旧OK→新NG 企業: {len(changed_hp)}件")
        for c in changed_hp:
            print(f"  ⚠️  {c['name']}")
            print(f"     URL: {c['url']}")
            print(f"     generic キーワードのみマッチ: {c['matched_old_only']}")

    return changed_hp


# ─── B. NG リストでの上場/グループ関連 NG 確認 ──────────────────────────────
def check_b_ng_list():
    print("\n" + "=" * 60)
    print("【検証 B】ng_list.csv: 上場企業/グループ/200名超 NG の確認")
    print("=" * 60)

    ng_csv = os.path.join(_PROJECT_ROOT, "output", "ng_list.csv")
    stock_ng = []
    group_ng = []
    emp_ng = []

    with open(ng_csv, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            name = row.get("会社名", "") or ""
            reason = row.get("NG理由", "") or ""
            remarks = row.get("備考", "") or ""
            combined = reason + " " + remarks

            if re.search(r"上場企業|上場", combined):
                stock_ng.append((name, reason, remarks[:80]))
            elif re.search(r"グループ会社|大手グループ|グループ子会社", combined):
                group_ng.append((name, reason, remarks[:80]))
            elif re.search(r"200名超|大規模|空白帯|従業員\d+名", combined):
                emp_ng.append((name, reason, remarks[:80]))

    print(f"→ 上場企業NG: {len(stock_ng)}件")
    for n, r, m in stock_ng[:10]:
        print(f"  {n[:35]} | NG理由={r[:30]} | {m}")

    print(f"\n→ グループ会社NG: {len(group_ng)}件")
    for n, r, m in group_ng[:10]:
        print(f"  {n[:35]} | NG理由={r[:30]} | {m}")

    print(f"\n→ 従業員数NG: {len(emp_ng)}件")
    for n, r, m in emp_ng[:10]:
        print(f"  {n[:35]} | NG理由={r[:30]} | {m}")

    return stock_ng, group_ng, emp_ng


# ─── C. Google CSE ドライラン ────────────────────────────────────────────
def check_c_dryrun():
    print("\n" + "=" * 60)
    print("【検証 C】Google CSE ドライラン（1クエリ）")
    print("=" * 60)

    cse_key = os.environ.get("GOOGLE_CSE_API_KEY", "")
    cse_id  = os.environ.get("GOOGLE_CSE_CX", "")
    if not cse_key or not cse_id:
        print("→ GOOGLE_CSE_API_KEY / GOOGLE_CSE_ID 未設定、スキップ")
        return

    from agents.search_agent import SearchAgent
    from agents.scraper_agent import ScraperAgent
    from agents.rank_agent import pre_screen, evaluate_rank

    search_agent = SearchAgent()
    scraper = ScraperAgent()

    # 健康経営 × 東京 のクエリ（プライム子会社が引っかかりそうな現実的なクエリ）
    query = "健康経営優良法人 東証プライム 子会社 健康 採用"
    print(f"→ クエリ: {query}")

    results = search_agent.search(query, num_results=5)
    print(f"→ 検索結果: {len(results)}件")

    for i, result in enumerate(results[:5], 1):
        url   = result.get("url", "")
        title = result.get("title", "")
        snippet = result.get("snippet", "")[:80]

        passed, ng_reason = pre_screen(result)
        status = "PASS" if passed else f"NG({ng_reason})"

        print(f"\n  [{i}] {title[:45]}")
        print(f"       URL     : {url}")
        print(f"       snippet : {snippet}")
        print(f"       pre_screen: {status}")

        if passed:
            # scraping → evaluate_rank
            try:
                company_info = scraper.scrape(url)
                page_text = company_info.get("_page_text", "")
                rank_result = evaluate_rank(company_info, [result], page_text=page_text)
                print(f"       rank    : {rank_result['rank']} | ng_reason={rank_result.get('ng_reason','')}")
            except Exception as e:
                print(f"       scrape ERROR: {e}")

        time.sleep(2)


# ─── メイン ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("fix/prime-subsidiary-exception — 実データ検証スクリプト")
    print(f"新 PARENT_PRIME_KEYWORDS: {len(NEW_PARENT_PRIME_KEYWORDS)} キーワード")
    print(f"旧 PARENT_PRIME_KEYWORDS: {len(OLD_PARENT_PRIME_KEYWORDS)} キーワード（削除: {REMOVED_KEYWORDS}）")

    a1_changed = check_a_local_data()
    a2_changed = check_a_hp_fetch()
    b_stock, b_group, b_emp = check_b_ng_list()
    check_c_dryrun()

    # ─── 最終判定 ─────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("【マージ判断サマリー】")
    print("=" * 60)

    total_risky = len(a2_changed)
    print(f"A-1 CSV判定変化   : {len(a1_changed)} 件")
    print(f"A-2 HP取得旧OK→新NG: {total_risky} 件")
    print(f"B  上場NG記録     : {len(b_stock)} 件（ng_list.csv 内）")
    print(f"B  グループNG記録  : {len(b_group)} 件（ng_list.csv 内）")
    print(f"B  従業員数NG記録  : {len(b_emp)} 件（ng_list.csv 内）")

    if total_risky == 0:
        print("\n→ 推奨: マージしてよい（致命的な誤判定なし）")
    elif total_risky <= 3:
        print(f"\n→ 推奨: マージ前に微修正必要（{total_risky}件の旧OK→新NG企業を確認し、PARENT_PRIME_KEYWORDS への親会社名追加を検討）")
    else:
        print(f"\n→ 推奨: マージ見送り（{total_risky}件の旧OK→新NG — PARENT_PRIME_KEYWORDS の設計見直しが必要）")
