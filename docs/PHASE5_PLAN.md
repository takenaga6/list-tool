# Phase 5 実装計画書（Claude Code 引き継ぎ用）

> 2026-05-05 web Claude セッションで決定した実装計画
> Claude Code はこのファイルを読んで段階的に実装する
> 配置先: docs/PHASE5_PLAN.md

---

## 🎯 目的

```
朝のリストアップで「Phase 1必須条件NG」連発で 0件登録だった問題を、
ツール設計の根本見直しで解決する。

49社契約企業データから判明した事実:
- 健康経営認定なしの継続率: 69%（9/13）
- 健康経営認定ありの継続率: 20%（5/25）
- 継続社14社の過半数（64%）が健康経営認定なし

含意:
- 健康経営認定は「契約獲得しやすい」が「継続しやすい」シグナルではない
- 必須条件「健康経営記載」が厳しすぎた
- 加点シグナルとして扱うべき
- ISO・SDGs・社長メッセージ詳細が継続率の強い予測子
```

---

## 📋 設計（確定）

### Phase 1必須条件（緩和）

```
維持する条件（業種・規模のみ）:
① NG_INDUSTRY_KEYWORDS_PHASE1（9個・広告/メディア系）
② INDUSTRY_PROFIT_MEDIUM_KEYWORDS（6個・SI/総合商社）
   - 例外: 大手プライム子会社（is_parent_prime_subsidiary）
⑥ 従業員数フィルター（細分化）
   - 6名未満NG / 6-9名は士業のみ / 10-199名OK
   - 200-499名空白帯NG / 500名以上は大手プライム子会社のみ

削除する条件（加点に降格）:
③ HP健康経営記載 必須 → 削除
④ HP採用情報 必須 → 削除
⑤ 福利厚生記載 必須 → 削除
```

### Phase 2加点シグナル（拡充）

```
既存維持:
S1: PR有料媒体掲載
S2: 健康経営メディア掲載
S3: 法定外福利厚生記載
S4: 健康経営注力
S5: 半年以内のHPリニューアル
S6: 自社ビル保有

新規追加（49社データの継続率予測子）:
S7: ISO認定（継続率3.5倍差）★+1点
S8: SDGs/サステナ宣言（継続率2倍差）★+1点
S9: 社長メッセージ健康記載_詳細（継続率4.3倍差・最強）★+2点

スコア閾値見直し:
- 旧: A=5点以上 / B=2-4点 / C=0-1点 / NG=-1以下
- 新: 検討必要（49社データで実シミュレーション）
```

### 母集団

```
維持:
- 健康経営認証リスト（kenko-keiei.jp 等の S2_MEDIA_LIST_URLS）
- PR媒体リスト（S1_MEDIA_LIST_URLS）
- 既存の検索クエリ（search_agent）

→ 母集団は変えない。何を弾くかと何を加点するかを変える。
```

---

## 📁 前提: 49社データの配置

```
Step 7（49社データシミュレーション）の実行に必要。

配置先: list_tool/data/2026年営業分析シート.xlsx

注意:
- data/ ディレクトリは .gitignore で除外（顧客情報保護）
- Git にはコミットしない
- 各自ローカルに配置する

確認方法:
ls -la data/
→ 2026年営業分析シート.xlsx が存在すればOK

存在しない場合:
- ユーザーに「Excelファイルを data/ に配置してください」と確認
- データ取得元はユーザーのクラウドストレージ等
- Step 7 はこのファイルがないと実行不可
```

---

## 🚧 実装ステップ（Claude Code 用）

### Step 1: rank_agent.py の Phase 1必須条件緩和（30分）

```
ファイル: agents/rank_agent.py
関数: check_phase1_must_conditions（199行〜）

変更内容:
- ③④⑤ の判定ブロック削除（または条件をコメントアウト）
- 業種NG（①②）と従業員数（⑥）のみ残す

注意:
- evaluate_rank() 内で page_text を使う他の判定があるか確認
- 不要になった HEALTH_KEIEI_REQUIRED_KEYWORDS / RECRUIT_PAGE_REQUIRED_KEYWORDS / WELFARE_KEYWORDS は config.py から削除しない
   → 加点シグナルで使うため残す
```

### Step 2: 新規加点シグナル S7/S8/S9 のキーワード定義（30分）

