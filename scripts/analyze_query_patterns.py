"""クエリをテンプレ・媒体・都道府県の次元で集計し、A/Bを生むパターンを特定する。

2階（A/Bを増やす本命）の「勝ちテンプレ横展開」のための読み取り専用分析。
パイプラインには一切触れない（get_sorted_queries 等を変更しない）ので、
走行観察期間中でも安全に実行できる。

使い方:
    python scripts/analyze_query_patterns.py                    # DATA_DIR/data/output から自動探索
    python scripts/analyze_query_patterns.py path/to/stats.json
"""
import json
import os
import sys
import collections

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_DIR, ".."))

try:
    from agents.keyword_agent import PR_MEDIA
    from config import SEARCH_REGIONS
except Exception:
    PR_MEDIA, SEARCH_REGIONS = [], []


def classify(query: str) -> str:
    """クエリをテンプレ家系に分類する。"""
    if query.startswith("[リストページ]"):
        return "list_page（リスト取得）"
    if "Voice Report" in query or "ボイスレポート" in query or "アクサ" in query:
        return "S2: アクサ Voice Report"
    if "KENCO" in query or "大同生命" in query:
        return "S2: 大同生命 KENCO"
    # 業種 × 健康経営優良法人 × 県
    if "健康経営優良法人" in query and any(r in query for r in SEARCH_REGIONS) \
            and any(ind in query for ind in ("IT企業", "コンサルティング", "製造業")):
        return "業種×健康経営優良法人×県"
    # 媒体名で始まる
    for m in PR_MEDIA:
        if query.startswith(m):
            return f"媒体: {m}"
    # 県 × サフィックス
    if any(query.startswith(r) for r in SEARCH_REGIONS):
        return "県×健康経営/福利厚生"
    return "その他（高精度フレーズ等）"


def region_of(query: str) -> str:
    for r in SEARCH_REGIONS:
        if r in query:
            return r
    return "(県なし)"


def main():
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        cands = []
        if os.environ.get("DATA_DIR"):
            cands.append(os.path.join(os.environ["DATA_DIR"], "keyword_stats.json"))
        cands += ["/data/keyword_stats.json", "output/keyword_stats.json"]
        path = next((p for p in cands if os.path.exists(p)), None)
    if not path or not os.path.exists(path):
        print(f"[ERROR] stats ファイルが見つからない: {path}")
        sys.exit(1)

    print(f"読込ファイル: {path}\n")
    raw = json.load(open(path, encoding="utf-8"))
    q = raw.get("queries", raw)

    # テンプレ家系別に集計
    fam = collections.defaultdict(lambda: {"A": 0, "B": 0, "NG": 0, "hits": 0, "n": 0, "ab_q": 0})
    region_ab = collections.Counter()  # A/Bを生んだ県
    for query, s in q.items():
        a = s.get("a_rank", 0); b = s.get("b_rank", 0)
        f = fam[classify(query)]
        f["A"] += a; f["B"] += b
        f["NG"] += s.get("ng_count", 0)
        f["hits"] += s.get("total_hits", 0)
        f["n"] += 1
        if a + b > 0:
            f["ab_q"] += 1
            region_ab[region_of(query)] += a + b

    print("=== テンプレ家系別の成績（A/B降順）===")
    print(f"  {'A':>4} {'B':>4} {'NG':>6} {'AB出すクエリ':>12} {'クエリ数':>8}  家系")
    for name, f in sorted(fam.items(), key=lambda kv: -(kv[1]['A'] + kv[1]['B'])):
        print(f"  {f['A']:>4} {f['B']:>4} {f['NG']:>6} "
              f"{f['ab_q']:>12} {f['n']:>8}  {name}")

    print("\n=== A/Bを生んだ県 TOP15（横展開で厚くする候補）===")
    for region, ab in region_ab.most_common(15):
        print(f"  A/B={ab:>3}  {region}")

    print("\n=== A/B生産クエリ TOP25（具体的な勝ち種）===")
    rows = []
    for query, s in q.items():
        ab = s.get("a_rank", 0) + s.get("b_rank", 0)
        if ab > 0:
            rows.append((ab, s.get("a_rank", 0), s.get("b_rank", 0), s.get("ng_count", 0), query))
    for ab, a, b, ng, query in sorted(rows, reverse=True)[:25]:
        print(f"  A{a} B{b} NG{ng}  {query}")


if __name__ == "__main__":
    main()
