# -*- coding: utf-8 -*-
"""output/results_with_query.csv の品質監査スクリプト"""
import csv, re, os, sys
from collections import defaultdict

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
CSV_FILE = os.path.join(ROOT, "output", "results_with_query.csv")
OUT_FILE = os.path.join(ROOT, "output", "csv_audit_report.md")

from utils.prefecture_resolver import (
    phone_to_prefecture, postal_code_to_prefecture, ALL_PREFECTURES
)

MANUFACTURING_WORDS = ["製缶","板金","製作所","工業","鍛造","鋳造","プレス","溶接",
                        "機械","金属","製鉄","製鋼","部品","組立","加工","製造",
                        "鉄工","ダンボール","段ボール","印刷","建設","土木","建築",
                        "工務店","リフォーム","リノベ","塗装","配管","電設","電機"]

def query_pref(query: str) -> str:
    for p in ALL_PREFECTURES:
        if p in query:
            return p
    return ""

def name_issues(name: str) -> list:
    issues = []
    if "ホームページ" in name or "トップページ" in name:
        issues.append("会社名に'ホームページ/トップページ'含む")
    if re.search(r"[-－][ 　]*(福島|東京|大阪|北海道|[^\s]{2,4}[都道府県])", name):
        issues.append("会社名に地名注釈含む")
    if "│" in name or "｜" in name:
        issues.append("会社名にパイプ文字含む")
    if len(name) > 50:
        issues.append(f"会社名が長すぎる({len(name)}文字)")
    return issues

# ── CSV 読み込み ────────────────────────────────────────────────────────
rows = []
with open(CSV_FILE, encoding="utf-8-sig", errors="replace") as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader, 1):
        row["_line"] = i
        rows.append(row)

# ── 各レコード判定 ───────────────────────────────────────────────────────
records = []
for row in rows:
    name     = (row.get("会社名") or "").strip()
    tel      = (row.get("電話番号") or "").strip()
    zipcode  = (row.get("郵便番号") or "").strip()
    pref_csv = (row.get("都道府県") or "").strip()
    query    = (row.get("検索クエリ") or "").strip()
    date     = (row.get("日時") or "").strip()
    rank     = (row.get("ランク") or "").strip()
    url      = (row.get("企業URL") or "").strip()
    gyoshu   = (row.get("業種") or "").strip()

    warns = []

    # 1. 市外局番
    tel_p = phone_to_prefecture(tel) or "" if tel else ""
    if tel_p and pref_csv and tel_p != pref_csv:
        warns.append(f"市外局番不一致: {tel}→{tel_p} vs CSV:{pref_csv}")

    # 2. 郵便番号
    zip_p = postal_code_to_prefecture(zipcode) or "" if zipcode else ""
    if zip_p and pref_csv and zip_p != pref_csv:
        warns.append(f"郵便番号不一致: {zipcode}→{zip_p} vs CSV:{pref_csv}")

    # 3. クエリ地域
    q_p = query_pref(query)
    if q_p and pref_csv and q_p != pref_csv:
        warns.append(f"クエリ地域不一致: クエリ内:{q_p} vs CSV:{pref_csv}")

    # 4. 会社名体裁
    for issue in name_issues(name):
        warns.append(f"会社名: {issue}")

    # 5. 業種誤分類疑い
    if gyoshu == "情報通信":
        for w in MANUFACTURING_WORDS:
            if w in name:
                warns.append(f"業種誤分類疑い: '{w}'含む名前なのに業種=情報通信")
                break

    records.append({
        "line": row["_line"], "date": date, "rank": rank,
        "name": name, "pref_csv": pref_csv, "tel": tel, "tel_p": tel_p,
        "zip": zipcode, "zip_p": zip_p, "q_p": q_p, "query": query,
        "url": url, "warns": warns,
    })

# 6. 重複チェック（URL・電話番号）
url_map  = defaultdict(list)
tel_map  = defaultdict(list)
for r in records:
    if r["url"]:
        url_map[r["url"]].append(r["line"])
    tel_digits = re.sub(r"[^\d]", "", r["tel"])
    if len(tel_digits) >= 9:
        tel_map[tel_digits].append(r["line"])

for r in records:
    if r["url"] and len(url_map[r["url"]]) > 1:
        dup_lines = [l for l in url_map[r["url"]] if l != r["line"]]
        r["warns"].append(f"URL重複: 行{dup_lines}と同じURL")
    tel_digits = re.sub(r"[^\d]", "", r["tel"])
    if len(tel_digits) >= 9 and len(tel_map[tel_digits]) > 1:
        dup_lines = [l for l in tel_map[tel_digits] if l != r["line"]]
        r["warns"].append(f"電話番号重複: 行{dup_lines}と同じ番号")