```
ファイル: config.py

追加するキーワードリスト:

# S7: ISO認定キーワード
ISO_CERT_KEYWORDS = [
    "ISO9001", "ISO 9001", "ISO27001", "ISO 27001",
    "ISO14001", "ISO 14001", "ISO45001", "ISO 45001",
    "ISO22301", "ISMS", "プライバシーマーク", "Pマーク",
    "情報セキュリティ", "品質マネジメント",
    "環境マネジメント", "労働安全衛生マネジメント",
]

# S8: SDGs/サステナビリティキーワード
SDGS_KEYWORDS = [
    "SDGs", "サステナビリティ", "サステナブル",
    "持続可能", "ESG経営", "ESG取り組み",
    "サステナビリティレポート", "統合報告書",
    "TCFD", "CDP", "SBT認定",
    "SDGs宣言", "SDGsパートナー", "SDGs登録",
    "カーボンニュートラル", "脱炭素",
]

# S9: 社長メッセージ健康記載 詳細パターン
# 49社データで「詳細区分」が継続率4.3倍差
# 単純な健康記載でなく、具体的な施策・想い・数値が含まれているもの
PRESIDENT_HEALTH_DETAIL_KEYWORDS = [
    # 想い・哲学系
    "社員の健康を守る", "従業員の幸せ",
    "健康こそ最大の財産", "健康経営の重要性",
    "ワークライフバランス",
    
    # 具体的施策系
    "健康投資", "健康支援制度",
    "健康セミナーを実施", "健康診断の充実",
    "メンタルヘルスケアに注力",
    
    # 数値系（具体性指標）
    "健康経営優良法人を取得", "健康経営優良法人に認定",
]
```

### Step 3: rank_agent.py に加点関数 S7/S8/S9 追加（30分）

```
ファイル: agents/rank_agent.py

追加する関数:

def check_s7_iso_cert(text: str) -> tuple[bool, list[str]]:
    """S7: ISO認定の有無
    
    Returns:
        (matched, [hit_keywords])
    """
    from config import ISO_CERT_KEYWORDS
    hits = [kw for kw in ISO_CERT_KEYWORDS if kw in text]
    return (bool(hits), hits)


def check_s8_sdgs(text: str) -> tuple[bool, list[str]]:
    """S8: SDGs/サステナビリティの有無"""
    from config import SDGS_KEYWORDS
    hits = [kw for kw in SDGS_KEYWORDS if kw in text]
    return (bool(hits), hits)


def check_s9_president_health_detail(text: str) -> tuple[bool, list[str]]:
    """S9: 社長メッセージに健康記載 詳細パターン
    
    49社データで継続率4.3倍差（最強シグナル）
    """
    from config import PRESIDENT_HEALTH_DETAIL_KEYWORDS
    hits = [kw for kw in PRESIDENT_HEALTH_DETAIL_KEYWORDS if kw in text]
    return (bool(hits), hits)
```

### Step 4: evaluate_useful_conditions に S7/S8/S9 統合（30分）

```
ファイル: agents/rank_agent.py
関数: evaluate_useful_conditions（659行〜）

追加するスコアリング:
- S7: +1点
- S8: +1点
- S9: +2点（最強シグナル）

実装方針:
- 既存の S3/S4/S5/S6 の判定ロジックを参考
- has_s7 = check_s7_iso_cert(page_text) ...
- 各シグナルでスコア加算 + 理由文字列追加
```

### Step 5: ランク閾値の再調整（15分）

```
ファイル: agents/rank_agent.py
関数: evaluate_rank_v2（804行〜）

現状:
- A: 5点以上
- B: 2-4点
- C: 0-1点
- NG: -1点以下

検討事項:
- S9（+2点）を含む新シグナルでスコアの上限が上がった
- 閾値を見直すか
- 49社データの実シミュレーションで判断

暫定（最初のリリース）:
- A: 6点以上（+1）
- B: 3-5点（+1）
- C: 0-2点（+1）
- NG: -1点以下（変更なし）

→ Step 7（実シミュレーション）の結果次第で再調整
```

### Step 6: テスト追加（45分）

```
ファイル: tests/test_phase5_signals.py（新規）

追加するテスト:

# Phase 1必須条件緩和の確認
def test_phase1_no_health_keiei_passes():
    """HP健康経営記載なしでも Phase 1必須条件を通過する"""
    
def test_phase1_no_recruit_passes():
    """HP採用情報なしでも Phase 1必須条件を通過する"""
    
def test_phase1_no_welfare_passes():
    """福利厚生記載なしでも Phase 1必須条件を通過する"""

# 業種NG・規模フィルタは従来通り動く
def test_phase1_ng_industry_still_blocks():
    """広告代理店等は引き続きNG"""
    
def test_phase1_employee_filter_still_blocks():
    """従業員500名以上は引き続きNG（プライム子会社例外）"""

# 新規シグナル S7/S8/S9
def test_s7_iso_detected():
    """ISO9001 を検出できる"""
    
def test_s8_sdgs_detected():
    """SDGsキーワードを検出できる"""
    
def test_s9_president_health_detail_detected():
    """社長メッセージ健康記載_詳細パターンを検出できる"""

# スコア統合
def test_evaluate_useful_includes_s7s8s9():
    """evaluate_useful_conditions に S7/S8/S9 が含まれる"""
```

### Step 7: 49社データシミュレーション（30分）

