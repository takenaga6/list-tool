"""
ランク判定エージェント（v2）

【このツールの用途とNGロジックの前提】
  本ツールはアウトバウンド営業（テレアポ・DM）用のリスト生成ツール。
  営業アプローチの到達可能性に基づき、以下の方針でNG/OK を決定する：

  - 上場企業（本体）は規模を問わずNG:
      上場企業は購買窓口到達のハードルが高く（受付→秘書→担当部署の複数経路が必要）、
      アウトバウンドでは事実上アプローチ不可能。
  - 東証プライム上場企業の子会社（is_prime_sub=True）は例外通過:
      親会社の信用力を持ちつつ、子会社は意思決定者（社長・役員）への距離が近く、
      アウトバウンドで届く確率が高い。
  - マーケティング流入・紹介経由の企業はこのロジックの対象外:
      本ツールはアウトバウンドのリストのみを生成する。

  ※ is_prime_sub の判定は config.py の PARENT_PRIME_KEYWORDS によるキーワードマッチ。
    スクレイプしたHP本文に「東証プライム上場の〇〇の子会社」等が含まれる場合に True。

【設計方針】
  S1（PR有料媒体掲載）またはS2（健康経営メディア掲載）に該当した時点でBランク確定。
  追加シグナル（S3〜S6）が2つ以上あればAランク。
  S1/S2なしの場合はS3〜S6の合計で判定（3つ以上でB）。

【シグナル定義（6本）】
  S1: PR有料媒体掲載（KENJA GLOBAL / エコノミスト / Newsweek等）
  S2: 健康経営メディア掲載（アクサ生命 / 健康経営の広場 / 大同生命等）
  S3: 法定外福利厚生の記載あり
  S4: 健康経営への注力が明確（認証・セミナー・経営者の健康意識）
  S5: 半年以内のHPリニューアル
  S6: 自社ビル保有

【ランク基準】
  A: S1/S2あり + S3〜S6のうち2つ以上
  B: S1またはS2に該当（即確定） / S1/S2なしでS3〜S6が3つ以上
  C: S1/S2なしでS3〜S6が1〜2つ
  NG: NG条件いずれかに該当
"""

