# Agent: リストページエージェント（list_page_agent.py）

> ⚠️ **Phase 4 Step 2 + 2.4 反映後の最新版**（2026-04-30）
> COMPANY_NAME_PATTERNS のバグ修正済み。

**目的**
- 健康経営優良法人リスト・PR媒体リストなどから企業名を抽出し、公式HPを自動検索してリストアップ候補を生成する。
- 1つのURLから大量の企業をまとめて扱いたいときに使う。

---

## 1. 役割（責務）

### ✅ やること
- リストページ（HTML）から企業名を抽出
- PDF/Word/Excelファイル内の企業名も抽出（リンクがあればダウンロードして解析）
- 抽出した企業名ごとに DDGS（複数検索エンジン分散）で検索し公式HP候補を取得
- search_agent 形式の辞書リスト（url, title, snippet, search_query 等）を返す

### ❌ やらないこと
- 企業HPの詳細スクレイピング（scraper_agent が担当）
- ランク付け（rank_agent が担当）

---

## 2. S1/S2/通常 の3種類のスクレイパー

main.py の `_scrape_list_with_signal()` でURL種別を判定して分岐:

```
_scrape_list_with_signal(list_url):
   if list_url が S2_MEDIA_LIST_URLS に該当:
       return scrape_s2_media() → source_confirmed_s2=True
   elif list_url が S1_MEDIA_LIST_URLS に該当:
       return scrape_s1_media() → source_confirmed_s1=True
   else:
       return scrape_company_list_page() → フラグなし
```

### S1: PR有料媒体（config.py 48行）

```python
S1_MEDIA_LIST_URLS = [
    "https://superceo.jp/list/company",       # SUPER CEO
    "https://business-plus.net/interview/",   # B-PLUS
]
```

### S2: 健康経営メディア（config.py 54行）

```python
S2_MEDIA_LIST_URLS = [
    "https://kenko-keiei.jp/houjin_list/",       # 健康経営優良法人（経産省・21,375社）
    "https://www.voice-report.jp/",              # アクサ生命ボイスレポート
    "https://kenkoukeiei-media.com/",            # 健康経営の広場
    "https://daido-kenco-award.jp/companies/",   # 大同生命
]
```

`MEDIA_LIST_URLS = S2_MEDIA_LIST_URLS + S1_MEDIA_LIST_URLS`（自動モードで全部処理）

---

## 3. 主な機能

### 3-1. 企業名抽出

- HTML: テーブル・リスト要素 (`<table>`, `<ul>/<ol>/<li>`) を優先して抽出
- テキスト全体から正規表現による企業名抽出も補完
- `extract_company_names_from_html()` / `extract_company_names_from_text()` で実行

#### COMPANY_NAME_PATTERNS（Step 2 修正後）

```python
COMPANY_NAME_PATTERNS = [
    r"((?:株式会社|合同会社|有限会社|一般社団法人|NPO法人)[^\s「」【】（）()\n\r<、。,]{1,30})",
    r"([^\s「」【】（）()\n\r<、。,]{1,30}(?:株式会社|合同会社|有限会社))",
]
```

**Phase 4 Step 2 で追加**: 除外文字に「（」「(」「）」「)」追加  
理由: 「こそが働きがいを育てる（三和建設株式会社」のような壊れた抽出を防ぐ

#### NUMERIC_PREFIX_PATTERN（Step 2.4 で追加）

```python
NUMERIC_PREFIX_PATTERN = re.compile(r'^[\d０-９①-⑳][.．、)）]?')
```

**Phase 4 Step 2.4 で追加**: 数字+ピリオド始まりの断片を除外  
理由: 「１．株式会社」「②株式会社」などのゴミ抽出を防ぐ

### 3-2. ファイル対応

- PDF（pdfplumber）
- Word .docx（python-docx）
- Excel .xlsx（openpyxl）

ライブラリがなければスキップ（ログ出力）。

### 3-3. 公式HP検索

- DDGS（複数検索エンジン分散: DuckDuckGo / Brave / Yandex / Mojeek / Yahoo）
- 結果のタイトル/本文/URLに対して企業名一致を判定
- 除外ドメインリスト（SKIP_DOMAINS, NG_DOMAIN_KEYWORDS）に合致するものは除外

---

## 4. 実行例

```python
from agents.list_page_agent import scrape_company_list_page

results = scrape_company_list_page("https://kenko-keiei.jp/houjin_list/")
for r in results:
    print(r["url"], r["search_query"])
```

---

## 5. 運用上の注意

- リストページの構造が大きく変わると抽出ロジックが破綻する可能性
   → 企業数が極端に減った場合は extract_company_names_from_html() の正規表現を調整
- 企業名が複数行にまたがる場合や複雑な表形式では抽出漏れが発生しやすい
- 大規模法人リスト（daikibo / 大規模 など）は自動的に除外
   → 違う語句の場合は手動で DAIKIBO_KEYWORDS を追加

---

## 6. 関連ファイル

- `agents/list_page_agent.py`: 実装本体
- `agents/search_agent.py`: 公式HP検索（5エンジン分散）
- `tests/test_list_page_agent.py`: テスト10件（Phase 4 Step 2 で追加）

---

## 7. テスト（tests/test_list_page_agent.py）

Phase 4 Step 2 で新規作成・10件:

```
基本ケース（4件）:
- test_simple_kabushiki_kaisha
- test_simple_yugen_kaisha
- test_simple_godou_kaisha
- test_simple_shadanhojin

Step 2 修正ケース（3件）:
- test_paren_zenkaku_breakdown（全角括弧）
- test_paren_hankaku_breakdown（半角括弧）
- test_paren_close_zenkaku（閉じ括弧）

Step 2.4 修正ケース（3件）:
- test_numeric_prefix_zenkaku_excluded（全角数字）
- test_numeric_prefix_hankaku_excluded（半角数字）
- test_marusuji_prefix_excluded（丸囲み数字）
```
