"""
HubSpotエージェント
重複チェック・企業登録（全項目）・NGリストCSV書き込みを担当する
"""

import csv
import logging
import os
import re
from datetime import datetime
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# PR有料媒体名 → HubSpot n_1（PR有料媒体の種類）選択肢値のマッピング
# コード内の媒体名文字列をキーに、HubSpotのenumeration valueを値とする。
# ──────────────────────────────────────────────────────────
MEDIA_TO_N1: dict[str, str] = {
    "KENJA GLOBAL":                       "KENJA GLOBAL",
    "エコノミスト ビジネスクロニクル":         "エコノミスト ビジネスクロニクル",
    "エコノミスト REC":                     "エコノミスト ビジネスクロニクル",
    "Newsweek WEB":                       "Newsweek CHALLENGER",
    "Newsweek Challenger":                "Newsweek CHALLENGER",
    "Newsweek CHALLENGING INNOVATOR":     "Newsweek CHALLENGING INNOVATOR",
    "時代のニューウェーブ":                  "日経CNBC「時代のニューウェーブ」",
    "j-newwave.com":                      "日経CNBC「時代のニューウェーブ」",
    "Leaders AWARD":                      "20万人の学生が選ぶ「LEADER'S AWARD」",
    "B-PLUS":                             "B-plus",
    "B-plus":                             "B-plus",
    "SUPER CEO":                          "その他有料媒体",
    "SMB Excellent AWARD":               "その他有料媒体",
    "For JAPAN":                          "その他有料媒体",
    "BS TIMES":                           "その他有料媒体",
    "ベンチャー通信":                       "その他有料媒体",
    "カンパニータンク":                     "その他有料媒体",
    "社長名鑑":                            "その他有料媒体",
    "経営者プライム":                       "その他有料媒体",
    "リーダーナビ":                         "その他有料媒体",
    "Fanterview":                         "その他有料媒体",
    "経営者通信":                           "その他有料媒体",
    "先見経済":                            "その他有料媒体",
    "企業と経営":                           "その他有料媒体",
    "サンデー毎日「会社の流儀」":             "サンデー毎日「会社の流儀」",
    "AERA「Business Report」":            "AERA「Business Report」",
    "週刊新潮「リーディングカンパニー」":      "週刊新潮「リーディングカンパニー」",
    "注目企業ONLINE":                      "注目企業ONLINEオリジナル",
    "オリジナルTHE 21「BUSINESS REPORT」": "THE 21「BUSINESS REPORT」",
    "週刊新潮「チャレンジカンパニー」":        "週刊新潮「チャレンジカンパニー」",
    "週刊朝日「Challenge 20◯◯」":         "週刊朝日「Challenge 20◯◯」",
    "週刊文春「会社の実力」":                "週刊文春「会社の実力」",
    "幻冬舎メディアコンサルティング":          "幻冬舎メディアコンサルティング（自費出版）",
    "文芸社":                              "文芸社（自費出版）",
    "ダイヤモンド（自費出版）":              "ダイヤモンド（自費出版）",
    "日経クロスメディア":                    "日経クロスメディア（自費出版）",
    "私のカクゴ":                           "私のカクゴ",
    "QualitasB-plus":                     "QualitasB-plus",
    "月刊企業情報誌『ルーツ』":              "月刊企業情報誌『ルーツ』",
    "月刊企業情報誌「Anchor」":             "月刊企業情報誌「Anchor」",
    "月刊企業情報誌「Masters」":            "月刊企業情報誌「Masters」",
    "月刊企業情報誌「CENTURY」":            "月刊企業情報誌「CENTURY」",
    "NewsPicks「PR記事」":                 "NewsPicks「PR記事」",
    "東京MXビジネス番組":                   "東京MXビジネス番組",
    "異業種ネット":                         "異業種ネット",
}

