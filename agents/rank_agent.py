"""
ランク判定エージェント
offi-stretch.com の契約企業実績に基づいてシグナルを精緻化。

【理想顧客プロファイル（契約実績から）】
- 情報通信・金融・人材・商社・コンサル・士業など高利益率のB2B業種
- 社長またはウェルフェア担当者が健康意識高い
- PR/広告に費用をかけており売上拡大中（承認欲求・ブランド意識高い）
- 既存福利厚生は多様だが「本格的なフィジカルケア」は未着手
- 自社ビル or 固定オフィス + 少人数（10〜100名）

採点方式:
  各項目1点。PR媒体クエリ経由は+2ボーナス。
  A: 6点以上 / B: 4〜5点 / C: 2〜3点 / それ以下もC
"""

import json
import os
import re
import logging
from urllib.parse import urlparse
from config import (
    PR_MEDIA_DOMAINS,
    HEALTH_MEDIA_DOMAINS,
    NG_INDUSTRY_KEYWORDS,
    HEALTH_CERT_DOMAINS,
    LARGE_COMPANY_DOMAINS,
)
from agents.keyword_agent import PR_MEDIA as PR_MEDIA_NAMES

logger = logging.getLogger(__name__)

_WEIGHTS_FILE = os.path.join(os.path.dirname(__file__), "..", "output", "signal_weights.json")


