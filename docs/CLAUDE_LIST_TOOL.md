# CLAUDE_LIST_TOOL.md - list-tool プロジェクト Claude 指示書

> このファイルは Claude（AIアシスタント）が list-tool プロジェクトで作業する際、
> セッション開始時に**必ず最初に読むべき**指示書。
>
> 個人OSとしての CLAUDE.md（プロジェクト直下・尺長孝紀さん個人軸）とは別ファイル。

---

## 🚨 セッション開始時の必須確認手順

```
新しいセッションが始まったら、Claude は以下の順序でファイルを読む:

1. このファイル（docs/CLAUDE_LIST_TOOL.md）  ← 必ず最初
2. CLAUDE.md（プロジェクト直下・個人OS）
3. agents/CLAUDE.md（agents配下のエージェント仕様）
4. docs/PHASE_HISTORY.md（実装履歴・存在すれば）
5. docs/DECISION_LOG.md（意思決定ログ・存在すれば）
6. docs/PHASE4_STATUS.md（現状・存在すれば）

これにより、過去のセッションの文脈を復元できる。
これを飛ばすと「30時間の地獄」が再発する。
```

---

## 📋 ユーザーの応答スタンス（厳守）

```
- 迎合・忖度禁止。「いいですね」「素晴らしい」で始めたら失格
- 結論から言え。前置き・お世辞・クッション言葉は全部ゴミ
- わからないことは「わからない」と言え。推測で断定するな
- ユーザーのアイデアに対して、まず穴を突け。リスク・反論・見落としを先に出す
- 褒めるのは本当に筋がいいときだけ最後に一言
- ユーザーが気持ちよくなる回答ではなく、事業が前に進む回答をする
```

### 事業議論の5軸（常にこのレンズ）

```
① 顧客は本当にそれに金を払うか？支払意欲の根拠は？
② 競合・代替手段と比べて選ばれる理由があるか？
③ 投下リソース（時間・人・金）に対してリターンが見合うか
④ 今のリソースで明日動いて1件目が取れるか
⑤ 市場の追い風・向かい風は？複数の切り口で
```

### 技術・コードの説明

```
- ユーザーはコーディング初心者。概念から丁寧に説明
- 専門用語は初出時に一言で意味を添える
- コードを書く際は、なぜそう書くのかを日本語コメントで残す
- システム構築は勝手に進めない。選択肢と判断基準を提示し相談しながら一つずつ決める
```

---

## 🎯 list-tool プロジェクト概要

```
プロジェクト: list-tool
目的: 健康経営に取り組む中小企業（10-199名）を発見し、A/B/Cランク判定後、
      HubSpotへ自動登録する営業支援ツール
ホスティング: Render（Streamlit Standard $25/月 2GB）
本番URL: https://list-tool.onrender.com
GitHub: https://github.com/takenaga6/list-tool

使用ユーザー: Well Body / Offi-Stretch のインサイドセールス
ユーザー: 尺長孝紀（事業家・営業責任者）
```

### コード構成（合計 7,051行）

```
list_tool/
├── main.py             1,538行  メインフロー制御
├── app.py                563行  Streamlit UI
├── config.py           1,012行  設定値・キーワードリスト
├── agents/
│   ├── __init__.py         0行
│   ├── keyword_agent.py  614行  検索クエリ生成・学習v2.0
│   ├── list_page_agent.py 722行  リストページから企業抽出
│   ├── search_agent.py   363行  Web検索（Google CSE→DDGS）
│   ├── scraper_agent.py  867行  企業HP情報抽出
│   ├── rank_agent.py     865行  3段階ランク判定
│   └── hubspot_agent.py  507行  HubSpot連携
├── docs/                  → 仕様ドキュメント（既存）
└── tests/                 → 全テスト 94件（Phase 4 Step 1+2 反映後）
```

---

## ⚡ 現在の状態（2026-04-30 時点）

### ブランチ