import re
import logging
from urllib.parse import urlparse
from config import (
    PR_MEDIA_DOMAINS,
    HEALTH_MEDIA_DOMAINS,
    NG_INDUSTRY_KEYWORDS,
    HEALTH_CERT_DOMAINS,
    LARGE_COMPANY_DOMAINS,
    RANK_A_EXTRA_SIGNALS,
    RANK_B_MIN_SIGNALS,
    NG_INDUSTRY_KEYWORDS_PHASE1,
    INDUSTRY_PROFIT_MEDIUM_KEYWORDS,
    FUKURI_LEGAL_ONLY_OK_INDUSTRY,
    PARENT_PRIME_KEYWORDS,
    HEALTH_KEIEI_REQUIRED_KEYWORDS,
    RECRUIT_PAGE_REQUIRED_KEYWORDS,
    EMPLOYEE_RANGE_CONFIG,
    # Phase 5: S7/S8/S9/S10 キーワード
    ISO_CERT_KEYWORDS,
    SDGS_KEYWORDS,
    PRESIDENT_PAGE_PATH_KEYWORDS,
    PRESIDENT_HEALTH_KEYWORDS,
    PROFITABLE_INDUSTRY_KEYWORDS,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# 定数
# ─────────────────────────────────────────────

# S1判定: PR有料媒体のキーワード（テキスト・クエリ内で使用）
PR_MEDIA_KEYWORDS = [
    "kenja global", "賢者グローバル",
    "ビジネスクロニクル", "business chronicle",
    "エコノミスト rec", "newsweek", "ニューズウィーク",
    "時代のニューウェーブ", "ニューウェーブ",
    "for japan", "leaders award",
    "smb excellent", "b-plus", "super ceo",
    "bs times", "t-times",
    "ベンチャー通信", "カンパニータンク",
    "社長名鑑", "経営者プライム",
]

# S2判定: 健康経営メディアのキーワード（テキスト内で使用）
HEALTH_MEDIA_KEYWORDS = [
    "アクサ生命", "ボイスレポート",
    "健康経営の広場", "大同生命",
    "健康経営優良法人", "ブライト500",
]

# S3判定: 法定外福利厚生キーワード
WELFARE_KEYWORDS = [
    "マッサージ", "整体", "酸素カプセル", "社員旅行", "食事補助", "食事手当",
    "法定外福利厚生", "リフレッシュ休暇", "スポーツジム", "フィットネス",
    "健康サポート", "鍼灸", "カイロプラクティック", "リラクゼーション",
    "ウェルネス", "健康手当", "人間ドック", "ヨガ", "ストレッチ",
    "スポーツ補助", "部活動", "サークル", "保養所", "社食",
    "無料ランチ", "ドリンク無料",
]

# S4判定: 健康経営注力キーワード
HEALTH_MGMT_KEYWORDS = [
    "健康経営", "えるぼし", "くるみん",
    "健康セミナー", "健康投資", "健康支援", "ウェルビーイング",
    "健康づくり", "社員の健康", "従業員の健康", "健康促進",
    "健康経営宣言", "健康経営認定",
    "ストレスチェック", "産業医",
    "健康推進", "ウェルフェア", "健康委員会",
    r"代表取締役.*健康", r"社長.*健康", r"社長.*福利厚生",
]

# S5判定: HPリニューアルキーワード
RENEWAL_KEYWORDS = [
    "リニューアル", "新サイト", "サイトをリニューアル",
    "ウェブサイトをリニューアル", "ホームページを刷新",
]

# S6判定: 自社ビルキーワード
OWN_BUILDING_KEYWORDS = [
    "自社ビル", "自社オフィス", "自社物件", "本社ビル", "自社所有",
]

# 多拠点パターン（NG判定用）
_MULTI_BRANCH_PATTERNS = [
    r"[2-9１-９]\s*拠点以上",
    r"全国\s*\d+\s*拠点",
    r"全国各地",
    r"(?:支社|支店|営業所)\s*\d+",
    r"\d+\s*(?:支社|支店|営業所)",
    r"全国展開",
    r"全国ネットワーク",
]


# ─────────────────────────────────────────────
# pre_screen: スクレイピング前フィルター（変更なし）
# ─────────────────────────────────────────────

def pre_screen(search_result: dict) -> tuple[bool, str]:
    """
    スクレイピング前にスニペット+URL+タイトルだけでNGを判定する。
    追加のHTTPリクエストは発生しない。高速フィルター。

    Returns:
        (passed, ng_reason)
    """
    url     = search_result.get("url", "")
    title   = search_result.get("title", "") or ""
    snippet = search_result.get("snippet", "") or ""
    text    = title + " " + snippet

    # プライム子会社候補をスニペット段階で先に判定する（案③）。
    # HP本文がないため PARENT_PRIME_KEYWORDS（厳格化済み）でのみマッチする。
    # True の場合、以降の「上場キーワード」「グループ会社」チェックをスキップし
    # HP取得後の evaluate_rank() での精密判定に委ねる。
    _maybe_prime_sub = any(kw in text for kw in PARENT_PRIME_KEYWORDS)

    # ① 上場・大規模グループチェック
    # プライム子会社候補はスキップ（evaluate_rank で is_prime_sub を再判定する）
    if not _maybe_prime_sub and re.search(r"東証|上場企業|証券コード|プライム市場|スタンダード市場|グロース市場|TSE:|NYSE:|NASDAQ:", text):
        return False, "上場企業"

    domain = urlparse(url).netloc.replace("www.", "").lower()

    from config import SMALL_COMPANY_DOMAINS
    if domain in SMALL_COMPANY_DOMAINS:
        return False, "小規模ドメイン"
    if domain in LARGE_COMPANY_DOMAINS:
        return False, "大企業ドメイン"

    if re.search(r"ホールディングス|Holdings|ホールディング\b", title):
        return False, "ホールディングス（大規模企業）"
    # プライム子会社候補はスキップ（evaluate_rank で is_prime_sub を再判定する）
    if not _maybe_prime_sub and re.search(r"GROUP|グループ会社|グループ子会社|\bグループ\b.*\b会社", title):
        return False, "大手グループ企業"

    # ② 従業員数（スニペットに明記されている場合）
    emp_m = re.search(r"(?:従業員[数人]?|社員[数人]?|スタッフ[数人]?)\s*[：:約\s]*(\d+)\s*名?", text)
    if emp_m:
        count = int(emp_m.group(1))
        if count > 200:
            return False, f"従業員{count}名（200名超）"
        if count < 10:
            return False, f"従業員{count}名（規模不足）"

    # ③ 多拠点チェック
    for pat in _MULTI_BRANCH_PATTERNS:
        if re.search(pat, text):
            return False, f"多拠点: {re.search(pat, text).group()}"

    # ④ NG業種チェック
    for ng_kw in NG_INDUSTRY_KEYWORDS:
        if ng_kw in text[:300]:
            return False, f"NG業種: {ng_kw}"

    # ⑤ Phase 1: 業種NG（広告/メディア）— スニペット段階
    for ng_kw in NG_INDUSTRY_KEYWORDS_PHASE1:
        if ng_kw in text:
            return False, f"NG業種(広告/メディア): {ng_kw}"

    # ⑥ Phase 1: 従業員数の細分化（スニペットから抽出可能な範囲のみ）
    emp_match = re.search(r"(?:従業員[数人]?|社員[数人]?)\s*[：:\s]*(\d+)", text)
    if emp_match:
        emp_count = int(emp_match.group(1))
        cfg = EMPLOYEE_RANGE_CONFIG
        if cfg["blank_zone_min"] <= emp_count <= cfg["blank_zone_max"]:
            return False, f"空白帯規模({emp_count}名)"
        if emp_count < cfg["min_special_industry"]:
            return False, f"極小規模({emp_count}名)"

    return True, ""


# ─────────────────────────────────────────────
# Phase 1 必須条件チェック（57社分析からの追加判定）
# ─────────────────────────────────────────────

def is_special_industry(text: str) -> bool:
    """士業・投資運用などの「法定のみ福利厚生でもOKな業種」を判定。"""
    return any(kw in text for kw in FUKURI_LEGAL_ONLY_OK_INDUSTRY)


def is_parent_prime_subsidiary(text: str) -> bool:
    """大手プライム子会社判定。HP全文・会社概要欄からキーワード検出。"""
    return any(kw in text for kw in PARENT_PRIME_KEYWORDS)


def check_phase1_must_conditions(company_info: dict, page_text: str) -> tuple[bool, str]:
    """Phase 1の必須条件チェック。1つでも違反したらNGとして即除外。

    既存のNG条件チェック後に呼ぶ。HP本文（page_text）が空の場合、
    健康経営/採用ページ判定はスキップ（既存処理に委ねる）。
    """
    company_name = company_info.get("company_name", "")
    industry = company_info.get("industry", "")
    full_text = f"{company_name} {industry} {page_text}"

    # ① 業種NG（広告/マーケ/メディア）
    for ng_kw in NG_INDUSTRY_KEYWORDS_PHASE1:
        if ng_kw in company_name or ng_kw in industry or ng_kw in page_text[:500]:
            return False, f"NG業種(広告/メディア): {ng_kw}"

    # ② 業界利益率「中」のレッドオーシャン業種NG（大手プライム子会社は例外）
    is_prime_sub = is_parent_prime_subsidiary(full_text)
    for ng_kw in INDUSTRY_PROFIT_MEDIUM_KEYWORDS:
        if ng_kw in company_name or ng_kw in industry or ng_kw in page_text[:500]:
            if not is_prime_sub:
                return False, f"レッドオーシャン業界(利益率中): {ng_kw}"

    # ⑥ 従業員数フィルター細分化
    emp_count_str = company_info.get("employee_count", "")
    if emp_count_str:
        try:
            emp_count = int(re.sub(r"\D", "", str(emp_count_str)))
        except ValueError:
            emp_count = None
        if emp_count is not None and emp_count > 0:
            cfg = EMPLOYEE_RANGE_CONFIG
            is_special = is_special_industry(full_text)
            # 6-9名は士業のみOK
            if cfg["min_special_industry"] <= emp_count <= cfg["max_special_industry"]:
                if not is_special:
                    return False, f"極小規模({emp_count}名)かつ士業以外"
            # 6名未満はNG
            elif emp_count < cfg["min_special_industry"]:
                return False, f"極小規模({emp_count}名)"
            # 200-499名はNG（空白帯）
            elif cfg["blank_zone_min"] <= emp_count <= cfg["blank_zone_max"]:
                return False, f"空白帯規模({emp_count}名)"
            # 500名以上は大手プライム子会社のみOK
            elif emp_count >= cfg["large_min"] and not is_prime_sub:
                return False, f"大規模({emp_count}名)かつ大手プライム子会社でない"

    return True, "OK"


# ─────────────────────────────────────────────
# evaluate_rank: ランク判定（v2・シンプル化）
# ─────────────────────────────────────────────

def evaluate_rank(
    company_info: dict,
    search_results: list[dict],
    page_text: str = "",
) -> dict:
    """
    企業ランクを判定する（6シグナル版）。

    S1/S2が確定している場合（source_confirmed_s1/s2）はスクレイピング結果に
    関わらずB確定。追加シグナルでAに昇格。

    Returns:
        {
          "rank": "A"/"B"/"C"/"NG",
          "score": int,
          "signals": {"S1": bool, "S2": bool, ...},
          "reasons": [str, ...],
          "ng_reason": str,
        }
    """
    # ソース確定シグナル（list_page_agent / keyword_agent が設定）
    sr0 = search_results[0] if search_results else {}
    confirmed_s1: bool = sr0.get("source_confirmed_s1", False)
    confirmed_s2: bool = sr0.get("source_confirmed_s2", False)

    search_query = sr0.get("search_query", "")
    source_list_url = sr0.get("source_list_url", "")

    all_search_urls  = [r.get("url", "") for r in search_results]
    all_search_text  = " ".join(
        r.get("title", "") + " " + r.get("snippet", "")
        for r in search_results
    )
    full_text = all_search_text + " " + page_text + " " + company_info.get("company_name", "")

    # HP本文を含む full_text が揃った時点でプライム子会社を精密判定する。
    # pre_screen の _maybe_prime_sub より信頼性が高い（HP本文ベース）。
    _is_prime_sub = is_parent_prime_subsidiary(full_text)

    # ─── NG判定 ───────────────────────────────────────
    # プライム子会社はアウトバウンドで届く（親の信用力×子会社の意思決定距離）ため例外通過。
    if not _is_prime_sub and re.search(r"東証|上場企業|TSE|NYSE|NASDAQ|証券コード|プライム市場|スタンダード市場|グロース市場", full_text):
        return _ng("上場企業")

    company_name = company_info.get("company_name", "")
    if re.search(r"ホールディングス|Holdings", company_name):
        return _ng("ホールディングス（大規模企業）")

    for ng_kw in NG_INDUSTRY_KEYWORDS:
        if ng_kw in (company_name + " " + all_search_text)[:400]:
            return _ng(f"NG業種: {ng_kw}")

    # 従業員数NG（scraper抽出値優先）
    # 200-499名は空白帯（プライム子会社も含め全員NG）。
    # 500名以上はプライム子会社のみ通過（非プライムはアウトバウンド不可）。
    cfg = EMPLOYEE_RANGE_CONFIG
    emp_raw = company_info.get("employee_count", "")
    if emp_raw:
        try:
            emp_n = int(re.sub(r"\D", "", str(emp_raw)))
            if cfg["blank_zone_min"] <= emp_n <= cfg["blank_zone_max"]:
                return _ng(f"従業員{emp_n}名（空白帯）")
            if emp_n >= cfg["large_min"] and not _is_prime_sub:
                return _ng(f"従業員{emp_n}名（大規模・非プライム子会社）")
            if emp_n < 10:
                return _ng(f"従業員{emp_n}名（下限未満）")
        except ValueError:
            pass

    emp_m = re.search(r"(?:従業員[数人]?|社員[数人]?|スタッフ[数人]?)\s*[：:\s]*(\d+)\s*名?", full_text)
    if emp_m:
        count = int(emp_m.group(1))
        if cfg["blank_zone_min"] <= count <= cfg["blank_zone_max"]:
            return _ng(f"従業員{count}名（空白帯）")
        if count >= cfg["large_min"] and not _is_prime_sub:
            return _ng(f"従業員{count}名（大規模・非プライム子会社）")
        if count < 10:
            return _ng(f"従業員{count}名（下限未満）")

    branch_m = re.search(r"(\d+)\s*拠点", full_text)
    if branch_m and int(branch_m.group(1)) >= 3:
        return _ng(f"{branch_m.group(1)}拠点（上限超）")

    # ─── Phase 1 必須条件チェック ───────────────────────
    # 既存NG条件をクリアした社に対してさらに精密チェック（HP本文要）
    ok, reason = check_phase1_must_conditions(company_info, page_text)
    if not ok:
        return _ng(f"Phase1必須条件NG: {reason}")

    # ─── S1 判定 ──────────────────────────────────────
    s1 = confirmed_s1
    s1_reason = ""

    if not s1:
        # ソースURLがPR媒体ドメインを含む
        if source_list_url and any(d in source_list_url for d in PR_MEDIA_DOMAINS):
            s1 = True
            s1_reason = f"PR媒体リスト経由: {source_list_url.split('/')[2]}"
        # 検索URLにPR媒体が含まれる
        elif any(any(d in u for d in PR_MEDIA_DOMAINS) for u in all_search_urls):
            s1 = True
            matched = next(d for d in PR_MEDIA_DOMAINS if any(d in u for u in all_search_urls))
            s1_reason = f"PR媒体URL: {matched}"
        # クエリまたはテキストにPR媒体キーワードが含まれる
        else:
            combined = (full_text + " " + search_query).lower()
            for kw in PR_MEDIA_KEYWORDS:
                if kw in combined:
                    s1 = True
                    s1_reason = f"PR媒体テキスト: {kw}"
                    break

    if s1 and not s1_reason:
        s1_reason = "PR有料媒体掲載（ソース確定）"

    # ─── S2 判定 ──────────────────────────────────────
    s2 = confirmed_s2
    s2_reason = ""

    if not s2:
        # ソースURLが健康経営メディアドメインを含む
        if source_list_url and any(d in source_list_url for d in HEALTH_MEDIA_DOMAINS):
            s2 = True
            s2_reason = f"健康経営メディアリスト経由: {source_list_url.split('/')[2]}"
        elif source_list_url and any(d in source_list_url for d in HEALTH_CERT_DOMAINS):
            s2 = True
            s2_reason = "健康経営優良法人認定（経産省リスト経由）"
        # テキストに健康経営メディアキーワードが含まれる
        else:
            for kw in HEALTH_MEDIA_KEYWORDS:
                if kw in full_text:
                    s2 = True
                    s2_reason = f"健康経営メディア: {kw}"
                    break

    if s2 and not s2_reason:
        s2_reason = "健康経営メディア掲載（ソース確定）"

    # ─── S3〜S6 判定 ─────────────────────────────────
    s3, s3_reason = _check_s3(full_text)
    s4, s4_reason = _check_s4(full_text)
    s5, s5_reason = _check_s5(full_text)
    s6, s6_reason = _check_s6(full_text)

    signals = {
        "S1": s1, "S2": s2,
        "S3": s3, "S4": s4, "S5": s5, "S6": s6,
    }
    reasons = []
    if s1: reasons.append(f"S1: {s1_reason}")
    if s2: reasons.append(f"S2: {s2_reason}")
    if s3: reasons.append(f"S3: {s3_reason}")
    if s4: reasons.append(f"S4: {s4_reason}")
    if s5: reasons.append(f"S5: {s5_reason}")
    if s6: reasons.append(f"S6: {s6_reason}")

    # ─── ランク決定 ───────────────────────────────────
    extra = sum([s3, s4, s5, s6])
    score = sum([s1, s2, s3, s4, s5, s6])

    if s1 or s2:
        rank = "A" if extra >= RANK_A_EXTRA_SIGNALS else "B"
    else:
        if extra >= RANK_B_MIN_SIGNALS:
            rank = "B"
        elif extra >= 1:
            rank = "C"
        else:
            rank = "C"

    logger.debug(f"ランク: {rank}({score}シグナル) - {reasons}")
    return {"rank": rank, "score": score, "signals": signals, "reasons": reasons, "ng_reason": ""}


# ─────────────────────────────────────────────
# 各シグナル判定ヘルパー
# ─────────────────────────────────────────────

def _ng(reason: str) -> dict:
    return {"rank": "NG", "score": 0, "signals": {}, "reasons": [], "ng_reason": reason}


def _check_s3(text: str) -> tuple[bool, str]:
    """S3: 法定外福利厚生の記載あり"""
    found = [k for k in WELFARE_KEYWORDS if k in text]
    if found:
        return True, f"法定外福利厚生: {', '.join(found[:3])}"
    return False, ""


def _check_s4(text: str) -> tuple[bool, str]:
    """S4: 健康経営への注力が明確"""
    for kw in HEALTH_MGMT_KEYWORDS:
        if ".*" in kw:
            if re.search(kw, text):
                return True, f"健康経営注力: {kw.replace('.*', '')}"
        elif kw in text:
            return True, f"健康経営注力: {kw}"
    return False, ""


def _check_s5(text: str) -> tuple[bool, str]:
    """S5: 半年以内のHPリニューアル"""
    for kw in RENEWAL_KEYWORDS:
        if kw in text:
            return True, f"HPリニューアル: {kw}"
    return False, ""


def _check_s6(text: str) -> tuple[bool, str]:
    """S6: 自社ビル保有"""
    for kw in OWN_BUILDING_KEYWORDS:
        if kw in text:
            return True, f"自社ビル: {kw}"
    return False, ""


# ═══════════════════════════════════════════════════════════
# Phase 2: 必須条件 + 加点 + 減点 の3層構造（2026-04-30〜）
# 49社の契約企業分析データから導出
# Phase2_実装計画.md / config.py の各マッピング辞書を参照
# ═══════════════════════════════════════════════════════════

import sys as _sys
import os as _os
_DIR = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _os.path.join(_DIR, ".."))

