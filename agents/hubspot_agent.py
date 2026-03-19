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


class HubSpotAgent:
    def __init__(self, token: str, ng_list_file: str):
        self.token = token
        self.ng_list_file = ng_list_file
        self.base_url = "https://api.hubapi.com"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    # -------------------------
    # 重複チェック
    # -------------------------

    def check_duplicate(self, company_name: str = "", domain: str = "") -> bool:
        if domain and self._search_company_by_domain(domain):
            logger.info(f"重複検出（ドメイン）: {domain}")
            return True
        if company_name:
            if self._search_company_by_name(company_name):
                logger.info(f"重複検出（会社名完全一致）: {company_name}")
                return True
            # 法人格を外した名称でもチェック（「株式会社ABC」と「ABC」を同一視）
            normalized = self._normalize_company_name(company_name)
            if normalized and normalized != company_name:
                if self._search_company_by_name(normalized):
                    logger.info(f"重複検出（会社名正規化）: {company_name} → {normalized}")
                    return True
        return False

    def _search_company_by_domain(self, domain: str) -> bool:
        url = f"{self.base_url}/crm/v3/objects/companies/search"
        payload = {
            "filterGroups": [{"filters": [{
                "propertyName": "domain", "operator": "EQ", "value": domain
            }]}],
            "limit": 1,
        }
        try:
            resp = requests.post(url, json=payload, headers=self.headers, timeout=10)
            if resp.ok:
                return resp.json().get("total", 0) > 0
        except Exception as e:
            logger.error(f"HubSpotドメイン検索エラー: {e}")
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

    def register_company(self, company_data: dict) -> bool:
        """
        HubSpotに企業（Company）と代表者（Contact）を登録する
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
        }
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