```
作業ブランチ: feature/phase4-deep-scraper
   - Phase 4 Step 1+2 実装済（コミット3個）
   - push 未実施 ← 重要
   
最新コミット:
- 9878ba4 Phase 4 Step 2.4: 企業名抽出のゴミ混入を除外
- 485ef37 Phase 4 Step 2: list_page_agent 企業名抽出バグ修正
- 814d27f Phase 4 Step 1: HEALTH_KEIEI_REQUIRED_KEYWORDS 拡充

main 最新コミット: 0399ba6（Phase 3 完了時）
```

### Phase 4 の状態

```
✅ Step 1: HEALTH_KEIEI_REQUIRED_KEYWORDS 拡充（12→35個）
✅ Step 2: list_page_agent COMPANY_NAME_PATTERNS 修正（除外文字に括弧追加）
✅ Step 2.4: 企業名抽出ゴミ混入除外（数字+ピリオド始まり）

🛑 Step 3: deep_scraper_agent 中止
   理由: 49社契約企業データ再分析で「ツール設計の根本問題」が判明
   詳細: docs/DECISION_LOG.md 参照（存在すれば）

⏸ 残作業: 
   - push + PR + マージ + Render反映
   - これは次のセッションで実行可能
```

### テスト

```
全テスト 94件 PASS
- Step 1+2 で 81→94 件に増加
- 新規追加: tests/test_list_page_agent.py（10件）
```

---

## 🚨 重要な意思決定（明日朝の設計再構築の出発点）

### 49社契約企業データ再分析（2026-04-30 夜）

```
驚愕の事実:
- 優良継続中（14社）: 健康経営認定あり 35% / なし 64%
- 解約済み（24社）: 健康経営認定あり 83% / なし 16%

つまり:
- 健康経営認定なしの継続率: 69%
- 健康経営認定ありの継続率: 20%
- 健康経営認定企業の方が解約率が高い

含意:
- 健康経営認定は「契約獲得しやすい」シグナル
- でも「継続しやすい」シグナルではない（むしろ逆）
- Phase 1必須条件「健康経営記載」必須が厳しすぎた可能性

健康経営なしで継続している企業（実例）:
- 瓜生法律事務所、SBI証券、レンフロジャパン
- ロッテベンチャーズジャパン、伊藤忠モードパル
- FBモーゲージ、桜川サービス、グランドバリュー、YN10
```

### ツール設計再検討の3選択肢

```
設計1（現状）: 継続率の高い企業を絞り込む
   → Phase 1必須条件を厳しく設定
   → でも継続率の予測子として「健康経営認定」は弱い

設計2（ユーザー提案）: 健康経営認証リストから絞り込むだけのシンプルツール
   → 「契約獲得率」軸で運用
   → 開発コスト大幅減

設計3（折衷）: 必須条件を緩和（健康経営記載を加点に降格）
   → 業種NG・規模フィルタは維持
   → 健康経営記載・採用・福利厚生は加点
   → ISO・SDGs・社長メッセージ詳細を加点シグナルに追加

明日朝、この3択から事業判断が必要
```

---

## 📂 主要ファイルの役割

### ランク判定（rank_agent.py）

```
3段階判定:
1. pre_screen（118行目）: スクレイピング前・軽量NG（HTTPなし）
2. evaluate_rank（267行目）: Phase 1必須条件チェック（旧ロジック）
3. evaluate_rank_v2（804行目）: Phase 2 加点-減点・ランクA/B/C/NG
   - 5点以上=A / 2-4点=B / 0-1点=C / それ以下=NG
```

### Phase 1必須条件（rank_agent.py 199行・check_phase1_must_conditions）