from config import (
    INDUSTRY_PROFIT_MAPPING,
    INDUSTRY_TURNOVER_MAPPING,
    INDUSTRY_CATEGORY_KEYWORDS,
    PRIME_LOCATION_KEYWORDS,
    LOCAL_LOCATION_KEYWORDS,
    RECRUIT_MEDIA_KEYWORDS,
    FOUNDER_OWNER_KEYWORDS,
)


# ── マッピング判定関数 ─────────────────────────────────────


def classify_industry_profit(industry: str) -> str:
    """業界利益率ランクを判定する.

    Args:
        industry: 業種名（scraperから取得した文字列）

    Returns:
        "high" / "medium-high" / "medium" / "low" / "unknown"
    """
    if not industry:
        return "unknown"
    text = industry.lower()
    industry_lower = industry  # 日本語比較用
    for rank, keywords in INDUSTRY_PROFIT_MAPPING.items():
        for kw in keywords:
            if kw.lower() in text or kw in industry_lower:
                return rank
    return "unknown"


def classify_industry_turnover(industry: str) -> str:
    """業界離職率ランクを判定する.

    Args:
        industry: 業種名

    Returns:
        "low" / "medium" / "unknown"
    """
    if not industry:
        return "unknown"
    text = industry.lower()
    industry_lower = industry
    for rank, keywords in INDUSTRY_TURNOVER_MAPPING.items():
        for kw in keywords:
            if kw.lower() in text or kw in industry_lower:
                return rank
    return "unknown"


