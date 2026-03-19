# 企業リストアップツール 全体設計書

**サービス**: Offi-Stretch（理学療法士によるオフィス出張施術）
**運営**: Well Body株式会社
**目的**: B2B営業のアタックリストを自動生成し、HubSpot CRMへ登録する

---

## ドキュメント構成（このファイルは大元のインデックス）

| ファイル | 内容 |
|---|---|
| `docs/agent_screener.md` | Agent1スクリーナー（pre_screen）詳細 |
| `docs/agent_researcher.md` | Agent2ディープリサーチャー（scraper_agent）詳細 |
| `docs/rank_criteria.md` | ランク判定基準（採点表・理想顧客プロファイル） |
| `docs/ng_conditions.md` | NG条件・除外ロジック詳細 |
| `docs/media_sources.md` | 優先媒体リスト（PR媒体・健康経営メディア） |
| `docs/search_patterns.md` | 有効検索パターン・知見 |
| `output/search_log.md` | 検索実績ログ（随時更新） |
| `output/call_logs/` | テレアポコールログ保存ディレクトリ |

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
  │
  ├─ 期間選択（1週間〜1年）
  │
  ├─ [STEP1] 媒体リストスクレイプ（最優先・自動モード時のみ）
  │    list_page_agent → 健康経営優良法人Excel / SUPER CEO / B-PLUS 等
  │    優先順序: 健康経営系 → PR媒体系  ※ docs/media_sources.md 参照
  │
  ├─ [STEP2] キーワード検索（STEP1 で目標未達の場合に続行）
  │    search_agent → DuckDuckGo検索  ※ docs/search_patterns.md 参照
  │
  ├─ [Agent1] スクリーナー（HTTPリクエストなし・高速）
  │    ※ docs/agent_screener.md 参照
  │
  ├─ [Agent2] スクレイプ・ランク判定（並列処理）
  │    scraper_agent → rank_agent
  │    ├─ スコア高・信頼度十分 → 自動登録（確認モードでも）
  │    ├─ スコア中間帯 → 確認待ちリストへ
  │    └─ スコア低・NG → 自動スキップ
  │    ※ docs/agent_researcher.md / docs/rank_criteria.md 参照
  │
  ├─ [確認モードの場合] 候補一覧を表示 → ユーザー承認
  │    y=全件登録 / n=スキップ / 1,3=個別選択 / x2=除外リストへ
  │
  ├─ HubSpot登録（hubspot_agent）
  │    重複チェック3段階（ドメイン/会社名/法人格正規化）
  │
  └─ 完了レポート

[24時間連続稼働] python main.py --daemon [--interval=60]
  └─ 媒体リスト → キーワード検索を1サイクルとして無限ループ

[監査] python main.py --audit [--scrape]
  └─ HubSpot登録済み企業を事後チェック → NG企業にフラグ + 学習

[ドキュメント更新] python main.py --update-docs
  └─ config.py の現在の設定値を OVERVIEW.md に自動反映
```

---

## ファイル構成

```
list_tool/
├── OVERVIEW.md               # このファイル（全体インデックス）
├── main.py                   # エントリーポイント・UI・処理フロー制御
├── config.py                 # 設定・定数・学習データ管理
├── agents/
│   ├── search_agent.py       # DuckDuckGo検索・除外フィルタ
│   ├── scraper_agent.py      # 企業HP情報取得・バリデーション
│   ├── rank_agent.py         # A/B/C/NG ランク判定（スクリーナー含む）
│   ├── hubspot_agent.py      # HubSpot API（登録・重複チェック）
│   ├── hubspot_auditor.py    # 登録済み企業の事後バリデーション
│   ├── list_page_agent.py    # リストページ（PDF/Excel/HTML）から一括抽出
│   └── keyword_agent.py      # 検索クエリの自動生成・学習
├── docs/                     # 機能別詳細ドキュメント
│   ├── agent_screener.md
│   ├── agent_researcher.md
│   ├── rank_criteria.md
│   ├── ng_conditions.md
│   ├── media_sources.md
│   └── search_patterns.md
└── output/
    ├── results.csv            # 登録成功した企業一覧
    ├── ng_list.csv            # NG企業リスト
    ├── exclude_list.csv       # 除外ドメインリスト（手動追加・承認時除外）
    ├── learned_exclude.json   # 自動学習した除外ドメイン
    ├── domain_fail_stats.json # ドメイン失敗カウンター（3回→自動除外）
    ├── feedback.csv           # テレアポ結果フィードバック
    ├── keyword_stats.json     # 検索クエリ別ヒット率ログ
    ├── search_log.md          # 検索実績ログ（手動更新）
    ├── call_logs/             # テレアポコールログ（手動保存）
    └── tool.log               # 実行ログ
