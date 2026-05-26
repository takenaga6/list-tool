# -*- coding: utf-8 -*-
"""keyword_stats.json と results_with_query.csv の集計スクリプト"""
import json
import csv
import sys
import os
from collections import Counter, defaultdict

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)

STATS_FILE = os.path.join(ROOT, "output", "keyword_stats.json")
CSV_FILE   = os.path.join(ROOT, "output", "results_with_query.csv")

# ────────────────────────────────────────────────
# 1. keyword_stats.json 読み込み
# ────────────────────────────────────────────────
with open(STATS_FILE, encoding="utf-8") as f:
    data = json.load(f)

version = data.get("_version", "v1")
queries = data.get("queries", data)

def is_dead(s):
    runs = s.get("runs", 0)
    hits = s.get("total_hits", 0)
    if runs >= 3 and hits == 0: return True
    if runs >= 5 and hits > 0 and hits / runs < 0.05: return True
    return False

all_q         = list(queries.items())
ran_q         = [(q, s) for q, s in all_q if s.get("runs", 0) > 0]
never_ran_q   = [(q, s) for q, s in all_q if s.get("runs", 0) == 0]
dead_q        = [(q, s) for q, s in all_q if is_dead(s)]
has_hits_q    = [(q, s) for q, s in all_q if s.get("total_hits", 0) > 0]
has_ab_q      = [(q, s) for q, s in all_q if s.get("a_rank", 0) + s.get("b_rank", 0) > 0]
has_a_q       = [(q, s) for q, s in all_q if s.get("a_rank", 0) > 0]
hits_no_ab_q  = [(q, s) for q, s in all_q if s.get("total_hits", 0) > 0
                 and s.get("a_rank", 0) + s.get("b_rank", 0) == 0]

print("=" * 60)
print("【1】keyword_stats.json 基本統計")
print("=" * 60)
print(f"  バージョン            : {version}")
print(f"  stats 内クエリ総数    : {len(all_q):>6}")
print(f"  実行済み              : {len(ran_q):>6}")
print(f"  未実行                : {len(never_ran_q):>6}")
print(f"  dead 判定             : {len(dead_q):>6}")
print(f"  ヒットあり            : {len(has_hits_q):>6}")
print(f"  A/B 登録実績あり      : {len(has_ab_q):>6}")
print(f"  A 登録実績あり        : {len(has_a_q):>6}")
print(f"  ヒットあり・登録ゼロ  : {len(hits_no_ab_q):>6}  ← 最重要")

print()
print("=" * 60)
print("【2】A 件数 Top 20 クエリ")
print("=" * 60)
print(f"  {'A':>3} {'B':>3} {'runs':>4} {'a_rate':>7}  クエリ")
print("  " + "-"*55)
top_a = sorted(has_a_q, key=lambda x: (-x[1]["a_rank"], -x[1].get("a_rate", 0)))[:20]
for q, s in top_a:
    print(f"  {s['a_rank']:>3} {s.get('b_rank',0):>3} {s['runs']:>4} {s.get('a_rate',0):>7.0%}  {q}")

print()
print("=" * 60)
print("【3】A+B 件数 Top 20 クエリ（ヒット率≧10%のみ）")
print("=" * 60)
print(f"  {'A':>3} {'B':>3} {'runs':>4} {'ab_rate':>8}  クエリ")
print("  " + "-"*60)
top_ab = sorted(
    [(q, s) for q, s in has_ab_q if s.get("ab_rate", 0) >= 0.05 and s.get("runs", 0) >= 3],
    key=lambda x: (-(x[1]["a_rank"]+x[1].get("b_rank",0)), -x[1].get("ab_rate",0))
)[:20]
for q, s in top_ab:
    print(f"  {s['a_rank']:>3} {s.get('b_rank',0):>3} {s['runs']:>4} {s.get('ab_rate',0):>8.1%}  {q}")

