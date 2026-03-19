# 企業リストアップツール 全体設計書

**サービス**: Offi-Stretch（理学療法士によるオフィス出張施術）
**目的**: B2B営業のアタックリストを自動生成し、HubSpot CRMへ登録する

---

## 全体フロー

```
[起動] python main.py
  │
  ├─ 登録方式選択
  │    1: 確認後に登録（推奨）
  │    2: 自動登録（従来通り）
  │
  ├─ 検索モード選択
  │    1: 自動モード（keyword_agent が有効パターンを提案）
  │    2: 手動モード（キーワードを自分で入力）
  │    + リストページURL（任意）
  │
  ├─ 期間選択（1週間〜1年）
  │
  ├─ [STEP1] 媒体リストスクレイプ（最優先・自動モード時のみ）
  │    list_page_agent → 健康経営優良法人Excel / SUPER CEO / B-PLUS 等
  │    ※ MEDIA_LIST_URLS に登録した媒体を順番に処理
  │
  ├─ [STEP2] キーワード検索（STEP1 で目標未達の場合に続行）
  │    search_agent → DuckDuckGo検索
  │
  ├─ [共通] スクレイプ・ランク判定（並列処理）
  │    scraper_agent → rank_agent
  │    ├─ スコア高・信頼度十分 → 自動登録（確認モードでも）
  │    ├─ スコア中間帯 → 確認待ちリストへ
  │    └─ スコア低・NG → 自動スキップ
  │
  ├─ [確認モードの場合] 候補一覧を表示 → ユーザー承認
  │    y=全件登録 / n=スキップ / 1,3=個別選択 / x2=除外リストへ
  │
  ├─ HubSpot登録（hubspot_agent）
  │
  └─ 完了レポート

[監査] python main.py --audit [--scrape]
  └─ HubSpot登録済み企業を事後チェック → NG企業にフラグ + 学習

[ドキュメント更新] python main.py --update-docs
  └─ config.py の現在の設定値を OVERVIEW.md に自動反映
```

---

## ファイル構成

```
list_tool/
├── main.py                    # エントリーポイント・UI・処理フロー制御
├── config.py                  # 設定・定数・学習データ管理
├── agents/
│   ├── search_agent.py        # DuckDuckGo検索・除外フィルタ
│   ├── scraper_agent.py       # 企業HP情報取得・バリデーション
│   ├── rank_agent.py          # A/B/C/NG ランク判定
│   ├── hubspot_agent.py       # HubSpot API（登録・重複チェック）
│   ├── hubspot_auditor.py     # 登録済み企業の事後バリデーション
│   ├── list_page_agent.py     # リストページ（PDF/Excel/HTML）から一括抽出
│   └── keyword_agent.py       # 検索クエリの自動生成・学習
└── output/
    ├── results.csv            # 登録成功した企業一覧
    ├── ng_list.csv            # NG企業リスト
    ├── exclude_list.csv       # 除外ドメインリスト（手動追加・承認時除外）
    ├── learned_exclude.json   # 自動学習した除外ドメイン
    ├── domain_fail_stats.json # ドメイン失敗カウンター（3回→自動除外）
    ├── feedback.csv           # テレアポ結果フィードバック
    └── tool.log               # 実行ログ
```

---

## 各エージェントの役割

### search_agent.py
- DuckDuckGo で検索クエリを実行
- 除外フィルタを多段階で適用

**除外ロジック（順番に適用）:**
1. `EXCLUDE_DOMAINS` — SNS・EC・大手ニュース・求人媒体
2. `NG_DOMAIN_KEYWORDS` — news/media/books/catalog 等のキーワード
3. `learned_exclude.json` + `exclude_list.csv` — 自動学習＋手動追加
4. 海外TLD（.us/.uk/.cn 等）
5. 媒体ドメイン自体（KENJA GLOBAL等の媒体記事 → 企業HP抽出フローへ）

### scraper_agent.py
- 企業HPをスクレイピングして情報抽出（会社名・代表者・住所・TEL等）
- `check_company_fields()` で5項目チェック（3/5以上で企業HP確認）
- 失敗ドメインは `record_domain_fail()` でカウント → 3回で自動除外
- JSレンダリングサイト → 検索スニペットで補完
- 文字コード多段階対応（utf-8 → apparent_encoding → cp932 → euc-jp）

**check_company_fields() チェック項目（5項目）:**
- 株式会社/合同会社/有限会社 等の法人格
- 代表者名（代表取締役・社長等）
- 住所（都道府県・丁目・番地等）
- TEL / FAX / 電話番号
- 事業内容 / サービス内容

### rank_agent.py
- 企業をA/B/C/NGにランク判定（採点方式）

**理想顧客プロファイル（ターゲット）:**
- 情報通信・金融・人材・商社・コンサル等の高利益率B2B業種
- 社長またはウェルフェア担当者が健康意識高い
- PR媒体に掲載されている（承認欲求・ブランド意識高い）
- 法定外福利厚生あり、ただし本格的フィジカルケアは未着手
- 自社ビルorオフィス固定 + 従業員10〜100名

