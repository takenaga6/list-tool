"""
キーワードエージェント
検索クエリの組み合わせを自動生成し、ヒット数を学習して高精度な順に並び替える

v2.0（Phase 3.3）:
- record系関数に source パラメータ追加（媒体次元）
- 後方互換マイグレーション（v1 → v2 自動変換）
- 媒体別統計関数 get_media_stats() 追加
"""

import json
import os
import sys as _sys
import logging
import itertools
from datetime import datetime

logger = logging.getLogger(__name__)

_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(_DIR, "..")
_sys.path.insert(0, _ROOT)
from config import OUTPUT_DIR as _OUTPUT_DIR
KEYWORD_STATS_FILE = os.path.join(_OUTPUT_DIR, "keyword_stats.json")

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
    # HubSpot n_1選択肢に対応する媒体（追加分）
    "サンデー毎日「会社の流儀」",
    "AERA「Business Report」",
    "週刊新潮「リーディングカンパニー」",
    "注目企業ONLINE",
    "オリジナルTHE 21「BUSINESS REPORT」",
    "週刊新潮「チャレンジカンパニー」",
    "週刊朝日「Challenge 20◯◯」",
    "週刊文春「会社の実力」",
    "幻冬舎メディアコンサルティング",
    "文芸社",
    "ダイヤモンド（自費出版）",
    "日経クロスメディア",
    "私のカクゴ",
    "Newsweek CHALLENGING INNOVATOR",
    "QualitasB-plus",
    "月刊企業情報誌『ルーツ』",
    "月刊企業情報誌「Anchor」",
    "月刊企業情報誌「Masters」",
    "月刊企業情報誌「CENTURY」",
    "NewsPicks「PR記事」",
    "東京MXビジネス番組",
    "異業種ネット",
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

# ⑤採用・認定シグナル（成長企業）
GROWTH_SIGNALS = [
    "中途採用 健康経営 株式会社",
    "正社員募集 健康経営",
    "健康経営 認定 取り組み",
    "健康経営 セミナー 登壇 代表",
    "健康経営 表彰 株式会社",
]

# ⑥採用媒体 × 福利厚生・健康経営
RECRUIT_MEDIA = [
    "doda",
    "マイナビ転職",
    "en転職",
    "type転職",
    "Indeed",
    "engage",
    "ベネフィッツ",
    "リクナビNEXT",
    "wantedly",
    "Green",
]

RECRUIT_SUFFIXES = [
    "福利厚生充実 株式会社",
    "福利厚生 マッサージ 株式会社",
    "福利厚生 健康 株式会社",
    "健康経営 株式会社",
    "健康経営優良法人 株式会社",
    "法定外福利厚生 株式会社",
    "社員の健康 株式会社",
]

# ===== クエリ品質フィルタ閾値 =====
NG_SKIP_THRESHOLD = 0.9   # NG率90%以上のクエリは末尾に回す
MIN_RUNS_FOR_NG_CHECK = 3  # 最低3回実行後に判定
A_RATE_THRESHOLD = 0.05   # A率5%未満かつ5回以上実行済み → 降格

# ===== Phase 6.7B: 履歴ない媒体の初回試行用・主要5都道府県 =====
PRIORITY_PREFECTURES = ["東京都", "大阪府", "愛知県", "神奈川県", "福岡県"]

# ===== Phase 3.3 学習システム拡張 =====
STATS_VERSION = "2.0"
DEFAULT_SOURCE = "search"  # source未指定時のデフォルト


def is_dead_query(stats: dict) -> bool:
    """死んだクエリ（除外すべき）かどうか判定。

    判定基準:
    - 試行3回以上 かつ ヒット数0 → 死んでいる
    - 試行5回以上 かつ ヒット率5%未満 → 効率悪すぎ
    """
    runs = stats.get("runs", 0)
    total_hits = stats.get("total_hits", 0)
    if runs >= 3 and total_hits == 0:
        return True
    if runs >= 5 and total_hits / runs < 0.05:
        return True
    return False