def classify_industry_category(industry: str) -> str | None:
    """業種カテゴリを判定する（最初にマッチしたカテゴリを返す）.

    Args:
        industry: 業種名

    Returns:
        "商社/卸売" / "金融" / "製造業" 等のカテゴリ名 / None
    """
    if not industry:
        return None
    for category, keywords in INDUSTRY_CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in industry:
                return category
    return None


def classify_location(address: str) -> str:
    """住所から立地グレードを判定する.

    Args:
        address: 住所（例：東京都千代田区丸の内1-1-1）

    Returns:
        "prime" (都心一等地) / "local" (地方) / "neither" (どちらでもない) / "unknown" (空)
    """
    if not address:
        return "unknown"
    # まず都心一等地チェック
    for kw in PRIME_LOCATION_KEYWORDS:
        if kw in address:
            return "prime"
    # 次に地方チェック
    for kw in LOCAL_LOCATION_KEYWORDS:
        if kw in address:
            return "local"
    return "neither"


def count_recruit_media(page_text: str) -> int:
    """HP本文から採用媒体の数を数える.

    Args:
        page_text: HP本文テキスト

    Returns:
        媒体数（0以上の整数）
    """
    if not page_text:
        return 0
    text_lower = page_text.lower()
    found_media = set()
    for kw in RECRUIT_MEDIA_KEYWORDS:
        if kw.lower() in text_lower:
            # 大文字小文字違いの重複を排除（例：doda と DODA は同じ）
            normalized = kw.lower()
            # rikunabi/リクナビ等の同義語をまとめる
            if "リクナビ" in kw or "rikunabi" in normalized:
                found_media.add("rikunabi")
            elif "マイナビ" in kw or "mynavi" in normalized:
                found_media.add("mynavi")
            elif "doda" == normalized or "doda" in normalized:
                found_media.add("doda")
            elif "engage" in normalized or "エンゲージ" in kw:
                found_media.add("engage")
            elif "indeed" in normalized:
                found_media.add("indeed")
            elif "bizreach" in normalized or "ビズリーチ" in kw:
                found_media.add("bizreach")
            elif "wantedly" in normalized or "ウォンテッドリー" in kw:
                found_media.add("wantedly")
            elif "type" in normalized or "タイプ" in kw:
                found_media.add("type")
            elif "リクルートエージェント" in kw:
                found_media.add("recruit_agent")
            elif "jac" in normalized:
                found_media.add("jac")
            elif "openwork" in normalized:
                found_media.add("openwork")
            elif "en転職" in kw or "エン転職" in kw:
                found_media.add("en_tenshoku")
            else:
                found_media.add(normalized)
    return len(found_media)


