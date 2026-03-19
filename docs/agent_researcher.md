# Agent2: ディープリサーチャー（scraper_agent）詳細

**ファイル**: `agents/scraper_agent.py`
**タイミング**: pre_screen通過後・スクレイピング実行

---

## 役割

企業HPをスクレイピングして会社情報を抽出し、企業HP確認スコアを計算する。
JSレンダリングサイトは検索スニペットで補完。失敗ドメインは自動学習で除外リストへ。

---

## 処理フロー

```
URL受け取り
  │
  ├─ HTTPリクエスト（requests + chardet）
  │    文字コード多段階対応: utf-8 → apparent_encoding → cp932 → euc-jp
  │
  ├─ check_company_fields()  ← 企業HPか否かを5項目で判定
  │    3/5以上 → 企業HP確認（信頼度UP）
  │    2/5以下 → スニペットで補完 or スキップ
  │
  ├─ 情報抽出
  │    会社名・代表者名・住所・電話番号・業種・従業員数 等
  │
  └─ 失敗時 → record_domain_fail() でカウント
       3回失敗 → learned_exclude.json に自動追加
```

---

## check_company_fields() — 5項目チェック

| # | チェック項目 | 検出パターン例 |
|---|---|---|
| 1 | 法人格 | 株式会社・合同会社・有限会社 等 |
| 2 | 代表者名 | 代表取締役・社長・CEO 等 |
| 3 | 住所 | 都道府県・丁目・番地 等 |
| 4 | 電話番号 | TEL / FAX / 電話番号 |
| 5 | 事業内容 | 事業内容・サービス内容・業務内容 |

**判定**: 3項目以上 → 企業HP確認（信頼度スコアに加算）

---

## 信頼度スコア（0〜4）

rank_agent の自動登録判定に使用:

| 信頼度 | 意味 |
|---|---|
| 0 | 情報がほぼ取れなかった |
| 1 | スニペット補完のみ |
| 2 | 必須フィールドの一部取得 |
| 3 | check_company_fields 3/5 以上 |
| 4 | 全フィールド取得 |

---

## 抽出フィールド一覧

| フィールド | 変数名 | HubSpotへのマッピング |
|---|---|---|
| 会社名 | `company_name` | name |
| 企業URL | `company_url` | website / domain |
| 代表者名 | `representative` | Contact: lastname/firstname |
| 電話番号 | `phone` | phone（国際化変換） |
| 郵便番号 | `zip_code` | zip |
| 都道府県 | `prefecture` | state / city |
| 所在地 | `address` | address |
| 業種 | `industry` | industry |
| 従業員数 | `employee_count` | numberofemployees |
| 備考 | `notes` | description |

---

## 失敗時の自動学習

`record_domain_fail(domain)` → `output/domain_fail_stats.json` にカウント記録
同一ドメインが **3回失敗** → `output/learned_exclude.json` に自動追加 → 次回以降スキップ

---

## 精度改善のポイント

- JSレンダリングサイト（Nuxt/React等）は情報取得できないことが多い → スニペット補完で対処
- 法律事務所・士業サイトは構造が独特 → 専用パターン追加で改善可能
- 電話番号フォーマットが特殊（ハイフンなし等）でも `_normalize_phone()` で吸収
