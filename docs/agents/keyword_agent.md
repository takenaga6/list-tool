# Agent: キーワードエージェント（keyword_agent.py）

**目的**
- 検索クエリ（キーワード）を自動生成し、実行結果のヒット実績を学習して精度の高いクエリ順に並べ替える。
- クエリの良し悪しを記録し、低品質なクエリの使用頻度を下げる。

---

## 1. 役割（責務）

### ✅ やること
- 検索クエリ候補を生成する（`generate_all_queries()`）
- 実行後のヒット数 / A/Bランクの割合 / NG率などを記録し、上位クエリを選別する
- `get_sorted_queries()` で実行順を返す（学習済み/未実績を含む）

### ❌ やらないこと
- 検索実行自体（`search_agent` が担当）
- 企業情報の解析/判定（`scraper_agent` / `rank_agent` が担当）

---

## 2. 主な機能

### 2-1. クエリ生成

- `generate_all_queries()`
  - PR媒体 × 定型フレーズ（最優先）
  - 健康・福利厚生系キーワード
  - 経営者シグナル系
  - 業種×健康経営
  - 地域×健康経営（首都圏重視）
  - 採用・認定シグナル
  - 媒体名×大分類キーワード（汎用）

- クエリは重複を排除しつつ順序を維持する。

### 2-2. 学習とソート

- `record_hit(query, hit_count)`：クエリ実行回数・ヒット数を記録
- `record_rank_result(query, rank)`：クエリ経由で得られたランク（A/B）を記録
- `record_ng(query)`：クエリ経由でNGになった件数を記録

- `get_sorted_queries(custom_queries: list[str] = None)`：
  - カスタムクエリを最優先
  - Aランク実績が多い順
  - AB率が高い順
  - 未実績クエリ（生成順）
  - NG率が高いクエリは末尾に回す

---

## 3. データ保存

- 保存先: `output/keyword_stats.json`（JSON形式）
- 保存内容（各クエリ）:
  - `total_hits`, `runs`, `avg_hits`
  - `a_rank`, `b_rank`, `ng_count`
  - `ab_rate`, `a_rate`, `ng_rate`
  - `last_run`

---

## 4. 運用上のポイント

- `NG_SKIP_THRESHOLD` や `A_RATE_THRESHOLD` を調整すると、実績不足クエリの扱いや学習速度をコントロールできる。
- クエリを追加したい場合は、`PR_MEDIA` / `MEDIA_SUFFIXES` / 各シグナルリスト（`HEALTH_WELFARE` など）へ追記する。

---

## 4. フィードバック・学習ループ（テレアポログとの連携）

- `keyword_agent` は `output/keyword_stats.json` を使ってクエリの良し悪しを学習します。
- `main.py` ではランク結果（A/B/C/NG）を `record_rank_result()` で記録しており、
  これが `keyword_stats.json` に反映されることで「今後どのクエリを優先するか」が改善されます。
- テレアポ・商談記録（`output/feedback.csv`）自体は現状自動でクエリ改善に使われませんが、
  ここで得た「アポ獲得」「NG理由」などのデータを `rank_agent` の信号重みや `keyword_agent` のクエリ評価に反映する拡張は可能です。

---

## 5. 関連ファイル

- `agents/keyword_agent.py` : 実装本体
- `agents/search_agent.py`  : 検索実行
- `output/keyword_stats.json` : 学習データ