def is_founder_owner(page_text: str) -> bool:
    """創業家オーナー判定（HP本文から）.

    Args:
        page_text: HP本文テキスト

    Returns:
        True: 創業家オーナーの可能性あり / False: なし
    """
    if not page_text:
        return False
    for kw in FOUNDER_OWNER_KEYWORDS:
        if kw in page_text:
            return True
    return False


def is_parent_prime_subsidiary_v2(page_text: str) -> bool:
    """大手プライム子会社判定（v2）.

    既存の is_parent_prime_subsidiary() と同じ動作。
    Phase 2のテスト用に別名で公開。

    Args:
        page_text: HP本文テキスト

    Returns:
        True: 大手プライム子会社 / False: そうでない
    """
    return is_parent_prime_subsidiary(page_text)


# ── 加点・減点ロジック ───────────────────────────────────


# ─── Phase 5: 新規シグナル S7/S8/S9/S10 ─────────────────────────────────


def check_s7_iso_cert(text: str) -> tuple[bool, list[str]]:
    """S7: ISO認定の有無（49社データで継続率2.42倍差・+2点）.

    継続社の67% vs 解約社の28%が保有。
    一般語（情報セキュリティ等）を除外し、ISO番号・規格名のみ判定。

    Args:
        text: 企業HP本文（会社名・業種・ページ全文の結合テキスト）

    Returns:
        (matched, hit_keywords)
    """
    hits = [kw for kw in ISO_CERT_KEYWORDS if kw in text]
    return (bool(hits), hits)


def check_s8_sdgs(text: str) -> tuple[bool, list[str]]:
    """S8: SDGs/サステナビリティの有無（49社データで継続率1.84倍差・+1点）.

    継続社の55% vs 解約社の30%が保有。
    「カーボンニュートラル」「脱炭素」だけでは判定しない（v2.0で除外）。

    Args:
        text: 企業HP本文

    Returns:
        (matched, hit_keywords)
    """
    hits = [kw for kw in SDGS_KEYWORDS if kw in text]
    return (bool(hits), hits)


