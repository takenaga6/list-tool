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

# 自動登録閾値
# スコア >= AUTO_REGISTER_SCORE かつ 信頼度 >= AUTO_REGISTER_CONFIDENCE → 確認不要で自動登録
# スコア < MIN_PENDING_SCORE → 候補リストにも追加しない（自動スキップ）
AUTO_REGISTER_SCORE = 8       # このスコア以上は自動登録
AUTO_REGISTER_CONFIDENCE = 2  # このフィールド信頼度以上が必要（0〜4）
MIN_PENDING_SCORE = 3         # これ未満は候補リストにも出さない

# 出力ファイル
OUTPUT_DIR = "output"
NG_LIST_FILE = os.path.join(OUTPUT_DIR, "ng_list.csv")
RESULTS_FILE = os.path.join(OUTPUT_DIR, "results.csv")
RESULTS_WITH_QUERY_FILE = os.path.join(OUTPUT_DIR, "results_with_query.csv")
LOG_FILE = os.path.join(OUTPUT_DIR, "tool.log")
LEARNED_EXCLUDE_FILE = os.path.join(OUTPUT_DIR, "learned_exclude.json")  # 自動学習した除外ドメイン
DOMAIN_FAIL_FILE = os.path.join(OUTPUT_DIR, "domain_fail_stats.json")    # 失敗カウンター
EXCLUDE_LIST_CSV = os.path.join(OUTPUT_DIR, "exclude_list.csv")          # 手動編集可能な除外ドメインCSV
FEEDBACK_FILE = os.path.join(OUTPUT_DIR, "feedback.csv")                 # テレアポ結果フィードバック
MEETINGS_FILE = os.path.join(OUTPUT_DIR, "meetings.csv")                 # 商談記録
IMPORT_SETTINGS_FILE = os.path.join(OUTPUT_DIR, "import_settings.json") # インポート設定の記憶


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
        "反応が良かったポイント", "メモ"
    ]

    # 既存のfeedback.csvに「検索クエリ」列がない場合はヘッダーを書き換えて追加（既存データは保持）
    if file_exists:
        try:
            with open(FEEDBACK_FILE, "r", encoding="utf-8-sig") as f:
                first_line = f.readline().strip()
            if "検索クエリ" not in first_line.split(","):
                # 既存データを読み込み直し（ヘッダーあり）
                with open(FEEDBACK_FILE, "r", encoding="utf-8-sig") as f:
                    reader = _csv.DictReader(f)
                    rows = list(reader)
                # ヘッダーを含めて上書き（既存行に検索クエリ列を追加）
                with open(FEEDBACK_FILE, "w", newline="", encoding="utf-8-sig") as f:
                    writer = _csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for row in rows:
                        row["検索クエリ"] = ""
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
        "商談結果", "契約", "次のアクション", "規模感・金額", "メモ"
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
MAX_RESULTS_PER_QUERY = 10

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
    # 建設・土木
    "建設", "土木", "工務店", "ゼネコン",
    # 運送・物流
    "運送", "運輸", "物流", "宅配", "配送", "トラック", "引越",
    # 医療・福祉
    "病院", "クリニック", "診療所", "薬局", "調剤", "医療法人",
    "介護", "デイサービス", "保育", "幼稚園",
    # toC小売・飲食・サービス
    "スーパー", "コンビニ", "飲食店", "レストラン", "居酒屋",
    "美容院", "美容室", "ネイルサロン",
    "小売", "量販店", "ドラッグストア",
    # 警備
    "警備", "ガードマン", "交通誘導",
    # 清掃・廃棄物
    "清掃業", "廃棄物", "ビルメンテナンス",
    # 自動車・整備
    "自動車販売", "車検", "カーディーラー",
    # SES・人材派遣（常駐型のためオフィス不在率が高い）
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

# 媒体リストページURL（自動モード起動時に最優先で処理するソース）
# ── 処理順: 健康経営系 → PR媒体系 → キーワード検索 ──
# ※ kenko-keiei.jp はページ内のExcelリンクを自動検出してDL（大規模法人は自動除外）
# ※ SPA（KENJA GLOBAL / SMB Excellent等）は Playwright 未対応のためキーワード検索で代替
MEDIA_LIST_URLS: list[str] = [
    # ── 健康経営系（最優先） ──────────────────────────────
    "https://kenko-keiei.jp/houjin_list/",   # 健康経営優良法人 中小規模（経産省認定・Excel自動DL）
    # ── PR媒体系（静的HTML） ─────────────────────────────
    "https://superceo.jp/list/company",       # SUPER CEO 掲載企業一覧（50音順）
    "https://business-plus.net/interview/",   # B-PLUS インタビュー掲載企業一覧
    # ── 将来対応予定 ─────────────────────────────────────
    # "https://smbexcellentcompany.com/2025/",  # SPA（Nuxt.js）→ Playwright対応後に追加
    # "https://kenja.tv/",                       # SPA → 同上
]