def _load_weights() -> dict:
    """signal_weights.json からシグナルウェイトを読み込む。ファイルがなければデフォルト1.0を返す。"""
    try:
        with open(_WEIGHTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("weights", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


# モジュールロード時に読み込む（起動ごとに1回）
_W = _load_weights()


def _w(key: str) -> float:
    """シグナルキーのウェイトを返す（デフォルト1.0）"""
    return _W.get(key, 1.0)

# 首都圏以外の都道府県（NG対象）
_NON_KANTO_PREFECTURES = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "栃木県", "群馬県",  # 茨城・埼玉・千葉は首都圏なので除外
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県",
    "岐阜県", "静岡県", "愛知県", "三重県",
    "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県",
    "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県",
    "福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
]

# 多拠点を示すパターン
_MULTI_BRANCH_PATTERNS = [
    r"[2-9１-９]\s*拠点以上",
    r"全国\s*\d+\s*拠点",
    r"全国各地",
    r"(?:支社|支店|営業所)\s*\d+",
    r"\d+\s*(?:支社|支店|営業所)",
    r"全国展開",
    r"全国ネットワーク",
]


def pre_screen(search_result: dict) -> tuple[bool, str]:
    """
    Agent1: スクレイピング前にスニペット+URL+タイトルだけでNGを判定する。
    追加のHTTPリクエストは発生しない。

    Returns:
        (passed, ng_reason)
        passed=False の場合はスクレイピングをスキップしてよい
    """
    url     = search_result.get("url", "")
    title   = search_result.get("title", "") or ""
    snippet = search_result.get("snippet", "") or ""
    text    = title + " " + snippet

    # ① 上場・大規模グループチェック
    if re.search(r"東証|上場企業|証券コード|プライム市場|スタンダード市場|グロース市場|TSE:|NYSE:|NASDAQ:", text):
        return False, "上場企業"

    # ①b ドメインから明らかに企業規模（大/小）を判断できる場合
    domain = urlparse(url).netloc.replace("www.", "").lower()

    # 小規模企業ドメイン（規模が小さくて提案価値が低いもの）
    from config import SMALL_COMPANY_DOMAINS

    if domain in SMALL_COMPANY_DOMAINS:
        return False, "小規模ドメイン"

    # 大企業ドメイン（規模が大きすぎて対象外）
    if domain in LARGE_COMPANY_DOMAINS:
        return False, "大企業ドメイン"

    # ホールディングス = 持株会社構造（多数の子会社を持つ大規模企業が多い）
    if re.search(r"ホールディングス|Holdings|ホールディング\b", title):
        return False, "ホールディングス（大規模企業）"
    # 大手グループ子会社シグナル
    if re.search(r"GROUP|グループ会社|グループ子会社|\bグループ\b.*\b会社", title):
        return False, "大手グループ企業"

    # ② 従業員数（スニペットに明記されている場合）
    emp_m = re.search(r"従業員[数人]?\s*[：:約]?\s*(\d+)\s*名?", text)
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

    # ④ NG業種チェック（タイトル+スニペット）
    for ng_kw in NG_INDUSTRY_KEYWORDS:
        if ng_kw in text[:300]:
            return False, f"NG業種: {ng_kw}"

    return True, ""

# PR媒体名（クエリ・テキスト内に含まれているか判定用）
PR_MEDIA_KEYWORDS = [m.lower() for m in PR_MEDIA_NAMES] + [
    "kenja global", "賢者グローバル",
    "ビジネスクロニクル", "business chronicle",
    "newsweek", "ニューズウィーク",
    "ニューウェーブ", "new wave",
    "for japan", "leaders award",
    "smb excellent", "b-plus",
    "super ceo", "bs times",
    "ベンチャー通信", "カンパニータンク",
    "サントリーウェルネス", "健康経営認定",
    "社長名鑑", "経営者プライム", "リーダーナビ",
    "fanterview", "経営者通信",
]

# 法定外福利厚生キーワード
WELFARE_KEYWORDS = [
    "マッサージ", "整体", "酸素カプセル", "社員旅行", "食事補助", "食事手当",
    "法定外福利厚生", "リフレッシュ休暇", "スポーツジム", "フィットネス",
    "健康サポート", "鍼灸", "カイロプラクティック", "リラクゼーション",
    "ウェルネス", "健康手当", "人間ドック", "ヨガ", "ストレッチ",
    "スポーツ補助", "部活動", "サークル", "保養所", "オフィスグリコ",
    "社食", "無料ランチ", "ドリンク無料", "リモートワーク手当",
]

# 健康経営キーワード
HEALTH_MGMT_KEYWORDS = [
    "健康経営優良法人", "健康経営", "えるぼし", "くるみん",
    "健康セミナー", "健康投資", "健康支援", "ウェルビーイング",
    "健康づくり", "社員の健康", "従業員の健康", "健康促進",
    "健康経営宣言", "健康経営認定", "ブライト500",
    "ストレスチェック", "健康診断充実", "産業医",
]

# ★契約実績シグナル①: PR/広告投資 → 承認欲求・ブランド意識 → 社員への体験投資も積極的
# FBモーゲージ・グランドバリューのパターン
PR_INVESTMENT_SIGNALS = [
    "広告費", "マーケティング費", "PR費", "プロモーション",
    "テレビ出演", "テレビCM", "CM放映", "雑誌掲載", "新聞掲載",
    "メディア掲載", "メディア出演", "取材を受け", "取材いただき",
    "掲載されました", "取り上げていただ", "紹介されました",
    "アワード受賞", "表彰", "認定企業", "受賞歴",
]

# ★契約実績シグナル②: 売上拡大・高利益率
# FBモーゲージ・グランドバリュー・マブチのパターン
PROFIT_SIGNALS = [
    "売上.*拡大", "増収", "増益", "過去最高", "最高益", "売上高.*億",
    "自社ビル", "自社オフィス", "自社物件", "本社ビル", "自社所有",
    "利益率", "高収益", "黒字", "連続増収",
    "リニューアル", "移転", "拡張", "新オフィス",
]

# ★契約実績シグナル③: 健康セミナー登壇・社内健康推進
# プラグマのパターン
HEALTH_PROMOTER_SIGNALS = [
    "健康セミナー", "健康イベント", "健康講座", "セミナー 登壇",
    "健康推進", "ウェルフェア", "健康委員会", "健康推進担当",
    "産業医.*相談", "保健師", "健康経営.*推進",
    "社員.*健康.*セミナー", "健康.*研修",
]

# ★契約実績シグナル④: 経営者の健康意識・承認欲求
# レンフロジャパン・FBモーゲージのパターン
CEO_HEALTH_SIGNALS = [
    r"代表取締役.*健康", r"社長.*健康", r"代表.*想い", r"代表.*メッセージ",
    r"社長.*メッセージ", r"経営者.*健康", r"代表.*こだわり",
    r"社長インタビュー", r"代表インタビュー", r"経営者インタビュー",
    r"社長.*福利厚生", r"代表.*社員.*幸せ", r"社長.*従業員.*大切",
    r"経営者.*ウェルビーイング",
]

# ★契約実績シグナル⑤: 高利益率B2B業種（フィジカルケアが刺さりやすい）
# 情報通信・金融・人材・商社・コンサル・士業
HIGH_MARGIN_INDUSTRY_KEYWORDS = [
    "情報通信", "システム", "ソフトウェア", "IT", "SaaS", "クラウド", "DX",
    "金融", "ファイナンス", "モーゲージ", "証券", "保険", "ファンド",
    "人材", "派遣", "HR", "採用支援", "リクルート",
    "商社", "専門商社", "卸売", "貿易",
    "コンサルティング", "コンサル", "経営コンサル",
    "社労士", "社会保険労務士", "税理士", "会計士", "弁護士",
    "広告", "PR", "マーケティング", "クリエイティブ",
]

# ★フィジカルケア未着手シグナル（既存福利充実だがマッサージ系なし → 提案余地大）
# 食事・イベント系はあるがストレッチ・マッサージ系がないパターンはスコアで反映
EXISTING_WELFARE_WITHOUT_PHYSICAL = [
    "食事補助", "社食", "社員旅行", "イベント", "スポーツジム",
    "フィットネス", "ヨガ", "健康診断", "人間ドック",
]
PHYSICAL_CARE_KEYWORDS = [
    "マッサージ", "整体", "ストレッチ", "鍼灸", "カイロ",
    "フィジカル", "ボディケア", "リラクゼーション",
]


def _contains_pr_media(text: str, query: str) -> tuple[bool, str]:
    """テキストまたはクエリにPR媒体が含まれるか判定"""
    combined = (text + " " + query).lower()
    for kw in PR_MEDIA_KEYWORDS:
        if kw in combined:
            return True, kw
    return False, ""


def evaluate_rank(
    company_info: dict,
    search_results: list[dict],
    page_text: str = "",
) -> dict:
    """
    企業のランクを判定する（offi-stretch契約実績ベース精緻化版）

    採点方式:
    - 各項目1点（最大12点）
    - PR媒体クエリ経由は+2点ボーナス
    - A: 6点以上 / B: 4〜5点 / C: 2〜3点
    """
    score = 0
    reasons = []

    search_query = search_results[0].get("search_query", "") if search_results else ""
    all_search_urls = [r.get("url", "") for r in search_results]
    all_search_text = " ".join(
        r.get("title", "") + " " + r.get("snippet", "")
        for r in search_results
    )
    full_text = all_search_text + " " + page_text + " " + company_info.get("company_name", "")

    # ===== NGチェック =====

    if re.search(r"東証|上場企業|TSE|NYSE|NASDAQ|証券コード|プライム市場|スタンダード市場|グロース市場", full_text):
        return {"rank": "NG", "score": 0, "reasons": [], "ng_reason": "上場企業"}

    company_name = company_info.get("company_name", "")
    # ホールディングス・大規模グループ会社
    if re.search(r"ホールディングス|Holdings", company_name):
        return {"rank": "NG", "score": 0, "reasons": [], "ng_reason": "ホールディングス（大規模企業）"}

    company_context = company_name + " " + all_search_text[:400]
    for ng_kw in NG_INDUSTRY_KEYWORDS:
        if ng_kw in company_context:
            return {"rank": "NG", "score": 0, "reasons": [], "ng_reason": f"NG業種: {ng_kw}"}

    emp_match = re.search(r"従業員[数人]?\s*[：:\s]*(\d+)\s*名?", full_text)
    if emp_match:
        count = int(emp_match.group(1))
        if count > 200:
            return {"rank": "NG", "score": 0, "reasons": [], "ng_reason": f"従業員{count}名（200名超）"}
        if count < 10:
            return {"rank": "NG", "score": 0, "reasons": [], "ng_reason": f"従業員{count}名（下限未満）"}

    branch_match = re.search(r"(\d+)\s*拠点", full_text)
    if branch_match and int(branch_match.group(1)) >= 3:
        return {"rank": "NG", "score": 0, "reasons": [], "ng_reason": f"{branch_match.group(1)}拠点（上限超）"}

    # ===== ボーナス: PR媒体クエリ経由（+2点）=====
    is_pr_query, matched_media = _contains_pr_media("", search_query)
    if is_pr_query:
        score += 2
        reasons.append(f"★PR媒体クエリ経由: {matched_media}（+2点）")

    # ===== ボーナス: 媒体リストページ経由（+2点）=====
    # list_page_agent 経由で発見した企業は source_list_url が設定されている
    source_list_url = search_results[0].get("source_list_url", "") if search_results else ""
    if source_list_url:
        # 健康経営優良法人リスト経由 → 認定確定（+2点）
        if any(d in source_list_url for d in HEALTH_CERT_DOMAINS):
            score += 2
            reasons.append("★健康経営優良法人認定（経産省リスト経由）（+2点）")
        # PR媒体リストページ経由 → 掲載確定（is_pr_query と重複しない場合のみ）
        elif not is_pr_query and any(d in source_list_url for d in PR_MEDIA_DOMAINS):
            score += 2
            src_domain = source_list_url.split("/")[2] if "/" in source_list_url else source_list_url
            reasons.append(f"★PR媒体リスト経由: {src_domain}（+2点）")

    # ===== 項目1: PR有料媒体掲載（承認欲求・ブランド意識のシグナル）=====
    matched_pr_url = [d for d in PR_MEDIA_DOMAINS if any(d in u for u in all_search_urls)]
    is_pr_text, pr_text_kw = _contains_pr_media(all_search_text, "")
    if matched_pr_url or is_pr_text:
        score += _w("PR媒体掲載")
        label = matched_pr_url[0] if matched_pr_url else pr_text_kw
        reasons.append(f"PR媒体掲載: {label}")

    # ===== 項目2: 健康経営メディア掲載 =====
    matched_health_url = [d for d in HEALTH_MEDIA_DOMAINS if any(d in u for u in all_search_urls)]
    health_media_in_text = any(kw in full_text for kw in ["アクサ生命", "ボイスレポート", "大同生命", "健康経営の広場"])
    if matched_health_url or health_media_in_text:
        score += _w("健康経営メディア掲載")
        reasons.append("健康経営メディア掲載")

    # ===== 項目3: 法定外福利厚生が充実（フィジカルケア以外）=====
    found_welfare = [k for k in WELFARE_KEYWORDS if k in full_text]
    if found_welfare:
        score += _w("法定外福利厚生")
        reasons.append(f"法定外福利厚生: {', '.join(found_welfare[:3])}")

    # ===== 項目4: フィジカルケア未着手ボーナス =====
    # 他の福利充実 + マッサージ/ストレッチ系なし → 提案余地大（Aランク押し上げ）
    has_other_welfare = any(k in full_text for k in EXISTING_WELFARE_WITHOUT_PHYSICAL)
    has_physical_care = any(k in full_text for k in PHYSICAL_CARE_KEYWORDS)
    if has_other_welfare and not has_physical_care:
        score += _w("フィジカルケア未着手")
        reasons.append("★福利厚生充実だがフィジカルケア未着手（提案余地大）")

    # ===== 項目5: 健康経営への注力 =====
    found_health = [k for k in HEALTH_MGMT_KEYWORDS if k in full_text]
    if found_health:
        score += _w("健康経営注力")
        reasons.append(f"健康経営注力: {', '.join(found_health[:2])}")

    # ===== 項目6: 健康セミナー登壇・社内健康推進担当（プラグマ型）=====
    found_promoter = [k for k in HEALTH_PROMOTER_SIGNALS if k in full_text]
    if found_promoter:
        score += _w("健康推進・セミナー")
        reasons.append(f"健康推進担当・セミナー登壇: {', '.join(found_promoter[:2])}")

    # ===== 項目7: 経営者の健康意識・承認欲求シグナル（レンフロ・FB型）=====
    found_ceo = [p for p in CEO_HEALTH_SIGNALS if re.search(p, full_text)]
    if found_ceo:
        score += _w("経営者の健康意識")
        reasons.append("経営者の健康意識・メディア露出")

    # ===== 項目8: PR/広告積極投資（FBモーゲージ・グランドバリュー型）=====
    found_pr_invest = [k for k in PR_INVESTMENT_SIGNALS if k in full_text]
    if found_pr_invest:
        score += _w("PR広告投資")
        reasons.append(f"PR/広告投資積極: {', '.join(found_pr_invest[:2])}")

    # ===== 項目9: 売上拡大・自社ビル・高利益シグナル（マブチ型）=====
    found_profit = []
    for k in PROFIT_SIGNALS:
        if ".*" in k:
            if re.search(k, full_text):
                found_profit.append(k.replace(".*", ""))
        elif k in full_text:
            found_profit.append(k)
    if found_profit:
        score += _w("成長・自社ビル")
        reasons.append(f"投資・成長・自社ビル: {', '.join(found_profit[:2])}")

    # ===== 項目10: 高利益率B2B業種（フィジカルケアが特に刺さる業種）=====
    industry = company_info.get("industry", "")
    found_high_margin = any(kw in full_text or kw in industry for kw in HIGH_MARGIN_INDUSTRY_KEYWORDS)
    if found_high_margin:
        score += _w("高利益率B2B業種")
        reasons.append("高利益率B2B業種（IT/金融/人材/商社/コンサル/士業）")

    # ===== 項目11: 従業員数20〜100名（offi-stretch契約実績サイズ）=====
    if emp_match:
        count = int(emp_match.group(1))
        if 20 <= count <= 100:
            score += _w("契約実績サイズ")
            reasons.append(f"契約実績サイズ: 従業員{count}名")

    # ===== 項目12: 単一・少拠点（固定オフィス訪問可能）=====
    has_multi = any(kw in full_text for kw in ["支店", "支社", "営業所", "出張所"])
    if not has_multi:
        score += _w("単一拠点")
        reasons.append("単一拠点（固定オフィス訪問可）")

    # ===== ランク決定 =====
    if score >= 6:
        rank = "A"
    elif score >= 4:
        rank = "B"
    elif score >= 2:
        rank = "C"
    else:
        rank = "C"

    logger.debug(f"ランク: {rank}({score}点) - {reasons}")
    return {"rank": rank, "score": score, "reasons": reasons, "ng_reason": ""}