```

---

## ランク判定サマリー（詳細は `docs/rank_criteria.md`）

**理想顧客**: 情報通信・金融・人材・商社・コンサル等B2B、健康意識高い経営者、従業員20〜100名、単一拠点

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

**NG条件**: 上場企業・従業員200名超・NG業種（飲食・toC小売・医療・建設・運送・警備・SES等）・個人事業主・フランチャイズ
→ 詳細: `docs/ng_conditions.md`

---

## 媒体ソース（詳細は `docs/media_sources.md`）

<!-- AUTO_UPDATE_START: media_sources -->
| URL | 種別 | 備考 |
|---|---|---|
| https://kenko-keiei.jp/houjin_list/ | 健康経営優良法人（経産省認定） | Excel自動DL・中小規模のみ |
| https://superceo.jp/list/company | PR媒体 - SUPER CEO | 静的HTML・50音順一覧 |
| https://business-plus.net/interview/ | PR媒体 - B-PLUS | 静的HTML・インタビュー一覧 |
<!-- AUTO_UPDATE_END: media_sources -->

---

## 精度向上サイクル

```
1. リストアップ実行（媒体リスト → キーワード検索）
        ↓
2. 承認ステップで不要企業を除外
   → x[番号] で exclude_list.csv に追加
        ↓
3. テレアポ実施 → 結果を output/call_logs/ に保存
   → feedback.csv に結果記録
        ↓
4. 傾向分析 → ランク判定基準・検索パターンの調整
   ※ docs/rank_criteria.md / docs/search_patterns.md を更新
        ↓
5. 繰り返し（精度向上）

【自動学習ループ】
  scraper失敗 → record_domain_fail() → 3回で learned_exclude.json へ
  承認時除外 → exclude_list.csv へ
  ng_list.csv の企業URL → ドメイン抽出 → 次回リストアップから自動除外
  監査NG → exclude_list.csv へ
```

---

## コマンド一覧

```bash
# 通常実行（毎回の使い方）
cd C:\Users\user\list_tool
python main.py

# 24時間連続稼働モード（確認なし・全自動登録）
python main.py --daemon

# 連続稼働モード（サイクル間隔を変更 例: 30分ごと）
python main.py --daemon --interval=30

# HubSpot監査（ドメインチェック＋会社名チェック）
python main.py --audit

# HubSpot監査（+ 軽量スクレイプ検証）
python main.py --audit --scrape

# OVERVIEW.md の自動更新セクションを現在の config.py から再生成
python main.py --update-docs
```

---

## メンバー向け セットアップ手順

### ① Pythonのインストール確認

**コマンドプロンプトを開く:**
1. `Windowsキー` + `R` → `cmd` → `Enter`

**バージョン確認:**
```
python --version
```
→ `Python 3.11.x` や `Python 3.12.x` と表示されればOK
→ 「認識されていません」の場合: https://www.python.org/downloads/ からインストール（**「Add Python to PATH」にチェック**）

### ② コードフォルダを配置する

受け取った `list_tool` フォルダを配置:
```
C:\Users\（自分のユーザー名）\list_tool\
```

### ③ ライブラリのインストール（初回のみ）

```
cd C:\Users\（自分のユーザー名）\list_tool
pip install -r requirements.txt
```

### ④ 動作確認

```
python main.py
```
起動メニューが表示されれば成功。

---

## メンバー向け 毎回の使い方

### STEP 2: モード選択（すべて数字で回答）

```
登録方式: 1（確認後に登録・推奨）
検索モード: 1（自動モード）
目標登録件数: 50（Enterで省略可）
検索期間: 2（直近1ヶ月が標準）
```

### STEP 3: 実行中（基本は放置）

```
⚡ 自動登録 [A(9点)] 株式会社〇〇     ← スコア高→自動登録
  [B(5点)] 候補追加: 株式会社△△        ← スコア中→後で確認
  ✂ スクリーナーNG [上場企業]: 〇〇HD  ← 自動除外（対応不要）
```

### STEP 4: 承認ステップ

```
操作:
  y       → 全件登録
  n       → 全件スキップ
  1,3     → 番号指定で登録
  x2      → 2番を除外リストに追加
```

**除外時の理由コード:**

| コード | 意味 |
|---|---|
| m | メディア・ポータルサイト |
| s | 規模が大きすぎる（200名超） |
| t | 規模が小さすぎる（10名未満） |
| i | 業種NG |
| o | その他 |

### 覚えること（3つだけ）

| やること | 操作 |
|---|---|
| 起動する | `python main.py` |
| 良い企業を登録する | `y` または `1,3` |
| 不要な企業を除外する | `x番号` → 理由コード入力 |

---

## HubSpot フィールドマッピング

| HubSpotフィールド | 取得元 |
|---|---|
| 会社名 | スクレイピング |
| ウェブサイト | 企業HP URL |
| 電話番号 | スクレイピング → 国際化変換（+81） |
| 住所・都道府県・郵便番号 | スクレイピング |
| 業種 | スクレイピング |
| 従業員数 | スクレイピング |
| 説明（備考） | 媒体記事URL / 検索クエリ / ランク理由 |
