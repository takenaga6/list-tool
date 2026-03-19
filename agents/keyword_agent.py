"""
キーワードエージェント
検索クエリの組み合わせを自動生成し、ヒット数を学習して高精度な順に並び替える
"""

import json
import os
import logging
import itertools
from datetime import datetime

logger = logging.getLogger(__name__)

KEYWORD_STATS_FILE = "output/keyword_stats.json"

# ===== キーワードマスタ =====

# PR媒体名（優先順）
PR_MEDIA = [
    "KENJA GLOBAL",
    "エコノミスト ビジネスクロニクル",
    "エコノミスト REC",
    "Newsweek WEB",
    "時代のニューウェーブ",
    "For JAPAN",
    "Leaders AWARD",
    "SMB Excellent AWARD",
    "B-PLUS",
    "SUPER CEO",
    "BS TIMES",
    "ベンチャー通信",
    "カンパニータンク",
    "サントリーウェルネスオンライン",
    "2026年健康経営認定",
    # 調査で発見した新規媒体
    "社長名鑑",
    "経営者プライム",
    "リーダーナビ",
    "Fanterview",
    "経営者通信",
    "先見経済",
    "企業と経営",
]

# 媒体と組み合わせる定型フレーズ
MEDIA_SUFFIXES = [
    "株式会社",
    "取材",
    "取り上げられました",
    "掲載",
    "代表取締役",
    "インタビュー",
    "紹介",
]

# ①健康・福利厚生系（高精度）
HEALTH_WELFARE = [
    "法定外福利厚生 株式会社",
    "健康経営優良法人",
    "健康経営 中小企業",
    "えるぼし認定 株式会社",
    "くるみん認定 株式会社",
    "ブライト500 株式会社",
    "酸素カプセル 福利厚生",
    "マッサージ 福利厚生 株式会社",
    "社員旅行 福利厚生 株式会社",
    "食事補助 福利厚生 株式会社",
    "スポーツジム 福利厚生 株式会社",
    "ウェルビーイング 経営 株式会社",
    "健康経営宣言 株式会社",
    "社員の健康 代表取締役",
    "従業員の健康 株式会社",
]

# ②経営者・投資シグナル系
CEO_SIGNALS = [
    "代表取締役 健康経営",
    "社長 健康経営 株式会社",
    "社長インタビュー 健康経営",
    "代表インタビュー 福利厚生",
    "自社ビル 株式会社 健康",
    "増収増益 健康経営",
    "社員50名 健康経営",
    "社員30名 福利厚生",
    "社員20名 健康経営",
]

# ③業種 × 健康経営（精度の高い組み合わせ）
INDUSTRY_HEALTH = [
    "IT企業 健康経営 福利厚生",
    "システム会社 健康経営",
    "コンサルティング 健康経営",
    "人材会社 健康経営",
    "不動産 健康経営 株式会社",
    "製造業 健康経営 福利厚生",
    "広告代理店 健康経営",
    "商社 健康経営 福利厚生",
]

# ④地域 × 健康経営（首都圏のみ）
REGION_HEALTH = [
    "東京 健康経営優良法人 株式会社",
    "横浜 健康経営 株式会社",
    "東京都 法定外福利厚生 株式会社",
]

# ⑤採用・認定シグナル（成長企業）
GROWTH_SIGNALS = [
    "中途採用 健康経営 株式会社",
    "正社員募集 健康経営",
    "健康経営 認定 取り組み",
    "健康経営 セミナー 登壇 代表",
    "健康経営 表彰 株式会社",
]

# ===== クエリ品質フィルタ閾値 =====
NG_SKIP_THRESHOLD = 0.9   # NG率90%以上のクエリは末尾に回す
MIN_RUNS_FOR_NG_CHECK = 3  # 最低3回実行後に判定
A_RATE_THRESHOLD = 0.05   # A率5%未満かつ5回以上実行済み → 降格