def has_media_hit_history(media: str, stats: dict) -> bool:
    """指定媒体について、過去にヒット実績があるかを判定。

    Args:
        media: 媒体名（例: "B-PLUS"）
        stats: load_stats() の queries 部分

    Returns:
        True: 過去に1件でもヒットしたクエリがある
        False: ヒット実績ゼロ（または履歴なし）
    """
    for query, query_stats in stats.items():
        if media in query and query_stats.get("total_hits", 0) > 0:
            return True
    return False


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

    # 5. 採用・認定シグナル
    queries.extend(GROWTH_SIGNALS)

    # 7. 媒体名 × 大分類（汎用）
    CATEGORY_L1 = ["株式会社", "健康経営", "代表取締役", "えるぼし認定", "法定外福利厚生"]
    for media in PR_MEDIA:
        for l1 in CATEGORY_L1:
            queries.append(f"{media} {l1}")

    # 8. 採用媒体 × 福利厚生・健康経営
    for media in RECRUIT_MEDIA:
        for suffix in RECRUIT_SUFFIXES:
            queries.append(f"{media} {suffix}")

    # 9. 地域 × 媒体名（S1-B検索型）
    # Phase 6.7B: 媒体ごとにヒット履歴を確認し、履歴なしは主要5都道府県のみ生成
    try:
        from config import SEARCH_REGIONS
        _stats_for_media = load_stats().get("queries", {})
        for media in PR_MEDIA:
            if has_media_hit_history(media, _stats_for_media):
                # ヒット実績あり → 全47都道府県
                for region in SEARCH_REGIONS:
                    queries.append(f"{media} {region} 株式会社")
            else:
                # 履歴なし → 主要5都道府県のみ（初回試行コスト削減）
                for region in PRIORITY_PREFECTURES:
                    queries.append(f"{media} {region} 株式会社")
    except ImportError:
        pass

    # 10. 地域 × 健康経営（47都道府県）
    try:
        from config import SEARCH_REGIONS
        REGION_SUFFIXES = ["健康経営 株式会社", "健康経営優良法人", "法定外福利厚生 株式会社", "福利厚生 充実 株式会社"]
        for region in SEARCH_REGIONS:
            for suffix in REGION_SUFFIXES:
                queries.append(f"{region} {suffix}")
    except ImportError:
        pass

    # 重複除去・順序保持
    seen = set()
    unique = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique.append(q)

    return unique


def _migrate_v1_to_v2(raw: dict) -> dict:
    """v1形式（フラット）をv2形式（_version + queries）に変換する.

    v1形式の例:
      {"クエリA": {"total_hits": 10, "runs": 5, ...}}

    v2形式の例:
      {"_version": "2.0", "queries": {"クエリA": {..., "by_source": {}}}}
    """
    # 既にv2形式なら何もしない
    if isinstance(raw, dict) and raw.get("_version") == STATS_VERSION:
        return raw

    # 空のdict → v2形式の空データを返す
    if not raw:
        return {"_version": STATS_VERSION, "queries": {}}

    # v1形式を v2形式に変換
    queries_v2 = {}
    for key, value in raw.items():
        if not isinstance(value, dict):
            continue  # 不正データはスキップ
        # v1のクエリデータをv2にコピー
        queries_v2[key] = dict(value)
        # by_source フィールドを追加（v1には存在しないので空）
        if "by_source" not in queries_v2[key]:
            queries_v2[key]["by_source"] = {}

    return {"_version": STATS_VERSION, "queries": queries_v2}


