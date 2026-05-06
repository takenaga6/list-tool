import os
import json
import re

# .envファイルがあれば読み込む（ローカル開発用）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# HubSpot APIトークン（環境変数から取得）
HUBSPOT_TOKEN = os.environ.get("HUBSPOT_TOKEN", "")

# Google Custom Search API（企業HP検索用）
GOOGLE_CSE_API_KEY = os.environ.get("GOOGLE_CSE_API_KEY", "")
GOOGLE_CSE_CX = os.environ.get("GOOGLE_CSE_CX", "")

# 出力ファイル
# Render Disk を使う場合は環境変数 OUTPUT_DIR にマウントパスを設定する
# 例: OUTPUT_DIR=/opt/render/project/src/output
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")
NG_LIST_FILE = os.path.join(OUTPUT_DIR, "ng_list.csv")
RESULTS_FILE = os.path.join(OUTPUT_DIR, "results.csv")
RESULTS_WITH_QUERY_FILE = os.path.join(OUTPUT_DIR, "results_with_query.csv")
LOG_FILE = os.path.join(OUTPUT_DIR, "tool.log")
LEARNED_EXCLUDE_FILE = os.path.join(OUTPUT_DIR, "learned_exclude.json")  # 自動学習した除外ドメイン
PROCESSED_URLS_FILE = os.path.join(OUTPUT_DIR, "processed_urls.json")    # 処理済みURL（サイクルまたぎ重複防止）
DOMAIN_FAIL_FILE = os.path.join(OUTPUT_DIR, "domain_fail_stats.json")    # 失敗カウンター
EXCLUDE_LIST_CSV = os.path.join(OUTPUT_DIR, "exclude_list.csv")          # 手動編集可能な除外ドメインCSV
FEEDBACK_FILE = os.path.join(OUTPUT_DIR, "feedback.csv")                 # テレアポ結果フィードバック
MEETINGS_FILE = os.path.join(OUTPUT_DIR, "meetings.csv")                 # 商談記録
CALL_LIST_FILE = os.path.join(OUTPUT_DIR, "call_list.csv")               # 架電先リスト
IMPORT_SETTINGS_FILE = os.path.join(OUTPUT_DIR, "import_settings.json") # インポート設定の記憶
USER_FEEDBACK_FILE   = os.path.join(OUTPUT_DIR, "user_feedback.csv")   # 利用者フィードバック

# ── シグナルキー（6本・Notion公式定義） ─────────────────────────────
# S1 or S2 に該当した時点でBランク確定（問答無用）
SIGNAL_KEYS = [
    "PR有料媒体掲載",       # S1: 単独でB確定
    "健康経営メディア掲載",  # S2: 単独でB確定
    "法定外福利厚生",        # S3
    "健康経営注力",          # S4
    "HPリニューアル",        # S5
    "自社ビル",              # S6
]

# S1: PR有料媒体リストページ（静的HTML・一覧スクレイプ）
S1_MEDIA_LIST_URLS: list[str] = [
    "https://superceo.jp/list/company",       # SUPER CEO
    "https://business-plus.net/interview/",   # B-PLUS
]

# S2: 健康経営メディアリストページ（一覧スクレイプ → S2確定）
S2_MEDIA_LIST_URLS: list[str] = [
    "https://kenko-keiei.jp/houjin_list/",       # 健康経営優良法人（Excel自動DL）
    "https://www.voice-report.jp/",              # アクサ生命ボイスレポート
    "https://kenkoukeiei-media.com/",            # 健康経営の広場
    "https://daido-kenco-award.jp/companies/",   # 大同生命
]

# ランク閾値
RANK_A_EXTRA_SIGNALS = 2   # S1/S2あり + S3〜S6がこの数以上 → A
RANK_B_MIN_SIGNALS   = 3   # S1/S2なしの場合のB最低ライン（S3〜S6の合計）
MIN_REGISTER_SIGNALS = 3   # HubSpot登録最低ライン（or S1/S2あり）


def load_exclude_list_csv() -> set[str]:
    """
    除外ドメインを3ソースから統合して返す。
    1. learned_exclude.json  （自動学習: スクレイプ失敗3回）
    2. exclude_list.csv      （手動追加・承認時除外・監査NG）
    3. ng_list.csv           （過去にNGになった企業のドメインを自動学習）
    """
    import csv as _csv
    from urllib.parse import urlparse as _urlparse

    domains = load_learned_excludes()  # 自動学習分

    # exclude_list.csv
    if os.path.exists(EXCLUDE_LIST_CSV):
        try:
            with open(EXCLUDE_LIST_CSV, "r", encoding="utf-8-sig") as f:
                reader = _csv.DictReader(f)
                for row in reader:
                    d = row.get("ドメイン", "").strip()
                    if d:
                        domains.add(d)
        except Exception:
            pass

    # ng_list.csv → 企業URLからドメインを抽出して除外学習
    if os.path.exists(NG_LIST_FILE):
        try:
            with open(NG_LIST_FILE, "r", encoding="utf-8-sig") as f:
                reader = _csv.DictReader(f)
                for row in reader:
                    url = row.get("企業URL", "").strip()
                    if url:
                        parsed = _urlparse(url)
                        domain = parsed.netloc.replace("www.", "").strip()
                        if domain:
                            domains.add(domain)
        except Exception:
            pass

    return domains


def add_to_exclude_csv(domain: str, reason: str = "手動追加"):
    """exclude_list.csv にドメインを手動追加する"""
    import csv as _csv
    from datetime import datetime as _dt
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    file_exists = os.path.exists(EXCLUDE_LIST_CSV) and os.path.getsize(EXCLUDE_LIST_CSV) > 0
    with open(EXCLUDE_LIST_CSV, "a", newline="", encoding="utf-8-sig") as f:
        writer = _csv.DictWriter(f, fieldnames=["ドメイン", "理由", "追加日"])
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "ドメイン": domain,
            "理由": reason,
            "追加日": _dt.now().strftime("%Y-%m-%d"),
        })


