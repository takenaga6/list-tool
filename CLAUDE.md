# CLAUDE.md - list-tool / xlsx-importer プロジェクト

このファイルは、list-tool / xlsx-importer プロジェクトで作業する Claude（claude.ai / Claude Code）が最初に読むべきルールを記載する。

個人OS・事業ポートフォリオ・判断軸など、事業全体に関わる内容は `~/projects/my-os/CLAUDE.md` を参照すること（グローバル CLAUDE.md）。
このファイルは list-tool / xlsx-importer 固有のルールに限定する。

---

## Well Body リスト生成ツール（list-tool / xlsx-importer）の引継ぎルール

以下のいずれかが該当する場合のみ、Claude は最初に
`~/projects/list_tool/docs/PHASE_HISTORY.md` を読む：

- ユーザーが「list-tool」「xlsx-importer」というツール名を明示的に挙げた
- ユーザーが「kaden-tool」「shodan-tool」を挙げ、それらと list-tool の連携について議論しようとしている
- ユーザーが list-tool 関連のリポジトリパス（`~/projects/list_tool/`、`~/projects/xlsx-importer/`）に言及した
- ユーザーが list-tool 関連の Phase 番号（Phase 0a、Phase 0b、Phase 5、Phase 7-A、Phase 7-B、Phase 7-C 等）に言及した
- ユーザーが list-tool / xlsx-importer 内部の固有名詞（rank_agent.py、keyword_agent.py、evaluate_rank_v2、phase1_must_check_passed、ng_industries.py 等）に言及した

該当する場合の動作：
1. 過去ログ検索の前に、必ず PHASE_HISTORY.md を読む
2. 特に末尾の「Phase 7-A 〜 Phase 0b 全体記録」セクション以降を最優先で読む
3. リスト条件（必須3つ + 加点シグナル + 従業員数表）は PHASE_HISTORY.md が真実の源
4. 過去ログ検索で得た情報より、PHASE_HISTORY.md の最新エントリを優先

該当しない場合（読まない）：
- 「リストアップ」「リスト生成」「企業発見」など、ツール名を伴わない一般的な言及
- AI業務改善のリスト議論、フアイア代理店リスト、PX Circles のターゲット選定
- Well Body の営業戦略・KPI・インターン組織・note記事・紹介施策
- 架電（kaden-tool 単独）、商談（shodan-tool 単独）の議論
- 雑談・他事業・個人的な相談

これを怠ると「右往左往」する Claude になる（2026-05-20 の反省）。

---

## 補足：旧 CLAUDE.md について

このファイルは元々、個人OS（私は誰か、事業ポートフォリオ、判断軸等）のコピーが入っていた。
ただし以下の経緯で「list-tool 専用ルール」に作り替えた（2026-05-20）：

- グローバル個人OSは `~/projects/my-os/CLAUDE.md` が真実の源として運用されている
- list_tool/CLAUDE.md の個人OSは古い（4/29版、my-os 側の 5/8 更新が反映されていない）
- list-tool プロジェクト固有のルール（PHASE_HISTORY.md 引継ぎルール等）を置く場所として再定義

---

## list-tool のコア判定ロジック変更ルール

このルールは list-tool プロジェクトに限定される。
他プロジェクトには適用しない。

### 適用対象
コア判定ロジック（rank_agent.py の pre_screen / evaluate_rank /
check_phase1_must_conditions、config.py のキーワード定義・スコアリング設定）を
変更する PR が対象。ドキュメント修正・テスト追加のみの PR は対象外。

### マージ手順
1. 実装 + ユニットテスト（事業仕様を反映したテストケース）
2. 実データ検証（既存のOK企業・NG企業のサンプルで挙動が変わらないか確認）
3. 検証結果に基づくマージ判断
4. マージ
5. マージ後の走行ログ観察（1〜2日、新規OK/NG判定をサンプルチェック）

### 「次のアクション候補」の出し方
完了報告時に「次のアクション候補」を出すとき、マージと実データ検証を
並列の選択肢として出さないこと。正しい順序は
「実データ検証 → 問題なければマージ」。

### マージ前の必須検証
- 既存OK企業のサンプル（10〜30社）で誤NG化が起きていないか
- 既存NG企業のサンプル（取れるなら）で誤OK化が起きていないか
- ドライラン1〜2クエリ（CSE 認証が有効な場合）

### マージ後の観察期間
- コア判定ロジック変更：1〜2日
- スコアリングロジック変更：3日
- データソース変更（外部API追加など）：1週間
観察期間中に致命的問題が見つかったら revert を即決判断する。

### このルールの背景
2026-05-20 の fix/prime-subsidiary-exception PR で、プライム子会社の
誤NG問題（3段階の上場/規模チェックで全弾きされていたバグ）が判明。
ユニットテスト 28/28 PASS の状態でも、PARENT_PRIME_KEYWORDS 厳格化が
既存OK企業に与える影響は実データ検証なしでは把握できなかった。
この経験を恒久ルール化した。