def generate_all_queries() -> list[str]:
    """
    全パターンの検索クエリを生成する。
    優先度順:
      1. 媒体名 × 定型フレーズ（最優先・A/Bランク発見率高）
      2. 健康・福利厚生系（高精度フレーズ）
      3. 経営者シグナル系
      4. 業種 × 健康経営
      5. 地域 × 健康経営
      6. 採用・認定シグナル
      7. 媒体名 × 大分類（汎用）
    """
    queries = []

    # 1. 媒体名 × 定型フレーズ（最優先）
    for media in PR_MEDIA:
        for suffix in MEDIA_SUFFIXES:
            queries.append(f"{media} {suffix}")

    # 2. 高精度フレーズ（健康・福利厚生）
    queries.extend(HEALTH_WELFARE)

    # 3. 経営者シグナル
    queries.extend(CEO_SIGNALS)

    # 4. 業種 × 健康経営
    queries.extend(INDUSTRY_HEALTH)

    # 5. 地域 × 健康経営
    queries.extend(REGION_HEALTH)

    # 6. 採用・認定シグナル
    queries.extend(GROWTH_SIGNALS)

    # 7. 媒体名 × 大分類（汎用）
    CATEGORY_L1 = ["株式会社", "健康経営", "代表取締役", "えるぼし認定", "法定外福利厚生"]
    for media in PR_MEDIA:
        for l1 in CATEGORY_L1:
            queries.append(f"{media} {l1}")

    # 重複除去・順序保持
    seen = set()
    unique = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique.append(q)

    return unique