def check_s9_president_message_health(page_text: str) -> bool:
    """S9: 社長メッセージ × 健康記載（49社データで継続率2.46倍差・+1点）【簡易版】.

    継続社の71% vs 解約社の29%が保有。

    簡易版の実装方針（別ページ取得なし）:
    - page_text に社長メッセージページを示すキーワードが含まれる
    - かつ page_text に健康関連ワードが含まれる
    - 両方満たせば True
    別ページ取得をしない理由: ページ取得失敗リスクの回避・処理速度の安定化。
    精度は正規版（別ページ取得）より落ちるが、誤判定は少ない。

    Args:
        page_text: 企業HP本文（トップページ全文）

    Returns:
        True: 社長メッセージページが存在し健康ワードを含む / False: それ以外
    """
    if not page_text:
        return False
    has_president_page = any(kw in page_text for kw in PRESIDENT_PAGE_PATH_KEYWORDS)
    has_health_keyword = any(kw in page_text for kw in PRESIDENT_HEALTH_KEYWORDS)
    return has_president_page and has_health_keyword


def _extract_capital_from_text(text: str) -> int:
    """HP本文から資本金（円）を抽出する。取得できない場合は 0 を返す。

    例: 「資本金 1億円」→ 100,000,000
        「資本金 3,000万円」→ 30,000,000
        「資本金：5億2,000万円」→ 520,000,000
    """
    if not text:
        return 0
    # 億円パターン（例: 1億、5億2,000万）
    m = re.search(r'資本金[^\d]{0,5}(\d[\d,]*(?:\.\d+)?)億(?:(\d[\d,]*)万)?', text)
    if m:
        try:
            oku = float(m.group(1).replace(',', '')) * 100_000_000
            man = int(m.group(2).replace(',', '')) * 10_000 if m.group(2) else 0
            return int(oku) + man
        except (ValueError, AttributeError):
            pass
    # 万円パターン（例: 3,000万円）
    m = re.search(r'資本金[^\d]{0,5}(\d[\d,]*)万', text)
    if m:
        try:
            return int(m.group(1).replace(',', '')) * 10_000
        except ValueError:
            pass
    return 0


def check_s10_profitable_industry(
    text: str,
    industry_text: str = "",
    company_info: dict | None = None,
) -> tuple[int, list[str]]:
    """S10: 儲かっている業界フラグ（49社データで継続率3.27倍差・+3点）【2段階判定】.

    年収B以上(3.27倍)・業界利益率高め(2.89倍)・業界離職率低め(2.56倍) を統合。

    2段階判定:
      Stage1: PROFITABLE_INDUSTRY_KEYWORDS にキーワードが含まれる → +1点
              ※ Stage1 単体では継続率差 0.90倍（業種マッチのみでは弱い）
      Stage2: Stage1 + 以下のいずれかを満たす → +3点
              - 従業員数 50名以上（company_info["employee_count"]）
              - 大手プライム子会社（is_parent_prime_subsidiary）
              - 資本金1億円以上（page_text から正規表現抽出）

    Args:
        text: 企業HP本文（ページ全文）
        industry_text: HubSpot業種フィールドや company_info["industry"]
        company_info: scraper が返した企業情報 dict

    Returns:
        (points, hit_keywords): points は 0 / 1 / 3
    """
    target_text = (industry_text or "") + " " + text

    # Stage1: キーワードマッチ
    hits = [kw for kw in PROFITABLE_INDUSTRY_KEYWORDS if kw in target_text]
    if not hits:
        return 0, []

    # Stage2: 規模・親会社・資本金フィルター
    stage2_passed = False

    # 条件A: 従業員数 50名以上
    if company_info:
        emp_str = company_info.get("employee_count", "")
        if emp_str:
            try:
                emp = int(re.sub(r"\D", "", str(emp_str)))
                if emp >= 50:
                    stage2_passed = True
            except ValueError:
                pass

    # 条件B: 大手プライム子会社
    if not stage2_passed and is_parent_prime_subsidiary(target_text):
        stage2_passed = True

    # 条件C: 資本金1億円以上（page_text から抽出）
    if not stage2_passed and _extract_capital_from_text(text) >= 100_000_000:
        stage2_passed = True

    return (3, hits) if stage2_passed else (1, hits)


def check_interaction_bonus(signals: dict) -> tuple[int, str]:
    """相互作用ボーナス判定（49社データで継続率100%の組み合わせ・+3点）.

    3点セット6種（49社データで継続率100%・すべて ISO または 採用高 を含む）:
      - s4_kenko_keiei + s7_iso + s10_profitable  (健康経営+ISO+儲かる業界)
      - s4_kenko_keiei + s7_iso + s8_sdgs         (健康経営+ISO+SDGs)
      - s4_kenko_keiei + s7_iso + s9_president_health  (健康経営+ISO+社長健康)
      - s7_iso + s9_president_health + s10_profitable  (ISO+社長健康+儲かる業界)
      - s7_iso + s9_president_health + s3_welfare  (ISO+社長健康+福利厚生)
      - s4_kenko_keiei + s8_sdgs + s10_profitable  (健康経営+SDGs+儲かる業界)

    ボーナス条件（重複加算なし・どちらかひとつで +3点）:
      1. 上記6セットのいずれかを完成
      2. シグナル合計 5個以上保有

    Args:
        signals: 各シグナルの True/False を収めた dict。
            想定キー:
              s1_pr, s2_kenko_media, s3_welfare, s4_kenko_keiei,
              s5_renewal, s6_jisha_bldg, s7_iso, s8_sdgs,
              s9_president_health, s10_profitable
            未定義キーは False 扱い。

    Returns:
        (bonus_points, reason): bonus_points は 0 または 3
    """
    # 3点セット定義（49社データで継続率100%が確認された組み合わせのみ）
    TRIPLE_SETS = [
        ("s4_kenko_keiei", "s7_iso", "s10_profitable"),
        ("s4_kenko_keiei", "s7_iso", "s8_sdgs"),
        ("s4_kenko_keiei", "s7_iso", "s9_president_health"),
        ("s7_iso",         "s9_president_health", "s10_profitable"),
        ("s7_iso",         "s9_president_health", "s3_welfare"),
        ("s4_kenko_keiei", "s8_sdgs",             "s10_profitable"),
    ]

    for triple in TRIPLE_SETS:
        if all(signals.get(s, False) for s in triple):
            return 3, f"3点セット達成: {'+'.join(triple)}"

    total = sum(1 for v in signals.values() if v)
    if total >= 5:
        return 3, f"シグナル{total}個保有"

    return 0, ""


