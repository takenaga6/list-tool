# agents/ — 各エージェントの役割・ルール・バグパターン

## エージェント一覧（現存ファイル）

| ファイル | 役割 |
|---|---|
| `rank_agent.py` | 企業をA/B/C/NGにスコアリング（6シグナル + Phase 1必須条件） |
| `keyword_agent.py` | 検索クエリ自動生成・A/Bランク発見率で優先順位付け。keyword_stats.jsonに学習 |
| `search_agent.py` | 検索実行（Google CSE優先 → DuckDuckGoフォールバック） |
| `scraper_agent.py` | 企業サイトのスクレイピング（会社名・電話・住所・従業員数・業種・HP本文を抽出） |
| `hubspot_agent.py` | HubSpot CRM への企業登録（Phase 1で6プロパティ追加） |
| `list_page_agent.py` | PR媒体・健康経営認定リストページからの企業リスト取得 |

### 削除済みエージェント（過去のコードや古いREADMEで言及されることあり）

- ❌ `feedback_learner.py` — シグナルウェイト学習機能（廃止）
- ❌ `supplement_agent.py` — results.csv 自動補完機能（廃止）
- ❌ `monitor_agent.py` — ヘルスチェック・自動修復（廃止）

これらは現存しない。古いコードでimportされていたら削除する。

---

## rank_agent.py の設計

### 評価フロー（Phase 1反映済み）

```
1. pre_screen(search_result) — スニペット段階の高速NG（HTTPリクエスト不要）
   ├─ 上場企業表記チェック
   ├─ ホールディングス名チェック
   ├─ 大手グループ会社チェック
   ├─ 従業員数（>200, <10）チェック
   ├─ 多拠点チェック
   ├─ NG業種26個チェック
   ├─ 広告/メディア業種チェック（Phase 1）
   ├─ 200-499名空白帯チェック（Phase 1）
   └─ 6名未満チェック（Phase 1）

2. evaluate_rank(company_info, search_results, page_text) — 精密判定
   ├─ 既存NGチェック（上場・ホールディングス・NG業種・従業員数・拠点）
   ├─ check_phase1_must_conditions(page_text) — Phase 1必須条件
   └─ シグナル判定（S1〜S6）

3. ランク決定
   - A: S1/S2あり + S3〜S6が2つ以上
   - B: S1またはS2に該当 / S1/S2なしで S3〜S6が3つ以上
   - C: S1/S2なしで S3〜S6が1〜2つ
   - NG: 必須条件違反 or スコア基準未達
```

### スコアリング（6シグナル）

```
S1: PR有料媒体掲載（KENJA GLOBAL、エコノミスト、Newsweek等）  → S1単独でB確定
S2: 健康経営メディア掲載（アクサ生命、健康経営の広場、大同生命） → S2単独でB確定
S3: 法定外福利厚生
S4: 健康経営注力
S5: HPリニューアル
S6: 自社ビル
```

PR媒体クエリ経由・健康経営認定リスト経由は **+2点ボーナス**。

### Phase 1必須条件チェック（check_phase1_must_conditions）

`evaluate_rank` 内で呼ばれる。HP本文（`page_text`）が必要なため、scraper_agent.py から `_page_text` フィールドを受け取る。

```
1. 広告/メディア業種（業種・会社名・本文先頭500字）
2. レッドオーシャン業種（受託SI/総合商社）※大手プライム子会社は例外
3. HP健康経営記載なし → NG
4. HP採用情報なし → NG
5. 福利厚生記載なし（士業以外） → NG
6. 6-9名+士業以外 → NG
7. 6名未満 → NG
8. 200-499名（空白帯） → NG
9. 500名以上+非プライム子会社 → NG
```

戻り値: `(passed: bool, reason: str)`。失敗時は `reason` に NG理由を返す。

### 補助関数

```python
is_special_industry(text)         # 士業・投資運用判定（福利厚生例外用）
is_parent_prime_subsidiary(text)  # 大手プライム子会社判定
```

### NGチェックの注意点

- 従業員数は「従業員」だけでなく「社員数」「スタッフ数」も正規表現でカバー
- `company_info["employee_count"]`（scraperが抽出した数値）を先にチェック
- 200超は NG、10未満も NG

---

## scraper_agent.py の設計

### 従業員数の扱い

- `EMPLOYEE_PATTERNS` で「従業員数」「社員数」「スタッフ数」「XXX名のスタッフ」を抽出
- `validate_company_info` では **200超でもクリアしない**（rank_agentに判定させる）
- 1〜200の範囲のみ confidence +1、200超は値保持のままスルー

### Phase 1で追加したフィールド

scraper の戻り値（company_info）に以下が含まれる：

```python
{
    ...,
    "_page_text": str,  # HP本文のテキスト（rank_agentの必須条件チェックで使用）
}
```

main.py の `process_one_company()` で `evaluate_rank(company_info, [search_result], page_text=company_info["_page_text"])` のように渡される。

