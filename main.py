#!/usr/bin/env python3
"""
企業リストアップツール
Google検索 → スクレイピング → ランク判定 → HubSpot登録
"""

import csv
import json
import logging
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from config import (
    HUBSPOT_TOKEN,
    LOG_FILE,
    MAX_RESULTS_PER_QUERY,
    MAX_WORKERS,
    NG_LIST_FILE,
    RESULTS_FILE,
    RESULTS_WITH_QUERY_FILE,
    TIME_PERIOD_TBS,
    TIME_PERIODS,
    OUTPUT_DIR,
    EXCLUDE_LIST_CSV,
    S1_MEDIA_LIST_URLS,
    S2_MEDIA_LIST_URLS,
    MEDIA_LIST_URLS,
    MIN_REGISTER_SIGNALS,
    PROCESSED_URLS_FILE,
    is_excluded_company,
    add_to_excluded_companies,
)
from agents.search_agent import extract_domain, search_google
from agents.scraper_agent import scrape_company_info, find_media_article_url
from agents.rank_agent import evaluate_rank, pre_screen
from agents.hubspot_agent import HubSpotAgent
from agents.keyword_agent import get_sorted_queries, record_hit, record_ng, record_rank_result, show_top_queries
from agents.list_page_agent import scrape_company_list_page, scrape_s1_media, scrape_s2_media

# ─── S1/S2対応リスト取得ヘルパー ──────────────────────────────────────────
def _scrape_list_with_signal(list_url: str, max_companies: int = 200) -> list[dict]:
    """
    URLがS1/S2媒体かどうかを判定して適切なスクレイパーを呼び出す。
    S2媒体 → scrape_s2_media (source_confirmed_s2=True)
    S1媒体 → scrape_s1_media (source_confirmed_s1=True)
    その他  → scrape_company_list_page (フラグなし)
    """
    from config import S2_MEDIA_LIST_URLS, S1_MEDIA_LIST_URLS
    if any(list_url.startswith(u) for u in S2_MEDIA_LIST_URLS):
        return scrape_s2_media(list_url, max_companies)
    elif any(list_url.startswith(u) for u in S1_MEDIA_LIST_URLS):
        return scrape_s1_media(list_url, max_companies)
    else:
        return scrape_company_list_page(list_url, max_companies)