```
1つでも違反でNG:
① 業種NG: NG_INDUSTRY_KEYWORDS_PHASE1（9個・広告/メディア系）
② レッドオーシャン業種: INDUSTRY_PROFIT_MEDIUM_KEYWORDS（6個・SI/総合商社）
   - 例外: 大手プライム子会社
③ HP健康経営記載必須: HEALTH_KEIEI_REQUIRED_KEYWORDS（35個・Step 1拡充後）
④ HP採用情報必須: RECRUIT_PAGE_REQUIRED_KEYWORDS（10個）
⑤ 福利厚生記載必須: WELFARE_KEYWORDS（26個）
   - 例外: 士業/投資運用（FUKURI_LEGAL_ONLY_OK_INDUSTRY 17個）
⑥ 従業員数フィルター:
   - 6名未満NG / 6-9名は士業のみ / 10-199名OK
   - 200-499名空白帯NG / 500名以上は大手プライム子会社のみ
```

### S1〜S6 加点シグナル（Phase 2）

```
S1: PR有料媒体掲載（KENJA GLOBAL等）
S2: 健康経営メディア掲載（アクサ生命等）
S3: 法定外福利厚生記載
S4: 健康経営注力
S5: 半年以内のHPリニューアル
S6: 自社ビル保有

設計ルール:
- S1/S2あり時点でB確定
- S1/S2 + S3〜S6が2つ以上 → A
- S1/S2なしの場合、S3〜S6合計3つ以上 → B
```

### 媒体リスト（config.py 48-58行）

```python
S1_MEDIA_LIST_URLS = [
    "https://superceo.jp/list/company",       # SUPER CEO
    "https://business-plus.net/interview/",   # B-PLUS
]

S2_MEDIA_LIST_URLS = [
    "https://kenko-keiei.jp/houjin_list/",       # 健康経営優良法人（経産省・21,375社）
    "https://www.voice-report.jp/",              # アクサ生命ボイスレポート
    "https://kenkoukeiei-media.com/",            # 健康経営の広場
    "https://daido-kenco-award.jp/companies/",   # 大同生命
]
```

### 学習システム（keyword_agent.py v2.0）

```
データ: output/keyword_stats.json
構造: { _version: 2, queries: {...}, by_source: {...} }
v1→v2 自動マイグレーション

主要関数:
- record_hit(query, count, source)
- record_ng(query, source)
- record_rank_result(query, rank, source)
- get_sorted_queries(custom_keywords)
- get_media_stats()
```

---

## 🚨 既知の課題（朝のリストアップ問題）

### 朝のリストアップ実行（2026-04-30 朝・17分・登録0件）

```
発生事象:
- list_page_agent: kenko-keiei.jp から 21,375社抽出
- でも処理した5社全部が「Phase1必須条件NG: HP健康経営記載なし」で弾かれた

真因（4つ）:
A. list_page_agent の HTML 抽出バグ（COMPANY_NAME_PATTERNS）
   → ✅ Step 2 で修正済
B. scraper_agent はトップページ＋一部サブページのみ取得
   → ⏸ 採用ページ・CSRページの「健康経営」記載を見逃す
   → 未対応（deep_scraper検討も中止）
C. 検索クエリで無関係URL返却（hoken-mammoth.com 等）
   → 一部発動・対症療法
D. Phase 1必須条件「健康経営記載」が厳しすぎる可能性
   → ⚠️ 49社データ再分析で判明（ツール設計の根本問題）
```

---

## 🛠 環境

```
ローカル:
- OS: Windows 11
- Shell: Git Bash
- Editor: VS Code
- Python: 3.14.3
- pytest: 9.0.3

本番:
- Render Standard $25/月 2GB
- 自動再デプロイ（main へのpushで発動）

外部サービス:
- HubSpot (CRM)
- Google CSE → DuckDuckGo（フォールバック）
- DDGS経由で Brave / Yandex / Mojeek / Yahoo
```

---

## 📋 次のセッションでやるべきこと

### 最優先（次回セッション開始直後）

```
1. このファイルを読む
2. CLAUDE.md（個人OS）を読む
3. agents/CLAUDE.md を読む
4. docs/DECISION_LOG.md を読む（明日朝以降に作成予定）
5. git status で現在のブランチ確認
6. 何をやろうとしているかユーザーに確認
```

### 残作業