# ── 集計 ────────────────────────────────────────────────────────────────
warn_records = [r for r in records if r["warns"]]
cnt = {
    "市外局番不一致": sum(1 for r in records if any("市外局番不一致" in w for w in r["warns"])),
    "郵便番号不一致": sum(1 for r in records if any("郵便番号不一致" in w for w in r["warns"])),
    "クエリ地域不一致": sum(1 for r in records if any("クエリ地域不一致" in w for w in r["warns"])),
    "会社名体裁問題": sum(1 for r in records if any("会社名:" in w for w in r["warns"])),
    "業種誤分類疑い": sum(1 for r in records if any("業種誤分類" in w for w in r["warns"])),
    "重複": sum(1 for r in records if any("重複" in w for w in r["warns"])),
}

# 経路別
media_records  = [r for r in records if "[リストページ]" in r["query"] or "媒体リスト" in r.get("query","")]
search_records = [r for r in records if r not in media_records]
# 備考列で判定し直す
route_counts = {"媒体リスト経由": 0, "検索クエリ経由": 0}
route_warn   = {"媒体リスト経由": 0, "検索クエリ経由": 0}
for row, r in zip(rows, records):
    biko = (row.get("備考") or "")
    if "媒体リスト" in biko or "[リストページ]" in r["query"]:
        route_counts["媒体リスト経由"] += 1
        if r["warns"]:
            route_warn["媒体リスト経由"] += 1
    else:
        route_counts["検索クエリ経由"] += 1
        if r["warns"]:
            route_warn["検索クエリ経由"] += 1

# ── レポート出力 ─────────────────────────────────────────────────────────
lines_out = []
lines_out.append("# CSV 監査レポート（{}件）\n".format(len(records)))
lines_out.append("## サマリー")
lines_out.append(f"- 総レコード数: {len(records)}")
lines_out.append(f"- 警告ありレコード: {len(warn_records)}件 ({len(warn_records)/max(len(records),1)*100:.0f}%)")
lines_out.append("- 内訳:")
for k, v in cnt.items():
    lines_out.append(f"  - {k}: {v}件")
lines_out.append("")

lines_out.append("## 全レコードの判定（表形式）")
lines_out.append("| # | 日時 | 会社名(先頭30字) | CSV都道府県 | 電話推定 | 郵便推定 | クエリ地域 | 判定 |")
lines_out.append("|---|------|-----------------|------------|---------|---------|-----------|------|")
for r in records:
    name_s = r["name"][:30].replace("|","｜")
    ok = "✅" if not r["warns"] else "❌"
    lines_out.append(
        f"| {r['line']} | {r['date'][:10]} | {name_s} | {r['pref_csv']} "
        f"| {r['tel_p'] or '-'} | {r['zip_p'] or '-'} | {r['q_p'] or '-'} | {ok} |"
    )
lines_out.append("")

lines_out.append("## 警告詳細")
for r in warn_records:
    lines_out.append(f"\n### 行{r['line']}: {r['name'][:50]}")
    lines_out.append(f"- 日時: {r['date']} / ランク: {r['rank']} / 都道府県(CSV): {r['pref_csv']}")
    lines_out.append(f"- 電話: {r['tel']} / 郵便: {r['zip']}")
    lines_out.append(f"- クエリ: {r['query']}")
    for w in r["warns"]:
        lines_out.append(f"- ⚠️ {w}")
lines_out.append("")

# 重大事故Top10（警告数多い順）
lines_out.append("## 重大事故Top10（警告数多い順）")
top10 = sorted(warn_records, key=lambda x: -len(x["warns"]))[:10]
lines_out.append("| 優先度 | 行 | 会社名 | 警告数 | 警告内容 |")
lines_out.append("|--------|----|---------|---------|---------| ")
for i, r in enumerate(top10, 1):
    lines_out.append(
        f"| {i} | {r['line']} | {r['name'][:35]} | {len(r['warns'])} | {'; '.join(r['warns'])[:80]} |"
    )
lines_out.append("")

lines_out.append("## 経路別の事故率")
for route, total in route_counts.items():
    w = route_warn[route]
    pct = w/total*100 if total else 0
    lines_out.append(f"- {route}（{total}件）: 警告{w}件（{pct:.0f}%）")

report_text = "\n".join(lines_out)
with open(OUT_FILE, "w", encoding="utf-8") as f:
    f.write(report_text)

print(report_text)
print(f"\n→ {OUT_FILE} に保存しました")