def load_stats() -> dict:
    """過去のヒット統計を読み込む"""
    if os.path.exists(KEYWORD_STATS_FILE):
        try:
            with open(KEYWORD_STATS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_stats(stats: dict):
    """ヒット統計を保存する"""
    os.makedirs(os.path.dirname(KEYWORD_STATS_FILE), exist_ok=True)
    with open(KEYWORD_STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


def record_hit(query: str, hit_count: int):
    """検索クエリのヒット数を記録する"""
    stats = load_stats()

    if query not in stats:
        stats[query] = {
            "total_hits": 0, "runs": 0, "avg_hits": 0.0,
            "a_rank": 0, "b_rank": 0, "ng_count": 0,
            "ab_rate": 0.0, "ng_rate": 0.0,
            "last_run": ""
        }

    stats[query]["total_hits"] += hit_count
    stats[query]["runs"] += 1
    stats[query]["avg_hits"] = stats[query]["total_hits"] / stats[query]["runs"]
    stats[query]["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    save_stats(stats)


def record_ng(query: str):
    """クエリ経由でNGになった企業数を記録する"""
    stats = load_stats()
    if query not in stats:
        return
    stats[query]["ng_count"] = stats[query].get("ng_count", 0) + 1
    runs = stats[query].get("runs", 1)
    total_processed = stats[query].get("a_rank", 0) + stats[query].get("b_rank", 0) + stats[query]["ng_count"]
    if total_processed > 0:
        stats[query]["ng_rate"] = stats[query]["ng_count"] / total_processed
    save_stats(stats)


def record_rank_result(query: str, rank: str):
    """クエリ経由で発見したランク結果を記録する（A/Bランク精度向上用）"""
    stats = load_stats()
    if query not in stats:
        stats[query] = {
            "total_hits": 0, "runs": 0, "avg_hits": 0.0,
            "a_rank": 0, "b_rank": 0, "ng_count": 0,
            "ab_rate": 0.0, "a_rate": 0.0, "ng_rate": 0.0,
            "last_run": ""
        }
    if rank == "A":
        stats[query]["a_rank"] = stats[query].get("a_rank", 0) + 1
    elif rank == "B":
        stats[query]["b_rank"] = stats[query].get("b_rank", 0) + 1

    total_ab = stats[query]["a_rank"] + stats[query].get("b_rank", 0)
    total_processed = total_ab + stats[query].get("ng_count", 0)
    total_hits = max(stats[query]["total_hits"], 1)
    stats[query]["ab_rate"] = total_ab / total_hits
    # A率 = Aランク件数 ÷ 処理済み件数（NG含む）
    stats[query]["a_rate"] = stats[query]["a_rank"] / max(total_processed, 1)
    save_stats(stats)


def get_sorted_queries(custom_queries: list[str] = None) -> list[str]:
    """
    A/Bランク発見率が高い順に並び替えたクエリリストを返す。

    優先度ロジック:
      グループ0: カスタム（手動追加）クエリ
      グループ1: Aランク実績あり（多い順）
      グループ2: AB率実績あり（高い順）
      グループ3: 未実績クエリ（生成順を維持）
      グループ4: NG率が高い低品質クエリ（末尾）
    """
    all_queries = generate_all_queries()

    if custom_queries:
        for q in reversed(custom_queries):
            if q in all_queries:
                all_queries.remove(q)
            all_queries.insert(0, q)

    stats = load_stats()
    custom_set = set(custom_queries or [])

    def sort_key(q):
        if q in custom_set:
            return (0, 0, 0, 0)  # カスタムは最優先

        s = stats.get(q)
        if not s:
            return (3, 0, 0, 0)  # 未実績: 中優先（生成順）

        runs = s.get("runs", 0)
        a_rank = s.get("a_rank", 0)
        a_rate = s.get("a_rate", 0.0)
        ab_rate = s.get("ab_rate", 0.0)
        ng_rate = s.get("ng_rate", 0.0)
        avg_hits = s.get("avg_hits", 0.0)

        # NG率が高く実績十分 → 最末尾
        if runs >= MIN_RUNS_FOR_NG_CHECK and ng_rate >= NG_SKIP_THRESHOLD:
            return (5, ng_rate, 0, 0)

        # A率が低く実績十分 → 降格（末尾手前）
        if runs >= 5 and a_rate < A_RATE_THRESHOLD and a_rank == 0:
            return (4, -avg_hits, 0, 0)

        if avg_hits == 0:
            return (3, 0, 0, 0)  # ヒットなし実績: 未実績扱い

        if a_rank > 0:
            return (1, -a_rate, -a_rank, -ab_rate)  # Aランクあり: A率→件数順

        if ab_rate > 0:
            return (2, -ab_rate, -avg_hits, 0)  # B率あり

        return (3, -avg_hits, 0, 0)  # ヒットのみ

    return sorted(all_queries, key=sort_key)


def show_top_queries(n: int = 20):
    """A/Bランク発見率の高いクエリTOPを表示する"""
    stats = load_stats()
    if not stats:
        print("  まだ統計データがありません（初回実行後に蓄積されます）")
        return

    has_rank_data = any(s.get("a_rank", 0) + s.get("b_rank", 0) > 0 for s in stats.values())

    if has_rank_data:
        # A率 → Aランク件数の順でソート
        sorted_stats = sorted(
            stats.items(),
            key=lambda x: (-x[1].get("a_rate", 0), -x[1].get("a_rank", 0))
        )
        print(f"\n{'='*60}")
        print(f"  Aランク発見クエリ TOP{n}")
        print(f"{'='*60}")
        for i, (query, data) in enumerate(sorted_stats[:n], 1):
            a = data.get("a_rank", 0)
            b = data.get("b_rank", 0)
            a_rate = data.get("a_rate", 0.0)
            runs = data.get("runs", 0)
            print(f"  [{i:2d}] A:{a}件 B:{b}件 A率:{a_rate:.0%} ({runs}回) | {query}")
    else:
        sorted_stats = sorted(stats.items(), key=lambda x: -x[1]["avg_hits"])
        print(f"\n{'='*60}")
        print(f"  📊 高ヒットクエリ TOP{n}（ランク学習前）")
        print(f"{'='*60}")
        for i, (query, data) in enumerate(sorted_stats[:n], 1):
            print(f"  [{i:2d}] 平均{data['avg_hits']:.1f}件 | {query}")
    print()