def load_stats() -> dict:
    """過去のヒット統計を読み込む（v1/v2両対応）.

    Returns:
        v2形式の dict: {"_version": "2.0", "queries": {...}}
    """
    if os.path.exists(KEYWORD_STATS_FILE):
        try:
            with open(KEYWORD_STATS_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
                # マイグレーション（v1 → v2）
                return _migrate_v1_to_v2(raw)
        except Exception:
            pass
    # ファイルなし → v2形式の空データを返す
    return {"_version": STATS_VERSION, "queries": {}}


def save_stats(stats: dict):
    """ヒット統計を保存する（v2形式）."""
    os.makedirs(os.path.dirname(KEYWORD_STATS_FILE), exist_ok=True)
    # version保証
    if "_version" not in stats:
        stats["_version"] = STATS_VERSION
    if "queries" not in stats:
        stats["queries"] = {}
    with open(KEYWORD_STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


def _get_query_data(stats: dict, query: str) -> dict:
    """v2形式の stats から指定クエリのデータを取得（なければ初期化）."""
    if "queries" not in stats:
        stats["queries"] = {}
    if query not in stats["queries"]:
        stats["queries"][query] = {
            "total_hits": 0, "runs": 0, "avg_hits": 0.0,
            "a_rank": 0, "b_rank": 0, "ng_count": 0,
            "ab_rate": 0.0, "a_rate": 0.0, "ng_rate": 0.0,
            "last_run": "",
            "by_source": {},
        }
    # by_source が古いデータでない場合の保険
    if "by_source" not in stats["queries"][query]:
        stats["queries"][query]["by_source"] = {}
    return stats["queries"][query]


def _get_source_data(query_data: dict, source: str) -> dict:
    """指定クエリの source 別データを取得（なければ初期化）."""
    if source not in query_data["by_source"]:
        query_data["by_source"][source] = {
            "hits": 0, "runs": 0, "a_rank": 0, "b_rank": 0, "ng_count": 0,
        }
    return query_data["by_source"][source]


def record_hit(query: str, hit_count: int, source: str = None):
    """検索クエリのヒット数を記録する.

    Args:
        query: 検索クエリ
        hit_count: ヒット件数
        source: データソース（"search:1週間" / "list_page:kenko-keiei.jp" 等）
                None の場合は DEFAULT_SOURCE("search") を使用
    """
    if source is None:
        source = DEFAULT_SOURCE
    stats = load_stats()
    qd = _get_query_data(stats, query)

    # クエリ全体の集計（既存と同じ）
    qd["total_hits"] += hit_count
    qd["runs"] += 1
    qd["avg_hits"] = qd["total_hits"] / qd["runs"]
    qd["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    # source別の集計（新規）
    sd = _get_source_data(qd, source)
    sd["hits"] += hit_count
    sd["runs"] += 1

    save_stats(stats)


def record_ng(query: str, source: str = None):
    """クエリ経由でNGになった企業数を記録する.

    Args:
        query: 検索クエリ
        source: データソース
    """
    if source is None:
        source = DEFAULT_SOURCE
    stats = load_stats()
    if "queries" not in stats or query not in stats["queries"]:
        return
    qd = stats["queries"][query]

    # クエリ全体（既存と同じ）
    qd["ng_count"] = qd.get("ng_count", 0) + 1
    total_processed = qd.get("a_rank", 0) + qd.get("b_rank", 0) + qd["ng_count"]
    if total_processed > 0:
        qd["ng_rate"] = qd["ng_count"] / total_processed

    # source別（新規）
    if "by_source" not in qd:
        qd["by_source"] = {}
    sd = _get_source_data(qd, source)
    sd["ng_count"] += 1

    save_stats(stats)


def record_rank_result(query: str, rank: str, source: str = None):
    """クエリ経由で発見したランク結果を記録する（A/Bランク精度向上用）.

    Args:
        query: 検索クエリ
        rank: "A" / "B" / "C" / "NG"
        source: データソース
    """
    if source is None:
        source = DEFAULT_SOURCE
    stats = load_stats()
    qd = _get_query_data(stats, query)

    # クエリ全体（既存と同じ）
    if rank == "A":
        qd["a_rank"] = qd.get("a_rank", 0) + 1
    elif rank == "B":
        qd["b_rank"] = qd.get("b_rank", 0) + 1

    total_ab = qd["a_rank"] + qd.get("b_rank", 0)
    total_processed = total_ab + qd.get("ng_count", 0)
    total_hits = max(qd["total_hits"], 1)
    qd["ab_rate"] = total_ab / total_hits
    qd["a_rate"] = qd["a_rank"] / max(total_processed, 1)

    # source別（新規）
    sd = _get_source_data(qd, source)
    if rank == "A":
        sd["a_rank"] += 1
    elif rank == "B":
        sd["b_rank"] += 1

    save_stats(stats)


def get_sorted_queries(
    custom_queries: list[str] = None,
    worker_offset: int = 0,
    exclude_dead: bool = True,
) -> list[str]:
    """
    A/Bランク発見率が高い順に並び替えたクエリリストを返す。

    優先度ロジック:
      グループ0: カスタム（手動追加）クエリ
      グループ1: Aランク実績あり（多い順）
      グループ2: AB率実績あり（高い順）
      グループ3: 未実績クエリ（生成順を維持）
      グループ4: NG率が高い低品質クエリ（末尾）

    exclude_dead:
      True（デフォルト）: 死んだクエリ（runs>=3でhits=0等）を除外する。
      False: 全クエリを返す（後方互換・デバッグ用）。
      カスタムクエリは exclude_dead=True でも除外されない。

    worker_offset:
      複数人が同時に使う場合、各グループ内の順番をワーカーごとにシャッフルする。
      同じ品質分布を保ちつつ、検索クエリの重複を避けられる。
      0 = シャッフルなし（デフォルト）
    """
    import random as _random

    all_queries = generate_all_queries()

    if custom_queries:
        for q in reversed(custom_queries):
            if q in all_queries:
                all_queries.remove(q)
            all_queries.insert(0, q)

    stats_v2 = load_stats()
    stats = stats_v2.get("queries", {})  # v2形式から queries 部分を取り出す
    custom_set = set(custom_queries or [])

    # Phase 6.7A: 死んだクエリを除外（カスタムクエリは対象外）
    if exclude_dead:
        filtered = []
        excluded_count = 0
        for q in all_queries:
            if q in custom_set:
                filtered.append(q)
            elif not is_dead_query(stats.get(q, {})):
                filtered.append(q)
            else:
                excluded_count += 1
        all_queries = filtered
        if excluded_count > 0:
            logger.info(
                f"[Phase 6.7A] 死んだクエリを{excluded_count}件除外（残り{len(all_queries)}件）"
            )

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

    sorted_queries = sorted(all_queries, key=sort_key)

    # worker_offsetが指定されている場合、各優先度グループ内をシャッフル
    # → 品質分布は保ちつつ、複数ワーカーが同じクエリに集中するのを防ぐ
    if worker_offset != 0:
        from itertools import groupby
        result = []
        # sort_keyの第1要素（グループ番号）でグループ化
        for _group_id, group_items in groupby(sorted_queries, key=lambda q: sort_key(q)[0]):
            group = list(group_items)
            rng = _random.Random(worker_offset + hash(str(_group_id)))
            rng.shuffle(group)
            result.extend(group)
        return result

    return sorted_queries


def show_top_queries(n: int = 20):
    """A/Bランク発見率の高いクエリTOPを表示する."""
    stats_v2 = load_stats()
    stats = stats_v2.get("queries", {})
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
        sorted_stats = sorted(stats.items(), key=lambda x: -x[1].get("avg_hits", 0))
        print(f"\n{'='*60}")
        print(f"  📊 高ヒットクエリ TOP{n}（ランク学習前）")
        print(f"{'='*60}")
        for i, (query, data) in enumerate(sorted_stats[:n], 1):
            print(f"  [{i:2d}] 平均{data.get('avg_hits', 0):.1f}件 | {query}")
    print()


def get_media_stats() -> list[dict]:
    """媒体（source）別の統計を集計して返す（Phase 3.3 新機能）.

    全クエリの by_source データを集計し、各 source ごとに：
      - 総ヒット数 / 総実行数 / 総NG数 / Aランク数 / Bランク数
      - A率（Aランク数 / 処理済み件数）
      - NG率
    を計算する。

    Returns:
        list[dict]: 各 source の統計（A率降順）
            例: [{"source": "list_page:kenko-keiei.jp", "total_hits": 100,
                  "runs": 50, "a_rank": 5, "b_rank": 10, "ng_count": 20,
                  "a_rate": 0.14, "ng_rate": 0.57}, ...]
    """
    stats_v2 = load_stats()
    queries = stats_v2.get("queries", {})

    # source別に集計
    media_agg: dict[str, dict] = {}
    for query, qd in queries.items():
        by_source = qd.get("by_source", {})
        for source, sd in by_source.items():
            if source not in media_agg:
                media_agg[source] = {
                    "source": source,
                    "total_hits": 0, "runs": 0,
                    "a_rank": 0, "b_rank": 0, "ng_count": 0,
                    "query_count": 0,  # この source を使ったクエリ数
                }
            ms = media_agg[source]
            ms["total_hits"] += sd.get("hits", 0)
            ms["runs"] += sd.get("runs", 0)
            ms["a_rank"] += sd.get("a_rank", 0)
            ms["b_rank"] += sd.get("b_rank", 0)
            ms["ng_count"] += sd.get("ng_count", 0)
            ms["query_count"] += 1

    # A率・NG率を計算
    result = []
    for source, ms in media_agg.items():
        total_processed = ms["a_rank"] + ms["b_rank"] + ms["ng_count"]
        ms["a_rate"] = ms["a_rank"] / max(total_processed, 1)
        ms["ng_rate"] = ms["ng_count"] / max(total_processed, 1)
        result.append(ms)

    # A率降順、同率ならAランク数降順
    result.sort(key=lambda x: (-x["a_rate"], -x["a_rank"]))
    return result


def show_media_stats(n: int = 20):
    """媒体別統計を表示する（Phase 3.3 新機能）."""
    media_stats = get_media_stats()
    if not media_stats:
        print("  まだ媒体別統計データがありません（初回実行後に蓄積されます）")
        return

    print(f"\n{'='*70}")
    print(f"  📡 媒体別 精度ランキング TOP{n}")
    print(f"{'='*70}")
    print(f"  {'順':>3} {'A率':>7} {'A':>4} {'B':>4} {'NG':>5} {'実行':>5} {'クエリ数':>6}  {'media'}")
    print(f"  {'-'*3} {'-'*7} {'-'*4} {'-'*4} {'-'*5} {'-'*5} {'-'*6}  {'-'*30}")
    for i, ms in enumerate(media_stats[:n], 1):
        print(
            f"  [{i:2d}] {ms['a_rate']:>6.1%} "
            f"{ms['a_rank']:>4d} {ms['b_rank']:>4d} {ms['ng_count']:>5d} "
            f"{ms['runs']:>5d} {ms['query_count']:>6d}  {ms['source']}"
        )
    print()