# ログ設定
os.makedirs(OUTPUT_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


class MultiDictWriter:
    """複数の csv.DictWriter に同じ行を書き出す。"""

    def __init__(self, *writers):
        self._writers = writers

    def writerow(self, row: dict):
        for w in self._writers:
            try:
                w.writerow(row)
            except Exception:
                # 個別の writer は extrasaction="ignore" で無視しておくのが前提
                pass


# =============================================================
# UI ヘルパー
# =============================================================

def print_header():
    print("\n" + "=" * 60)
    print("  企業リストアップツール")
    print("  Google検索 → 企業情報取得 → HubSpot自動登録")
    print("=" * 60)


def select_register_mode() -> bool:
    """登録前確認モードを選択する。True=確認あり、False=自動登録"""
    print("\n登録方式を選択してください")
    print("-" * 40)
    print("  1: 確認後に登録（推奨）  ← 一覧を見てからHubSpotに登録")
    print("  2: 自動登録（従来通り）  ← 全件を自動でHubSpotに登録")
    print("-" * 40)
    while True:
        choice = input("番号を入力 > ").strip()
        if choice == "1":
            print("確認モードで実行します\n")
            return True
        if choice == "2":
            print("自動登録モードで実行します\n")
            return False
        print("1 または 2 を入力してください")


def print_ng_suggestions(session_exclusions: list[dict]) -> None:
    """
    セッション中の除外企業を分析し、NGパターンをサジェスト＆自動学習する。

    - 同一ドメインが2回以上除外 → exclude_list.csv に自動追加
    - 理由別集計・会社名パターンをターミナルに表示
    """
    from config import add_to_exclude_csv, load_exclude_list_csv

    if not session_exclusions:
        return

    print("\n" + "=" * 60)
    print("  📊 精度改善サマリー（今セッションの除外分析）")
    print("=" * 60)

    # 理由別集計
    reason_counts: dict[str, int] = {}
    domain_reasons: dict[str, list[str]] = {}
    name_patterns: list[str] = []

    for ex in session_exclusions:
        reason = ex.get("reason", "不明")
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
        domain = ex.get("domain", "")
        if domain:
            domain_reasons.setdefault(domain, []).append(reason)
        name = ex.get("name", "")
        if name:
            name_patterns.append(name)

    # 理由別サマリー
    print("  除外理由の内訳:")
    for reason, cnt in sorted(reason_counts.items(), key=lambda x: -x[1]):
        print(f"    {reason}: {cnt}件")

    # 2回以上除外されたドメイン → 自動でexclude_list追加
    already_excluded = load_exclude_list_csv()
    auto_added = []
    for domain, reasons in domain_reasons.items():
        if len(reasons) >= 2 and domain not in already_excluded:
            add_to_exclude_csv(domain, f"自動学習: {reasons[0]}")
            auto_added.append(domain)

    if auto_added:
        print(f"\n  自動除外リスト追加（2回以上除外されたドメイン）:")
        for d in auto_added:
            print(f"    + {d}")

    # 会社名パターンのサジェスト
    pattern_hits: dict[str, int] = {}
    check_patterns = [
        "ホールディングス", "Holdings", "グループ", "フランチャイズ",
        "協会", "財団", "学校法人", "医療法人", "社会福祉法人",
    ]
    for name in name_patterns:
        for pat in check_patterns:
            if pat in name:
                pattern_hits[pat] = pattern_hits.get(pat, 0) + 1

    if pattern_hits:
        print("\n  会社名パターン（config.py の NG チェック追加を検討）:")
        for pat, cnt in sorted(pattern_hits.items(), key=lambda x: -x[1]):
            print(f"    「{pat}」含む企業が {cnt}件 除外されました")

    print("=" * 60)


def review_and_register(
    pending: list[dict],
    hubspot: "HubSpotAgent",
    results_writer: "csv.DictWriter",
    processed_domains: set,
    session_exclusions: list | None = None,
) -> int:
    """
    収集した登録候補を一覧表示し、ユーザーの承認を経てHubSpotに登録する。

    Returns:
        登録成功件数
    """
    from config import add_to_exclude_csv
    from urllib.parse import urlparse

    if not pending:
        return 0

    print("\n" + "=" * 60)
    print(f"  登録候補一覧 ({len(pending)}社)")
    print("=" * 60)
    for i, item in enumerate(pending, 1):
        info = item["company_info"]
        rank = item["rank_result"]["rank"]
        score = item["rank_result"]["score"]
        conf = info.get("_confidence", "-")
        name = info.get("company_name", "（名称不明）")
        url = info.get("company_url", "")
        reasons = ", ".join(item["rank_result"].get("reasons", [])[:2])
        phone  = info.get("phone", "") or "－"
        addr   = info.get("address", "") or "－"
        emp    = info.get("employee_count", "") or "－"
        ind    = info.get("industry", "") or "－"
        rep    = info.get("representative", "") or "－"
        print(f"  {i:2}. [{rank}({score}点) 信頼度:{conf}/4] {name}")
        print(f"       URL : {url}")
        print(f"       TEL : {phone}  代表: {rep}")
        print(f"       住所: {addr}")
        print(f"       人数: {emp}名  業種: {ind}")
        print(f"       理由: {reasons}")
    print("-" * 60)
    print("  操作: y=全件登録 / n=全件スキップ / 番号=個別選択(例:1,3)")
    print("        x番号=除外リストへ追加(例:x2)  番号 + x = 組み合わせ可")
    print("-" * 60)

    choice = input("入力 > ").strip().lower()

    # 除外指定を先に処理（x番号: 除外リスト追加 + NG理由を聞く）
    exclude_indices = set()
    for token in choice.replace(",", " ").split():
        if token.startswith("x"):
            try:
                idx = int(token[1:]) - 1
                if 0 <= idx < len(pending):
                    exclude_indices.add(idx)
                    item = pending[idx]
                    info = item["company_info"]
                    domain = urlparse(info.get("company_url", "")).netloc.replace("www.", "")
                    name = info.get("company_name", "")
                    # 除外理由の分類
                    print(f"  [{name}] 除外理由: m=メディア/s=規模大/t=規模小/i=業種/o=その他 > ", end="")
                    reason_code = input().strip().lower()
                    reason_map = {"m": "メディア・ポータル", "s": "規模NG（大企業）", "t": "規模NG（小規模）", "i": "業種NG", "o": "その他"}
                    reason = reason_map.get(reason_code, "承認時除外")
                    if domain:
                        add_to_exclude_csv(domain, reason)
                        print(f"  除外リストに追加: {domain} ({reason})")
                    # セッション除外ログに追記（精度改善サマリー用）
                    if session_exclusions is not None:
                        session_exclusions.append({
                            "name": name,
                            "domain": domain,
                            "reason": reason,
                            "source": item.get("company_info", {}).get("notes", ""),
                        })
                    # クエリのNG記録（学習）
                    from agents.keyword_agent import record_ng
                    record_ng(item.get("search_query", ""))
            except ValueError:
                pass

    # 承認対象を決定
    if choice == "y":
        approved = [i for i in range(len(pending)) if i not in exclude_indices]
    elif choice == "n":
        # 全件スキップの場合もNGをクエリ学習に記録
        from agents.keyword_agent import record_ng
        for item in pending:
            record_ng(item.get("search_query", ""))
        print("  スキップしました")
        return 0
    else:
        approved = []
        for token in choice.replace(",", " ").split():
            if token.startswith("x"):
                continue
            try:
                idx = int(token) - 1
                if 0 <= idx < len(pending) and idx not in exclude_indices:
                    approved.append(idx)
            except ValueError:
                pass
        # 選択されなかった企業もNG記録
        from agents.keyword_agent import record_ng
        approved_set = set(approved)
        for i, item in enumerate(pending):
            if i not in approved_set and i not in exclude_indices:
                record_ng(item.get("search_query", ""))

    success_count = 0
    for idx in approved:
        item = pending[idx]
        info = item["company_info"]
        rank = item["rank_result"]["rank"]
        name = info.get("company_name", "")
        company_domain = urlparse(info.get("company_url", "")).netloc.replace("www.", "")

        # HubSpot重複チェック
        if hubspot.check_duplicate(company_name=name, domain=company_domain):
            add_to_excluded_companies(name, "HubSpot重複")
            print(f"  重複→スキップ: {name}")
            continue

        info["rank"] = rank  # HubSpot a_12 書き込み用
        if hubspot.register_company(info):
            print(f"  [{rank}] 登録: {name}")
            write_result_row({
                "日時":    datetime.now().strftime("%Y-%m-%d %H:%M"),
                "ランク":   rank,
                "会社名":   info["company_name"],
                "企業URL":  info["company_url"],
                "代表氏名":  info["representative"],
                "電話番号":  info["phone"],
                "郵便番号":  info.get("zip_code", ""),
                "都道府県":  info.get("prefecture", ""),
                "所在地":   info["address"],
                "業種":    info.get("industry", ""),
                "従業員数":  info.get("employee_count", ""),
                "備考":    info.get("notes", ""),
                "元URL":   info.get("source_url", ""),
                "検索クエリ": item.get("search_query", ""),
            })
            success_count += 1

    print(f"  → {success_count}社を登録しました")
    return success_count


def select_time_period() -> list[tuple[str, str]]:
    """期間選択（複数可）"""
    print("\n📅 検索期間を選択してください（複数可、カンマ区切り例: 1,2,3）")
    print("-" * 40)
    for key, label in TIME_PERIODS.items():
        print(f"  {key}: {label}")
    print("-" * 40)

    while True:
        choice = input("番号を入力 > ").strip()
        keys = [k.strip() for k in choice.replace("、", ",").split(",")]
        valid = [k for k in keys if k in TIME_PERIODS]
        if valid:
            selected = []
            for k in valid:
                label = TIME_PERIODS[k]
                tbs = TIME_PERIOD_TBS[label]
                selected.append((label, tbs))
            labels = "、".join(l for l, _ in selected)
            print(f"✅ 選択: {labels}\n")
            return selected
        print("❌ 正しい番号を入力してください")


def input_keywords() -> tuple[list[str], bool]:
    """
    キーワード入力モードを選択する

    Returns:
        (keywords, is_auto_mode)
        is_auto_mode=True のとき keywords は手動追加分のみ（自動生成と合算される）
    """
    print("\n🔍 検索モードを選択してください")
    print("-" * 40)
    print("  1: 自動モード（キーワード自動生成＋学習）※おすすめ")
    print("  2: 手動モード（キーワードを自分で入力）")
    print("-" * 40)

    while True:
        mode = input("番号を入力 > ").strip()
        if mode in ("1", "2"):
            break
        print("❌ 1 または 2 を入力してください")

    if mode == "1":
        show_top_queries(10)
        print("▼ 追加したいキーワードがあれば入力（不要ならそのままEnter）")
        custom = []
        while True:
            kw = input(f"  追加キーワード {len(custom) + 1}: ").strip()
            if not kw:
                break
            custom.append(kw)
            print(f"  ✅ 追加: {kw}")
        keywords, is_auto = custom, True
    else:
        print("\n【例】")
        print("  KENJA GLOBAL 株式会社")
        print("  健康経営 法定外福利厚生 株式会社")
        print("空白のままEnterで入力終了\n")
        keywords = []
        while True:
            kw = input(f"  キーワード {len(keywords) + 1}: ").strip()
            if not kw:
                if not keywords:
                    print("  ⚠️ 少なくとも1つ入力してください")
                    continue
                break
            keywords.append(kw)
            print(f"  ✅ 追加: {kw}")
        is_auto = False

    # リストページURL（任意・両モード共通）
    print("\n📋 リストページURLがあれば入力（不要ならそのままEnter）")
    print("   例: https://kenko-keiei.jp/houjin_list/  ※PDF/Word/Excel対応")
    list_urls = []
    while True:
        url = input(f"  リストURL {len(list_urls) + 1}: ").strip()
        if not url:
            break
        list_urls.append(url)
        print(f"  ✅ 追加: {url}")

    return keywords, is_auto, list_urls or None


def input_target_count() -> int:
    """目標件数入力"""
    while True:
        val = input("\n🎯 目標登録件数を入力してください (デフォルト: 50): ").strip()
        if not val:
            return 50
        if val.isdigit() and int(val) > 0:
            return int(val)
        print("❌ 正の整数を入力してください")


def print_settings(periods: list, keywords: list, target: int):
    """設定確認表示"""
    print("\n" + "=" * 60)
    print("⚙️  実行設定")
    print("=" * 60)
    period_labels = "、".join(l for l, _ in periods)
    print(f"  期間    : {period_labels}")
    print(f"  目標件数: {target}件")
    print(f"  並列数  : {MAX_WORKERS}")
    print(f"  キーワード ({len(keywords)}件):")
    for i, kw in enumerate(keywords, 1):
        print(f"    {i}. {kw}")
    print("=" * 60)
    input("\n▶ Enterキーで開始します...")


def print_progress(stats: dict, start_time: float):
    """進捗表示"""
    elapsed = time.time() - start_time
    rate = stats["success"] / (elapsed / 3600) if elapsed > 0 else 0
    elapsed_min = elapsed / 60
    pending = stats.get("pending", 0)

    print(
        f"\n📊 進捗 | "
        f"登録:{stats['success']}件  "
        + (f"承認待:{pending}件  " if pending else "")
        + f"重複:{stats['duplicate']}件  "
        f"NG:{stats['ng']}件  "
        f"エラー:{stats['error']}件  "
        f"経過:{elapsed_min:.1f}分  "
        f"速度:{rate:.0f}件/時"
    )


# =============================================================
# 企業処理（1社分）
# =============================================================

def process_one_company(
    search_result: dict,
    hubspot: HubSpotAgent,
    results_writer: csv.DictWriter,
    processed_domains: set,
    pending_list: list | None = None,
) -> str:
    """
    1件の検索結果を処理する

    Returns:
        "success" | "duplicate" | "ng" | "error"
    """
    url = search_result["url"]
    is_media_page = search_result.get("is_media_page", False)
    file_type = search_result.get("file_type", "")

    try:
        # 重複チェック
        session_key = url
        if session_key in processed_domains:
            return "skip"
        processed_domains.add(session_key)

        # ── ファイルURL（PDF/Excel/Word）の場合は企業リスト一括取得 ──
        if file_type:
            logger.info(f"ファイルURL検出（{file_type.upper()}）: {url}")
            from agents.list_page_agent import scrape_company_list_page
            list_results = scrape_company_list_page(url, max_companies=50)
            success_count = 0
            for r in list_results:
                r_key = r["url"]
                if r_key not in processed_domains:
                    status = process_one_company(r, hubspot, results_writer, processed_domains)
                    if status == "success":
                        success_count += 1
            logger.info(f"ファイルから{success_count}社登録: {url}")
            return "success" if success_count > 0 else "skip"

        # ── 除外済み企業チェック（スクレイピング前・HTTPリクエスト不要）──
        # リストページ経由の場合 search_query = 会社名 なので確実にマッチする
        if search_result.get("source_list_url"):
            _pre_name = search_result.get("search_query", "")
            if _pre_name and is_excluded_company(_pre_name):
                logger.info(f"除外済みスキップ（スクレイピング前）: {_pre_name}")
                return "ng"

        # ── Agent1: スクリーナー（スニペット+URLだけで軽量NG判定）──
        passed, screen_reason = pre_screen(search_result)
        if not passed:
            title = search_result.get("title", url)[:30]
            print(f"  ✂ スクリーナーNG [{screen_reason}]: {title}")
            record_ng(search_result["search_query"])
            return "ng"

        # ── Agent2: スクレイピング ──────────────────────────────────
        # S1/S2確定企業は minimal=True（電話番号・従業員数・都道府県のみ取得・高速）
        _s1_confirmed = search_result.get("source_confirmed_s1", False)
        _s2_confirmed = search_result.get("source_confirmed_s2", False)
        company_info = scrape_company_info(
            url,
            is_media_page=is_media_page,
            media_domain=search_result.get("media_domain", ""),
            search_snippet=search_result.get("snippet", ""),
            minimal=(_s1_confirmed or _s2_confirmed),
        )

        # 企業URLが取れなかった場合はスキップ（官公庁・サービスサイト・株式会社未確認）
        if not company_info.get("company_url"):
            logger.debug(f"企業URL未確認→スキップ: {url}")
            return "skip"

        # ── 除外済み企業チェック（スクレイピング後・実際の会社名で確認）──
        _scraped_name = company_info.get("company_name", "")
        if _scraped_name and is_excluded_company(_scraped_name):
            logger.info(f"除外済みスキップ（スクレイピング後）: {_scraped_name}")
            return "ng"

        # 企業ドメインで重複チェック（同じ会社の別記事をスキップ）
        company_domain = extract_domain(company_info.get("company_url") or url)
        if company_domain in processed_domains:
            return "skip"
        processed_domains.add(company_domain)

        # ランク判定
        rank_result = evaluate_rank(company_info, [search_result])
        company_info["rank"] = rank_result["rank"]  # HubSpot a_12 書き込み用

        if rank_result["rank"] == "NG":
            _ng_name = company_info.get("company_name") or ""
            print(f"  ⛔ NGスキップ: {_ng_name or company_domain} [{rank_result['ng_reason']}]")
            record_ng(search_result["search_query"])  # NGをクエリ学習に反映
            add_to_excluded_companies(_ng_name, f"NG: {rank_result.get('ng_reason', '')}")
            return "ng"

        # 媒体記事URLを取得（媒体クエリ経由の場合のみ、バックグラウンドで検索）
        media_article_url = find_media_article_url(
            company_name=company_info.get("company_name", ""),
            search_query=search_result["search_query"],
        )

        # リストアップ元を特定（媒体名 or 検索クエリ）
        source_list_url = search_result.get("source_list_url", "")
        if source_list_url:
            # 媒体名を逆引き
            from config import MEDIA_NAME_TO_DOMAIN
            media_label = next(
                (name for name, domain in MEDIA_NAME_TO_DOMAIN.items() if domain in source_list_url),
                source_list_url
            )
            list_source = f"媒体リスト: {media_label} ({source_list_url})"
        else:
            list_source = f"検索クエリ: {search_result['search_query']}"

        # n_1/n_13書き込み用のメディア名を特定してcompany_infoに格納
        _media_name = ""
        if source_list_url:
            # リストページ経由: media_labelが逆引きできた場合のみ使用
            if media_label != source_list_url:
                _media_name = media_label
            else:
                # MEDIA_NAME_TO_DOMAINにないURL（kenko-keiei.jp等）を別途マッピング
                from config import HEALTH_CERT_DOMAINS
                if any(d in source_list_url for d in HEALTH_CERT_DOMAINS):
                    _media_name = "健康経営優良法人"
        else:
            # キーワード検索経由: search_queryの先頭がPR_MEDIA名と一致するか確認
            _sq = search_result.get("search_query", "")
            from agents.keyword_agent import PR_MEDIA as _PR_MEDIA_LIST
            for _m in _PR_MEDIA_LIST:
                if _sq.startswith(_m):
                    _media_name = _m
                    break
        company_info["media_name"] = _media_name

        # 備考：リストアップ元 + 媒体記事URL + ランク理由
        notes_parts = [f"リストアップ元: {list_source}"]
        if media_article_url:
            notes_parts.append(f"媒体記事URL: {media_article_url}")
        notes_parts += [
            f"ランク: {rank_result['rank']}({rank_result['score']}点)",
            f"理由: {', '.join(rank_result['reasons'][:3])}",
        ]
        notes = " | ".join(notes_parts)
        company_info["notes"] = notes

        score = rank_result["score"]
        confidence = company_info.get("_confidence", 0)
        # pending リスト追加の最低条件（会社名＋電話or住所）
        has_min_fields = bool(company_info.get("company_name")) and (
            bool(company_info.get("phone")) or bool(company_info.get("address"))
        )
        # 自動登録の必須条件（会社名＋URLがあればOK、電話・従業員数は任意）
        has_auto_fields = (
            bool(company_info.get("company_name"))
            and bool(company_info.get("company_url"))
        )

        # スコアが低すぎる or 必須フィールド不足 → 候補にも出さない
        if score < MIN_REGISTER_SIGNALS or not has_min_fields:
            _low_name = company_info.get("company_name") or ""
            logger.debug(
                f"自動スキップ（スコア{score}点 / 信頼度{confidence} / フィールド:{has_min_fields}）: "
                f"{_low_name or company_domain}"
            )
            record_ng(search_result["search_query"])
            add_to_excluded_companies(_low_name, f"スコア不足（{score}点）")
            return "ng"

        # スコアが高く信頼度も十分かつ必須フィールド全揃い → 確認モードでも自動登録
        if score >= MIN_REGISTER_SIGNALS and has_auto_fields:
            is_dup = hubspot.check_duplicate(
                company_name=company_info["company_name"],
                domain=company_domain,
            )
            if is_dup:
                add_to_excluded_companies(company_info.get("company_name", ""), "HubSpot重複")
                return "duplicate"
            if hubspot.register_company(company_info):
                print(
                    f"  ⚡ 自動登録 [{rank_result['rank']}({score}点)] "
                    f"{company_info.get('company_name') or company_domain}"
                )
                results_writer.writerow({
                    "日時":    datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "ランク":   rank_result["rank"],
                    "会社名":   company_info["company_name"],
                    "企業URL":  company_info["company_url"],
                    "代表氏名":  company_info["representative"],
                    "電話番号":  company_info["phone"],
                    "郵便番号":  company_info.get("zip_code", ""),
                    "都道府県":  company_info.get("prefecture", ""),
                    "所在地":   company_info["address"],
                    "業種":    company_info.get("industry", ""),
                    "従業員数":  company_info.get("employee_count", ""),
                    "備考":    company_info.get("notes", ""),
                    "元URL":   company_info.get("source_url", ""),
                    "検索クエリ": search_result.get("search_query", ""),
                })
                record_rank_result(search_result["search_query"], rank_result["rank"])
                return "success"

        # 確認モード：pendingリストに追加して後でまとめて承認
        if pending_list is not None:
            pending_list.append({
                "company_info":  company_info,
                "rank_result":   rank_result,
                "search_query":  search_result["search_query"],
            })
            print(
                f"  [{rank_result['rank']}({score}点)] 候補追加: "
                f"{company_info.get('company_name') or company_domain}"
            )
            record_rank_result(search_result["search_query"], rank_result["rank"])
            return "pending"  # 承認前はpending（successと区別）

        # 自動登録モード
        # HubSpot重複チェック（企業ドメインで確認）
        is_dup = hubspot.check_duplicate(
            company_name=company_info["company_name"],
            domain=company_domain,
        )

        if is_dup:
            hubspot.add_to_ng_list(company_info, reason="HubSpot重複")
            add_to_excluded_companies(company_info.get("company_name", ""), "HubSpot重複")
            print(f"  重複→NGリスト: {company_info.get('company_name') or company_domain}")
            return "duplicate"

        success = hubspot.register_company(company_info)

        if success:
            rank = rank_result["rank"]
            print(f"  [{rank}ランク] 登録: {company_info.get('company_name') or company_domain}")
            results_writer.writerow({
                "日時":    datetime.now().strftime("%Y-%m-%d %H:%M"),
                "ランク":   rank,
                "会社名":   company_info["company_name"],
                "企業URL":  company_info["company_url"],
                "代表氏名":  company_info["representative"],
                "電話番号":  company_info["phone"],
                "郵便番号":  company_info.get("zip_code", ""),
                "都道府県":  company_info.get("prefecture", ""),
                "所在地":   company_info["address"],
                "業種":    company_info.get("industry", ""),
                "従業員数":  company_info.get("employee_count", ""),
                "備考":    notes,
                "元URL":   company_info.get("source_url", url),
                "検索クエリ": search_result.get("search_query", ""),
            })
            record_rank_result(search_result["search_query"], rank)

            found_files = company_info.get("found_file_links", [])
            if found_files:
                from agents.list_page_agent import scrape_company_list_page
                for file_url, ftype in found_files[:3]:
                    if file_url not in processed_domains:
                        processed_domains.add(file_url)
                        file_results = scrape_company_list_page(file_url, max_companies=30)
                        for r in file_results:
                            if r["url"] not in processed_domains:
                                process_one_company(r, hubspot, results_writer, processed_domains)

            return "success"
        else:
            return "error"

    except Exception as e:
        logger.error(f"処理エラー ({url}): {e}")
        return "error"


# =============================================================
# メイン
# =============================================================

def main():
    print_header()

    # 入力受付
    custom_keywords, is_auto, list_urls = input_keywords()
    target_count = input_target_count()

    # 期間選択・クエリ構築
    periods = select_time_period()
    if is_auto:
        query_list = get_sorted_queries(custom_keywords)
        # 自動モードでは媒体リストページを最優先ソースとして先頭に追加
        if list_urls is None:
            list_urls = list(MEDIA_LIST_URLS)
        else:
            list_urls = list(MEDIA_LIST_URLS) + list_urls
        print(f"\n✅ 自動モード: 媒体リスト{len(MEDIA_LIST_URLS)}件 + {len(query_list)}種類のクエリ × {len(periods)}期間")
    else:
        query_list = custom_keywords
    if list_urls:
        print(f"✅ 媒体リストページ: {len(list_urls)}件を先行処理します")
    print_settings(periods, query_list[:5], target_count)

    # 登録モード選択
    confirm_mode = select_register_mode()
    pending_list: list | None = [] if confirm_mode else None

    # 統計
    stats = {"success": 0, "duplicate": 0, "ng": 0, "error": 0, "skip": 0, "pending": 0}
    processed_domains: set[str] = set()
    session_exclusions: list[dict] = []
    start_time = time.time()

    # エージェント初期化
    hubspot = HubSpotAgent(HUBSPOT_TOKEN, NG_LIST_FILE)

    # 結果CSV初期化（buffering=1: 行バッファ → writerow後に即フラッシュ）
    results_file = open(RESULTS_FILE, "a", newline="", encoding="utf-8-sig", buffering=1)
    results_with_query_file = open(RESULTS_WITH_QUERY_FILE, "a", newline="", encoding="utf-8-sig", buffering=1)

    fieldnames = [
        "日時", "ランク", "会社名", "企業URL", "代表氏名", "電話番号",
        "郵便番号", "都道府県", "所在地", "業種", "従業員数", "備考", "元URL"
    ]
    fieldnames_with_query = fieldnames + ["検索クエリ"]

    # 既存の results.csv はそのまま書き出し
    results_writer = csv.DictWriter(results_file, fieldnames=fieldnames, extrasaction="ignore")
    if os.path.getsize(RESULTS_FILE) == 0:
        results_writer.writeheader()

    # 新規リスト（search_query付き）
    results_with_query_writer = csv.DictWriter(
        results_with_query_file, fieldnames=fieldnames_with_query, extrasaction="ignore"
    )
    if os.path.getsize(RESULTS_WITH_QUERY_FILE) == 0:
        results_with_query_writer.writeheader()

    def write_result_row(row: dict):
        results_writer.writerow(row)
        results_with_query_writer.writerow(row)

    # 両ファイルに同時書き込みする writer
    combined_results_writer = MultiDictWriter(results_writer, results_with_query_writer)

    # ─── リストページ先行処理（キーワード検索と併用可）────────
    if list_urls:
        try:
            for list_url in list_urls:
                print(f"\n📋 リストページ取得中: {list_url}")
                list_results = _scrape_list_with_signal(list_url, max_companies=target_count * 2)
                print(f"  → {len(list_results)}社のHP取得完了。処理開始...")

                with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    futures = {
                        executor.submit(
                            process_one_company,
                            result,
                            hubspot,
                            results_writer,
                            processed_domains,
                            pending_list,
                        ): result
                        for result in list_results
                    }
                    for future in as_completed(futures):
                        status = future.result()
                        if status in stats:
                            stats[status] += 1

                print_progress(stats, start_time)

                # 確認モード：収集完了後に承認ステップ
                if pending_list:
                    registered = review_and_register(pending_list, hubspot, combined_results_writer, processed_domains, session_exclusions=session_exclusions)
                    stats["success"] += registered
                    pending_list.clear()

                if stats["success"] >= target_count:
                    print(f"\n目標達成！ {target_count}件登録完了")
                    results_file.close()
                    results_with_query_file.close()
                    return
        except KeyboardInterrupt:
            print("\n\n中断されました")
            results_file.close()
            results_with_query_file.close()
            return

    # ─── キーワード検索（自動 or 手動）──────────────────────
    # キーワード × 期間 の全組み合わせリストを作成
    search_tasks = [
        (keyword, label, tbs)
        for keyword in query_list
        for label, tbs in periods
    ]
    task_index = 0
    no_result_count = 0

    try:
        while stats["success"] < target_count:
            # タスクをローテーション（自動モードは1周したら終了）
            if task_index >= len(search_tasks):
                if is_auto:
                    print("\n⚠️ 全クエリ×期間の組み合わせを試しました。終了します")
                    break
                task_index = 0  # 手動モードはループ

            keyword, period_label, period_tbs = search_tasks[task_index]
            task_index += 1

            print(f"\n🔍 [{period_label}] 検索中 ({task_index}/{len(search_tasks)}): {keyword}")
            search_results = search_google(keyword, period_tbs, MAX_RESULTS_PER_QUERY)

            # ヒット数を学習データとして記録
            record_hit(keyword, len(search_results))

            if not search_results:
                no_result_count += 1
                print("  ⚠️ 検索結果なし")
                if not is_auto and no_result_count >= len(query_list) * 3:
                    print("\n⚠️ 全キーワードで結果が得られなかったため終了します")
                    break
                continue

            no_result_count = 0
            print(f"  → {len(search_results)}件ヒット")

            # 並列処理
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {
                    executor.submit(
                        process_one_company,
                        result,
                        hubspot,
                        combined_results_writer,
                        processed_domains,
                        pending_list,
                    ): result
                    for result in search_results
                }

                for future in as_completed(futures):
                    status = future.result()
                    if status in stats:
                        stats[status] += 1

            print_progress(stats, start_time)

            # 確認モード：キーワードバッチ完了後に承認ステップ
            if pending_list:
                registered = review_and_register(pending_list, hubspot, combined_results_writer, processed_domains, session_exclusions=session_exclusions)
                stats["success"] += registered
                pending_list.clear()

            if stats["success"] >= target_count:
                print(f"\n目標達成！ {target_count}件登録完了")
                break

            # クールダウン
            wait = random.uniform(2, 4)
            time.sleep(wait)

    except KeyboardInterrupt:
        print("\n\n⛔ 中断されました")

    finally:
        results_file.close()
        results_with_query_file.close()

    # 最終レポート
    elapsed = time.time() - start_time
    rate = stats["success"] / (elapsed / 3600) if elapsed > 0 else 0

    print(f"""
{"=" * 60}
📋 完了レポート
{"=" * 60}
  処理時間  : {elapsed / 60:.1f}分
  登録成功  : {stats['success']}件
  重複→NG  : {stats['duplicate']}件
  ランクNG  : {stats['ng']}件
  エラー    : {stats['error']}件
  平均速度  : {rate:.0f}件/時

  📁 結果CSV        : {RESULTS_FILE}
  📁 NGリスト       : {NG_LIST_FILE}
  📁 フィードバック  : {FEEDBACK_FILE}  ← テレアポ結果を記録して精度向上
  📁 除外リスト      : {EXCLUDE_LIST_CSV}  ← 手動で除外ドメインを追加可
  📁 ログ            : {LOG_FILE}
{"=" * 60}
""")

    # 精度改善サマリー（除外パターン分析・自動学習）
    print_ng_suggestions(session_exclusions)


def run_daemon(interval_minutes: int = 60):
    """
    24時間連続稼働モード。
    媒体リスト → キーワード検索を1サイクルとして繰り返す。
    Ctrl+C で即停止。

    Usage:
        python main.py --daemon
        python main.py --daemon --interval=30   # 30分ごとに再実行
    """
    print_header()
    print(f"\n🤖 デーモンモード起動 (サイクル間隔: {interval_minutes}分)")
    print("  確認なし・全件自動登録モードで稼働します")
    print("  Ctrl+C で安全に停止します\n")

    cycle = 0
    total_stats = {"success": 0, "duplicate": 0, "ng": 0, "error": 0, "skip": 0}

    # HubSpot・CSVは起動時に1回だけ初期化（buffering=1: 行バッファ → 即フラッシュ）
    hubspot = HubSpotAgent(HUBSPOT_TOKEN, NG_LIST_FILE)
    results_file = open(RESULTS_FILE, "a", newline="", encoding="utf-8-sig", buffering=1)
    results_with_query_file = open(RESULTS_WITH_QUERY_FILE, "a", newline="", encoding="utf-8-sig", buffering=1)

    fieldnames = [
        "日時", "ランク", "会社名", "企業URL", "代表氏名", "電話番号",
        "郵便番号", "都道府県", "所在地", "業種", "従業員数", "備考", "元URL"
    ]
    fieldnames_with_query = fieldnames + ["検索クエリ"]

    results_writer = csv.DictWriter(results_file, fieldnames=fieldnames)
    if os.path.getsize(RESULTS_FILE) == 0:
        results_writer.writeheader()

    results_with_query_writer = csv.DictWriter(
        results_with_query_file, fieldnames=fieldnames_with_query, extrasaction="ignore"
    )
    if os.path.getsize(RESULTS_WITH_QUERY_FILE) == 0:
        results_with_query_writer.writeheader()

    combined_results_writer = MultiDictWriter(results_writer, results_with_query_writer)

    try:
        while True:
            cycle += 1
            cycle_start = time.time()
            processed_domains: set[str] = set()  # サイクルごとにリセット
            stats = {"success": 0, "duplicate": 0, "ng": 0, "error": 0, "skip": 0}

            print(f"\n{'=' * 60}")
            print(f"  🔄 サイクル #{cycle}  開始: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            print(f"{'=' * 60}")
            logger.info(f"[DAEMON] Cycle #{cycle} started")

            # ─── ① 媒体リスト先行処理（健康経営系 → PR媒体系）────
            for list_url in list(MEDIA_LIST_URLS):
                print(f"\n📋 リストページ取得中: {list_url}")
                try:
                    list_results = _scrape_list_with_signal(list_url, max_companies=1000)
                    print(f"  → {len(list_results)}社を処理開始...")
                    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                        futures = {
                            executor.submit(
                                process_one_company, r, hubspot, combined_results_writer, processed_domains, None
                            ): r for r in list_results
                        }
                        for future in as_completed(futures):
                            status = future.result()
                            if status in stats:
                                stats[status] += 1
                    print_progress(stats, cycle_start)
                except Exception as e:
                    logger.error(f"[DAEMON] list page error {list_url}: {e}")

            # ─── ② キーワード検索（学習済みクエリを自動取得）───────
            query_list = get_sorted_queries([])
            period_tbs = TIME_PERIOD_TBS["3カ月以内"]
            for keyword in query_list:
                try:
                    print(f"\n🔍 検索中: {keyword}")
                    search_results = search_google(keyword, period_tbs, MAX_RESULTS_PER_QUERY)
                    record_hit(keyword, len(search_results))
                    if not search_results:
                        continue
                    print(f"  → {len(search_results)}件ヒット")
                    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                        futures = {
                            executor.submit(
                                process_one_company, r, hubspot, combined_results_writer, processed_domains, None
                            ): r for r in search_results
                        }
                        for future in as_completed(futures):
                            status = future.result()
                            if status in stats:
                                stats[status] += 1
                    wait = random.uniform(2, 4)
                    time.sleep(wait)
                except Exception as e:
                    logger.error(f"[DAEMON] keyword error {keyword}: {e}")

            # ─── サイクル完了レポート ─────────────────────────────
            elapsed = time.time() - cycle_start
            for k in total_stats:
                total_stats[k] += stats.get(k, 0)

            print(f"""
{'=' * 60}
  ✅ サイクル #{cycle} 完了  ({datetime.now().strftime('%Y-%m-%d %H:%M')})
     登録: {stats['success']}件  重複: {stats['duplicate']}件  NG: {stats['ng']}件
     経過: {elapsed / 60:.1f}分  /  累計登録: {total_stats['success']}件
{'=' * 60}""")
            logger.info(
                f"[DAEMON] Cycle #{cycle} done — "
                f"success={stats['success']} dup={stats['duplicate']} ng={stats['ng']} "
                f"elapsed={elapsed/60:.1f}min  total={total_stats['success']}"
            )

            # ─── 次サイクルまで待機（30秒ごとにカウントダウン表示）─
            print(f"\n⏳ 次のサイクルまで {interval_minutes}分 待機... (Ctrl+C で停止)")
            wait_until = time.time() + interval_minutes * 60
            while time.time() < wait_until:
                remaining = int(wait_until - time.time())
                print(f"  残り {remaining // 60}分{remaining % 60:02d}秒...", end="\r", flush=True)
                time.sleep(30)
            print()

    except KeyboardInterrupt:
        print(f"\n\n⛔ デーモン停止 (Ctrl+C)")
        print(f"  完了サイクル: {cycle}回  /  累計登録: {total_stats['success']}社")
        logger.info(f"[DAEMON] stopped by user after {cycle} cycles, total={total_stats['success']}")
    finally:
        results_file.close()


def run_list_daemon(interval_minutes: int = 60):
    """
    リストアップ専用デーモンモード。
    - 高スコア＋必須フィールド全揃い → 自動登録（HubSpot）
    - 中間スコア → pending_review.json に蓄積（上書きせず追記）
    - Ctrl+C で安全に停止

    Usage:
        python main.py --list-daemon
        python main.py --list-daemon --interval=30   # 30分ごとに再実行
    """
    print_header()
    print(f"\n📋 リストアップ専用デーモン起動 (サイクル間隔: {interval_minutes}分)")
    print("  高スコア＋必須フィールド揃い → 自動登録")
    print("  中間スコア → pending_review.json に蓄積（後で python main.py で確認）")
    print("  Ctrl+C で安全に停止します\n")

    pending_path = os.path.join(OUTPUT_DIR, "pending_review.json")
    cycle = 0
    total_stats = {"success": 0, "duplicate": 0, "ng": 0, "error": 0, "skip": 0, "pending": 0}

    hubspot = HubSpotAgent(HUBSPOT_TOKEN, NG_LIST_FILE)
    results_file = open(RESULTS_FILE, "a", newline="", encoding="utf-8-sig", buffering=1)
    results_with_query_file = open(RESULTS_WITH_QUERY_FILE, "a", newline="", encoding="utf-8-sig", buffering=1)

    fieldnames = [
        "日時", "ランク", "会社名", "企業URL", "代表氏名", "電話番号",
        "郵便番号", "都道府県", "所在地", "業種", "従業員数", "備考", "元URL"
    ]
    fieldnames_with_query = fieldnames + ["検索クエリ"]

    results_writer = csv.DictWriter(results_file, fieldnames=fieldnames)
    if os.path.getsize(RESULTS_FILE) == 0:
        results_writer.writeheader()

    results_with_query_writer = csv.DictWriter(
        results_with_query_file, fieldnames=fieldnames_with_query, extrasaction="ignore"
    )
    if os.path.getsize(RESULTS_WITH_QUERY_FILE) == 0:
        results_with_query_writer.writeheader()

    combined_results_writer = MultiDictWriter(results_writer, results_with_query_writer)

    # 処理済みURLをファイルから読み込む（サイクルまたぎ重複防止）
    def _load_processed_urls() -> set[str]:
        if os.path.exists(PROCESSED_URLS_FILE):
            try:
                with open(PROCESSED_URLS_FILE, "r", encoding="utf-8") as f:
                    return set(json.load(f))
            except Exception:
                pass
        return set()

    def _save_processed_urls(urls: set[str]) -> None:
        try:
            with open(PROCESSED_URLS_FILE, "w", encoding="utf-8") as f:
                json.dump(list(urls), f, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"処理済みURL保存失敗: {e}")

    # 全サイクル共通の処理済みURLセット（媒体記事はURL単位、企業HPはドメイン単位で記録）
    global_processed_urls: set[str] = _load_processed_urls()
    logger.info(f"[LIST-DAEMON] 処理済みURL読み込み: {len(global_processed_urls)}件")

    try:
        while True:
            cycle += 1
            cycle_start = time.time()
            processed_domains: set[str] = set(global_processed_urls)  # 今サイクルの重複チェック用
            stats = {"success": 0, "duplicate": 0, "ng": 0, "error": 0, "skip": 0, "pending": 0}
            cycle_pending: list[dict] = []  # このサイクルで発見した中間スコア候補

            print(f"\n{'=' * 60}")
            print(f"  📋 サイクル #{cycle}  開始: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            print(f"{'=' * 60}")
            logger.info(f"[LIST-DAEMON] Cycle #{cycle} started")

            # ─── ① 媒体リスト先行処理 ────────────────────────────────
            for list_url in list(MEDIA_LIST_URLS):
                print(f"\n📋 リストページ取得中: {list_url}")
                try:
                    list_results = _scrape_list_with_signal(list_url, max_companies=1000)
                    print(f"  → {len(list_results)}社を処理開始...")
                    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                        futures = {
                            executor.submit(
                                process_one_company, r, hubspot, combined_results_writer,
                                processed_domains, cycle_pending
                            ): r for r in list_results
                        }
                        for future in as_completed(futures):
                            status = future.result()
                            if status in stats:
                                stats[status] += 1
                    print_progress(stats, cycle_start)
                except Exception as e:
                    logger.error(f"[LIST-DAEMON] list page error {list_url}: {e}")

            # ─── ② キーワード検索 ─────────────────────────────────────
            query_list = get_sorted_queries([])
            period_tbs = TIME_PERIOD_TBS["3カ月以内"]
            for keyword in query_list:
                try:
                    print(f"\n🔍 検索中: {keyword}")
                    search_results = search_google(keyword, period_tbs, MAX_RESULTS_PER_QUERY)
                    record_hit(keyword, len(search_results))
                    if not search_results:
                        continue
                    print(f"  → {len(search_results)}件ヒット")
                    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                        futures = {
                            executor.submit(
                                process_one_company, r, hubspot, combined_results_writer,
                                processed_domains, cycle_pending
                            ): r for r in search_results
                        }
                        for future in as_completed(futures):
                            status = future.result()
                            if status in stats:
                                stats[status] += 1
                    wait = random.uniform(2, 4)
                    time.sleep(wait)
                except Exception as e:
                    logger.error(f"[LIST-DAEMON] keyword error {keyword}: {e}")

            # ─── pending_review.json に追記（重複除去）────────────────
            if cycle_pending:
                # 既存ファイルを読み込む
                existing: list[dict] = []
                if os.path.exists(pending_path):
                    try:
                        with open(pending_path, "r", encoding="utf-8") as f:
                            existing = json.load(f)
                    except Exception:
                        existing = []

                # 既登録済みのURLを除外キーとして使う（daemon形式とflat形式の両方に対応）
                existing_urls = set()
                for e in existing:
                    if "company_info" in e:
                        url = e.get("company_info", {}).get("company_url", "")
                    else:
                        url = e.get("企業URL", e.get("company_url", ""))
                    if url:
                        existing_urls.add(url)

                # 新規候補のうち、まだない企業だけ追加
                new_entries = [
                    e for e in cycle_pending
                    if e.get("company_info", {}).get("company_url", "") not in existing_urls
                ]

                merged = existing + new_entries
                with open(pending_path, "w", encoding="utf-8") as f:
                    json.dump(merged, f, ensure_ascii=False, indent=2)

                stats["pending"] = len(new_entries)
                print(f"\n  📥 {len(new_entries)}件を pending_review.json に追加（累計: {len(merged)}件）")
                logger.info(f"[LIST-DAEMON] pending追加: {len(new_entries)}件 / 累計: {len(merged)}件")

            # ─── 処理済みURLを永続保存（次サイクルの重複スキップ用）────────
            new_urls = processed_domains - global_processed_urls
            if new_urls:
                global_processed_urls.update(new_urls)
                _save_processed_urls(global_processed_urls)
                logger.info(f"[LIST-DAEMON] 処理済みURL追加: {len(new_urls)}件 / 累計: {len(global_processed_urls)}件")

            # ─── サイクル完了レポート ─────────────────────────────────
            elapsed = time.time() - cycle_start
            for k in total_stats:
                total_stats[k] += stats.get(k, 0)

            print(f"""
{'=' * 60}
  ✅ サイクル #{cycle} 完了  ({datetime.now().strftime('%Y-%m-%d %H:%M')})
     自動登録: {stats['success']}件  重複: {stats['duplicate']}件  NG: {stats['ng']}件
     pending追加: {stats['pending']}件  経過: {elapsed / 60:.1f}分
     累計自動登録: {total_stats['success']}件 / 累計pending: {total_stats['pending']}件
{'=' * 60}""")
            logger.info(
                f"[LIST-DAEMON] Cycle #{cycle} done — "
                f"success={stats['success']} pending={stats['pending']} "
                f"dup={stats['duplicate']} ng={stats['ng']} elapsed={elapsed/60:.1f}min"
            )

            # ─── 次サイクルまで待機 ───────────────────────────────────
            print(f"\n⏳ 次のサイクルまで {interval_minutes}分 待機... (Ctrl+C で停止)")
            wait_until = time.time() + interval_minutes * 60
            while time.time() < wait_until:
                remaining = int(wait_until - time.time())
                print(f"  残り {remaining // 60}分{remaining % 60:02d}秒...", end="\r", flush=True)
                time.sleep(30)
            print()

    except KeyboardInterrupt:
        print(f"\n\n⛔ リストアップデーモン停止 (Ctrl+C)")
        print(f"  完了サイクル: {cycle}回")
        print(f"  累計自動登録: {total_stats['success']}社  /  累計pending蓄積: {total_stats['pending']}社")
        print(f"  → 蓄積候補を確認するには: python main.py")
        logger.info(
            f"[LIST-DAEMON] stopped after {cycle} cycles, "
            f"total_success={total_stats['success']} total_pending={total_stats['pending']}"
        )
    finally:
        results_file.close()
        results_with_query_file.close()


def update_overview_docs():
    """
    OVERVIEW.md の <!-- AUTO_UPDATE_START/END --> セクションを
    config.py の現在の設定値から自動再生成する。

    更新対象セクション:
      - media_sources : MEDIA_LIST_URLS の一覧表
      - rank_thresholds : 自動登録・スキップ閾値
    """
    import re as _re
    from config import (
        MEDIA_LIST_URLS, HEALTH_CERT_DOMAINS,
        MIN_REGISTER_SIGNALS,
    )

    overview_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "OVERVIEW.md")
    if not os.path.exists(overview_path):
        print(f"[ERROR] OVERVIEW.md not found: {overview_path}")
        return

    with open(overview_path, "r", encoding="utf-8") as f:
        content = f.read()

    # ── media_sources セクション ────────────────────────────────────
    media_rows = ["| URL | 種別 | 備考 |", "|---|---|---|"]
    for url in MEDIA_LIST_URLS:
        if any(d in url for d in HEALTH_CERT_DOMAINS):
            media_rows.append(f"| {url} | 健康経営優良法人（経産省認定） | Excel自動DL・中小規模のみ |")
        elif "superceo.jp" in url:
            media_rows.append(f"| {url} | PR媒体 - SUPER CEO | 静的HTML・50音順一覧 |")
        elif "business-plus.net" in url:
            media_rows.append(f"| {url} | PR媒体 - B-PLUS | 静的HTML・インタビュー一覧 |")
        else:
            domain = url.split("/")[2] if "/" in url else url
            media_rows.append(f"| {url} | PR媒体 - {domain} | HTML/PDF/Excel |")
    if not MEDIA_LIST_URLS:
        media_rows.append("| （設定なし） | — | — |")
    media_block = "\n".join(media_rows)

    # ── rank_thresholds セクション ──────────────────────────────────
    rank_block = f"""| シグナル | 点数 |
|---|---|
| PR媒体掲載（KENJA GLOBAL等） | +1 |
| 健康経営メディア掲載 | +1 |
| 法定外福利厚生あり | +1 |
| 福利厚生充実＆フィジカルケア未着手 | +1 |
| 健康経営への注力 | +1 |
| 経営者の健康意識・メディア露出 | +1 |
| PR/広告積極投資 | +1 |
| 売上拡大・自社ビル | +1 |
| 高利益率B2B業種（IT/金融/人材等） | +1 |
| 従業員数 20〜100名 | +1 |
| 単一拠点 | +1 |
| ★PR媒体クエリ経由 | **+2ボーナス** |
| ★健康経営優良法人リスト経由（経産省） | **+2ボーナス** |
| ★PR媒体リストページ経由 | **+2ボーナス** |

**ランク基準:** A=6点以上 / B=4〜5点 / C=2〜3点

**自動登録・スキップ閾値:**
- スコア **{MIN_REGISTER_SIGNALS}点以上** かつ **必須フィールド（会社名・URL）全揃い** → 自動登録
- スコア **{MIN_REGISTER_SIGNALS}点未満** または pending最低条件（会社名＋電話or住所）不足 → 候補リストにも出さず自動スキップ
- 上記以外（中間スコア or フィールド不足） → `pending_review.json` に蓄積して確認待ち"""

    # ── マーカー置換 ──────────────────────────────────────────────
    updates = {
        "media_sources":   media_block,
        "rank_thresholds": rank_block,
    }
    new_content = content
    found_keys = []
    updated_keys = []
    for key, block in updates.items():
        pattern = (
            rf"(<!-- AUTO_UPDATE_START: {key} -->)"
            rf".*?"
            rf"(<!-- AUTO_UPDATE_END: {key} -->)"
        )
        if not _re.search(pattern, new_content, flags=_re.DOTALL):
            continue
        found_keys.append(key)
        replacement = f"\\1\n{block}\n\\2"
        result = _re.sub(pattern, replacement, new_content, flags=_re.DOTALL)
        if result != new_content:
            new_content = result
            updated_keys.append(key)

    if not found_keys:
        print("[WARNING] AUTO_UPDATE marker not found in OVERVIEW.md")
        return

    if updated_keys:
        with open(overview_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print("[OK] OVERVIEW.md updated")
        for key in updated_keys:
            print(f"  - {key} regenerated")
    else:
        print("[OK] OVERVIEW.md is already up to date")

    print(f"  - media sources: {len(MEDIA_LIST_URLS)} entries")
    print(f"  - auto-register threshold: score>={MIN_REGISTER_SIGNALS} / skip: score<{MIN_REGISTER_SIGNALS}")


def analyze_feedback():
    """
    feedback.csv と results.csv を突合してアポ率・シグナル効果を分析する。

    分析内容:
      1. ランク別アポ率（A/B/C）
      2. シグナル別アポ率（どのシグナルが実際にアポに繋がったか）
      3. 断り理由の集計
      4. 改善提案（閾値調整・NG業種追加）
    """
    import re as _re

    if not os.path.exists(FEEDBACK_FILE):
        print("feedback.csv がありません。")
        print("Streamlit アプリからテレアポ結果を記録してください: streamlit run app.py")
        return

    if not os.path.exists(RESULTS_FILE):
        print("results.csv がありません。まずリストアップを実行してください。")
        return

    with open(FEEDBACK_FILE, "r", encoding="utf-8-sig") as f:
        feedback_rows = list(csv.DictReader(f))
    with open(RESULTS_FILE, "r", encoding="utf-8-sig") as f:
        results_rows = list(csv.DictReader(f))

    if not feedback_rows:
        print("feedback.csv にデータがありません。")
        return

    total = len(feedback_rows)
    apo_count = sum(1 for r in feedback_rows if r.get("アポ獲得") == "はい")
    apo_rate = apo_count / total * 100 if total > 0 else 0

    print("\n" + "=" * 60)
    print("  📊 テレアポ分析レポート")
    print("=" * 60)
    print(f"  総コール数: {total}件  /  アポ獲得: {apo_count}件  /  アポ率: {apo_rate:.1f}%")

    # results.csv を会社名でインデックス化
    results_by_name = {r.get("会社名", "").strip(): r for r in results_rows if r.get("会社名")}

    matched = 0
    signal_stats: dict[str, dict] = {}
    rank_stats: dict[str, dict] = {}
    industry_stats: dict[str, dict] = {}
    rejection_counts: dict[str, int] = {}

    for fb in feedback_rows:
        name = fb.get("会社名", "").strip()
        got_apo = fb.get("アポ獲得") == "はい"
        rejection = fb.get("断り理由", "").strip()

        if rejection:
            rejection_counts[rejection] = rejection_counts.get(rejection, 0) + 1

        result = results_by_name.get(name)
        if not result:
            continue
        matched += 1

        # ランク別
        rank = result.get("ランク", "").strip()
        if rank:
            s = rank_stats.setdefault(rank, {"apo": 0, "total": 0})
            s["total"] += 1
            if got_apo:
                s["apo"] += 1

        # 業種別
        industry = result.get("業種", "").strip()
        if industry:
            s = industry_stats.setdefault(industry, {"apo": 0, "total": 0})
            s["total"] += 1
            if got_apo:
                s["apo"] += 1

        # シグナル別（備考フィールドの「理由: ...」を解析）
        notes = result.get("備考", "")
        m = _re.search(r"理由: (.+?)(?:\s*\||$)", notes)
        if m:
            for sig in [s.strip() for s in m.group(1).split(",")]:
                key = sig[:35]
                s = signal_stats.setdefault(key, {"apo": 0, "total": 0})
                s["total"] += 1
                if got_apo:
                    s["apo"] += 1

    print(f"  results.csv との突合: {matched}/{total}件\n")

    def bar(rate: float) -> str:
        return "█" * int(rate / 5)

    # ── ランク別アポ率 ──────────────────────────────────
    print("─" * 60)
    print("  ランク別アポ率")
    print("─" * 60)
    for rank in ["A", "B", "C"]:
        if rank in rank_stats:
            s = rank_stats[rank]
            r = s["apo"] / s["total"] * 100 if s["total"] > 0 else 0
            print(f"  {rank}ランク: {r:5.1f}%  {bar(r)}  ({s['apo']}/{s['total']}件)")

    # ── シグナル別アポ率（3件以上）────────────────────
    print("\n─" * 1 + "─" * 59)
    print("  シグナル別アポ率（高い順）")
    print("─" * 60)
    signal_rates = sorted(
        [(sig, s["apo"] / s["total"] * 100, s["apo"], s["total"])
         for sig, s in signal_stats.items() if s["total"] >= 3],
        key=lambda x: -x[1],
    )
    if signal_rates:
        for sig, rate, apo, tot in signal_rates[:12]:
            print(f"  {sig[:32]:<32}: {rate:5.1f}%  {bar(rate)}  ({apo}/{tot}件)")
    else:
        print("  （データ不足 — 3件以上コール結果が記録されたシグナルが必要）")

    # ── 断り理由 ────────────────────────────────────────
    print("\n" + "─" * 60)
    print("  断り理由の内訳")
    print("─" * 60)
    if rejection_counts:
        for reason, cnt in sorted(rejection_counts.items(), key=lambda x: -x[1]):
            print(f"  {reason}: {cnt}件")
    else:
        print("  （記録なし）")

    # ── 改善提案 ──────────────────────────────────────
    print("\n" + "─" * 60)
    print("  💡 改善提案")
    print("─" * 60)
    suggestions = []

    already_have = rejection_counts.get("既導入", 0)
    if already_have >= 3:
        suggestions.append(f"「既導入」が{already_have}件 → 競合サービスを入れている業種をNG業種に追加を検討")

    low_signals = [(sig, rate, tot) for sig, rate, _, tot in signal_rates if rate < 10 and tot >= 5]
    if low_signals:
        s_list = "、".join(f"「{sig[:15]}」" for sig, _, _ in low_signals[:3])
        suggestions.append(f"アポ率10%未満のシグナル: {s_list} → 採点ウェイト削減を検討")

    if "A" in rank_stats and rank_stats["A"]["total"] >= 5:
        a_rate = rank_stats["A"]["apo"] / rank_stats["A"]["total"] * 100
        if a_rate < 20:
            suggestions.append(
                f"Aランクのアポ率が{a_rate:.1f}%と低い "
                f"→ MIN_REGISTER_SIGNALS（現在{MIN_REGISTER_SIGNALS}点）の引き上げを検討"
            )
        elif a_rate >= 40:
            suggestions.append(
                f"Aランクのアポ率が{a_rate:.1f}%と高い "
                f"→ MIN_REGISTER_SIGNALS（現在{MIN_REGISTER_SIGNALS}点）の引き下げで自動登録を増やせる"
            )

    if matched < 10:
        suggestions.append("データがまだ少ない（突合できた件数が10件未満）。50件以上で傾向が安定します")

    if suggestions:
        for s in suggestions:
            print(f"  ⚠️  {s}")
    else:
        print("  特筆すべき問題は検出されませんでした")

    print("=" * 60)


def run_batch(
    keywords: list[str],
    target_count: int = 50,
    period_keys: list[str] | None = None,
    auto_mode: bool = True,
    extra_list_urls: list[str] | None = None,
    confirm_mode: bool = False,
) -> dict:
    """
    バッチモード: input() なしでリストアップを実行する。
    Streamlit / python main.py --batch から呼ばれる。
    confirm_mode=True の場合は HubSpot 登録せず output/pending_review.json に候補を書き出す。
    """
    if period_keys is None:
        period_keys = ["3"]

    print_header()
    print(f"\n[BATCH] バッチモード起動")
    print(f"  キーワード: {', '.join(keywords) if keywords else '（なし・自動のみ）'}")
    print(f"  目標件数: {target_count}件")
    print(f"  期間キー: {', '.join(period_keys)}")
    print(f"  モード: {'自動（媒体リスト＋学習クエリ）' if auto_mode else '手動（キーワードのみ）'}")
    if confirm_mode:
        print(f"  [確認モード] HubSpot登録せず pending_review.json に書き出します\n")
    else:
        print()

    periods = []
    for pk in period_keys:
        label = TIME_PERIODS.get(pk, "3カ月以内")
        tbs   = TIME_PERIOD_TBS.get(label, "")
        periods.append((label, tbs))

    # monitor_agent / feedback_learner は廃止（シグナルウェイト学習廃止）

    list_urls: list | None = None
    if auto_mode:
        # 複数人同時使用時の分散: LISTUP_WORKER_OFFSETで各ワーカーの開始位置をずらす
        worker_offset = int(os.environ.get("LISTUP_WORKER_OFFSET", "0"))
        query_list = get_sorted_queries(keywords, worker_offset=worker_offset)
        list_urls  = list(MEDIA_LIST_URLS)
        if extra_list_urls:
            list_urls = extra_list_urls + list_urls
        print(f"[OK] 自動モード: 媒体リスト{len(list_urls)}件 + {len(query_list)}クエリ x {len(periods)}期間")
    else:
        query_list = keywords if keywords else []
        list_urls  = extra_list_urls if extra_list_urls else None

    if not query_list and not list_urls:
        print("[WARN] キーワードも媒体リストもありません。終了します")
        return {"success": 0}

    periods_label = "、".join(lbl for lbl, _ in periods)
    print(f"⚙️  期間: {periods_label} / 目標: {target_count}件\n")

    stats             = {"success": 0, "duplicate": 0, "ng": 0, "error": 0, "skip": 0}
    processed_domains: set[str] = set()
    session_exclusions: list[dict] = []
    start_time        = time.time()

    hubspot = HubSpotAgent(HUBSPOT_TOKEN, NG_LIST_FILE)

    fieldnames = [
        "日時", "ランク", "会社名", "企業URL", "代表氏名", "電話番号",
        "郵便番号", "都道府県", "所在地", "業種", "従業員数", "備考", "元URL",
    ]

    # 旧フォーマット（8列）のままなら別ファイルに退避して新フォーマットで開始
    if os.path.exists(RESULTS_FILE) and os.path.getsize(RESULTS_FILE) > 0:
        with open(RESULTS_FILE, "r", encoding="utf-8-sig") as _chk:
            _header = _chk.readline().strip()
        if "郵便番号" not in _header:
            import shutil as _shutil
            _backup = RESULTS_FILE.replace(".csv", "_old.csv")
            _shutil.move(RESULTS_FILE, _backup)
            print(f"[INFO] 旧フォーマットの results.csv を {os.path.basename(_backup)} にバックアップしました")

    results_file = open(RESULTS_FILE, "a", newline="", encoding="utf-8-sig", buffering=1)
    results_with_query_file = open(RESULTS_WITH_QUERY_FILE, "a", newline="", encoding="utf-8-sig", buffering=1)

    fieldnames_with_query = fieldnames + ["検索クエリ"]

    results_writer = csv.DictWriter(results_file, fieldnames=fieldnames)
    if os.path.getsize(RESULTS_FILE) == 0:
        results_writer.writeheader()

    results_with_query_writer = csv.DictWriter(
        results_with_query_file, fieldnames=fieldnames_with_query, extrasaction="ignore"
    )
    if os.path.getsize(RESULTS_WITH_QUERY_FILE) == 0:
        results_with_query_writer.writeheader()

    combined_results_writer = MultiDictWriter(results_writer, results_with_query_writer)

    try:
        # ─── ① 媒体リスト先行処理 ─────────────────────────────────
        if list_urls:
            for list_url in list_urls:
                if stats["success"] >= target_count:
                    break
                print(f"\n📋 リストページ取得中: {list_url}")
                list_results = _scrape_list_with_signal(list_url, max_companies=target_count * 2)
                print(f"  → {len(list_results)}社を処理開始...")
                with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    futures = {
                        executor.submit(
                            process_one_company, r, hubspot, combined_results_writer, processed_domains, None
                        ): r for r in list_results
                    }
                    for future in as_completed(futures):
                        status = future.result()
                        if status in stats:
                            stats[status] += 1
                print_progress(stats, start_time)

        # ─── ② キーワード検索 ─────────────────────────────────────
        if stats["success"] < target_count and query_list:
            search_tasks = [
                (keyword, lbl, tbs) for keyword in query_list for lbl, tbs in periods
            ]
            task_index      = 0
            no_result_count = 0
            while stats["success"] < target_count and task_index < len(search_tasks):
                keyword, period_label_i, period_tbs_i = search_tasks[task_index]
                task_index += 1
                print(f"\n🔍 [{period_label_i}] 検索中 ({task_index}/{len(search_tasks)}): {keyword}")
                search_results = search_google(keyword, period_tbs_i, MAX_RESULTS_PER_QUERY)
                record_hit(keyword, len(search_results))
                if not search_results:
                    no_result_count += 1
                    print("  ⚠️ 検索結果なし")
                    if no_result_count >= max(len(query_list) * 2, 6):
                        print("\n⚠️ 全キーワードで結果なし。終了します")
                        break
                    continue
                no_result_count = 0
                print(f"  → {len(search_results)}件ヒット")
                with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    futures = {
                        executor.submit(
                            process_one_company, r, hubspot, combined_results_writer, processed_domains, None
                        ): r for r in search_results
                    }
                    for future in as_completed(futures):
                        status = future.result()
                        if status in stats:
                            stats[status] += 1
                print_progress(stats, start_time)
                time.sleep(random.uniform(2, 4))

    except KeyboardInterrupt:
        print("\n\n⛔ 中断されました")
    finally:
        results_file.close()
        results_with_query_file.close()

    elapsed = time.time() - start_time
    rate    = stats["success"] / (elapsed / 3600) if elapsed > 0 else 0
    print(f"""
{"=" * 60}
📋 完了レポート
{"=" * 60}
  処理時間  : {elapsed / 60:.1f}分
  登録成功  : {stats['success']}件
  重複→NG  : {stats['duplicate']}件
  ランクNG  : {stats['ng']}件
  エラー    : {stats['error']}件
  平均速度  : {rate:.0f}件/時
{"=" * 60}
""")
    print_ng_suggestions(session_exclusions)

    # 確認モード: 今回のバッチ結果を pending_review.json に書き出す
    if confirm_mode:
        import json as _json
        pending_path = os.path.join(OUTPUT_DIR, "pending_review.json")
        try:
            # ファイルヘッダーを確認して正しい fieldnames で読む
            with open(RESULTS_FILE, "r", encoding="utf-8-sig") as f:
                _hdr = f.readline().strip()
                _expected = ["日時", "ランク", "会社名", "企業URL", "代表氏名", "電話番号",
                             "郵便番号", "都道府県", "所在地", "業種", "従業員数", "備考", "元URL"]
                if "郵便番号" in _hdr:
                    reader = csv.DictReader(f)  # ヘッダーが正しい
                else:
                    reader = csv.DictReader(f, fieldnames=_expected)  # 旧ヘッダー対策
                all_rows = list(reader)
            # 今回のバッチで追加された行（最新 stats["success"] 件）
            new_rows = all_rows[-stats["success"]:] if stats["success"] > 0 else []
            with open(pending_path, "w", encoding="utf-8") as f:
                _json.dump(new_rows, f, ensure_ascii=False, indent=2)
            print(f"\n[確認モード] {len(new_rows)}件を pending_review.json に書き出しました")
            print(f"   Streamlit の「リストアップ」タブで承認/却下できます")
        except Exception as e:
            print(f"\n[ERROR] pending_review.json 書き出しエラー: {e}")

    return stats


if __name__ == "__main__":
    if "--review-pending" in sys.argv:
        # 確認待ちリスト（pending_review.json）を端末上で表示・登録する
        pending_path = os.path.join(OUTPUT_DIR, "pending_review.json")
        if not os.path.exists(pending_path):
            print("確認待ちリストがありません。")
            sys.exit(0)
        with open(pending_path, "r", encoding="utf-8") as _f:
            raw = json.load(_f)
        if not raw:
            print("確認待ちの候補がありません。")
            sys.exit(0)
        # daemon形式（ネスト）とflat形式の両方に対応
        pending_items = []
        for item in raw:
            if "company_info" in item:
                pending_items.append(item)
            else:
                pending_items.append({
                    "company_info": {k: item.get(k, "") for k in
                                     ["company_name", "company_url", "representative", "phone",
                                      "zip_code", "prefecture", "address", "industry", "employee_count", "notes"]
                                     if k in {
                                         "company_name": item.get("会社名", ""),
                                         "company_url":  item.get("企業URL", ""),
                                         "representative": item.get("代表氏名", ""),
                                         "phone":        item.get("電話番号", ""),
                                         "zip_code":     item.get("郵便番号", ""),
                                         "prefecture":   item.get("都道府県", ""),
                                         "address":      item.get("所在地", ""),
                                         "industry":     item.get("業種", ""),
                                         "employee_count": item.get("従業員数", ""),
                                         "notes":        item.get("備考", ""),
                                     }
                                     },
                    "rank_result":  {"rank": item.get("ランク", ""), "score": 0, "reasons": []},
                    "search_query": "",
                })
        print_header()
        hubspot = HubSpotAgent(HUBSPOT_TOKEN, NG_LIST_FILE)
        results_file = open(RESULTS_FILE, "a", newline="", encoding="utf-8-sig", buffering=1)
        fieldnames = ["日時", "ランク", "会社名", "企業URL", "代表氏名", "電話番号",
                      "郵便番号", "都道府県", "所在地", "業種", "従業員数", "備考", "元URL"]
        results_writer = csv.DictWriter(results_file, fieldnames=fieldnames)
        if os.path.getsize(RESULTS_FILE) == 0:
            results_writer.writeheader()
        processed_domains: set = set()
        registered = review_and_register(pending_items, hubspot, results_writer, processed_domains)
        print(f"\n✅ {registered}件を登録しました。")
        # 登録済みを pending_review.json から削除（クリア）
        if registered > 0:
            with open(pending_path, "w", encoding="utf-8") as _f:
                json.dump([], _f, ensure_ascii=False)
        results_file.close()
    elif "--analyze" in sys.argv:
        analyze_feedback()
    elif "--audit" in sys.argv:
        # hubspot_auditor は v2 で廃止
        print("--audit は v2 で廃止されました。HubSpot管理画面から直接確認してください。")
    elif "--update-docs" in sys.argv:
        update_overview_docs()
    elif "--list-daemon" in sys.argv:
        # リストアップ専用デーモン（中間スコアはpending蓄積・高スコアのみ自動登録）
        interval = 60
        for arg in sys.argv:
            if arg.startswith("--interval="):
                try:
                    interval = int(arg.split("=")[1])
                except ValueError:
                    pass
        run_list_daemon(interval_minutes=interval)
    elif "--daemon" in sys.argv:
        # デフォルト60分間隔、--interval=N で変更可
        interval = 60
        for arg in sys.argv:
            if arg.startswith("--interval="):
                try:
                    interval = int(arg.split("=")[1])
                except ValueError:
                    pass
        run_daemon(interval_minutes=interval)
    elif "--batch" in sys.argv:
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--batch",      action="store_true")
        parser.add_argument("--keywords",   nargs="*", default=[])
        parser.add_argument("--count",      type=int, default=50)
        parser.add_argument("--periods",    nargs="*", default=["3"])
        parser.add_argument("--list-urls",  nargs="*", default=[], dest="list_urls")
        parser.add_argument("--auto",       action="store_true")
        parser.add_argument("--confirm",    action="store_true")
        args = parser.parse_args()
        run_batch(
            keywords=args.keywords or [],
            target_count=args.count,
            period_keys=args.periods or ["3"],
            auto_mode=args.auto,
            extra_list_urls=args.list_urls or None,
            confirm_mode=args.confirm,
        )
    else:
        main()