```
ファイル: tests/test_phase5_simulation.py（新規）

目的:
49社契約企業データに対して、新ロジックで判定を実行し、
- 継続社14社のうち何社がA/B判定されるか
- 解約社24社のうち何社がC/NG判定されるか
を検証する。

成果物:
- シミュレーション結果のCSV出力
- ランク閾値の最適化判断材料

注意:
- 49社のExcelデータは事前に Python で読み込む
- 各企業の HP本文取得は不要（既存の属性データを使う）
- 「擬似的に Phase 1+2 を回す」スクリプト
```

### Step 8: 既存docs更新（30分）

```
更新ファイル:
- docs/rank_criteria.md
   - Phase 1必須条件の変更を反映
   - 加点シグナル S7/S8/S9 追加
- docs/CLAUDE_LIST_TOOL.md
   - Phase 5 実装完了を反映
- docs/PHASE_HISTORY.md
   - Phase 5 セクション追加
- docs/DECISION_LOG.md
   - Phase 5 設計判断を追記
```

### Step 9: コミット + PR + マージ + Render反映（15分）

```
ブランチ: feature/phase5-relax-must-conditions

コミット粒度:
1. Phase 5 Step 1: Phase 1必須条件緩和（③④⑤削除）
2. Phase 5 Step 2-4: S7/S8/S9 加点シグナル追加
3. Phase 5 Step 5: ランク閾値調整
4. Phase 5 Step 6: テスト追加
5. Phase 5 Step 7: 49社データシミュレーション
6. Phase 5 Step 8: ドキュメント更新

PR タイトル:
"Phase 5: Phase 1必須条件緩和 + 加点シグナル拡充（S7 ISO / S8 SDGs / S9 社長メッセージ詳細）"
```

---

## 📊 期待される効果

```
朝のリストアップ問題:
- リストアップ17分・登録0件 → 大幅改善見込み
- 健康経営記載なしの企業も Phase 1通過するように

49社データ整合:
- 継続社14社の過半数（健康経営認定なし）が取れるように
- ISO・SDGs・社長メッセージ詳細でランク差別化

既存資産活用:
- rank_agent.py 865行 ほぼ維持
- 学習システム v2.0 維持
- 段階的拡張で品質担保
```

---

## ⚠️ 注意事項（Claude Code への指示）

```
1. このファイルとリンクされた他ドキュメントを必ず先に読む
   - docs/CLAUDE_LIST_TOOL.md
   - docs/DECISION_LOG.md
   - docs/PHASE_HISTORY.md
   - docs/rank_criteria.md

2. ステップごとに動作確認
   - Step ごとに pytest 実行
   - 既存テスト（94件）が PASS するか確認
   - PASS しない場合は原因分析してから次のステップへ

3. 推測で進めない
   - わからない部分はユーザーに確認
   - 「こっちのほうがいいので入れました」は禁止
   - 選択肢と判断基準を提示してから進める

4. コードコメント
   - 日本語コメントで理由を残す
   - 49社データの継続率データを根拠として明示

5. 段階的コミット
   - Step ごとにコミット（後でレビュー可能なように）
   - コミットメッセージは日本語で具体的に

6. ユーザーは事業家
   - コーディング初心者
   - 概念から丁寧に説明
   - 専門用語は初出時に意味を添える
```

---

## 🚀 Claude Code への引き継ぎコマンド

```
claude を起動したら、以下を貼り付ける:

「list-tool プロジェクトです。Phase 5 の実装に着手します。

まず以下を順番に読んで現状把握してください:
1. docs/CLAUDE_LIST_TOOL.md（Claude指示書）
2. docs/PHASE5_PLAN.md（このファイル・Phase 5 実装計画書）
3. docs/DECISION_LOG.md（直近の意思決定）
4. docs/PHASE_HISTORY.md（Phase 1〜4 実装履歴）
5. docs/rank_criteria.md（最新ランク判定基準）

読み終わったら『文脈復元しました。Phase 5 Step 1 から進めますか？』と返答してください。

応答スタンス:
- 迎合・忖度禁止
- 結論から
- わからないことは「わからない」
- 推測で断定しない
- 私のアイデアにまず穴を突く
- 日本語で応答
- コーディング初心者なので概念から丁寧に
- 各 Step 完了ごとにユーザーに確認」
```

---

## 📅 想定タイムライン

```
Phase 5 実装（Claude Code）:
- Step 1: 30分（必須条件緩和）
- Step 2: 30分（キーワード定義）
- Step 3: 30分（加点関数追加）
- Step 4: 30分（評価統合）
- Step 5: 15分（閾値調整）
- Step 6: 45分（テスト）
- Step 7: 30分（シミュレーション）
- Step 8: 30分（ドキュメント更新）
- Step 9: 15分（commit + push + マージ）

合計: 約4時間15分

休憩・確認時間込み: 約5時間

→ 1日で完了可能。または 2日に分割推奨。
```