def evaluate_useful_conditions(
    company_info: dict,
    page_text: str = "",
    extra_signals: dict | None = None,
    return_signals: bool = False,
) -> tuple[int, list[str]] | tuple[int, list[str], dict]:
    """加点条件を評価する（Phase 5拡充版: S7/S8/S9/S10 + 相互作用ボーナス）.

    Args:
        company_info: scraperで取得した企業情報
        page_text: HP本文
        extra_signals: evaluate_rank_v2 から渡す S1/S2/S5/S6 の bool dict。
            キー: s1_pr, s2_kenko_media, s5_renewal, s6_jisha_bldg。
            相互作用ボーナスの signals dict に統合される。None の場合は全 False 扱い。
        return_signals: True の場合、相互作用ボーナス算出に使った signals dict
            （s1_pr〜s10_profitable の bool）も返す。後方互換のためデフォルト False。

    Returns:
        return_signals=False（既定）: (score, reasons)
        return_signals=True:        (score, reasons, signals)
    """
    score = 0
    reasons: list[str] = []

    industry = company_info.get("industry", "") or ""
    address = company_info.get("address", "") or ""
    company_name = company_info.get("company_name", "") or ""

    # ===== +2点：強いシグナル =====

    # 業種カテゴリ判定（+2点）
    category = classify_industry_category(industry)
    if category in ("商社/卸売", "金融", "教育ソフト"):
        score += 2
        reasons.append(f"+2 業種:{category}")
    elif category in ("人材派遣", "投資運用", "士業"):
        score += 1
        reasons.append(f"+1 業種:{category}")

    # 業界平均利益率（+2 / +1）
    profit = classify_industry_profit(industry)
    if profit == "high":
        score += 2
        reasons.append("+2 業界利益率「高」")
    elif profit == "medium-high":
        score += 1
        reasons.append("+1 業界利益率「中-高/低-中」")

    # 大手プライム子会社（+2点）
    if page_text and is_parent_prime_subsidiary(page_text):
        score += 2
        reasons.append("+2 大手プライム子会社")

    # 採用媒体カウント（+2 / +1）
    if page_text:
        media_count = count_recruit_media(page_text)
        if media_count >= 3:
            score += 2
            reasons.append(f"+2 採用媒体3つ以上({media_count}媒体)")
        elif media_count >= 1:
            score += 1
            reasons.append(f"+1 採用媒体1-2つ({media_count}媒体)")

    # ===== +1点：中程度シグナル =====

    # HP健康経営記載（S4相当）
    s4_kenko_keiei = False
    if page_text:
        for kw in HEALTH_KEIEI_REQUIRED_KEYWORDS:
            if kw in page_text:
                score += 1
                reasons.append("+1 HP健康経営記載(S4)")
                s4_kenko_keiei = True
                break

    # 法定外福利厚生記載（S3相当）
    s3_welfare = False
    if page_text:
        fukuri_kws = ["人間ドック", "マッサージ", "社員旅行", "リフレッシュ休暇",
                      "リラクゼーション", "ジム利用", "保養所", "社内託児"]
        for kw in fukuri_kws:
            if kw in page_text:
                score += 1
                reasons.append(f"+1 法定外福利厚生記載(S3:{kw})")
                s3_welfare = True
                break

    # 立地（都心一等地）
    location = classify_location(address)
    if location == "prime":
        score += 1
        reasons.append("+1 立地:都心一等地/Aクラス")

    # ===== Phase 5: 新規シグナル S7/S8/S9/S10 =====

    s7_iso = False
    s8_sdgs = False
    s9_president_health = False
    s10_profitable = False

    if page_text:
        # S7: ISO認定 +2点（49社データ継続率2.42倍差）
        iso_match, iso_hits = check_s7_iso_cert(page_text)
        if iso_match:
            score += 2
            reasons.append(f"+2 S7:ISO認定({iso_hits[0]})")
            s7_iso = True

        # S8: SDGs/サステナビリティ +1点（49社データ継続率1.84倍差）
        sdgs_match, sdgs_hits = check_s8_sdgs(page_text)
        if sdgs_match:
            score += 1
            reasons.append(f"+1 S8:SDGs({sdgs_hits[0]})")
            s8_sdgs = True

        # S9: 社長メッセージ健康記載 +1点（49社データ継続率2.46倍差・簡易版）
        if check_s9_president_message_health(page_text):
            score += 1
            reasons.append("+1 S9:社長メッセージ健康記載")
            s9_president_health = True

        # S10: 儲かっている業界 +1/+3点（49社データ継続率3.27倍差・2段階判定）
        s10_pts, s10_hits = check_s10_profitable_industry(
            text=page_text,
            industry_text=industry,
            company_info=company_info,
        )
        if s10_pts > 0:
            score += s10_pts
            hit_label = s10_hits[0] if s10_hits else ""
            reasons.append(f"+{s10_pts} S10:儲かる業界({hit_label})")
            s10_profitable = True

    # ===== 相互作用ボーナス（3点セット or 5シグナル以上 → +3点）=====
    base = extra_signals or {}
    signals = {
        "s1_pr":               base.get("s1_pr", False),
        "s2_kenko_media":      base.get("s2_kenko_media", False),
        "s3_welfare":          s3_welfare,
        "s4_kenko_keiei":      s4_kenko_keiei,
        "s5_renewal":          base.get("s5_renewal", False),
        "s6_jisha_bldg":       base.get("s6_jisha_bldg", False),
        "s7_iso":              s7_iso,
        "s8_sdgs":             s8_sdgs,
        "s9_president_health": s9_president_health,
        "s10_profitable":      s10_profitable,
    }
    bonus, bonus_reason = check_interaction_bonus(signals)
    if bonus > 0:
        score += bonus
        reasons.append(f"+{bonus} 相互作用ボーナス({bonus_reason})")

    if return_signals:
        return score, reasons, signals
    return score, reasons


