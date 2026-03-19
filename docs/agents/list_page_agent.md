# Agent: リストページエージェント（list_page_agent.py）

**目的**
- 健康経営優良法人リストなどの「企業リストページ」から企業名を抽出し、公式HPを自動検索してリストアップ候補を生成する。
- 1つのURLから大量の企業をまとめて扱いたいときに使う。

---

## 1. 役割（責務）

### ✅ やること
- リストページ（HTML）から企業名を抽出
- PDF/Word/Excelファイル内の企業名も抽出（リンクがあればダウンロードして解析）
- 抽出した企業名ごとに DuckDuckGo 検索を行い、公式HP候補を取得
- `search_agent` 形式の辞書リスト（`url,title,snippet,search_query` など）を返す

### ❌ やらないこと
- 企業HPの詳細スクレイピング（`scraper_agent` が担当）
- ランク付け（`rank_agent` が担当）

---

## 2. 主な機能

### 2-1. 企業名抽出

- HTML: テーブル・リスト要素 (`<table>`, `<ul>/<ol>/<li>`) を優先して抽出
- テキスト全体から正規表現による企業名抽出（`株式会社` など）も補完として使用
- 企業名抽出は `extract_company_names_from_html()` / `extract_company_names_from_text()` で行う

### 2-2. ファイル対応

- PDF（`pdfplumber`）
- Word `.docx`（`python-docx`）
- Excel `.xlsx`（`openpyxl`）

※ これらのライブラリがインストールされていない場合はログ出力してスキップする。

### 2-3. 公式HP検索

- `search_company_hp()` で企業名を DuckDuckGo 検索
- 結果のタイトル/本文/URLに対して企業名一致を判定し、誤マッチ（求人サイト・ポータル等）を除外
- 除外ドメインリスト（`SKIP_DOMAINS`, `NG_DOMAIN_KEYWORDS`）に合致するものは除外

---

## 3. 実行例

```python
from agents.list_page_agent import scrape_company_list_page

results = scrape_company_list_page("https://kenko-keiei.jp/houjin_list/")
for r in results:
    print(r["url"], r["search_query"])
```

---

## 4. 運用上の注意

- リストページの構造が大きく変わると抽出ロジックが破綻するため、途中で企業数が極端に減った場合は `extract_company_names_from_html()` の正規表現や抽出優先処理を調整する必要がある。
- 企業名が複数行にまたがる場合や表形式が複雑な場合、抽出漏れが発生しやすい。
- 大規模法人リスト（`daikibo` / `大規模` など）を自動的に除外する仕組みがあるが、違う語句で書かれている場合は手動で `DAIKIBO_KEYWORDS` を追加する。

---

## 5. 関連ファイル

- `agents/list_page_agent.py` : 実装本体
- `agents/search_agent.py`    : 公式HP検索（DuckDuckGo）