def _find_query_for_company(company_name: str) -> str:
    """results_with_query.csv から会社名に紐づく検索クエリを返す。

    最新の行を優先し、見つからない場合は空文字を返す。
    """
    if not company_name:
        return ""
    try:
        import csv as _csv
        with open(RESULTS_WITH_QUERY_FILE, "r", encoding="utf-8-sig") as f:
            reader = _csv.DictReader(f)
            query = ""
            for row in reader:
                if row.get("会社名", "").strip() == company_name.strip():
                    query = row.get("検索クエリ", "")
            return query or ""
    except Exception:
        return ""


def _find_domain_for_company(company_name: str) -> str:
    """results_with_query.csv から会社名に紐づく企業ドメインを返す。"""
    if not company_name:
        return ""
    try:
        import csv as _csv
        from urllib.parse import urlparse as _urlparse
        with open(RESULTS_WITH_QUERY_FILE, "r", encoding="utf-8-sig") as f:
            reader = _csv.DictReader(f)
            domain = ""
            for row in reader:
                if row.get("会社名", "").strip() == company_name.strip():
                    url = row.get("企業URL", "")
                    if url:
                        parsed = _urlparse(url)
                        domain = parsed.netloc.replace("www.", "").strip()
            return domain or ""
    except Exception:
        return ""


def record_feedback(
    company_name: str,
    approach_result: str,
    got_appointment: bool = False,
    rejection_reason: str = "",
    temperature: str = "",
    company_scale: str = "",
    ng_reason: str = "",
    good_points: str = "",
    memo: str = "",
    tantosha: str = "",   # 架電担当者名
):
    """
    テレアポ結果をfeedback.csvに記録する。
    精度向上サイクルの素材として蓄積する。

    Args:
        company_name: 会社名
        approach_result: 結果（アポ獲得/断り/留守/後日/その他）
        got_appointment: アポ獲得したか
        rejection_reason: 断り理由（既導入/興味なし/予算なし/タイミング/担当不在等）
        temperature: 温度感（高/中/低）
        company_scale: 企業規模（大/中/小/不明）
        ng_reason: NG理由（規模NG/業種NG/メディアNGなど）
        good_points: 反応が良かったポイント
        memo: その他メモ
    """
    import csv as _csv
    from datetime import datetime as _dt
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    file_exists = os.path.exists(FEEDBACK_FILE) and os.path.getsize(FEEDBACK_FILE) > 0
    fieldnames = [
        "記録日", "会社名", "アプローチ結果", "アポ獲得",
        "規模", "NG理由", "断り理由", "温度感", "検索クエリ",
        "反応が良かったポイント", "メモ", "担当名"
    ]

    # 既存のfeedback.csvに列が足りない場合はヘッダーを書き換えて追加（既存データは保持）
    if file_exists:
        try:
            with open(FEEDBACK_FILE, "r", encoding="utf-8-sig") as f:
                first_line = f.readline().strip()
            existing_cols = first_line.split(",")
            if "検索クエリ" not in existing_cols or "担当名" not in existing_cols:
                # 既存データを読み込み直し（ヘッダーあり）
                with open(FEEDBACK_FILE, "r", encoding="utf-8-sig") as f:
                    reader = _csv.DictReader(f)
                    rows = list(reader)
                # ヘッダーを含めて上書き（既存行に検索クエリ列を追加）
                with open(FEEDBACK_FILE, "w", newline="", encoding="utf-8-sig") as f:
                    writer = _csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for row in rows:
                        if "検索クエリ" not in row:
                            row["検索クエリ"] = ""
                        if "担当名" not in row:
                            row["担当名"] = ""
                        writer.writerow(row)
        except Exception:
            pass

    with open(FEEDBACK_FILE, "a", newline="", encoding="utf-8-sig") as f:
        writer = _csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        query = _find_query_for_company(company_name)
        writer.writerow({
            "記録日":           _dt.now().strftime("%Y-%m-%d"),
            "会社名":           company_name,
            "アプローチ結果":    approach_result,
            "アポ獲得":         "はい" if got_appointment else "いいえ",
            "規模":             company_scale,
            "NG理由":          ng_reason,
            "断り理由":         rejection_reason,
            "温度感":           temperature,
            "検索クエリ":       query,
            "反応が良かったポイント": good_points,
            "メモ":             memo,
            "担当名":           tantosha,
        })

    # 見込み/NG情報を学習に活用する（検索クエリに連携）
    try:
        from agents.keyword_agent import record_ng, record_rank_result

        if query:
            # 低見込み(C/なし) or 断りは NG としてクエリ学習に反映
            if temperature in ("C", "なし", "") or approach_result == "断り":
                record_ng(query)
            # アポ獲得 or Aランクは良いクエリとして記録
            if got_appointment or temperature == "A":
                record_rank_result(query, "A")
            elif temperature == "B":
                record_rank_result(query, "B")

        # ドメインを除外リストに入れて今後の検索から除外
        if temperature in ("C", "なし", "") or approach_result == "断り" or (ng_reason and ng_reason != "なし"):
            domain = _find_domain_for_company(company_name)
            if domain:
                excludes = load_exclude_list_csv()
                if domain not in excludes:
                    add_to_exclude_csv(domain, f"見込み低 / {ng_reason or approach_result}")
    except Exception:
        pass