# S2媒体名のセット（n_1ではなく n_13="有り" を書く）
_S2_MEDIA_NAMES: set[str] = {
    "健康経営優良法人",
    "アクサ生命ボイスレポート",
    "健康経営の広場",
    "大同生命",
}


def build_wb_signal_props(company_data: dict) -> dict:
    """回収トラック用の構造化シグナルプロパティ（wb_sig_*）を組み立てる.

    rank_agent が判定した S1〜S10 / スコア / ランクロジック版 / 流入経路 を
    HubSpot の構造化プロパティへ永続化するための props dict を返す。
    description 自由文のパースに頼らず「実績 × シグナル」検証を成立させるのが目的
    （README: list-rank-validation）。

    NOTE: wb_sig_* プロパティは HubSpot 側で未作成。未作成のまま書き込むと
          登録が 400 で全停止するため、呼び出し側で config.ENABLE_WB_SIGNALS による
          ゲートを必ず通すこと。本関数自体はゲートを行わない（純粋関数・テスト容易性のため）。

    Args:
        company_data: register_company に渡る企業情報。参照キー:
            - signals: {"S1": bool, ..., "S10": bool}（evaluate_rank_v2 の戻り値）
            - score:   int（加点-減点の合計）
            - rank_version: str（省略時 config.RANK_LOGIC_VERSION）
            - wb_lead_source_type: str（list/紹介/inbound/手動。省略時 "list"）

    Returns:
        HubSpot 書き込み用の props dict（bool は "true"/"false" 文字列）。
        空値は呼び出し側の空文字除去に委ねる。
    """
    from datetime import datetime as _dt
    from config import RANK_LOGIC_VERSION

    props: dict = {}

    signals = company_data.get("signals") or {}
    for i in range(1, 11):
        val = signals.get(f"S{i}")
        if val is not None:
            props[f"wb_sig_s{i}"] = "true" if val else "false"

    score = company_data.get("score")
    if score is not None and score != "":
        props["wb_sig_score"] = str(score)

    props["wb_rank_version"] = company_data.get("rank_version") or RANK_LOGIC_VERSION
    # rank_agent が生成するのはアウトバウンドのリストのみ → 既定は "list"
    props["wb_lead_source_type"] = company_data.get("wb_lead_source_type") or "list"
    props["wb_ranked_at"] = _dt.now().strftime("%Y-%m-%d")

    return props


