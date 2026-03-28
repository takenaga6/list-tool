"""
補完エージェント

meetings.csv / call_list.csv にいて results.csv に未登録の会社を
自動でHP検索 → スクレイピング → ランク判定 → results.csv 追記する。

呼び出し元:
  - feedback_learner.run_learning(): 学習実行前に call_list / meetings を補完
  - app.py 商談インポート後: インポートした会社を補完
"""

import csv
import logging
import os
import random
import sys
import time
from datetime import datetime

_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(_DIR, "..")
sys.path.insert(0, _ROOT)

from config import OUTPUT_DIR, RESULTS_FILE

logger = logging.getLogger(__name__)

# results.csv のカラム定義（main.py と同じ順序）
_RESULTS_COLS = [
    "日時", "ランク", "会社名", "企業URL", "代表氏名", "電話番号",
    "郵便番号", "都道府県", "所在地", "業種", "従業員数", "備考", "元URL",
]


def _load_existing_names() -> set[str]:
    """results.csv に登録済みの会社名セットを返す"""
    if not os.path.exists(RESULTS_FILE):
        return set()
    try:
        with open(RESULTS_FILE, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            return {(row.get("会社名") or "").strip() for row in reader if row.get("会社名")}
    except Exception:
        return set()


def _normalize(name: str) -> str:
    """会社名を正規化（feedback_learner._normalize_name と同じロジック）"""
    import re
    import unicodedata
    name = re.split(r"[|｜｜\-－―]", name)[0]
    for kw in ["株式会社", "有限会社", "合同会社", "合資会社", "一般社団法人",
               "公益社団法人", "医療法人", "学校法人", "社会福祉法人"]:
        name = name.replace(kw, "")
    name = unicodedata.normalize("NFKC", name)
    name = name.lower()
    import re
    name = re.sub(r"[\s\u3000\.\-_（）()・　]+", "", name)
    return name.strip()


def _append_to_results(row: dict):
    """results.csv に1行追記する（ヘッダーがなければ先に書く）"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    file_exists = os.path.exists(RESULTS_FILE) and os.path.getsize(RESULTS_FILE) > 0
    with open(RESULTS_FILE, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=_RESULTS_COLS, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def supplement_results_csv(
    company_names: list[str],
    max_companies: int = 30,
    progress_callback=None,
) -> int:
    """
    company_names の中で results.csv に未登録の会社を検索・スクレイピングして追加する。

    Args:
        company_names:     補完対象の会社名リスト
        max_companies:     1回で処理する最大件数（時間制限のため）
        progress_callback: (current, total, company_name) を受け取る任意のコールバック

    Returns:
        追加した件数
    """
    from agents.list_page_agent import search_company_hp
    from agents.scraper_agent import scrape_company_info
    from agents.rank_agent import evaluate_rank

    # 既登録の正規化名セット
    existing_names = _load_existing_names()
    existing_normalized = {_normalize(n) for n in existing_names}

    # 未登録企業のみ抽出（重複除去・空除去）
    seen = set()
    targets = []
    for name in company_names:
        name = (name or "").strip()
        if not name:
            continue
        norm = _normalize(name)
        if norm in existing_normalized or norm in seen:
            continue
        seen.add(norm)
        targets.append(name)

    if not targets:
        logger.info("補完対象なし（全社 results.csv に登録済み）")
        return 0

    targets = targets[:max_companies]
    total = len(targets)
    logger.info(f"補完スクレイピング開始: {total}社")

    added = 0
    for i, name in enumerate(targets):
        if progress_callback:
            progress_callback(i + 1, total, name)

        try:
            # HP検索（Google CSE → DuckDuckGo フォールバック）
            result = search_company_hp(name, "")
            if not result:
                logger.debug(f"HP未発見（スキップ）: {name}")
                continue

            url = result["url"]

            # スクレイピング
            info = scrape_company_info(
                url,
                is_media_page=False,
                media_domain="",
                search_snippet=result.get("snippet", ""),
            )
            # 会社名・URLが取れなかった場合は入力値で補完
            if not info.get("company_name"):
                info["company_name"] = name
            if not info.get("company_url"):
                info["company_url"] = url

            # ランク判定
            rank_result = evaluate_rank(info, [result])
            reasons_str = ", ".join(rank_result.get("reasons", []))
            notes = (
                f"補完スクレイピング | "
                f"ランク: {rank_result['rank']}({rank_result['score']}点) | "
                f"理由: {reasons_str}"
            )

            # results.csv に追記
            _append_to_results({
                "日時":    datetime.now().strftime("%Y-%m-%d %H:%M"),
                "ランク":   rank_result["rank"],
                "会社名":   info.get("company_name", name),
                "企業URL":  info.get("company_url", url),
                "代表氏名": info.get("representative", ""),
                "電話番号": info.get("phone", ""),
                "郵便番号": info.get("postal_code", ""),
                "都道府県": info.get("prefecture", ""),
                "所在地":   info.get("address", ""),
                "業種":     info.get("industry", ""),
                "従業員数": info.get("employee_count", ""),
                "備考":     notes,
                "元URL":    url,
            })
            added += 1
            logger.info(f"補完追加 [{rank_result['rank']}]: {info.get('company_name', name)}")

        except Exception as e:
            logger.warning(f"補完エラー（スキップ）: {name} - {e}")

        # DuckDuckGo レート制限対策
        time.sleep(random.uniform(1.0, 2.0))

    logger.info(f"補完完了: {added}/{total}社を results.csv に追加")
    return added
