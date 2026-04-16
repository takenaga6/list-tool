import os
import json

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
