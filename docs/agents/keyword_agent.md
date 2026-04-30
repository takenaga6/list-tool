# Agent: キーワードエージェント（keyword_agent.py）

> ⚠️ **Phase 3.3 v2.0 反映後の最新版**（2026-04-30）
> データ構造が v1（フラット）→ v2（_version + queries + by_source）に拡張済み。

**目的**
- 検索クエリ（キーワード）を自動生成し、実行結果のヒット実績を学習して精度の高いクエリ順に並べ替える。
- クエリの良し悪しを記録し、低品質なクエリの使用頻度を下げる。
- **媒体次元も追跡**（Phase 3.3で追加）: 「期間×媒体×ワード」の組み合わせ精度を学習。

---

## 1. 役割（責務）

### ✅ やること
- 検索クエリ候補を生成する（generate_all_queries()）
- 実行後のヒット数 / A/Bランクの割合 / NG率などを記録し、上位クエリを選別する
- 媒体別の精度統計を取る（by_source）
- get_sorted_queries() で実行順を返す（学習済み/未実績を含む）

### ❌ やらないこと
- 検索実行自体（search_agent が担当）
- 企業情報の解析/判定（scraper_agent / rank_agent が担当）

---

## 2. データ構造（v2.0・Phase 3.3）

```json
{
  "_version": 2,
  "queries": {
    "クエリ文字列": {
      "hits": int,         // 検索ヒット累計
      "ng": int,           // NG発生数
      "rank_a": int,       // A判定数
      "rank_b": int,
      "rank_c": int,
      "rank_ng": int
    }
  },
  "by_source": {
    "search:1ヶ月以内": {
      "hits": int,
      "ng": int,
      "rank_a": int,
      "rank_b": int,
      ...
    },
    "search:6ヶ月以内": { ... },
    "list_page:kenko-keiei.jp": { ... }
  }
}
```

### v1→v2 自動マイグレーション

起動時に v1（フラット）形式を検出したら自動で v2 形式に変換。  
後方互換性あり（既存の record_hit/ng/rank_result も source なしで動作）。

---

## 3. 主な機能

### 3-1. クエリ生成（generate_all_queries）

```
- PR媒体 × 定型フレーズ（最優先）
- 健康・福利厚生系キーワード
- 経営者シグナル系
- 業種×健康経営
- 地域×健康経営（首都圏重視）
- 採用・認定シグナル
- 媒体名×大分類キーワード（汎用）
```

クエリは重複を排除しつつ順序を維持する。

### 3-2. 学習とソート

```
record_hit(query, count, source=None)
  → クエリのヒット数を記録
  → source 例: "search:1ヶ月以内", "list_page:kenko-keiei.jp"

record_ng(query, source=None)
  → NG発生数を記録

record_rank_result(query, rank, source=None)
  → ランク結果（A/B/C/NG）を記録

get_sorted_queries(custom_queries=None)
  → カスタムクエリを最優先
  → Aランク実績が多い順
  → AB率が高い順
  → 未実績クエリ（生成順）
  → NG率が高いクエリは末尾に回す

get_media_stats() → dict
  → 媒体別の統計（Phase 3.3で追加）

show_media_stats()
  → 媒体別ランキング表示
```

---

## 4. 媒体別統計（Phase 3.3 で追加）

```
main.py の record_hit 呼び出し箇所（898行・1385行）:
   record_hit(keyword, len(search_results), source=f"search:{period_label}")

これにより:
- 「1ヶ月以内」「6ヶ月以内」等の期間別精度が記録される
- list_page_agent 経由のヒットも区別可能（拡張可能）

app.py のシステム診断タブで可視化:
- 媒体別精度ランキング表
- 高精度クエリ TOP20
- 低品質クエリ表
```

---

## 5. データ保存

- 保存先: `output/keyword_stats.json`
- 形式: JSON（v2形式）
- 更新タイミング: 各 record_* 呼び出し時に即座に保存

---

## 6. 運用上のポイント

- `NG_SKIP_THRESHOLD` や `A_RATE_THRESHOLD` を調整すると、実績不足クエリの扱いや学習速度をコントロールできる。
- クエリを追加したい場合は、PR_MEDIA / MEDIA_SUFFIXES / 各シグナルリスト（HEALTH_WELFARE など）へ追記する。
- 媒体次元の学習データは1〜2週間蓄積してから判断を始めるのが目安。

---

## 7. フィードバック・学習ループ

- record_hit/ng/rank_result によりクエリの良し悪しを学習
- main.py でランク結果（A/B/C/NG）を記録
- これが keyword_stats.json に反映され、「今後どのクエリを優先するか」が改善
- テレアポログ（output/feedback.csv）はまだ自動学習に使われていない（拡張余地）

---

## 8. 関連ファイル

- `agents/keyword_agent.py`: 実装本体
- `agents/search_agent.py`: 検索実行
- `output/keyword_stats.json`: 学習データ（v2形式）
- `app.py`: システム診断タブで可視化
