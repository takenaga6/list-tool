# agents/ — 各エージェントの役割・ルール・バグパターン

## エージェント一覧

| ファイル | 役割 |
|---|---|
| `rank_agent.py` | 企業をA/B/C/NGにスコアリング（12シグナル）。signal_weights.jsonをTTLキャッシュ（5分）で読む |
| `keyword_agent.py` | 検索クエリ自動生成・A/Bランク発見率で優先順位付け。keyword_stats.jsonに学習 |
| `feedback_learner.py` | call_list.csv + meetings.csv → signal_weights.json を自動更新（アポ率ベース）。学習前に未登録企業を自動補完 |
| `supplement_agent.py` | 会社名リストを受け取り results.csv 未登録企業をHP検索→スクレイピング→ランク判定して追記。feedback_learner と app.py 商談インポートから呼ばれる |
| `monitor_agent.py` | ヘルスチェック＋自動修復（ファイル破損・ウェイト異常・学習停滞を検知） |
| `search_agent.py` | 検索実行（Google CSE優先 → DuckDuckGoフォールバック） |
| `scraper_agent.py` | 企業サイトのスクレイピング（会社名・電話・住所・従業員数・業種を抽出） |
| `hubspot_agent.py` | HubSpot CRM への企業登録 |
| `list_page_agent.py` | PR媒体・健康経営認定リストページからの企業リスト取得 |

## rank_agent.py の設計

### スコアリング（12シグナル、各1点）
PR媒体掲載 / 健康経営メディア掲載 / 法定外福利厚生 / フィジカルケア未着手 /
健康経営注力 / 健康推進・セミナー / 経営者の健康意識 / PR広告投資 /
成長・自社ビル / 高利益率B2B業種 / 契約実績サイズ / 単一拠点

PR媒体クエリ経由・健康経営認定リスト経由は +2点ボーナス。A:6点以上 / B:4〜5点 / C:2〜3点

### signal_weights.json の読み込み
- モジュール起動時1回だけ読むと学習が反映されない問題あり → TTLキャッシュ（5分）で解決済み
- キャッシュ変数: `_W`, `_W_LOADED_AT`, `_W_TTL = 300.0`

### NGチェックの注意点
- 従業員数は「従業員」だけでなく「社員数」「スタッフ数」も正規表現でカバーする
- `company_info["employee_count"]`（scraperが抽出した数値）を先にチェックする
- 200超は NG、10未満も NG

## scraper_agent.py の設計

### 従業員数の扱い
- `EMPLOYEE_PATTERNS` で「従業員数」「社員数」「スタッフ数」「XXX名のスタッフ」を抽出
- `validate_company_info` では **200超でもクリアしない**（rank_agentに判定させる）
- 1〜200の範囲のみ confidence +1、200超は値保持のままスルー

## feedback_learner.py の設計

### 学習フロー
1. call_list.csv・meetings.csv の会社名を収集
2. **`supplement_agent.supplement_results_csv()` を呼び出し**、results.csv に未登録の企業を自動補完（最大20社）
3. `call_list.csv` → アポ獲得○・見込みA = 成功 / NG系 = 失敗
4. `meetings.csv` → 契約=はい = 成約（+2重みカウント）
5. `results.csv` の備考欄でシグナルキーを抽出（会社名正規化で突合）
6. シグナルごとの成功率 → 旧値70% + 新値30% ブレンドでウェイト更新

### meetings.csv のカラム定義（重要）
- 会社名キーは **「会社名」**（旧「企業名」は廃止）
- **「契約」列が必須**（受注時に「はい」を自動セット）
- `load_meetings()` が旧「企業名」列を「会社名」に自動マイグレーションする

### 会社名正規化（`_normalize_name`）
法人格除去 → NFKC正規化 → 小文字化 → 記号除去。4文字以上なら部分一致も試みる。

## supplement_agent.py の設計

### 目的
リストアップ以外のルート（過去商談インポート・手入力）で登録された会社が results.csv にない場合、学習が0になる問題を解消する。

### 呼び出しタイミング
| 呼び出し元 | タイミング | 最大件数 |
|---|---|---|
| `feedback_learner.run_learning()` | 「学習を実行」ボタン押下時 | 20社 |
| `app.py` 商談インポートタブ | CSVインポート完了直後 | 50社 |

### 処理フロー
1. 既存 results.csv の会社名を正規化してセット化
2. 引数の会社名リストから未登録分のみ抽出
3. 各社: `list_page_agent.search_company_hp()` → `scraper_agent.scrape_company_info()` → `rank_agent.evaluate_rank()`
4. 備考列に `"理由: シグナル名1, シグナル名2"` 形式で記録（`_extract_signals_from_reasons` が読める形式）
5. results.csv に追記

### 注意
- 1社あたり約2秒のスリープ（DuckDuckGoレート制限対策）
- エラーが出た社はスキップして続行（全体を止めない）

## monitor_agent.py のチェック項目

| チェック | 種別 | 動作 |
|---|---|---|
| OUTPUT_DIR存在 | 自動修復 | なければ作成 |
| signal_weights.json整合性 | 自動修復 | 破損・ウェイト全張り付きでリセット |
| CSVカラム整合性 | 検知のみ | 必須カラム欠落を警告 |
| keyword_stats.json異常値 | 検知のみ | NaN/Inf を警告 |
| feedback学習24h未実行 | 自動修復 | run_learning() を強制実行 |
| ログERROR多発 | 検知のみ | 件数を警告 |

起動タイミング: `main.py` 起動時に自動実行 / `app.py` の「システム診断」タブから手動実行
