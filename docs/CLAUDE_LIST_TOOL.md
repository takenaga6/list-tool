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

## ⚡ 現在の状態（2026-05-06 時点）

### ブランチ

```
作業ブランチ: feature/phase5-relax-must-conditions
   - Phase 5 全ステップ（Step 1〜8）実装済
   - Step 9: ドキュメント更新（現在）
   - Step 10: push + PR + マージ + Render反映（次のアクション）

最新コミット:
- 4c7d3dc Phase 5 Step 8: tests/test_phase5_signals.py 追加（25テスト・119件PASS）
- 28677cf Phase 5 Step 6: evaluate_useful_conditions に S7/S8/S9/S10 + 相互作用ボーナスを統合
- af1bcfb Phase 5 Step 5: check_interaction_bonus 関数を rank_agent.py に追加
- be477d5 Phase 5 Step 4: S7/S8/S9/S10 の加点判定関数を rank_agent.py に追加
- 0dbb9be Phase 5 Step 3: S7/S8/S9/S10 キーワード定義を config.py に追加
- 99570e1 Phase 5 Step 2: Phase 1必須条件③④⑤を削除

main 最新コミット: 58a2d1d（Phase 4 PR #6 マージ済）
```

### Phase 5 の状態

```
✅ Step 1: 49社シミュレーション（scripts/phase5_simulation.py）
✅ Step 2: Phase 1必須条件③④⑤削除（健康経営記載/採用情報/福利厚生 → 加点に降格）
✅ Step 3: S7/S8/S9/S10 キーワード定義（config.py）
✅ Step 4: 加点判定関数追加（rank_agent.py）
✅ Step 5: check_interaction_bonus 関数追加
✅ Step 6: evaluate_useful_conditions に統合（+ evaluate_rank_v2 閾値更新）
✅ Step 7: ランク閾値確定（A:8点以上 / B:5-7点 / C:1-4点 / NG:0点以下）
✅ Step 8: テスト追加（25テスト追加・119件全PASS）
🔄 Step 9: ドキュメント更新（現在）
⏸ Step 10: push + PR + マージ + Render反映（次のアクション）
```

### テスト

```
全テスト 119件 PASS
- Phase 5 で 94→119 件に増加（+25件）
- 新規追加: tests/test_phase5_signals.py（25件）
  - TestPhase1Relaxation（5件）: ③④⑤削除の確認
  - TestS7IsoCert（2件）/ TestS8Sdgs（2件）
  - TestS9PresidentHealth（4件）/ TestS10ProfitableIndustry（4件）
  - TestInteractionBonus（6件）
  - その他（2件）
```

---

## ✅ Phase 5 設計判断（2026-05-06 完了）

### 49社契約企業データ再集計（正しい数字）

```
【重要】旧ドキュメント（2026-04-30）の数字は誤りだった。Phase 5 v2.0 で訂正済み。

【旧（誤り）】
- 健康経営認定なしの継続率: 69% / ありの継続率: 20%（逆相関と誤判断）

【正（Phase 5 v2.0 確定）】
- 健康経営認定あり → 継続率 55%
- 健康経営認定なし → 継続率 30%
- 1.84倍差（正の予測子）

詳細シグナル倍率（継続14社 vs 解約24社 で計算）:
- ISO認定: 2.42倍差 → S7 +2点
- SDGs宣言: 1.84倍差 → S8 +1点
- 社長メッセージ詳細: 2.46倍差 → S9 +1点（自動判定限界で減額）
- 儲かっている業界: 最大3.27倍差 → S10 +1〜+3点（最強シグナル）
```

### 選択された設計（設計3: 折衷案）

```
→ Phase 1必須条件 ③④⑤ を削除（加点に降格）
→ S7/S8/S9/S10 新設・相互作用ボーナス追加
→ 継続率100%の3点セット組み合わせをボーナスで報酬
→ Phase 5 全ステップ実装完了（2026-05-06）
```

---

## 📂 主要ファイルの役割

### ランク判定（rank_agent.py）

```
3段階判定:
1. pre_screen: スクレイピング前・軽量NG（HTTPなし）
2. evaluate_rank: Phase 1必須条件チェック（①②⑥のみ有効・③④⑤は Phase 5 で削除）
3. evaluate_rank_v2: S1〜S10 + 相互作用ボーナスでランクA/B/C/NG
   - 8点以上=A / 5-7点=B / 1-4点=C / 0点以下=NG（Phase 5 v2.0）
```