**採点（各1点 + ボーナス）:**

<!-- AUTO_UPDATE_START: rank_thresholds -->
| シグナル | 点数 |
|---|---|
| PR媒体掲載（KENJA GLOBAL等） | +1 |
| 健康経営メディア掲載 | +1 |
| 法定外福利厚生あり | +1 |
| 福利厚生充実＆フィジカルケア未着手 | +1 |
| 健康経営への注力 | +1 |
| 経営者の健康意識・メディア露出 | +1 |
| PR/広告積極投資 | +1 |
| 売上拡大・自社ビル | +1 |
| 高利益率B2B業種（IT/金融/人材等） | +1 |
| 従業員数 20〜100名 | +1 |
| 単一拠点 | +1 |
| ★PR媒体クエリ経由 | **+2ボーナス** |
| ★健康経営優良法人リスト経由（経産省） | **+2ボーナス** |
| ★PR媒体リストページ経由 | **+2ボーナス** |

**ランク基準:** A=6点以上 / B=4〜5点 / C=2〜3点

**自動登録・スキップ閾値:**
- スコア **8点以上** かつ 信頼度2以上 → 確認モードでも自動登録
- スコア **3点未満** または 必須フィールド不足 → 候補リストにも出さず自動スキップ
<!-- AUTO_UPDATE_END: rank_thresholds -->

**NG条件（即除外）:**
- 上場企業（東証・NYSE等）
- 従業員200名超の大企業
- NG業種（飲食・小売・教育・医療・建設等）
- 個人事業主・フランチャイズ・協会・財団

### hubspot_agent.py
- HubSpot CRM API v3 で企業を登録
- 電話番号の国際化変換（03-1234-5678 → +81312345678）
- 重複チェック（ドメイン・会社名）
- 担当者（コンタクト）の同時登録

### hubspot_auditor.py
- 登録済み企業を事後検証し、NGにフラグ立て
- 実行: `python main.py --audit`

**チェック順（軽い順）:**
1. ドメインキーワード（即時・無コスト）
2. 会社名 vs ドメイン一致（即時・無コスト）
3. 軽量スクレイプ（`--scrape` オプション時のみ）

NG判定 → HubSpotの説明フィールドに「【要確認】」追記 + `exclude_list.csv` に学習

### list_page_agent.py
- **自動モードの最優先ソース**: `MEDIA_LIST_URLS` の媒体サイトをキーワード検索より先に処理
- 対応形式: HTML / PDF / Word(.docx) / Excel(.xlsx/.xls)
- 大規模法人ファイル（daikibo/大規模）は除外（中小企業のみ対象）
- 抽出した企業名でDuckDuckGo検索 → 公式HP特定
- `_is_likely_company_hp()` で企業名一致チェック

**現在の媒体リスト（`MEDIA_LIST_URLS`）:**

<!-- AUTO_UPDATE_START: media_sources -->
| URL | 種別 | 備考 |
|---|---|---|
| https://kenko-keiei.jp/houjin_list/ | 健康経営優良法人（経産省認定） | Excel自動DL・中小規模のみ |
| https://superceo.jp/list/company | PR媒体 - SUPER CEO | 静的HTML・50音順一覧 |
| https://business-plus.net/interview/ | PR媒体 - B-PLUS | 静的HTML・インタビュー一覧 |
<!-- AUTO_UPDATE_END: media_sources -->

### keyword_agent.py
- 検索クエリのヒット率・ランク率を学習・記録
- 有効パターンを自動ランキングして提案

---

## 精度向上サイクル

```
1. リストアップ実行
        ↓
2. 承認ステップで不要企業を除外
   → x[番号] で除外リスト（exclude_list.csv）に追加
        ↓
3. テレアポ実施
   → feedback.csv に結果記録
        ↓
4. 傾向分析 → ランク判定基準・検索パターンの調整
        ↓
5. 繰り返し（精度向上）

【自動学習ループ】
  check_company_fields 失敗 → record_domain_fail() → 3回で learned_exclude.json へ
  承認時除外 → exclude_list.csv へ
  監査NG → exclude_list.csv へ
  → 次回リストアップから自動除外
```

---

## コマンド一覧

```bash
# 通常実行
cd C:\Users\user\list_tool
python main.py

# HubSpot監査（ドメインチェック＋会社名チェック）
python main.py --audit

# HubSpot監査（+ 軽量スクレイプ検証）
python main.py --audit --scrape

# OVERVIEW.md の自動更新セクションを現在の config.py から再生成
python main.py --update-docs
```

---

## 除外ドメインの管理