def record_meeting(
    company_name: str,
    contact_name: str,
    meeting_date: str,
    phase: str,
    result: str,
    contracted: bool = False,
    next_action: str = "",
    deal_size: str = "",
    memo: str = "",
    tantosha: str = "",   # パスアポ対応者名
    extra_fields: dict | None = None,
):
    """商談結果を meetings.csv に記録する。extra_fields でカスタム項目を追加できる。"""
    import csv as _csv
    from datetime import datetime as _dt
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    extra = extra_fields or {}

    # 既存CSVのヘッダーを取得して列を引き継ぐ
    existing_fields: list[str] = []
    if os.path.exists(MEETINGS_FILE) and os.path.getsize(MEETINGS_FILE) > 0:
        try:
            with open(MEETINGS_FILE, "r", encoding="utf-8-sig") as f:
                reader = _csv.reader(f)
                existing_fields = next(reader, [])
        except Exception:
            pass

    base_fieldnames = [
        "記録日", "商談日", "会社名", "担当者名", "フェーズ",
        "商談結果", "契約", "次のアクション", "規模感・金額", "メモ", "担当名"
    ]
    all_fields = list(existing_fields) if existing_fields else list(base_fieldnames)
    for key in extra:
        if key not in all_fields:
            all_fields.append(key)

    file_exists = os.path.exists(MEETINGS_FILE) and os.path.getsize(MEETINGS_FILE) > 0

    with open(MEETINGS_FILE, "a", newline="", encoding="utf-8-sig") as f:
        writer = _csv.DictWriter(f, fieldnames=all_fields, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        row: dict = {
            "記録日":       _dt.now().strftime("%Y-%m-%d"),
            "商談日":       meeting_date,
            "会社名":       company_name,
            "担当者名":     contact_name,
            "フェーズ":     phase,
            "商談結果":     result,
            "契約":         "はい" if contracted else "いいえ",
            "次のアクション": next_action,
            "規模感・金額":  deal_size,
            "メモ":         memo,
            "担当名":       tantosha,
        }
        row.update(extra)
        writer.writerow(row)


def load_learned_excludes() -> set[str]:
    """自動学習した除外ドメインを読み込む"""
    if os.path.exists(LEARNED_EXCLUDE_FILE):
        try:
            with open(LEARNED_EXCLUDE_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def record_domain_fail(domain: str, threshold: int = 3):
    """
    ドメインの失敗カウントを記録し、threshold回以上失敗したら自動除外リストに追加。

    Args:
        domain: 失敗したドメイン
        threshold: 何回失敗で自動除外するか（デフォルト3回）
    """
    if not domain:
        return
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 失敗カウント読み込み
    fail_stats = {}
    if os.path.exists(DOMAIN_FAIL_FILE):
        try:
            with open(DOMAIN_FAIL_FILE, "r", encoding="utf-8") as f:
                fail_stats = json.load(f)
        except Exception:
            pass

    fail_stats[domain] = fail_stats.get(domain, 0) + 1

    # threshold以上でlearned_excludeに追加
    if fail_stats[domain] >= threshold:
        excludes = load_learned_excludes()
        excludes.add(domain)
        with open(LEARNED_EXCLUDE_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(excludes), f, ensure_ascii=False, indent=2)

    # カウント保存
    with open(DOMAIN_FAIL_FILE, "w", encoding="utf-8") as f:
        json.dump(fail_stats, f, ensure_ascii=False, indent=2)

# 並列スクレイピング数（増やすと速くなるがブロックされやすい）
MAX_WORKERS = 5

# Google検索1クエリあたりの取得件数
MAX_RESULTS_PER_QUERY = 50

# 検索クールダウン（秒）Googleブロック防止
SEARCH_DELAY_MIN = 3
SEARCH_DELAY_MAX = 5

# 検索期間の選択肢
TIME_PERIODS = {
    "1": "1週間",
    "2": "2週間",
    "3": "1カ月以内",
    "4": "2カ月以内",
    "5": "3カ月以内",
    "6": "6カ月以内",
    "7": "9カ月以内",
    "8": "1年以内",
}

# Google tbs パラメータ（期間フィルター）
TIME_PERIOD_TBS = {
    "1週間":    "qdr:w",
    "2週間":    "qdr:w2",
    "1カ月以内": "qdr:m",
    "2カ月以内": "qdr:m2",
    "3カ月以内": "qdr:m3",
    "6カ月以内": "qdr:m6",
    "9カ月以内": "qdr:m9",
    "1年以内":  "qdr:y",
}

# 媒体名 → ドメインのマッピング（媒体クエリフィルタリング用）
MEDIA_NAME_TO_DOMAIN = {
    "KENJA GLOBAL":           "kenja.tv",
    "賢者グローバル":           "kenja.tv",
    "エコノミスト ビジネスクロニクル": "business-chronicle.com",
    "ビジネスクロニクル":        "business-chronicle.com",
    "エコノミスト REC":         "weekly-economist.com",
    "Newsweek WEB":           "newsweekjapan.jp",
    "Newsweek":               "newsweekjapan.jp",
    "時代のニューウェーブ":       "j-newwave.com",
    "For JAPAN":              "forjapan-project.com",
    "Leaders AWARD":          "leaders-award.jp",
    "SMB Excellent AWARD":    "smbexcellentcompany.com",
    "B-PLUS":                 "business-plus.net",
    "SUPER CEO":              "superceo.jp",
    "BS TIMES":               "bs-times.com",
    "ベンチャー通信":            "v-tsushin.jp",
    "カンパニータンク":          "challenge-plus.jp",
    "アクサ生命ボイスレポート":    "voice-report.jp",
    "アクサ生命":               "voice-report.jp",
    "ボイスレポート":            "voice-report.jp",
    "健康経営の広場":            "kenkoukeiei-media.com",
    "大同生命":                 "daido-kenco-award.jp",
    # 新規追加媒体
    "社長名鑑":                 "shachomeikan.jp",
    "経営者プライム":            "keieisha-prime.com",
    "リーダーナビ":              "leader-navi.com",
    "Fanterview":              "fanterview.net",
    "経営者通信":               "k-tsushin.jp",
    "先見経済":                 "senken-keizai.co.jp",
    "企業と経営":               "kigyotokeiei.jp",
}

# PR有料媒体ドメイン（Aランク判定）
PR_MEDIA_DOMAINS = [
    "kenja.tv",
    "business-chronicle.com",
    "weekly-economist.com",
    "challenger.newsweekjapan.jp",
    "j-newwave.com",
    "forjapan-project.com",
    "leaders-award.jp",
    "smbexcellentcompany.com",
    "business-plus.net",
    "superceo.jp",
    "bs-times.com",
    "1242.com",
    "v-tsushin.jp",
    "challenge-plus.jp",
    # 新規追加
    "shachomeikan.jp",
    "keieisha-prime.com",
    "leader-navi.com",
    "fanterview.net",
    "k-tsushin.jp",
    "senken-keizai.co.jp",
    "kigyotokeiei.jp",
]

# 健康経営メディアドメイン（Aランク判定）
HEALTH_MEDIA_DOMAINS = [
    "voice-report.jp",
    "kenkoukeiei-media.com",
    "daido-kenco-award.jp",
]

# 検索時に除外された URL を保存する（調査・改善用）
REJECTED_SEARCH_URLS_FILE = os.path.join(OUTPUT_DIR, "rejected_search_urls.csv")

# NG業種キーワード
NG_INDUSTRY_KEYWORDS = [
    # 建設・土木（Notion公式NG）
    "建設", "土木", "工務店", "ゼネコン",
    # 運送・運輸（Notion公式NG）
    "運送", "運輸", "宅配", "トラック", "引越",
    # 医療・福祉
    "病院", "クリニック", "診療所", "薬局", "調剤", "医療法人",
    "介護", "デイサービス", "保育", "幼稚園",
    # 店舗展開型toC（飲食・小売・美容）
    "スーパー", "コンビニ", "飲食店", "レストラン", "居酒屋",
    "美容院", "美容室", "ネイルサロン",
    "小売", "量販店", "ドラッグストア",
    # 警備・清掃（現場常駐型）
    "警備", "ガードマン", "清掃業", "廃棄物",
    # SES・常駐（客先常駐でオフィスに社員がいない）
    "SES", "システムエンジニアリングサービス", "常駐", "派遣エンジニア",
    # フランチャイズチェーン（店舗型toC）
    "ファミリーマート", "セブンイレブン", "ローソン", "ミニストップ",
    "マクドナルド", "すき家", "吉野家", "松屋", "サイゼリヤ",
]

# 大企業ドメイン（規模が合わないと判断して除外したい代表的なドメイン）
LARGE_COMPANY_DOMAINS = [
    "fanuc.co.jp",
    "rizapgroup.com",
]

# 小規模企業ドメイン（規模が小さくて提案価値が低いため除外）
SMALL_COMPANY_DOMAINS = [
    "nagata-sho.com",
    "ginza-kigyo.com",
]

# 経産省健康経営優良法人認定リストのソースドメイン
# このドメイン経由で発見した企業は rank_agent で +2点ボーナス（認定確定）
HEALTH_CERT_DOMAINS = [
    "kenko-keiei.jp",   # 健康経営優良法人認定事務局ポータル（経産省）
]

# 媒体リストページURL（後方互換用・S1+S2を統合した全リスト）
# main.py からはこれを参照するか S1_MEDIA_LIST_URLS / S2_MEDIA_LIST_URLS を直接使う
MEDIA_LIST_URLS: list[str] = S2_MEDIA_LIST_URLS + S1_MEDIA_LIST_URLS

# ── 除外済み企業ファイル（excluded_companies.json）──────────────────
# NG判定・HubSpot重複で弾かれた企業を蓄積し、次回実行時にHTTPリクエスト不要でスキップする

EXCLUDED_COMPANIES_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "excluded_companies.json"
)

_excluded_cache: set[str] | None = None  # プロセス内インメモリキャッシュ


def _load_excluded_cache() -> set[str]:
    """excluded_companies.json を読み込みキャッシュを初期化する（初回のみIOアクセス）"""
    global _excluded_cache
    if _excluded_cache is None:
        try:
            if os.path.exists(EXCLUDED_COMPANIES_FILE):
                with open(EXCLUDED_COMPANIES_FILE, "r", encoding="utf-8") as f:
                    entries = json.load(f)
                _excluded_cache = {e["company_name"] for e in entries if e.get("company_name")}
            else:
                _excluded_cache = set()
        except Exception:
            _excluded_cache = set()
    return _excluded_cache


def is_excluded_company(company_name: str) -> bool:
    """会社名が除外済みリストに登録されているか確認する（HTTPリクエスト不要）"""
    if not company_name:
        return False
    return company_name in _load_excluded_cache()


def add_to_excluded_companies(company_name: str, reason: str):
    """
    NG/重複企業を excluded_companies.json に追記する。
    既に登録済みの場合は何もしない。キャッシュも同時更新。
    """
    if not company_name:
        return
    cache = _load_excluded_cache()
    if company_name in cache:
        return  # 重複追記しない

    entries: list = []
    if os.path.exists(EXCLUDED_COMPANIES_FILE):
        try:
            with open(EXCLUDED_COMPANIES_FILE, "r", encoding="utf-8") as f:
                entries = json.load(f)
        except Exception:
            entries = []

    from datetime import datetime as _dt
    entries.append({
        "company_name": company_name,
        "reason":       reason,
        "excluded_at":  _dt.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    try:
        with open(EXCLUDED_COMPANIES_FILE, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        cache.add(company_name)  # インメモリキャッシュも更新
    except Exception:
        pass

# ── media_config.json からカスタム媒体を自動マージ ────────────────────
# 起動時に一度だけ実行され、S1/S2/MEDIA_LIST_URLS を自動拡張する。
# スクレイピングロジックはこれらの変数を参照するだけなので変更不要。
_MEDIA_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media_config.json")
if os.path.exists(_MEDIA_CONFIG_FILE):
    try:
        _mc_data = json.load(open(_MEDIA_CONFIG_FILE, encoding="utf-8"))
        for _mc_entry in _mc_data.get("S1", []):
            _mc_url = _mc_entry.get("url", "")
            if _mc_url and _mc_url not in S1_MEDIA_LIST_URLS:
                S1_MEDIA_LIST_URLS.append(_mc_url)
        for _mc_entry in _mc_data.get("S2", []):
            _mc_url = _mc_entry.get("url", "")
            if _mc_url and _mc_url not in S2_MEDIA_LIST_URLS:
                S2_MEDIA_LIST_URLS.append(_mc_url)
        # MEDIA_LIST_URLS を再構築（S2 → S1 の順序を維持）
        MEDIA_LIST_URLS[:] = S2_MEDIA_LIST_URLS + S1_MEDIA_LIST_URLS
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════
# S1-B: 検索型媒体（一覧ページなし → Google検索で掲載企業を抽出）
# ═══════════════════════════════════════════════════════════
S1_SEARCH_MEDIA = [
    "KENJA GLOBAL",
    "エコノミスト ビジネスクロニクル",
    "エコノミスト REC",
    "Newsweek Challenger",
    "時代のニューウェーブ",
    "For JAPAN",
    "Leaders AWARD",
    "SMB Excellent AWARD",
    "BS TIMES",
    "ベンチャー通信",
    "カンパニータンク",
]

# 検索キーワードテンプレート（{media}が媒体名に置換される）
SEARCH_TEMPLATES = [
    "{media} 株式会社",
    "{media} 取り上げられました",
    "{media} 掲載されました",
    "{media} インタビュー",
    "{media} 代表取締役",
    "{media} 代表 インタビュー",
    "{media} 掲載企業",
    "{media} 出演",
    "{media} 受賞",
    "{media} 選出",
]

# 47都道府県（媒体名と組み合わせて地域別検索に使用）
SEARCH_REGIONS = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県",
    "山形県", "福島県", "茨城県", "栃木県", "群馬県",
    "埼玉県", "千葉県", "東京都", "神奈川県", "新潟県",
    "富山県", "石川県", "福井県", "山梨県", "長野県",
    "岐阜県", "静岡県", "愛知県", "三重県", "滋賀県",
    "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県",
    "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県", "福岡県",
    "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県",
    "鹿児島県", "沖縄県",
]

# 検索期間フィルター（Google検索のtbs / 新しい順に試行）
SEARCH_PERIODS = [
    "qdr:w",    # 1週間以内
    "qdr:m",    # 1ヶ月以内
    "qdr:m3",   # 3ヶ月以内
    "qdr:m6",   # 6ヶ月以内
    "qdr:y",    # 1年以内
]


# ===== Phase 1: Well Body本命条件チェック用定数 =====
# 57社（継続25/非継続32）の分析結果から導出した必須条件・NG条件
# 既存のNG_INDUSTRY_KEYWORDS（line 484、26件）はそのまま維持

# 業種別NGキーワード追加分（広告/マーケ/メディア）
# 0/4で全社非継続のため除外
NG_INDUSTRY_KEYWORDS_PHASE1 = [
    "広告代理店", "総合広告", "PR会社", "マーケティング会社",
    "クリエイティブエージェンシー", "メディア運営", "出版社",
    "デジタルマーケティング", "デジタルエージェンシー",
]

# 業界平均利益率「中（レッドオーシャン）」を示す業種キーワード
# 該当社は17%しか継続しないため除外（ただし大手プライム子会社は例外）
INDUSTRY_PROFIT_MEDIUM_KEYWORDS = [
    "受託開発", "システム開発", "SI", "SIer",
    "システムインテグレ",
    "総合商社",  # 伊藤忠は例外として大手プライム子会社判定で救う
]

# 福利厚生「法定のみ」を許容する業種（士業・投資運用は例外）
# これらの業種は「法定のみ」記載でも継続率が高いため除外しない
FUKURI_LEGAL_ONLY_OK_INDUSTRY = [
    "弁護士", "法律事務所", "弁護士法人",
    "税理士", "会計事務所", "税理士法人",
    "投資運用", "資産運用", "ファミリーオフィス",
    "VC", "ベンチャーキャピタル", "PE", "プライベートエクイティ",
    "投資ファンド", "アセットマネジメント",
    "特許事務所", "弁理士",
    "社労士", "社会保険労務士",
    "司法書士", "行政書士",
]

# 大手プライム子会社判定キーワード（HP全文・会社概要で検出）
# 親会社が東証プライム上場の社は別扱い
PARENT_PRIME_KEYWORDS = [
    "東証プライム上場の", "プライム上場企業の",
    "プライム市場上場企業の", "上場企業の100%子会社",
    "100%子会社", "完全子会社",
    "の連結子会社", "の関連会社",
    "グループ会社",
    # 具体的な親会社名（東証プライム上場企業）
    "SBIホールディングス", "SBI Holdings",
    "伊藤忠商事", "三井物産", "住友商事", "丸紅", "双日", "豊田通商",
    "ANAホールディングス", "JALホールディングス",
    "SOMPOホールディングス", "東京海上ホールディングス",
    "三井住友フィナンシャル", "三菱UFJフィナンシャル", "みずほフィナンシャル",
    "野村ホールディングス", "大和証券グループ",
    "GMOインターネットグループ",
]

# ─────────────────────────────────────────────
# HP健康経営記載の検出キーワード（Phase 1必須条件として独立判定）
# 既存のHEALTH_MGMT_KEYWORDS(rank_agent.py:74)とは独立
#
# 設計思想:
#   - 既存12個（健康経営の抽象語彙）
#   - 認証系（経済産業省・厚労省の公的認証）
#   - 健康施策（法定外のみ。健康診断・産業医・ストレスチェックは法定内のため除外）
#   - 計34個
# ─────────────────────────────────────────────
HEALTH_KEIEI_REQUIRED_KEYWORDS = [
    # ── 既存キーワード（健康経営の抽象語彙） ─────────────
    "健康経営", "働き方改革", "従業員の健康",
    "ホワイト500", "ブライト500", "健康経営優良法人",
    "ウェルビーイング", "Well-being", "well-being",
    "ウェルネス経営",
    "従業員のwell", "社員のwell",

    # ── 認証系（経済産業省の健康経営認定）─────────────
    # 健康経営優良法人は年度別表記もカバー
    "健康経営優良法人2024",
    "健康経営優良法人2025",
    "健康経営優良法人2026",
    "ネクストブライト1000",      # 中小規模501-1500位
    "健康経営銘柄",              # 東証上場企業

    # ── 認証系（厚生労働省の関連認定）─────────────
    # 49社契約企業データで継続率に効果あり
    "ユースエール",              # 若者雇用優良企業認定
    "プラチナくるみん",          # 子育て支援・上位認定（通常くるみんは除外）
    "えるぼし",                  # 女性活躍認定
    "プラチナえるぼし",          # 女性活躍・上位認定
    "安全衛生優良企業マーク",    # SHEM（安全衛生優良企業マーク推進機構）

    # ── 健康施策（法定外のみ）──────────────────────────
    # 法定内（健康診断・産業医・ストレスチェック）は除外
    "脳ドック",                  # 法定外・早期発見施策
    "がん検診",                  # 法定外・福利厚生
    "人間ドック",                # 法定外・健康増進
    "メンタルヘルスケア",        # 一般的施策名
    "メンタルヘルス",            # 包括的キーワード
    "健康保険組合",              # 大手企業の健康施策の中核
    "保健指導",                  # 法定外保健指導
    "健康増進",
    "健康配慮",
    "従業員健康",
    "社員健康",
    "健康支援",
    "健康サポート",
]


# ─────────────────────────────────────────────
# deep_scraper_agent 用の広めワード
#
# 設計思想:
#   採用ページ・CSRページ・福利厚生ページ × 広めワード
#   でコンテキスト×ワードのかけ算で精度を出す。
#
#   通常: 全ページ × 精密ワード（健康経営優良法人など固有名詞）
#   ↓
#   この設計: 採用/CSR/福利厚生ページ × 「健康」など広めワード
#
#   理由:
#   - 採用ページに「健康」と書くなら、それは大体「従業員の健康に配慮」
#   - CSRページに「健康」と書くなら、それは大体「健康経営の文脈」
#   - 商品紹介ページの「健康」（健康食品等）とは違う
# ─────────────────────────────────────────────
DEEP_SCRAPE_HEALTH_KEYWORDS = [
    # ── 健康関連の広めワード ────────────────────────────
    "健康",
    "ウェルネス",
    "ウェルビーイング",

    # ── 法定外福利厚生施策（広く拾う）─────────────────
    "人間ドック",
    "脳ドック",
    "がん検診",
    "がん",
    "メンタルヘルスケア",
    "メンタルヘルス",
    "マッサージ",
    "整体",
    "酸素カプセル",
    "ジム",
    "フィットネス",
    "ヨガ",
    "リフレッシュ休暇",
    "保養所",
    "社員旅行",
    "食事補助",
]

# HP採用情報の検出キーワード（採用ページの存在確認）
RECRUIT_PAGE_REQUIRED_KEYWORDS = [
    "採用情報", "採用 情報", "Recruit", "Recruiting",
    "Career", "Careers", "新卒採用", "中途採用",
    "募集要項", "求人情報",
]

# 従業員数フィルター（細分化）
# 既存の > 200 / < 10 を置き換える設定値
EMPLOYEE_RANGE_CONFIG = {
    "min_special_industry": 6,     # 6名未満は士業でもNG
    "max_special_industry": 9,     # 6-9名は士業のみOK
    "small_min": 10,               # 10名以上はOK
    "small_max": 199,              # 199名以下はOK
    "blank_zone_min": 200,         # 200-499名は空白帯NG
    "blank_zone_max": 499,
    "large_min": 500,              # 500名以上は大手プライム子会社のみOK
}


# ═══════════════════════════════════════════════════════════
# Phase 2: 必須条件 + 加点 + 減点 の3層構造（2026-04-30〜）
# 49社の契約企業分析データから導出
# Phase2_実装計画.md 参照
# ═══════════════════════════════════════════════════════════

# ── 業界利益率マッピング ─────────────────────────────
# 業種カテゴリキーワード → 利益率ランク
# 加点・減点の根拠：49社分析の継続率データ
INDUSTRY_PROFIT_MAPPING = {
    # 利益率「高/極高」（継続率83%・5/1社）→ +2点
    "high": [
        "金融", "銀行", "証券", "信託", "ローン",
        "投資運用", "資産運用", "ファミリーオフィス",
        "VC", "ベンチャーキャピタル", "PE",
        "アセットマネジメント", "投資ファンド",
        "弁護士", "法律事務所", "法律法人",
        "税理士", "会計事務所",
        "特許", "弁理士", "司法書士",
    ],
    # 利益率「中-高」「低-中」（継続率40-66%）→ +1点
    "medium-high": [
        "卸売", "商社", "商事", "商会",
        "教育", "学習塾", "予備校", "教材",
        "出版", "教育ソフト",
        "人材派遣", "人材紹介",
        "保険",
    ],
    # 利益率「中」（レッドオーシャン・継続率10%・母数19）→ -2点
    "medium": [
        "受託開発", "システム開発", "SI", "SIer",
        "システムインテグレ",
        "IT受託", "業務システム",
        "総合商社",  # ※伊藤忠等は大手プライム子会社で例外
        "広告", "メディア", "PR", "プロモーション",
        "印刷",
    ],
    # 利益率「低」（継続率33%）→ 加点なし
    "low": [
        "小売", "量販店",
        "運送", "運輸", "物流", "宅配", "トラック",
        "建設", "土木", "工務店", "ゼネコン",
    ],
}

# ── 業界離職率マッピング ─────────────────────────────
# 「中」業種は継続率15%（3/17解約・母数20で確定）→ -2点
INDUSTRY_TURNOVER_MAPPING = {
    # 離職率「低」（継続率100%・4/0社）→ +2点
    "low": [
        "金融", "銀行", "証券",
        "投資運用", "資産運用",
        "弁護士", "法律事務所",
        "税理士", "会計事務所",
        "卸売", "商社", "商事",
    ],
    # 離職率「中」（継続率15%）→ -2点
    "medium": [
        "小売", "量販店",
        "運送", "運輸", "物流",
        "建設", "土木", "工務店",
        "製造", "メーカー", "工業", "鉄工", "工場",
        "受託開発", "システム開発", "SI",
        "出版", "印刷",
    ],
    # 離職率「高」→ 必須NG業種に既に含まれる（飲食/美容/派遣等）
}

# ── 業種カテゴリ判定キーワード ─────────────────────────────
# 大分類で判定（49社分析の業種カテゴリ列を参考）
# 1社が複数カテゴリにマッチする可能性あり、最初にマッチしたカテゴリを採用
INDUSTRY_CATEGORY_KEYWORDS = {
    # +2点：継続率高（100%）
    "商社/卸売": [
        "商社", "商事", "商会", "卸売", "貿易", "輸入", "輸出",
    ],
    "金融": [
        "金融", "銀行", "証券", "信託", "ローン", "クレジット",
        "投資銀行", "信用組合", "リース",
    ],
    "教育ソフト": [
        "教育ソフト", "学習システム", "eラーニング", "教育プラットフォーム",
        "教材", "教科書", "オンライン学習",
    ],
    # +1点：継続率高（母数小）
    "人材派遣": [
        "人材派遣", "人材紹介", "派遣会社", "アウトソーシング",
    ],
    "投資運用": [
        "投資運用", "資産運用", "アセットマネジメント",
        "ファミリーオフィス", "VC", "ベンチャーキャピタル",
        "PE", "プライベートエクイティ", "投資ファンド",
    ],
    "士業": [
        "弁護士法人", "法律事務所",
        "税理士法人", "会計事務所",
        "特許事務所", "弁理士",
        "社労士", "社会保険労務士",
        "司法書士", "行政書士",
    ],
    # -2点：継続率0%（母数大で確定的）
    "製造業": [
        "製造", "メーカー", "工業", "鉄工", "工場",
        "工機", "製作所", "金属加工", "機械加工",
        "プラスチック", "化学工業", "食品製造",
    ],
    "IT/通信": [
        "IT", "情報通信", "通信",
        "ソフトウェア", "システム",
        "テレコム",
    ],
    "コンサル・サービス": [
        "コンサル", "コンサルティング",
        "経営支援", "経営コンサル",
        "業務改善",
    ],
}

# ── 都心一等地キーワード（東京・大阪等の都心一等地） ─────────────────
# 49社分析：都心一等地55%、都心Aクラス50%継続率 → +1点
PRIME_LOCATION_KEYWORDS = [
    # 東京都心一等地
    "千代田区", "中央区", "港区", "渋谷区", "新宿区",
    # 都心一等地の有名地名（区名と被らない地名のみ）
    # ※「品川」「恵比寿」は「品川区西品川」「恵比寿駅東口」等で誤判定するため除外
    "丸の内", "大手町", "六本木", "赤坂", "青山",
    "銀座", "日本橋", "虎ノ門", "麻布", "表参道",
    "原宿", "汐留",
    # 大阪都心一等地
    "梅田", "中之島", "本町",
    # その他主要都市の都心
    "名古屋市中区", "札幌市中央区",
    "福岡市中央区", "福岡市博多区",
    "横浜市西区", "京都市中京区", "京都市下京区",
]

# ── 地方・郊外キーワード（都心以外）─────────────────────
# 49社分析：地方20%、都市部0%継続率 → -1点
# 都道府県名 + 市町村名で判定（都心キーワードと矛盾しないこと）
LOCAL_LOCATION_KEYWORDS = [
    # 県名（地方）
    "北海道", "青森", "岩手", "宮城", "秋田", "山形", "福島",
    "茨城", "栃木", "群馬", "新潟", "富山", "石川", "福井",
    "山梨", "長野", "岐阜", "静岡", "三重",
    "滋賀", "奈良", "和歌山",
    "鳥取", "島根", "岡山", "広島", "山口",
    "徳島", "香川", "愛媛", "高知",
    "佐賀", "長崎", "熊本", "大分", "宮崎", "鹿児島", "沖縄",
]

# ── 採用媒体キーワード（HP本文判定）─────────────────────
# 49社分析：採用ランクS=100%継続、3媒体以上掲載=Sランク相当 → +2点
# 1〜2媒体掲載=中規模採用 → +1点
RECRUIT_MEDIA_KEYWORDS = [
    "リクナビ", "rikunabi",
    "マイナビ", "mynavi",
    "doda", "DODA",
    "engage", "エンゲージ",
    "Indeed", "indeed",
    "BIZREACH", "ビズリーチ",
    "Wantedly", "ウォンテッドリー",
    "type", "TYPE",
    "@type", "アットタイプ",
    "リクルートエージェント",
    "JACリクルートメント",
    "OpenWork",
    "en転職", "エン転職",
]

# ── 創業家オーナー判定キーワード ─────────────────────
# 49社分析：継続率20%（4/16・母数20）→ -1点
# HP本文・株主構成で「創業家オーナー」を示すキーワード
FOUNDER_OWNER_KEYWORDS = [
    "創業家", "創業者一族",
    "創業以来", "創業者の理念",
    "オーナー企業", "同族経営",
    # 持株比率明示
    "代表取締役が筆頭株主",
    "創業家が筆頭株主",
    # 単独経営者の長期在任
    "創業者代表",
]

# ── 日本語文字判定ヘルパー ─────────────────────
# search_agent.py（スニペット事前判定）と scraper_agent.py（ページ本文判定）の両方で利用
# 半角カタカナ（･-ﾟ）・全角記号（「・」「：」等）は日本語文字と見なさない
JAPANESE_MIN_CHARS_IN_SNIPPET = 1  # スニペット中の日本語文字の最小必要数（後で調整可）


def count_japanese_chars(text: str) -> int:
    """ひらがな・カタカナ・漢字の合計文字数を返す（半角カタカナ・全角記号は含まない）。
    除外: ・(U+30FB 中点)、゠(U+30A0 二重ハイフン) 等の約物。
    """
    return len(re.findall(r'[぀-ゟァ-ヺー-ヿ一-鿿]', text))


# ═══════════════════════════════════════════════════════════
# Phase 5: 新規加点シグナル S7/S8/S9/S10 のキーワード定義（2026-05-06）
# 49社契約企業データの継続率分析（v2.0 再集計・分母修正済み）から追加
# ═══════════════════════════════════════════════════════════

# S7: ISO認定キーワード（49社データで継続率2.42倍差・+2点配点の根拠）
# 継続社の67%が保有 vs 解約社の28%が保有（14社中9社 vs 24社中7社）
#
# 注: 一般語「情報セキュリティ」「品質マネジメント」「環境マネジメント」は
#     認証取得していなくてもHPに出現するため除外（v2.0で厳格化）
#     ISO番号・規格名・プライバシーマークのみ対象とする
ISO_CERT_KEYWORDS = [
    "ISO9001", "ISO 9001",          # 品質マネジメントシステム
    "ISO27001", "ISO 27001",        # 情報セキュリティマネジメント
    "ISO14001", "ISO 14001",        # 環境マネジメントシステム
    "ISO45001", "ISO 45001",        # 労働安全衛生マネジメント
    "ISO22301",                     # 事業継続マネジメント
    "ISO13485",                     # 医療機器向け品質マネジメント
    "ISMS",                         # 情報セキュリティマネジメントシステム（認証済み表記）
    "プライバシーマーク", "Pマーク", # 個人情報保護認証（JIPDEC）
]

# S8: SDGs/サステナビリティキーワード（49社データで継続率1.84倍差・+1点配点の根拠）
# 継続社の55%が保有 vs 解約社の30%が保有（14社中8社 vs 24社中7社）
#
# 注: 「カーボンニュートラル」「脱炭素」だけでは SDGs 取り組みと判定しない（v2.0で除外）
#     → 環境対応のみの企業と経営全体のサステナ取り組み企業を区別するため
SDGS_KEYWORDS = [
    "SDGs", "SDGs宣言", "SDGsパートナー", "SDGs登録",
    "サステナビリティ", "サステナブル",
    "持続可能",
    "ESG経営", "ESG取り組み",
    "サステナビリティレポート", "統合報告書",
    "TCFD",     # 気候関連財務情報開示タスクフォース
    "CDP",      # カーボン開示プロジェクト（参加企業は積極的開示層）
    "SBT認定",  # 科学的根拠に基づく排出削減目標（認定済み企業のみ）
]

# S9: 社長メッセージ × 健康記載（49社データで継続率2.46倍差・+1点配点の根拠）
# 継続社の71%が保有 vs 解約社の29%が保有（14社中10社 vs 24社中7社）
#
# 実装制約:
#   49社データの「詳細区分」列は人間が手動判定したもの。
#   キーワードマッチによる完全自動再現は不可能。
#   → 簡易版として「社長メッセージページ × 健康ワード含有」で +1点止まり。
#   （v1.0 の +2点から +1点に引き下げた理由）
#
# 判定方法（rank_agent.py の check_s9_president_message_health で実装）:
#   Step 1: scraper が取得した top_html から PRESIDENT_PAGE_PATH_KEYWORDS に
#           マッチするリンク href を探す
#   Step 2: そのページを取得し、PRESIDENT_HEALTH_KEYWORDS が1つ以上含まれるか確認
#   → 両条件を満たした場合のみ S9=True
PRESIDENT_PAGE_PATH_KEYWORDS = [
    # URL・リンクテキストの英語パターン
    "message", "greeting", "ceo", "president",
    # 日本語パターン
    "社長メッセージ", "代表挨拶", "代表メッセージ",
    "トップメッセージ", "ご挨拶", "代表者挨拶",
]
PRESIDENT_HEALTH_KEYWORDS = [
    "健康", "ウェルビーイング", "ウェルネス",
    "従業員の幸せ", "心身の健康", "ワークライフバランス",
    "健康経営",
]

# S10: 儲かっている業界フラグ（49社データで継続率3.27倍差・+3点配点の根拠）
# 以下3シグナルを1フラグに統合（個別配点より統合のほうが精度高い）:
#   - 年収レベルB以上:  継続率 73% vs 22% = 3.27倍 ← 全シグナル中最強
#   - 業界利益率高め:   継続率 67% vs 23% = 2.89倍
#   - 業界離職率低め:   継続率 62% vs 24% = 2.56倍
#
# 2段階判定（rank_agent.py の check_s10_profitable_industry で実装）:
#   Stage1: PROFITABLE_INDUSTRY_KEYWORDS にキーワードが含まれる → +1点
#           ※ Stage1 単体では継続率差 0.90倍（ほぼシグナルなし・業種マッチのみでは弱い）
#   Stage2: Stage1 + 企業規模・資本金・創業家フィルター → +3点
#           ※ Stage2 達成時の継続率差 3.27倍（最強シグナル）
#           ※ Stage2 の具体条件は rank_agent.py の実装コメント参照
#
# v2.0 追加キーワード（49社シミュレーションで Stage2 検証に使用した業種）:
#   証券・金融サービス・保険 / 総合商社・専門商社・商社 / モーゲージ / 医療機器・製薬
#
# 注意: "総合商社" は INDUSTRY_PROFIT_MEDIUM_KEYWORDS（Phase 1 NG条件）にも含まれる
#       rank_agent.py 側で is_parent_prime_subsidiary 例外を尊重して処理すること
PROFITABLE_INDUSTRY_KEYWORDS = [
    # ── 金融サービス（高利益率 × 低離職率 × 高年収） ───────────
    "投資", "ファンド", "VC", "ベンチャーキャピタル",
    "アセットマネジメント", "資産運用",
    "金融サービス", "証券",
    "モーゲージ", "プライベートバンキング",
    # ── 保険（安定高利益率業界） ────────────────────────────
    "保険", "保険代理店",
    # ── 法律・士業（高利益率 × 低離職率） ──────────────────
    "法律事務所", "弁護士法人", "税理士法人", "監査法人",
    "士業",
    # ── コンサルティング（高利益率） ──────────────────────
    "コンサルティング", "経営コンサル", "戦略コンサル",
    # ── IT/SaaS（成熟した会社・高利益率） ───────────────────
    "SaaS", "クラウドサービス",
    # ── 商社（高利益率 × 業歴長） ───────────────────────────
    "総合商社", "専門商社", "商社",
    # ── 高付加価値製造・医療 ─────────────────────────────
    "精密機器", "半導体製造装置", "医療機器製造", "医療機器",
    "製薬",
    # ── 不動産（高単価系） ───────────────────────────────
    "不動産投資",
]