class HubSpotAgent:
    def __init__(self, token: str, ng_list_file: str):
        self.token = token
        self.ng_list_file = ng_list_file
        self.base_url = "https://api.hubapi.com"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        # 担当者自動割り振り用
        # MEMBERSが未設定の場合は空リストになり、割り振り処理はスキップされる
        self._members: list[str] = self._load_members()
        # 各担当者の未架電件数キャッシュ（初回登録時にHubSpotから取得して以降はローカルで加算）
        self._member_counts: dict[str, int] | None = None
        # ラウンドロビン用インデックス（未架電件数が同数のときのタイブレーク）
        self._rr_index: int = 0

    # -------------------------
    # 重複チェック
    # -------------------------

    def check_duplicate(self, company_name: str = "", domain: str = "") -> bool:
        # 会社名のみで1回チェック（高速化）
        if company_name and self._search_company_by_name(company_name):
            logger.info(f"重複検出（会社名）: {company_name}")
            return True
        return False

    def _search_company_by_name(self, name: str) -> bool:
        url = f"{self.base_url}/crm/v3/objects/companies/search"
        payload = {
            "filterGroups": [{"filters": [{
                "propertyName": "name", "operator": "EQ", "value": name
            }]}],
            "limit": 1,
        }
        try:
            resp = requests.post(url, json=payload, headers=self.headers, timeout=10)
            if resp.ok:
                return resp.json().get("total", 0) > 0
        except Exception as e:
            logger.error(f"HubSpot会社名検索エラー: {e}")
        return False

    # -------------------------
    # 企業・担当者登録
    # -------------------------

    def register_company(self, company_data: dict, media_name: str = "", signals: dict = None) -> bool:
        """
        HubSpotに企業（Company）と代表者（Contact）を登録する
        media_name: PR媒体名。MEDIA_TO_N1に一致すればn_1に、S2媒体ならn_13="有り"に書き込む。
                    空文字の場合はcompany_data["media_name"]を参照する。
        signals:    S3〜S6シグナル判定結果 {"s3": bool, "s4": bool, "s5": bool, "s6": bool}。
                    Noneまたは空の場合はcompany_data["signals"]を参照する。
        """
        domain = self._extract_domain(company_data.get("company_url", ""))

        company_props = {
            "name":              company_data.get("company_name", ""),
            "domain":            domain,
            "website":           company_data.get("company_url", ""),
            "phone":             self._normalize_phone(company_data.get("phone", "")),
            "address":           company_data.get("address", ""),
            "state":             company_data.get("prefecture", ""),
            "zip":               company_data.get("zip_code", ""),
            "country":           "Japan",
            "industry":          self._map_industry(company_data.get("industry", "")),
            "numberofemployees": company_data.get("employee_count", ""),
            "description":       company_data.get("notes", ""),
            "city":              company_data.get("prefecture", ""),  # 都道府県をcityにも入れる
            "a_12":              company_data.get("rank", ""),        # リストランク（A/B/C）
        }

        # n_1 / n_13 の書き込み（media_name引数 > company_data["media_name"] の優先順）
        _media = media_name or company_data.get("media_name", "")
        if _media in _S2_MEDIA_NAMES:
            # S2媒体はn_13（PR・広告の有料媒体の有無）に "有り" を書く
            company_props["n_13"] = "有り"
        elif _media and MEDIA_TO_N1.get(_media):
            # S1媒体はn_1（PR有料媒体の種類）に媒体名選択肢値を書く
            company_props["n_1"] = MEDIA_TO_N1[_media]

        # S3〜S6シグナル判定結果をbool型プロパティに書き込む
        # signals引数 > company_data["signals"] の優先順。None/空ならスキップ。
        _signals = signals or company_data.get("signals") or {}
        if _signals:
            # HubSpotのbool型はJSON文字列 "true"/"false" で送る
            _SIGNAL_PROP_MAP = {
                "S3": "houteigaifukurikouseinokisaiari",   # 法定外福利厚生の記載あり
                "S4": "kenkoukeieihenochuuryoku",           # 健康経営への注力
                "S5": "hantoshiinaihprinyuaru",             # 半年以内HPリニューアル
                "S6": "jishabiruhoyuu",                    # 自社ビル保有
            }
            for _sig_key, _prop_name in _SIGNAL_PROP_MAP.items():
                _val = _signals.get(_sig_key)
                if _val is not None:
                    company_props[_prop_name] = "true" if _val else "false"

        # Phase 1: 本命条件チェック結果（HubSpot側で6プロパティを手動作成済み）
        company_props["phase1_must_check_passed"] = (
            "true" if company_data.get("phase1_must_check_passed", True) else "false"
        )
        company_props["phase1_ng_reason"] = company_data.get("phase1_ng_reason", "")
        company_props["industry_profit_estimate"] = company_data.get("industry_profit_estimate", "")
        company_props["is_parent_prime_subsidiary"] = (
            "true" if company_data.get("is_parent_prime_subsidiary", False) else "false"
        )
        company_props["has_kenkokeiei_hp"] = (
            "true" if company_data.get("has_kenkokeiei_hp", False) else "false"
        )
        company_props["has_recruit_page"] = (
            "true" if company_data.get("has_recruit_page", False) else "false"
        )

        # 回収トラック: 構造化シグナル wb_sig_* を書き込む（デフォルト OFF）。
        # wb_* プロパティが HubSpot 側で未作成のうちは ENABLE_WB_SIGNALS=False のため
        # 一切書き込まず、登録挙動は従来と完全に同一になる。
        from config import ENABLE_WB_SIGNALS
        if ENABLE_WB_SIGNALS:
            company_props.update(build_wb_signal_props(company_data))

        # 空文字・Noneを除去
        company_props = {k: v for k, v in company_props.items() if v}

        def _post_company(props: dict) -> requests.Response:
            return requests.post(
                f"{self.base_url}/crm/v3/objects/companies",
                json={"properties": props},
                headers=self.headers,
                timeout=10,
            )

        try:
            logger.info(
                f"HubSpot登録試行: {company_data.get('company_name')} phone={company_props.get('phone')}"
            )
            resp = _post_company(company_props)
            if not resp.ok:
                body = resp.text
                # HubSpotが「似ているようですが」と判定した重複（DUPLICATE_RECORD）→ 登録しない
                if resp.status_code == 409 or "DUPLICATE" in body.upper():
                    logger.info(
                        f"HubSpot重複検出（DUPLICATE_RECORD）: "
                        f"{company_data.get('company_name')} → スキップ"
                    )
                    return False

                # 電話番号がフォーマット不正でエラーになる場合、電話を外して再登録
                if (
                    resp.status_code == 400
                    and (
                        "INVALID_PHONE_NUMBER" in body.upper()
                        or "NUMBER ISN'T VALID" in body.upper()
                    )
                    and "phone" in company_props
                ):
                    # エラーログに電話番号を含めて出力（ログレベルがERRORの環境でも見えるように）
                    logger.error(
                        f"HubSpot電話番号フォーマットエラー: {company_props.get('phone')} → 電話を除外して再登録"
                    )
                    company_props.pop("phone", None)
                    resp = _post_company(company_props)

                if not resp.ok:
                    body = resp.text
                    logger.error(
                        f"企業登録失敗: {resp.status_code} phone={company_props.get('phone')} - {body[:200]}"
                    )
                    return False

            company_id = resp.json().get("id")
            logger.info(f"企業登録成功: {company_data.get('company_name')} (ID:{company_id})")

            # 担当者を自動割り振り（MEMBERS未設定の場合はスキップ）
            self._assign_member_to_company(company_id)

            if company_data.get("representative"):
                self._register_and_associate_contact(company_data, company_id)

            return True

        except Exception as e:
            logger.error(f"企業登録例外: {e}")
            return False

    def _register_and_associate_contact(self, company_data: dict, company_id: str):
        """代表者をContactとして登録し企業と紐付ける"""
        rep_name = company_data.get("representative", "")
        parts = rep_name.split()
        lastname = parts[0] if parts else rep_name
        firstname = parts[1] if len(parts) > 1 else ""

        contact_props = {
            "lastname":  lastname,
            "firstname": firstname,
            "company":   company_data.get("company_name", ""),
            "phone":     self._normalize_phone(company_data.get("phone", "")),
        }
        contact_props = {k: v for k, v in contact_props.items() if v}

        try:
            resp = requests.post(
                f"{self.base_url}/crm/v3/objects/contacts",
                json={"properties": contact_props},
                headers=self.headers,
                timeout=10,
            )
            if resp.ok:
                contact_id = resp.json().get("id")
                self._associate_contact_to_company(contact_id, company_id)
        except Exception as e:
            logger.error(f"担当者登録エラー: {e}")

    def _associate_contact_to_company(self, contact_id: str, company_id: str):
        url = (
            f"{self.base_url}/crm/v3/objects/contacts/{contact_id}"
            f"/associations/companies/{company_id}/contact_to_company"
        )
        try:
            requests.put(url, headers=self.headers, timeout=10)
        except Exception as e:
            logger.error(f"関連付けエラー: {e}")

    # -------------------------
    # NGリスト（CSV）
    # -------------------------

    def add_to_ng_list(self, company_data: dict, reason: str = "HubSpot重複"):
        """NGリストCSVに追記する"""
        os.makedirs(os.path.dirname(self.ng_list_file), exist_ok=True)
        file_exists = os.path.exists(self.ng_list_file) and os.path.getsize(self.ng_list_file) > 0
        fieldnames = [
            "日時", "会社名", "企業URL", "代表氏名", "電話番号",
            "郵便番号", "都道府県", "所在地", "業種", "従業員数", "備考", "NG理由"
        ]
        with open(self.ng_list_file, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow({
                "日時":    datetime.now().strftime("%Y-%m-%d %H:%M"),
                "会社名":   company_data.get("company_name", ""),
                "企業URL":  company_data.get("company_url", ""),
                "代表氏名":  company_data.get("representative", ""),
                "電話番号":  company_data.get("phone", ""),
                "郵便番号":  company_data.get("zip_code", ""),
                "都道府県":  company_data.get("prefecture", ""),
                "所在地":   company_data.get("address", ""),
                "業種":    company_data.get("industry", ""),
                "従業員数":  company_data.get("employee_count", ""),
                "備考":    company_data.get("notes", ""),
                "NG理由":   reason,
            })

    # -------------------------
    # 担当者自動割り振り
    # -------------------------

    @staticmethod
    def _load_members() -> list[str]:
        """環境変数 MEMBERS（カンマ区切り）からメンバーリストを取得する"""
        raw = os.getenv("MEMBERS", "")
        return [m.strip() for m in raw.split(",") if m.strip()]

    def _fetch_member_counts(self) -> dict[str, int]:
        """
        各担当者の「未架電件数」をHubSpotから取得する。
        未架電 = kadentantoushamei が自分 かつ apurochinaiyou が未設定。
        取得失敗した担当者は 0 として扱う。
        """
        counts: dict[str, int] = {m: 0 for m in self._members}
        url = f"{self.base_url}/crm/v3/objects/companies/search"
        for member in self._members:
            payload = {
                "filterGroups": [{
                    "filters": [
                        {"propertyName": "kadentantoushamei",
                         "operator": "EQ", "value": member},
                        {"propertyName": "apurochinaiyou",
                         "operator": "NOT_HAS_PROPERTY"},
                    ]
                }],
                "properties": ["name"],
                "limit": 1,
            }
            try:
                resp = requests.post(url, json=payload, headers=self.headers, timeout=10)
                if resp.ok:
                    counts[member] = resp.json().get("total", 0)
            except Exception as e:
                logger.warning(f"未架電件数取得失敗 ({member}): {e}")
        logger.info(f"[割り振り] 未架電件数: {counts}")
        return counts

    def _pick_next_member(self) -> str | None:
        """
        未架電件数が最も少ない担当者を返す（均等化）。
        同数の場合はラウンドロビンインデックスでタイブレーク。
        メンバーリストが空の場合は None を返す。
        """
        if not self._members:
            return None
        # 初回のみHubSpotから実件数を取得してキャッシュ
        if self._member_counts is None:
            self._member_counts = self._fetch_member_counts()

        min_count = min(self._member_counts.values())
        # 最小件数を持つ担当者を元のリスト順で絞り込む
        candidates = [m for m in self._members if self._member_counts[m] == min_count]
        chosen = candidates[self._rr_index % len(candidates)]
        self._rr_index += 1
        # ローカルカウントをインクリメント（毎回HubSpotを叩かないようにするため）
        self._member_counts[chosen] += 1
        return chosen

    def _assign_member_to_company(self, company_id: str) -> None:
        """
        企業レコードに kadentantoushamei（架電担当者名）を設定する。
        MEMBERSが未設定の場合はスキップ。失敗しても企業登録結果には影響しない。
        """
        member = self._pick_next_member()
        if not member:
            return  # MEMBERSが未設定 → スキップ
        try:
            resp = requests.patch(
                f"{self.base_url}/crm/v3/objects/companies/{company_id}",
                json={"properties": {"kadentantoushamei": member}},
                headers=self.headers,
                timeout=10,
            )
            if resp.ok:
                logger.info(f"[割り振り] {member} → company_id={company_id}")
            else:
                logger.warning(
                    f"[割り振り] PATCH失敗: {resp.status_code} {resp.text[:100]}"
                )
        except Exception as e:
            logger.error(f"[割り振り] 例外: {e}")

    # -------------------------
    # ユーティリティ
    # -------------------------

    @staticmethod
    def _normalize_company_name(name: str) -> str:
        """
        法人格を除去して正規化した会社名を返す。
        例: 「株式会社ABC」→「ABC」、「ABCコーポレーション株式会社」→「ABCコーポレーション」
        重複チェックのファジーマッチに使用。
        """
        import re as _re
        name = _re.sub(r'^(株式会社|有限会社|合同会社|一般社団法人|一般財団法人|医療法人|社会福祉法人)\s*', '', name)
        name = _re.sub(r'\s*(株式会社|有限会社|合同会社|一般社団法人|一般財団法人|医療法人|社会福祉法人)$', '', name)
        return name.strip()

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """日本の電話番号をHubSpot国際形式に変換する。

        HubSpotの電話番号フォーマット要求:
          +18884827768 or +18884827768 ext 123

        例:
          03-1234-5678       → +81312345678
          090-1234-5678      → +819012345678
          03-1234-5678内線123 → +81312345678 ext 123
        """
        if not phone:
            return ""

        # 全角数字を半角に変換
        fullwidth_digits = str.maketrans(
            "０１２３４５６７８９",
            "0123456789",
        )
        phone = phone.translate(fullwidth_digits)

        # 内線/ext/x などを検出しておく
        ext = ""
        m = re.search(r"(?:内線|ext|extension|x)\s*[:\-]??\s*(\d+)", phone, flags=re.IGNORECASE)
        if m:
            ext = m.group(1)
            phone = phone[: m.start()] + phone[m.end():]

        # 住所の郵便番号っぽい文字列（例: 004-0821, 061-1405）を誤って電話番号として拾っていることがあるので除外
        if re.match(r"^\d{3}-\d{4}$", phone.strip()):
            return ""

        # すでに国際形式（+）で与えられている場合はそのまま使う
        if phone.strip().startswith("+"):
            digits = re.sub(r"[^\d]", "", phone)
            if not digits:
                return ""
            normalized = f"+{digits}"
            if ext:
                normalized = f"{normalized} ext {ext}"
            return normalized

        # 数字のみ抽出
        digits = re.sub(r"[^\d]", "", phone)
        if not digits:
            return ""

        # 先頭の0を取り除いて+81を付与
        if digits.startswith("0"):
            digits = digits[1:]
        normalized = f"+81{digits}"
        if ext:
            normalized = f"{normalized} ext {ext}"
        return normalized

    @staticmethod
    def _extract_domain(url: str) -> str:
        if not url:
            return ""
        parsed = urlparse(url)
        domain = parsed.netloc
        if domain.startswith("www."):
            domain = domain[4:]
        return domain

    @staticmethod
    def _map_industry(industry_jp: str) -> str:
        """日本語業種をHubSpot業種コードに変換（任意）"""
        mapping = {
            "情報通信":              "COMPUTER_SOFTWARE",
            "製造":                 "MACHINERY",
            "人材サービス":           "STAFFING_AND_RECRUITING",
            "コンサルティング・士業":   "MANAGEMENT_CONSULTING",
            "不動産":               "REAL_ESTATE",
            "金融・保険":            "FINANCIAL_SERVICES",
            "広告・マーケティング":    "MARKETING_AND_ADVERTISING",
            "商社・卸売":            "WHOLESALE",
            "教育":                 "EDUCATION_MANAGEMENT",
        }
        return mapping.get(industry_jp, "")
