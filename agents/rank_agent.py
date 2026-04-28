"""
ランク判定エージェント（v2）

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

    # ① 上場・大規模グループチェック
    if re.search(r"東証|上場企業|証券コード|プライム市場|スタンダード市場|グロース市場|TSE:|NYSE:|NASDAQ:", text):
        return False, "上場企業"

    domain = urlparse(url).netloc.replace("www.", "").lower()

    from config import SMALL_COMPANY_DOMAINS
    if domain in SMALL_COMPANY_DOMAINS:
        return False, "小規模ドメイン"
    if domain in LARGE_COMPANY_DOMAINS:
        return False, "大企業ドメイン"

    if re.search(r"ホールディングス|Holdings|ホールディング\b", title):
        return False, "ホールディングス（大規模企業）"
    if re.search(r"GROUP|グループ会社|グループ子会社|\bグループ\b.*\b会社", title):
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

    # ③④ HP本文がある時のみ判定（pre_screen段階・スニペット限定処理では空）
    if page_text:
        # ③ HP健康経営記載なしNG
        if not any(kw in page_text for kw in HEALTH_KEIEI_REQUIRED_KEYWORDS):
            return False, "HP健康経営記載なし"

        # ④ HP採用情報なしNG
        if not any(kw in page_text for kw in RECRUIT_PAGE_REQUIRED_KEYWORDS):
            return False, "HP採用情報なし"

        # ⑤ 福利厚生「法定のみ」NG（士業・投資運用は例外）
        has_welfare = any(kw in page_text for kw in WELFARE_KEYWORDS)
        if not has_welfare and not is_special_industry(full_text):
            return False, "福利厚生記載なし(士業以外)"

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

    # ─── NG判定 ───────────────────────────────────────
    if re.search(r"東証|上場企業|TSE|NYSE|NASDAQ|証券コード|プライム市場|スタンダード市場|グロース市場", full_text):
        return _ng("上場企業")

    company_name = company_info.get("company_name", "")
    if re.search(r"ホールディングス|Holdings", company_name):
        return _ng("ホールディングス（大規模企業）")

    for ng_kw in NG_INDUSTRY_KEYWORDS:
        if ng_kw in (company_name + " " + all_search_text)[:400]:
            return _ng(f"NG業種: {ng_kw}")

    # 従業員数NG（scraper抽出値優先）
    emp_raw = company_info.get("employee_count", "")
    if emp_raw:
        try:
            emp_n = int(re.sub(r"\D", "", str(emp_raw)))
            if emp_n > 200:
                return _ng(f"従業員{emp_n}名（200名超）")
            if emp_n < 10:
                return _ng(f"従業員{emp_n}名（下限未満）")
        except ValueError:
            pass

    emp_m = re.search(r"(?:従業員[数人]?|社員[数人]?|スタッフ[数人]?)\s*[：:\s]*(\d+)\s*名?", full_text)
    if emp_m:
        count = int(emp_m.group(1))
        if count > 200:
            return _ng(f"従業員{count}名（200名超）")
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
