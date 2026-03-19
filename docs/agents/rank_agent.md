# Agent: ランク判定エージェント（rank_agent.py）

**目的**
- 収集した企業候補に対し、契約実績に基づく"理想顧客"シグナルでスコアリングし、A/B/C/NGにランク付けする。
- 複数のシグナルから合計スコアを算出し、明示的に除外すべき企業（NG）を早期に弾く。

---

## 1. 役割（責務）

### ✅ やること
- 検索結果のタイトル・スニペットから「上場/大企業/グループ」などのNGシグナルを先に弾く（`pre_screen()`）
- 企業情報と検索結果を組み合わせてスコアを算出し、A/B/C/NGを判定する（`evaluate_rank()`）
- しきい値を超える企業は自動登録候補とし、低いものは除外する

### ❌ やらないこと
- 企業情報のスクレイピング（`scraper_agent` が担当）
- 検索クエリの生成や学習（`keyword_agent` が担当）
- HubSpot登録（`hubspot_agent` が担当）

---

## 2. 主な機能

### 2-1. `pre_screen(search_result: dict) -> tuple[bool, str]`
- Google/DuckDuckGo の検索結果タイトル・スニペットのみで NG 判定を行う。
- 実行前にスクレイピングを省略できるため高速（HTTPリクエスト不要）。
- 主な NG 条件:
  - 上場・証券コード・東証市場の記載
  - 大企業 / 小規模企業ドメイン（`config.py` の `LARGE_COMPANY_DOMAINS` / `SMALL_COMPANY_DOMAINS` に依存）
  - ホールディングス / グループ会社兆候
  - スニペット内に従業員数が書かれている場合の「200名超」「10名未満」
  - NG 業種キーワード（`config.py` の `NG_INDUSTRY_KEYWORDS`）

### 2-2. `evaluate_rank(company_info: dict, search_results: list[dict], page_text: str = "") -> dict`
- 企業情報（`scraper_agent` で取得）や検索結果のテキストからシグナルを集計し、スコア（0〜12前後）を算出する。
- シグナルの例:
  - PR/広告露出（`PR_MEDIA_DOMAINS`, `PR_MEDIA_KEYWORDS`）
  - 健康メディア掲載（`HEALTH_MEDIA_DOMAINS`）
  - 健康経営認定系（`HEALTH_CERT_DOMAINS`）
  - 既存福利厚生 / フィジカルケアの手がかり（`WELFARE_KEYWORDS`, `PHYSICAL_CARE_KEYWORDS`）
  - 高利益率業種（`HIGH_MARGIN_INDUSTRY_KEYWORDS`）
  - 多拠点・全国展開・従業員規模など（`_MULTI_BRANCH_PATTERNS`, `pre_screen` で一部確認）

- 評価結果は以下のような dict で返る:
  - `rank`: "A"/"B"/"C"/"NG"
  - `score`: スコア値
  - `reasons`: 付加したシグナル理由のリスト
  - `ng_reason`: NG に該当した場合の理由

---

## 3. 設定・重み付け

### signal_weights.json
- `output/signal_weights.json` に重みを定義すると、特定シグナルのスコア影響度を調整できる。
- 変更は起動時に読み込まれ、`_w(key)` 経由で適用される。

---

## 4. 運用上の注意

- `pre_screen()` は先行フィルタであり、NG 理由は `rank_result['ng_reason']` に文字列として入る。
- `evaluate_rank()` の挙動を変えたい場合は、`PR_INVESTMENT_SIGNALS` / `HEALTH_PROMOTER_SIGNALS` 等のシグナルリスト追加が最も簡単。
- 大規模・小規模ドメインリストは `config.py` に定義されているため、運用時にここを更新するだけで除外対象を変更できる。

---

## 5. フィードバック・学習ループ（テレアポログとの連携）

- `rank_agent` が返す `rank`（A/B/C/NG）は、`main.py` 側で `record_rank_result()` を呼び出すことで `keyword_stats.json` に記録され、
  `keyword_agent` のクエリ優先度に反映されます。
- `output/feedback.csv` の「アポ獲得」や「NG理由」データを使うと、
  - `rank_agent` の重み（`signal_weights.json`）調整
  - `search_agent` の除外ルール（`EXCLUDE_DOMAINS` 等）追加
  - `keyword_agent` の評価指標の拡張
  など、より現場に即した学習が可能になります。

---

## 5. 関連ファイル

- `agents/rank_agent.py`  : 実装本体
- `config.py`            : 各種ドメインリスト・NG業種キーワード・外部設定
- `output/signal_weights.json` : ウェイト調整ファイル