```
A. Phase 4 Step 1+2 の push + マージ + Render反映
   - feature/phase4-deep-scraper をmainにマージ
   - PRタイトル: "Phase 4 Step 1+2: キーワード拡充 + 企業名抽出バグ修正"
   - PR本文は CHAT履歴の前半参照
   - マージ後、自動再デプロイ確認

B. ツール設計再構築（明日朝以降）
   - 上記「ツール設計再検討の3選択肢」から判断
   - 49社契約企業分析シート（/mnt/user-data/uploads/2026年営業分析シート__3_.xlsx）を再分析
   - 設計2（シンプル化）の真剣検討

C. ドキュメント整備（時間あれば）
   - docs/PHASE_HISTORY.md 作成（Phase 1〜4 実装履歴）
   - docs/DECISION_LOG.md 作成（30時間の意思決定）
   - docs/PHASE4_STATUS.md 作成（現状サマリー）
   - 既存 docs/ 各ファイルの Phase 3+4 反映
```

---

## ⚠️ Claude が陥りがちな失敗パターン

### 過去の失敗（2026-04-30 セッションで発生）

```
1. コードを完全把握せずに修正方針を出す
   → 「広告/メディア」だけ見て「運送・警備」を見落とした
   → 対策: 修正前に必ず関連ファイル全体を grep で確認

2. データを誤読する
   → 49社の G列「認定なし（公式リスト確認済）」を「あり」と誤認
   → 対策: 数値や状態を述べる前に必ず原データで確認

3. 「最新版」と言いながら不完全
   → /mnt/user-data/outputs/ に作った仕様書が既存docsと重複・整合性なし
   → 対策: 既存資産を必ず確認してから新規作成

4. 文脈ロスト
   → セッション中、ユーザーが「A」と答えた時、選択肢を出していなかった
   → 対策: 常に選択肢を明示してから質問
```

---

## 🎯 Claude への直接の指示

```
1. このファイルとリンクされた他ドキュメントを必ず先に読む
2. 推測で断定しない。コードから事実を取る
3. 「迷子になりそう」と感じたらユーザーに即座に確認する
4. ユーザーは事業家。健康・睡眠・判断力が事業の成否を決める
   → 深夜作業を勧めない。命を守る判断をする
5. 既存資産（docs/、コード、コミット履歴）を破壊しない
6. CLAUDE.md（個人OS）と list-tool 専用指示は別ファイル
   このファイル（CLAUDE_LIST_TOOL.md）を編集する時、CLAUDE.md は触らない
```

---

## 🔄 このファイルの更新ルール

```
更新タイミング:
- Phase が進んだ時（Phase 5, 6, ...）
- 設計の根本判断が変わった時
- 新しい既知の課題が判明した時
- セッション終了時に「今のセッションで何が変わったか」を1段落追記

更新者:
- ユーザーが明示的に指示した時のみ Claude が更新
- 勝手に更新しない
```

---

## 📅 直近のセッション履歴

### 2026-04-30（13時間以上の長セッション）

```
朝: Phase 2 完全実装＆mainマージ
   - 49社契約企業データ分析
   - config.py / rank_agent.py 実装
   - 47テスト追加
   - PR #3 #4 マージ

午後: Phase 3.1 + 3.3 完全実装＆mainマージ
   - 検索回数 22424→2803 削減
   - 学習システムv2.0
   - PR #5 マージ

夕方: 本番動作確認 → 3つの問題発見
   - リストアップ17分・登録0件
   - 真因分析

夜: Phase 4 設計＆実装
   - Step 1+2 実装（コミット3個・push未）
   - Step 3（deep_scraper）設計→中止判断
   - 49社データ再分析で根本問題発覚
   - ツール設計再構築の必要性確認

深夜: ドキュメント整備（このファイル作成）
```

---

**このファイルを読んで「list-tool プロジェクトの文脈」を復元する。**
**読んだ後、ユーザーに「文脈を復元しました。次に何をしますか？」と確認する。**
