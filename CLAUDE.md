# list_tool プロジェクト — Claude向け作業ガイド

## プロジェクト概要
Offi-Stretch（Well Body株式会社）のテレアポ営業支援SaaS。
- **UI**: `app.py`（Streamlit）— タブ: 架電先リスト/確認待ち/履歴/ダッシュボード/取り込み/リストアップ/商談一覧/システム診断
- **CLI**: `main.py` — Google検索→スクレイピング→ランク判定→HubSpot登録
- **設定**: `config.py` — 全パス・定数の管理元

## 絶対ルール

### ファイルパスは必ずOUTPUT_DIRベース
```python
# 正しい
os.path.join(OUTPUT_DIR, "filename.csv")

# 禁止（Renderの永続ストレージ /data に書かれない）
"output/filename.csv"
```
`OUTPUT_DIR` は `config.py` から import する。新ファイルを追加するときも必ず同じ形式で。

### 新しいエージェントファイルは config から OUTPUT_DIR を import する
```python
import sys as _sys, os
_DIR = os.path.dirname(os.path.abspath(__file__))
_sys.path.insert(0, os.path.join(_DIR, ".."))
from config import OUTPUT_DIR as _OUTPUT_DIR
```

### 変更前に必ず影響範囲を確認
- ファイルパス・定数を変えたら `grep` で全ファイルを横断チェック
- 1ファイルだけ直して他が残るパターンが過去に複数発生している

## インフラ（Render）
- **永続ストレージ**: Disk マウントパス `/data` → `OUTPUT_DIR=/data` を環境変数に設定済み
- **Start Command**: `streamlit run app.py --server.port $PORT --theme.base light --theme.textColor "#111827" --theme.backgroundColor "#ffffff" --theme.primaryColor "#40b680"`
- **必須環境変数**: `OUTPUT_DIR`, `HUBSPOT_TOKEN`, `GOOGLE_CSE_API_KEY`（任意）, `GOOGLE_CSE_CX`（任意）
- Renderの環境変数キーは**全大文字**（`hubspot_token` はNG）

## 検索エンジン
- **第1優先**: Google Custom Search API（`GOOGLE_CSE_API_KEY` + `GOOGLE_CSE_CX` が設定されている場合）
- **フォールバック**: DuckDuckGo（設定なしでも動く）
- Google CSEの「ウェブ全体を検索」は廃止済み → CSEはサイト指定のみ

## HubSpot連携
- Private App（非公開アプリ）を使用
- リスト取得: `POST /crm/v3/lists/search`（GETではなくPOST）
- 必要スコープ: `crm.lists.read`

## UIテーマ（Streamlit）
- テーマは Start Command の `--theme.*` フラグで指定（config.tomlより優先）
- `data_editor`（Glide Data Grid）はCanvasレンダリング → **CSS上書き禁止**
  - `.dvn-scroller`, `.glideDataEditor`, `[class*="gdg-"]` に `background-color` や `color` をCSSで当てると、Canvasの上に白板が被さって内容が見えなくなる
  - `div { color: ... }` の一括指定もGDGのJS色計算を狂わせる
- 外枠（`border`）のみCSSで指定してよい

## 自動保存
- `streamlit-autorefresh` で30分ごとに自動保存
- 保存後は `st.session_state.pop("cl_data_editor", None)` + `st.rerun()` が必須（キャッシュ残留防止）

## 共有定数（config.py で一元管理）

以下は **config.py が唯一の定義元**。他のファイルで再定義しないこと。

| 定数 | 内容 |
|---|---|
| `SIGNAL_KEYS` | 12シグナルのキー名リスト |
| `WEIGHT_MIN` / `WEIGHT_MAX` / `DEFAULT_WEIGHT` | シグナルウェイトのクランプ範囲 |
| `OUTPUT_DIR` + 各ファイルパス | 全データファイルのパス定義 |

```python
# 正しいimport例（agentsディレクトリ内から）
from config import OUTPUT_DIR, SIGNAL_KEYS, WEIGHT_MIN, WEIGHT_MAX
```

## meetings.csv のカラム定義

`_MEETING_COLS`（app.py）が正式定義。以下を守ること。

- 会社名キーは **「会社名」**（旧「企業名」は廃止済み）
- **「契約」列が必須**（受注時に自動で「はい」をセット）
- `load_meetings()` が旧「企業名」→「会社名」を自動マイグレーションする（後方互換）
- `feedback_learner.py` は `row.get("会社名")` と `row.get("契約")` を読む

## フィードバック学習の前提条件

学習が機能するには **meetings.csv / call_list.csv の会社名が results.csv にも存在する**必要がある。

リストアップ以外のルート（過去商談インポート・手入力）で登録した会社は results.csv にないため、`supplement_agent.supplement_results_csv()` が自動補完する:
- 「学習を実行」ボタン → call_list + meetings の未登録企業を最大20社補完してから学習
- 商談インポート完了後 → インポートした会社を最大50社補完

## 既知のバグパターン（再発防止）

### 従業員数フィルター漏れ
- `evaluate_rank` は `company_info["employee_count"]`（scraperが抽出した値）を直接チェックする
- 正規表現は「従業員」だけでなく「社員数」「スタッフ数」も含める
- `validate_company_info` で200超をクリアしない（rank_agentに判定させる）

### Streamlit data_editor が真っ白になる
- 原因: CSS で GDG要素に `background-color: #ffffff` を当てるとCanvasが隠れる
- 対処: data_editor 内部への CSS 上書き一切禁止。テーマはCLIフラグに任せる

### ダッシュボードの KeyError
- meetings.csv に存在しない列を直接 `df["列名"]` で参照すると落ちる
- 必ず `"列名" in df.columns` でチェックするか、`df.get("列名")` を使う