print()
print("=" * 60)
print("【4】ヒットあり・登録ゼロ クエリ Top 20（ヒット数多い順）")
print("=" * 60)
print(f"  {'hits':>5} {'runs':>4} {'avg':>5}  クエリ")
print("  " + "-"*55)
top_wasted = sorted(hits_no_ab_q, key=lambda x: -x[1].get("total_hits", 0))[:20]
for q, s in top_wasted:
    print(f"  {s['total_hits']:>5} {s['runs']:>4} {s.get('avg_hits',0):>5.1f}  {q}")

# ────────────────────────────────────────────────
# 5. results_with_query.csv 読み込み
# ────────────────────────────────────────────────
print()
print("=" * 60)
print("【5】results_with_query.csv 分析")
print("=" * 60)

rows = []
if os.path.exists(CSV_FILE):
    with open(CSV_FILE, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    rows = [r for r in rows if r.get("会社名", "").strip()]  # 空行除去

if not rows:
    print("  ⚠ CSV が空またはヘッダーのみ（Render から取得が必要）")
    print()
    print("  Render Shell での取得手順:")
    print("    $ ls -la /data/*.csv")
    print("    $ wc -l /data/results_with_query.csv")
    print("    $ head -5 /data/results_with_query.csv")
    print("  → Render Dashboard > Shell > ファイルダウンロード または scp で取得")
else:
    print(f"  登録総件数: {len(rows)}")

    # ランク内訳
    rank_cnt = Counter(r.get("ランク", "不明") for r in rows)
    print()
    print("  ランク内訳:")
    for rank in ["A", "B", "C", "NG", "不明"]:
        if rank in rank_cnt:
            print(f"    {rank}: {rank_cnt[rank]:>4} 件")

    # クエリ別
    q_cnt = Counter(r.get("検索クエリ", "") for r in rows)
    print()
    print("  クエリ別 Top 20:")
    print(f"    {'件数':>5}  クエリ")
    print("    " + "-"*60)
    for q, c in q_cnt.most_common(20):
        print(f"    {c:>5}  {q[:70]}")

    # 都道府県
    pref_cnt = Counter(r.get("都道府県", "不明") for r in rows)
    print()
    print("  都道府県 Top 15:")
    for pref, c in pref_cnt.most_common(15):
        bar = "■" * min(c, 20)
        print(f"    {pref:<6} {c:>4} {bar}")

    # 日別
    date_cnt = Counter(r.get("日時", "")[:10] for r in rows if r.get("日時"))
    print()
    print("  登録日別件数:")
    for dt in sorted(date_cnt.keys()):
        bar = "■" * min(date_cnt[dt], 30)
        print(f"    {dt}  {date_cnt[dt]:>4} {bar}")

    # メディアソース
    media_cnt = Counter()
    for r in rows:
        備考 = r.get("備考", "")
        if "媒体リスト:" in 備考:
            media_cnt["S1/S2 リスト経由"] += 1
        elif "検索クエリ:" in 備考:
            media_cnt["キーワード検索経由"] += 1
        else:
            media_cnt["不明"] += 1
    print()
    print("  ソース別:")
    for src, c in media_cnt.most_common():
        print(f"    {src}: {c}")

print()
print("=" * 60)
print("【6】keyword_stats と CSV の突き合わせ（CSV がある場合のみ）")
print("=" * 60)
if rows:
    registered_queries = set(r.get("検索クエリ", "") for r in rows if r.get("検索クエリ"))
    print(f"  登録に至ったユニーククエリ数 : {len(registered_queries)}")
    print(f"  ヒットあり・登録ゼロ          : {len(hits_no_ab_q)}")
    # 登録クエリのうち stats に記録があるもの
    in_stats = [q for q in registered_queries if q in queries]
    print(f"  登録クエリのうち stats にあるもの: {len(in_stats)}")
else:
    print("  CSV データなし → Render から取得後に再実行してください")
    print(f"  stats 内での A/B 登録実績クエリ数  : {len(has_ab_q)}")
    print(f"  stats 内でのヒットあり・登録ゼロ   : {len(hits_no_ab_q)}")
