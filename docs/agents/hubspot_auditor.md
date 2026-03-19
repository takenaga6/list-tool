# Agent: HubSpot監査エージェント（hubspot_auditor.py）

**目的**
- 既にHubSpotに登録されている企業を定期的にチェックし、登録ミスや誤登録の可能性が高い企業を発見してフラグ付け・除外リストに追加する。

---

## 1. 役割（責務）

### ✅ やること
- HubSpot API から登録済み企業を全件取得
- 以下の順序でチェックを行い、NGなら「要確認フラグ」を付与し除外リストに追加
  1. ドメインに NG キーワードが含まれていないか（除外ドメイン/NGキーワード）
  2. 会社名とドメインの一致性（会社名のコアとドメインに重複があるか）
  3. オプション（`scrape_borderline=True`）で軽量スクレイプを実行し、`scraper_agent.check_company_fields()` で企業サイト判定

### ❌ やらないこと
- HubSpotへの登録・更新（`hubspot_agent` が担当）
- 企業情報の詳細スクレイピング（最低限のチェックのみ実施）

---

## 2. 主な機能

### 2-1. `audit_hubspot(scrape_borderline: bool = False) -> dict`
- HubSpot の企業リストを取得し、NG企業を検出
- NG 企業は次を実行:
  - `【要確認】` を説明フィールドに追記
  - `exclude_list.csv` にドメインを追加（`config.add_to_exclude_csv()`）
- 戻り値:
  - `{"total": N, "ng": N, "flagged": [...]}`

### 2-2. NG 判定ロジック
- `_check_domain_keywords(domain)`
  - `agents/search_agent.NG_DOMAIN_KEYWORDS` / `agents/search_agent.EXCLUDE_DOMAINS` を用いた判定
- `_check_name_vs_domain(company_name, domain)`
  - 会社名の法人格を除外したコア名をドメインに含むか確認
  - 一致が全くない場合は疑わしいものとして NG 扱い
- `_quick_scrape_check(url)`
  - 5000文字程度を取得し `scraper_agent.check_company_fields()` を実行

---

## 3. 設定・前提

- HubSpot API トークンは `config.HUBSPOT_TOKEN` に設定されている必要がある。
- API レート制限やエラーへの耐性は最低限の retry しかないため、頻繁に実行する場合は注意。

---

## 4. 実行例

```bash
python -c "from agents.hubspot_auditor import audit_hubspot; audit_hubspot(scrape_borderline=True)"
```

---

## 5. 関連ファイル

- `agents/hubspot_auditor.py` : 実装本体
- `config.py`                : `add_to_exclude_csv()` 等の共通ユーティリティ
- `output/exclude_list.csv`  : 自動学習で追加される除外ドメインリスト