### Phase 1必須条件（rank_agent.py・check_phase1_must_conditions）

```
1つでも違反でNG（Phase 5 以降）:
① 業種NG: NG_INDUSTRY_KEYWORDS_PHASE1（9個・広告/メディア系）★維持
② レッドオーシャン業種: INDUSTRY_PROFIT_MEDIUM_KEYWORDS（6個・SI/総合商社）★維持
   - 例外: 大手プライム子会社
~~③ HP健康経営記載必須~~ → Phase 5 で S4 加点に降格（削除済）
~~④ HP採用情報必須~~     → Phase 5 で加点に降格（削除済）
~~⑤ 福利厚生記載必須~~   → Phase 5 で S3 加点に降格（削除済）
⑥ 従業員数フィルター: ★維持
   - 6名未満NG / 6-9名は士業のみ / 10-199名OK
   - 200-499名空白帯NG / 500名以上は大手プライム子会社のみ
```

### S1〜S10 加点シグナル（Phase 2 + Phase 5）

```
S1: PR有料媒体掲載（KENJA GLOBAL等）+1点
S2: 健康経営メディア掲載（アクサ生命等）+1点
S3: 法定外福利厚生記載（旧⑤必須から降格）+1点
S4: 健康経営注力（旧③必須から降格）+1点
S5: 半年以内のHPリニューアル +1点
S6: 自社ビル保有 +1点
S7: ISO認定取得（ISO9001/14001/27001/45001等）+2点　★Phase 5 新設
S8: SDGs/サステナビリティ宣言 +1点　★Phase 5 新設
S9: 社長メッセージ内健康記載（簡易版）+1点　★Phase 5 新設
S10: 儲かっている業界フラグ +1〜+3点　★Phase 5 新設（最強シグナル）

相互作用ボーナス（いずれか1つ発動で +3点・重複なし）:
- 3点セット（健康経営×ISO×採用高 等 6種）完成
- シグナル5個以上保有

ランク閾値（Phase 5 v2.0）:
- A: 8点以上 / B: 5-7点 / C: 1-4点 / NG: 0点以下
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

## ✅ 解消済み課題（朝のリストアップ問題）

### 朝のリストアップ実行（2026-04-30 朝・17分・登録0件）→ Phase 5 で対応済み

```
発生事象:
- list_page_agent: kenko-keiei.jp から 21,375社抽出
- でも処理した5社全部が「Phase1必須条件NG: HP健康経営記載なし」で弾かれた

真因と対応状況:
A. list_page_agent の HTML 抽出バグ（COMPANY_NAME_PATTERNS）
   → ✅ Phase 4 Step 2 で修正済
B. scraper_agent はトップページ＋一部サブページのみ取得
   → ⚠️ 未対応（deep_scraper は中止）ただし C の対応で軽減
C. 検索クエリで無関係URL返却
   → 一部発動・対症療法（継続課題）
D. Phase 1必須条件「健康経営記載」が厳しすぎる
   → ✅ Phase 5 Step 2 で③④⑤を削除。根本対応完了。
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
3. docs/DECISION_LOG.md を読む
4. git status で現在のブランチ確認
5. 何をやろうとしているかユーザーに確認
```

### 残作業（Phase 5 Step 10）

```
feature/phase5-relax-must-conditions の push + PR + マージ + Render反映
PRタイトル: "Phase 5: Phase 1必須条件緩和 + 加点シグナル拡充（S7-S10 + 相互作用ボーナス）"
マージ後、本番でリストアップ実行して登録件数確認
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

### 2026-05-06（Phase 5 実装セッション）

```
設計: Phase 5 v1.0 の穴を突いて v2.0 に刷新
   - 49社データ再集計で「逆相関」は誤りと確定（1.84倍差・正の予測子）
   - S9 自動判定不可の問題を発見・簡易版に変更
   - S10 は S10/S11/S12 を統合（業界属性の過大評価を防止）
   - 相互作用ボーナス設計（継続率100%の3点セット6種）

実装: Step 1〜8 完全実施
   - Step 1: 49社シミュレーション（Scenario C で精度確認）
   - Step 2: Phase 1必須条件③④⑤削除
   - Step 3: キーワード定義（config.py）
   - Step 4: 加点関数 4本追加
   - Step 5: check_interaction_bonus 追加
   - Step 6+7: evaluate_useful_conditions 統合・閾値更新
   - Step 8: テスト25件追加（119件PASS）

テスト結果: 119件全PASS
現在: Step 9（ドキュメント更新中）
```

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