| ファイル | 用途 | 更新タイミング |
|---|---|---|
| `exclude_list.csv` | 手動追加・承認時除外・監査NG | 承認ステップ(x操作) / 監査実行時 |
| `learned_exclude.json` | 自動学習（3回失敗で追加） | scraper_agent が自動更新 |
| `domain_fail_stats.json` | ドメイン失敗カウンター | scraper_agent が自動更新 |

**手動でドメインを除外したい場合:**
`output/exclude_list.csv` を直接編集（フォーマット: `ドメイン,理由,追加日`）

---

## メンバー向け セットアップ手順

### ① Pythonのインストール確認

まずPythonが入っているか確認します。

**コマンドプロンプトを開く:**
1. キーボードの `Windowsキー` + `R` を押す
2. `cmd` と入力して `Enter`
3. 黒い画面（コマンドプロンプト）が開く

**バージョン確認:**
```
python --version
```

→ `Python 3.11.x` や `Python 3.12.x` と表示されればOK

→ 「認識されていません」と出た場合: [https://www.python.org/downloads/](https://www.python.org/downloads/) からインストール
　 インストール時に **「Add Python to PATH」にチェックを入れること**（重要）

---

### ② コードフォルダを配置する

管理者から受け取った `list_tool` フォルダを、自分のPCの以下の場所に置く:

```
C:\Users\（自分のユーザー名）\list_tool\
```

例: ユーザー名が `tanaka` の場合 → `C:\Users\tanaka\list_tool\`

---

### ③ ライブラリのインストール（初回のみ・5〜10分）

コマンドプロンプトで以下を1行ずつ実行:

```
cd C:\Users\（自分のユーザー名）\list_tool
```
```
pip install -r requirements.txt
```

→ ずらずらとインストールログが流れ、最後に `Successfully installed ...` と出ればOK

---

### ④ 動作確認

```
python main.py
```

起動メニューが表示されれば成功。

---

## メンバー向け 毎回の使い方

### STEP 1: 起動

1. `Windowsキー` + `R` → `cmd` → `Enter`（コマンドプロンプトを開く）
2. 以下を入力（ユーザー名を自分のものに変える）:

```
cd C:\Users\（自分のユーザー名）\list_tool
```

3. 続けて実行:

```
python main.py
```

→ 起動メニューが表示される

### STEP 2: モード選択（すべて数字で回答）

```
登録方式を選択してください
  1: 確認後に登録（推奨）  ← 必ずこちらを選択
  2: 自動登録

検索モードを選択してください
  1: 自動モード（おすすめ）
  2: 手動モード（キーワードを自分で入力）

目標登録件数: 50  ← Enterで省略可

検索期間: 2  ← 直近1ヶ月が標準
```

### STEP 3: 実行中（基本は放置）

自動でフィルタリング・スクレイピングが進みます。

```
⚡ 自動登録 [A(9点)] 株式会社〇〇     ← スコアが高い企業は自動でHubSpotへ登録
  [B(5点)] 候補追加: 株式会社△△        ← スコアが中間の企業は後で確認
  ✂ スクリーナーNG [上場企業]: 〇〇HD  ← 自動除外（対応不要）
```

### STEP 4: 承認ステップ（バッチ完了後に表示）

スコアが中間帯の企業だけが確認画面に表示されます。

```
  1. [B(5点) 信頼度:3/4] 株式会社〇〇
       URL : https://example.co.jp
       TEL : 03-1234-5678  代表: 山田太郎
       住所: 東京都渋谷区〇〇
       人数: 45名  業種: ITコンサルティング
       理由: 健康経営注力, 単一拠点

操作:
  y       → 全件登録
  n       → 全件スキップ
  1,3     → 番号指定で登録（1番と3番だけ登録）
  x2      → 2番を除外リストに追加（以後この会社は出なくなる）
```

**除外時の理由コード:**
| コード | 意味 |
|---|---|
| m | メディア・ポータルサイト |
| s | 規模が大きすぎる |
| i | 業種NG |
| o | その他 |

### STEP 5: 終了時のサマリーを確認

```
📊 精度改善サマリー
  除外理由の内訳:
    規模NG（大企業）: 5件
    NG業種: 3件
  自動除外リスト追加: example.co.jp  ← 2回以上除外されたドメインは自動学習
```

このサマリーで気になるパターンがあれば管理者に共有してください。

---

## 覚えること（3つだけ）

| やること | 操作 |
|---|---|
| 起動する | `python main.py` |
| 良い企業を登録する | `y`（全件）または `1,3`（番号選択） |
| 不要な企業を除外する | `x番号` → 理由コード入力 |

---

## HubSpot フィールドマッピング

| HubSpotフィールド | 取得元 |
|---|---|
| 会社名 | スクレイピング |
| ウェブサイト | 企業HP URL |
| 電話番号 | スクレイピング → 国際化変換 |
| 住所・都道府県・郵便番号 | スクレイピング |
| 業種 | スクレイピング |
| 従業員数 | スクレイピング |
| 説明（備考） | 媒体記事URL / 検索クエリ / ランク理由 |