def evaluate_negative_conditions(
    company_info: dict, page_text: str = ""
) -> tuple[int, list[str]]:
    """減点条件を評価する（49社分析からの減点条件）.

    Args:
        company_info: scraperで取得した企業情報
        page_text: HP本文

    Returns:
        (score, reasons): 減点合計（負の値）と理由リスト
    """
    score = 0
    reasons: list[str] = []

    industry = company_info.get("industry", "") or ""

    # ===== -2点：強いマイナス =====

    # 業種カテゴリ判定（-2点）
    category = classify_industry_category(industry)
    if category in ("製造業", "IT/通信", "コンサル・サービス"):
        score -= 2
        reasons.append(f"-2 業種:{category}")

    # 業界利益率「中」（レッドオーシャン）
    profit = classify_industry_profit(industry)
    if profit == "medium":
        # 大手プライム子会社例外（伊藤忠等）はチェック
        if not (page_text and is_parent_prime_subsidiary(page_text)):
            score -= 2
            reasons.append("-2 業界利益率「中」(レッドオーシャン)")

    # 業界離職率「中」
    turnover = classify_industry_turnover(industry)
    if turnover == "medium":
        # 既に製造業で-2減点されている場合は重複しない
        if category != "製造業":
            score -= 2
            reasons.append("-2 業界離職率「中」")

    # ===== -1点：中程度マイナス =====

    # 立地（地方・都市部近郊・都市部）
    address = company_info.get("address", "") or ""
    location = classify_location(address)
    if location == "local":
        score -= 1
        reasons.append("-1 立地:地方/都市部")

    # 創業家オーナー判定
    if page_text and is_founder_owner(page_text):
        score -= 1
        reasons.append("-1 創業家オーナー")

    return score, reasons


# ── 統合評価関数（v2）───────────────────────────────────


def evaluate_rank_v2(
    company_info: dict,
    search_results: list[dict],
    page_text: str = "",
) -> dict:
    """Phase 2 統合ランク判定（必須条件NG → 加点 - 減点）.

    既存の evaluate_rank() を破壊せず、並列追加。

    Args:
        company_info: scraperで取得した企業情報
        search_results: 検索結果リスト
        page_text: HP本文

    Returns:
        {
            "rank": "A" / "B" / "C" / "NG",
            "score": int (加点-減点の合計),
            "reasons": list[str] (理由),
            "signals": dict (S1〜S10 の bool。HubSpot 構造化プロパティ書き込み用),
            "rank_version": str (ランクロジック版),
            "useful_score": int,
            "negative_score": int,
            "ng_reason": str (NG時のみ),
        }
    """
    from config import RANK_LOGIC_VERSION

    # ===== 必須条件NGチェック（既存ロジックを使う） =====
    # 既存の evaluate_rank() の必須NG部分を踏襲
    existing_result = evaluate_rank(company_info, search_results, page_text=page_text)
    if existing_result.get("rank") == "NG":
        # 既存NG判定に従う
        return {
            "rank": "NG",
            "score": -99,
            "reasons": existing_result.get("reasons", []),
            "signals": {f"S{i}": False for i in range(1, 11)},
            "rank_version": RANK_LOGIC_VERSION,
            "useful_score": 0,
            "negative_score": 0,
            "ng_reason": existing_result.get("ng_reason", ""),
        }

    # ===== 加点 - 減点で総合スコア =====
    # evaluate_rank で判定した S1/S2/S5/S6 を相互作用ボーナス計算に渡す
    old_signals = existing_result.get("signals", {})
    extra_sigs = {
        "s1_pr":          old_signals.get("S1", False),
        "s2_kenko_media": old_signals.get("S2", False),
        "s5_renewal":     old_signals.get("S5", False),
        "s6_jisha_bldg":  old_signals.get("S6", False),
    }
    useful_score, useful_reasons, uc_signals = evaluate_useful_conditions(
        company_info, page_text, extra_signals=extra_sigs, return_signals=True
    )
    negative_score, negative_reasons = evaluate_negative_conditions(company_info, page_text)
    total_score = useful_score + negative_score

    # ===== ランク決定（Phase 5閾値: A≥8, B=5-7, C=1-4, NG≤0） =====
    if total_score >= 8:
        rank = "A"
    elif total_score >= 5:
        rank = "B"
    elif total_score >= 1:
        rank = "C"
    else:
        rank = "NG"

    all_reasons = useful_reasons + negative_reasons

    # ===== 構造化シグナル（S1〜S10）=====
    # uc_signals は evaluate_useful_conditions が実際に加点判定に用いた値。
    # v2 が確定した値を真実の源とし、HubSpot 構造化プロパティへ永続化する。
    signals = {
        "S1":  uc_signals.get("s1_pr", False),
        "S2":  uc_signals.get("s2_kenko_media", False),
        "S3":  uc_signals.get("s3_welfare", False),
        "S4":  uc_signals.get("s4_kenko_keiei", False),
        "S5":  uc_signals.get("s5_renewal", False),
        "S6":  uc_signals.get("s6_jisha_bldg", False),
        "S7":  uc_signals.get("s7_iso", False),
        "S8":  uc_signals.get("s8_sdgs", False),
        "S9":  uc_signals.get("s9_president_health", False),
        "S10": uc_signals.get("s10_profitable", False),
    }

    return {
        "rank": rank,
        "score": total_score,
        "reasons": all_reasons,
        "signals": signals,
        "rank_version": RANK_LOGIC_VERSION,
        "useful_score": useful_score,
        "negative_score": negative_score,
    }