### minimal モード

S1/S2確定企業は `minimal=True` で軽量取得（電話番号・従業員数・都道府県のみ）。

---

## hubspot_agent.py の設計

### Phase 1で追加した書き込みプロパティ

`register_company()` 実行時、以下を自動セット：

```
- phase1_must_check_passed（Boolean）
- phase1_ng_reason（Text）
- industry_profit_estimate（Text）
- is_parent_prime_subsidiary（Boolean）
- has_kenkokeiei_hp（Boolean）
- has_recruit_page（Boolean）
```

これらのプロパティは **HubSpot側で手動作成済み**。HubSpotで未作成だとAPI呼び出し時にエラーになる。

### main.py からの値セット

```python
# Phase 1必須条件をクリアした社は phase1_must_check_passed=True
company_info["phase1_must_check_passed"] = True
company_info["has_kenkokeiei_hp"] = True
company_info["has_recruit_page"] = True
company_info["is_parent_prime_subsidiary"] = is_parent_prime_subsidiary(_full_text_for_phase1)

# Phase 1必須条件NGの場合
if "Phase1必須条件NG" in _ng_reason:
    company_info["phase1_must_check_passed"] = False
    company_info["phase1_ng_reason"] = _ng_reason
```

---

## keyword_agent.py の設計

### 検索クエリの自動生成

PR媒体名・健康経営キーワード・47都道府県の組み合わせから2803個のクエリを生成。

### 学習データ

`output/keyword_stats.json` に以下を記録：
- ヒット数（`record_hit(query, count)`）
- NG結果（`record_ng(query)`）
- ランク結果（`record_rank_result(query, rank)`）

### 既知の課題（Phase 3で改修予定）

「マイナー媒体名 × 地方」の組み合わせはGoogleにヒットしにくい：
- 2026-04-28ログ：80検索クエリで177 NG、登録0件
- 検索クエリと地方の組み合わせが弱い → `keyword_agent.py` 全体を見直し予定

---

## list_page_agent.py の設計

### S1（PR有料媒体リストページ）

```python
S1_MEDIA_LIST_URLS = [
    "https://superceo.jp/list/company",       # SUPER CEO
    "https://business-plus.net/interview/",   # B-PLUS
]
```

`scrape_s1_media()` で取得 → 各社に `source_confirmed_s1=True` フラグを付与。

### S2（健康経営メディアリストページ）

```python
S2_MEDIA_LIST_URLS = [
    "https://kenko-keiei.jp/houjin_list/",       # 健康経営優良法人（Excel自動DL）
    "https://www.voice-report.jp/",              # アクサ生命ボイスレポート
    "https://kenkoukeiei-media.com/",            # 健康経営の広場
    "https://daido-kenco-award.jp/companies/",   # 大同生命
]
```

`scrape_s2_media()` で取得 → 各社に `source_confirmed_s2=True` フラグを付与。

S1/S2確定企業は scraper_agent.py で `minimal=True` 取得（高速）。

---

## search_agent.py の設計

### 検索エンジンフォールバック

```
1. Google Custom Search API（GOOGLE_CSE_API_KEY設定時）
2. DuckDuckGo
3. その他（Yahoo, Brave, Mojeek, Yandex）
```

並列実行ではなく、順次フォールバック。

### URL判定

`looks_like_company_url(url, signals)` で「企業HPらしいURL」を判定。
- `.co.jp` は常に True
- `.com` はシグナル必要
- `.jp` `.net` 等は2つ以上のシグナル必要

---

## 既知のバグパターン

### 1. signal_weights.json への参照（廃止済み）

過去のコードで `signal_weights.json` を読むコードが残っていたら削除する。

### 2. feedback_learner / supplement_agent / monitor_agent の import エラー

存在しないファイルを import しているコードが残っていないか確認。

### 3. evaluate_rank の signature 変更（Phase 1で）

```python
# 旧
evaluate_rank(company_info, search_results)

# 新（Phase 1）
evaluate_rank(company_info, search_results, page_text="")
```

`page_text` 引数なしで呼び出しても動くが、Phase 1必須条件チェックがスキップされるので注意。

---

## 改修時の注意

### Phase 2（リスト条件全面見直し）の方針

Phase 1の必須条件のみから、**「必須 + 加点 + 減点」3層構造**へ進化させる。

詳細はプロジェクトルートの `Phase2_実装計画.md` 参照。

実装時の修正対象：
- `rank_agent.py` に評価関数を追加
- `config.py` に業種マッピング・立地キーワード・採用媒体キーワード追加
- 既存の `evaluate_rank()` は破壊せず、`evaluate_rank_v2()` として並列追加

### テスト書き方

- `tests/test_phase1_must_conditions.py` を参考に
- リポジトリルートから実行：`python -m pytest tests/ -v`
- `cd tests; pytest` は ModuleNotFoundError で失敗する
