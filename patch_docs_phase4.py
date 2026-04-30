"""
Phase 4: 既存docs 本格更新パッチ

更新対象（本格更新）:
- docs/rank_criteria.md     : Phase 1必須条件 + Phase 2 evaluate_rank_v2 全反映
- docs/ng_conditions.md     : Phase 1必須条件追加
- docs/agents/list_page_agent.md : Step 2 修正 + 5エンジン検索反映
- docs/agents/keyword_agent.md   : Phase 3.3 v2.0 反映

更新対象（注記のみ追加）:
- docs/agent_screener.md
- docs/agent_researcher.md
- docs/media_sources.md
- docs/search_patterns.md
- docs/agents/rank_agent.md
- docs/agents/scraper_agent.md
- docs/agents/search_agent.md
- docs/agents/hubspot_agent.md
- docs/agents/hubspot_auditor.md

実行:
    python patch_docs_phase4.py
"""

import shutil
from pathlib import Path

# ============================================================
# 完全置換ファイル（4ファイル）
# ============================================================

RANK_CRITERIA_NEW = '''# ランク判定基準（rank_agent）詳細

> ⚠️ **このファイルは Phase 4 Step 1+2 反映後の最新版**（2026-04-30）
> 過去のセッション履歴・意思決定ログは以下を参照:
> - docs/CLAUDE_LIST_TOOL.md（Claude指示書）
> - docs/PHASE_HISTORY.md（実装履歴）
> - docs/DECISION_LOG.md（意思決定ログ）

**ファイル**: `agents/rank_agent.py`
**主要関数**: `pre_screen()` / `check_phase1_must_conditions()` / `evaluate_rank_v2()`

---

## 理想顧客プロファイル（Offi-Stretch 契約実績ベース）

| 軸 | 内容 |
|---|---|
| **業種** | 情報通信・金融・人材・商社・コンサル・士業等の高利益率B2B |
| **意識** | 社長 or ウェルフェア担当者が健康意識高い |
| **ブランド** | PR媒体に掲載（承認欲求・ブランド意識高い） |
| **福利厚生** | 法定外福利充実だがフィジカルケアは未着手 |
| **規模・拠点** | 自社ビル or 固定オフィス、従業員10〜199名、単一〜少拠点 |

---

## 判定3段階（重要）

```
process_one_company で実行される判定:

1. pre_screen（軽量NG・HTTPなし）
   → 詳細は agent_screener.md
   
2. check_phase1_must_conditions（Phase 1必須条件・199行目）
   → スクレイピング後・page_text を見て判定
   → 1つでも違反でNG確定
   
3. evaluate_rank_v2（Phase 2 加点減点・804行目）
   → 5点以上=A / 2-4点=B / 0-1点=C / それ以下=NG
```

---

## Phase 1 必須条件（check_phase1_must_conditions）

### ① 業種NG: NG_INDUSTRY_KEYWORDS_PHASE1（9個）

```
広告代理店, 総合広告, PR会社, マーケティング会社,
クリエイティブエージェンシー, メディア運営, 出版社,
デジタルマーケティング, デジタルエージェンシー
```

判定対象: company_name / industry / page_text先頭500文字  
理由表示: "NG業種(広告/メディア): {キーワード}"  
根拠: 49社契約企業データで0/4 全社非継続

### ② レッドオーシャン業種: INDUSTRY_PROFIT_MEDIUM_KEYWORDS（6個）

```
受託開発, システム開発, SI, SIer,
システムインテグレ, 総合商社
```

例外: 大手プライム子会社（is_parent_prime_subsidiary）  
理由表示: "レッドオーシャン業界(利益率中): {キーワード}"  
根拠: 該当社は17%しか継続しない

### ③ HP健康経営記載必須: HEALTH_KEIEI_REQUIRED_KEYWORDS（35個）

**Phase 4 Step 1 で 12個 → 35個 に拡充**

```
既存12個（抽象語彙）:
健康経営, 働き方改革, 従業員の健康,
ホワイト500, ブライト500, 健康経営優良法人,
ウェルビーイング, Well-being, well-being,
ウェルネス経営, 従業員のwell, 社員のwell

認証系（経済産業省）5個:
健康経営優良法人2024, 健康経営優良法人2025, 健康経営優良法人2026,
ネクストブライト1000（中小規模501-1500位）, 健康経営銘柄（東証）

認証系（厚生労働省）5個:
ユースエール, プラチナくるみん, えるぼし, プラチナえるぼし,
安全衛生優良企業マーク（SHEM）

健康施策（法定外のみ）13個:
脳ドック, がん検診, 人間ドック,
メンタルヘルスケア, メンタルヘルス,
健康保険組合, 保健指導,
健康増進, 健康配慮,
従業員健康, 社員健康,
健康支援, 健康サポート

※ くるみん（通常）は 49社データで効果なし（0%）のため除外
※ 健康診断・産業医・ストレスチェックは法定内のため除外
```

理由表示: "HP健康経営記載なし"

### ④ HP採用情報必須: RECRUIT_PAGE_REQUIRED_KEYWORDS（10個）

```
採用情報, 採用 情報, Recruit, Recruiting,
Career, Careers, 新卒採用, 中途採用,
募集要項, 求人情報
```

理由表示: "HP採用情報なし"

### ⑤ 福利厚生記載必須: WELFARE_KEYWORDS（26個）

```
マッサージ, 整体, 酸素カプセル, 社員旅行, 食事補助, 食事手当,
法定外福利厚生, リフレッシュ休暇, スポーツジム, フィットネス,
健康サポート, 鍼灸, カイロプラクティック, リラクゼーション,
ウェルネス, 健康手当, 人間ドック, ヨガ, ストレッチ,
スポーツ補助, 部活動, サークル, 保養所, 社食,
無料ランチ, ドリンク無料
```

例外: 士業/投資運用（FUKURI_LEGAL_ONLY_OK_INDUSTRY 17個）  
理由表示: "福利厚生記載なし(士業以外)"

### ⑥ 従業員数フィルター（EMPLOYEE_RANGE_CONFIG）

| 従業員数 | 判定 | 理由 |
|---|---|---|
| 6名未満 | NG | 極小規模(N名) |
| 6-9名 | 士業のみOK | 極小規模(N名)かつ士業以外 |
| 10-199名 | OK | - |
| 200-499名 | NG | 空白帯規模(N名) |
| 500名以上 | 大手プライム子会社のみOK | 大規模(N名)かつ大手プライム子会社でない |

---

## Phase 2 加点シグナル（evaluate_useful_conditions / S1〜S6）

```
S1: PR有料媒体掲載（KENJA GLOBAL / エコノミスト / Newsweek等）
S2: 健康経営メディア掲載（アクサ生命 / 健康経営の広場 / 大同生命等）
S3: 法定外福利厚生記載（WELFARE_KEYWORDS と同じ26個）
S4: 健康経営注力（HEALTH_MGMT_KEYWORDS 20個）
   - 健康経営, えるぼし, くるみん, 健康セミナー, 健康投資,
   - 健康支援, ウェルビーイング, 健康づくり, 社員の健康,
   - 従業員の健康, 健康促進, 健康経営宣言, 健康経営認定,
   - ストレスチェック, 産業医, 健康推進, ウェルフェア,
   - 健康委員会, 代表取締役.*健康, 社長.*健康, 社長.*福利厚生
S5: 半年以内のHPリニューアル
S6: 自社ビル保有
```

### 設計ルール（コメントから）

```
S1（PR有料媒体掲載）またはS2（健康経営メディア掲載）に該当した時点でBランク確定。
追加シグナル（S3〜S6）が2つ以上あればAランク。
S1/S2なしの場合はS3〜S6の合計で判定（3つ以上でB）。
```

---

## ランク基準（evaluate_rank_v2 の最終判定）

| ランク | スコア | 対応 |
|---|---|---|
| **A** | 5点以上 | 最優先・自動登録 |
| **B** | 2〜4点 | 優先・登録 |
| **C** | 0〜1点 | 候補・営業判断 |
| **NG** | -1点以下 | 即除外 |

---

## ⚠️ 設計再検討の必要性（2026-04-30 夜・要対応）

49社契約企業データの正確な再分析で衝撃の事実が判明:

```
- 優良継続中（14社）: 健康経営認定あり 35% / なし 64%
- 解約済み（24社）: 健康経営認定あり 83% / なし 16%
- 健康経営認定なしの継続率: 69%
- 健康経営認定ありの継続率: 20%
```

**含意**: 健康経営認定は「契約獲得しやすい」が「継続しやすい」シグナルではない。  
むしろ逆相関の可能性。Phase 1必須条件「健康経営記載」必須が厳しすぎた可能性。

詳細は `docs/DECISION_LOG.md` 参照。

### ツール設計の3選択肢（明日朝の判断）

```
設計1（現状）: 継続率の高い企業を絞り込む
設計2（シンプル化）: 健康経営認証リストから絞り込むだけ（ユーザー提案）
設計3（折衷）: 必須条件を緩和（健康経営記載を加点に降格）
```

---

## 自動登録・スキップ閾値

| 条件 | 動作 |
|---|---|
| ランクA（5点以上）かつ 信頼度2以上 かつ 必須フィールド全揃い | 確認モードでも自動登録（HubSpot） |
| ランクC未満 / pending最低条件不足（会社名＋電話or住所） | 候補リストにも出さず自動スキップ |

### 自動登録の必須フィールド（has_auto_fields）

| フィールド | 理由 |
|---|---|
| 会社名 | 登録の基本単位 |
| 企業URL | 重複チェック・HubSpotのドメイン紐付け |
| 電話番号 | テレアポ必須 |
| 従業員数 | ターゲット規模の確認（10〜199名） |
'''


NG_CONDITIONS_NEW = '''# NG条件・除外ロジック詳細

> ⚠️ **このファイルは Phase 4 Step 1+2 反映後の最新版**（2026-04-30）
> Phase 1必須条件は別途存在。下記参照。

---

## 判定の3層構造

```
1. pre_screen（軽量NG・HTTPなし） ← agent_screener.md
2. Phase 1必須条件（rank_agent.py 199行・check_phase1_must_conditions）
3. Phase 2加点減点 → ランクA/B/C/NG
```

---

## pre_screen NG条件（即除外・スコア0）

スクレイピング前にスニペット+URL+タイトルだけで判定（HTTPリクエスト不要）。

| カテゴリ | 条件 | 理由 |
|---|---|---|
| 上場企業 | 東証・NYSE・NASDAQ・証券コード・プライム市場等 | 規模大・意思決定が遅い |
| 既知ドメイン | SMALL_COMPANY_DOMAINS / LARGE_COMPANY_DOMAINS | 過去の学習結果 |
| 大規模企業 | ホールディングス・大手グループ子会社 | 同上 |
| 従業員超過 | 200名超 | 訪問コスト対効果が合わない |
| 従業員不足 | 10名未満 | 施術需要が少ない・予算不足 |
| 多拠点 | _MULTI_BRANCH_PATTERNS マッチ | 拠点ごとの契約が必要 |
| NG業種 | NG_INDUSTRY_KEYWORDS | 意思決定者・勤務形態がターゲット外 |

---

## Phase 1必須条件（rank_agent.py 199行）

スクレイピング後、HP本文（page_text）を含めて判定。1つでも違反でNG。

詳細は `rank_criteria.md` 参照。

```
① 業種NG: NG_INDUSTRY_KEYWORDS_PHASE1（9個・広告/メディア系）
② レッドオーシャン業種: INDUSTRY_PROFIT_MEDIUM_KEYWORDS（6個）
③ HP健康経営記載必須: HEALTH_KEIEI_REQUIRED_KEYWORDS（35個・Step 1拡充後）
④ HP採用情報必須: RECRUIT_PAGE_REQUIRED_KEYWORDS（10個）
⑤ 福利厚生記載必須: WELFARE_KEYWORDS（26個）
⑥ 従業員数フィルター（細分化）
```

---

## NG業種一覧（`config.py` — `NG_INDUSTRY_KEYWORDS`・26件）

### 建設・土木
`建設` `土木` `工務店` `ゼネコン`

### 運送・物流
`運送` `運輸` `物流` `宅配` `配送` `トラック` `引越`

### 医療・福祉
`病院` `クリニック` `診療所` `薬局` `調剤` `医療法人`
`介護` `デイサービス` `保育` `幼稚園`

### toC小売・飲食・サービス
`スーパー` `コンビニ` `飲食店` `レストラン` `居酒屋`
`美容院` `美容室` `ネイルサロン`
`小売` `量販店` `ドラッグストア`

### 警備・清掃
`警備` `ガードマン` `交通誘導`
`清掃業` `廃棄物` `ビルメンテナンス`

### 自動車・整備
`自動車販売` `車検` `カーディーラー`

### SES・人材派遣（常駐型）
`SES` `システムエンジニアリングサービス` `常駐` `派遣エンジニア`

### フランチャイズチェーン（toC）
主要コンビニ・ファストフードチェーン名

---

## NG業種（Phase 1必須条件専用 — `NG_INDUSTRY_KEYWORDS_PHASE1`・9件）

49社契約企業データで0/4 全社非継続のため Phase 1必須条件として独立判定:

```
広告代理店, 総合広告, PR会社, マーケティング会社,
クリエイティブエージェンシー, メディア運営, 出版社,
デジタルマーケティング, デジタルエージェンシー
```

---

## レッドオーシャン業種（— `INDUSTRY_PROFIT_MEDIUM_KEYWORDS`・6件）

該当社は17%しか継続しない（49社データ）。大手プライム子会社のみ例外:

```
受託開発, システム開発, SI, SIer,
システムインテグレ, 総合商社
```

---

## 除外ドメイン管理（4ソース統合）

`config.py` — `load_exclude_list_csv()` が起動時に統合読み込み

| ソース | ファイル | 更新タイミング |
|---|---|---|
| 自動学習（スクレイプ失敗3回） | `output/learned_exclude.json` | scraper_agent が自動更新 |
| 手動追加・承認時除外・監査NG | `output/exclude_list.csv` | 承認ステップ(x操作) / 監査実行時 |
| NG企業URL → ドメイン自動抽出 | `output/ng_list.csv` | HubSpot重複検出時・監査NG時 |
| 失敗カウンター | `output/domain_fail_stats.json` | scraper_agent が自動更新 |

---

## 除外済み企業（excluded_companies.json）

新規追加（Phase 2以降）:

```
NG判定・HubSpot重複で弾かれた企業を蓄積
次回実行時にHTTPリクエスト不要でスキップ

is_excluded_company(company_name) で判定
add_to_excluded_companies(company_name, reason) で追加

スクレイピング前後の2段階で参照:
- スクレイピング前: search_query が会社名のとき
- スクレイピング後: 実会社名で再確認
```

---

## 承認ステップの除外操作

```
x2      → 2番の企業を除外リストに追加
           → 理由コードを入力:
```

| コード | 意味 | 学習先 |
|---|---|---|
| m | メディア・ポータルサイト | exclude_list.csv |
| s | 規模が大きすぎる（200名超） | exclude_list.csv |
| t | 規模が小さすぎる（10名未満） | exclude_list.csv |
| i | 業種NG | exclude_list.csv |
| o | その他 | exclude_list.csv |

---

## 検索段階の除外フィルター（search_agent）

スクレイピング前にURLレベルで除外（`agents/search_agent.py`）:

1. **EXCLUDE_DOMAINS**: Google・YouTube・SNS・EC・求人媒体・大手ニュース等
2. **NG_DOMAIN_KEYWORDS**: news/media/books/research/navi/ranking 等
3. **learned_exclude.json + exclude_list.csv**: 自動学習＋手動追加
4. **海外TLD**: .us/.uk/.au/.de/.fr/.cn/.kr等
5. **媒体ドメイン自体**: KENJA GLOBAL等（is_media_page=True で企業HP抽出フローへ）

---

## NG条件の追加方法

### NG業種を追加する場合

`config.py` の以下を編集:
- `NG_INDUSTRY_KEYWORDS`（pre_screen 用）
- `NG_INDUSTRY_KEYWORDS_PHASE1`（Phase 1必須条件用）

### 特定ドメインを永続除外する場合

```
output/exclude_list.csv を直接編集
フォーマット: ドメイン,理由,追加日
例: example.co.jp,手動追加,2026-03-17
```

または承認ステップで `x番号` → 理由コード入力。
'''


LIST_PAGE_AGENT_NEW = '''# Agent: リストページエージェント（list_page_agent.py）

> ⚠️ **Phase 4 Step 2 + 2.4 反映後の最新版**（2026-04-30）
> COMPANY_NAME_PATTERNS のバグ修正済み。

**目的**
- 健康経営優良法人リスト・PR媒体リストなどから企業名を抽出し、公式HPを自動検索してリストアップ候補を生成する。
- 1つのURLから大量の企業をまとめて扱いたいときに使う。

---

## 1. 役割（責務）

### ✅ やること
- リストページ（HTML）から企業名を抽出
- PDF/Word/Excelファイル内の企業名も抽出（リンクがあればダウンロードして解析）
- 抽出した企業名ごとに DDGS（複数検索エンジン分散）で検索し公式HP候補を取得
- search_agent 形式の辞書リスト（url, title, snippet, search_query 等）を返す

### ❌ やらないこと
- 企業HPの詳細スクレイピング（scraper_agent が担当）
- ランク付け（rank_agent が担当）

---

## 2. S1/S2/通常 の3種類のスクレイパー

main.py の `_scrape_list_with_signal()` でURL種別を判定して分岐:

```
_scrape_list_with_signal(list_url):
   if list_url が S2_MEDIA_LIST_URLS に該当:
       return scrape_s2_media() → source_confirmed_s2=True
   elif list_url が S1_MEDIA_LIST_URLS に該当:
       return scrape_s1_media() → source_confirmed_s1=True
   else:
       return scrape_company_list_page() → フラグなし
```

### S1: PR有料媒体（config.py 48行）

```python
S1_MEDIA_LIST_URLS = [
    "https://superceo.jp/list/company",       # SUPER CEO
    "https://business-plus.net/interview/",   # B-PLUS
]
```

### S2: 健康経営メディア（config.py 54行）

```python
S2_MEDIA_LIST_URLS = [
    "https://kenko-keiei.jp/houjin_list/",       # 健康経営優良法人（経産省・21,375社）
    "https://www.voice-report.jp/",              # アクサ生命ボイスレポート
    "https://kenkoukeiei-media.com/",            # 健康経営の広場
    "https://daido-kenco-award.jp/companies/",   # 大同生命
]
```

`MEDIA_LIST_URLS = S2_MEDIA_LIST_URLS + S1_MEDIA_LIST_URLS`（自動モードで全部処理）

---

## 3. 主な機能

### 3-1. 企業名抽出

- HTML: テーブル・リスト要素 (`<table>`, `<ul>/<ol>/<li>`) を優先して抽出
- テキスト全体から正規表現による企業名抽出も補完
- `extract_company_names_from_html()` / `extract_company_names_from_text()` で実行

#### COMPANY_NAME_PATTERNS（Step 2 修正後）

```python
COMPANY_NAME_PATTERNS = [
    r"((?:株式会社|合同会社|有限会社|一般社団法人|NPO法人)[^\\s「」【】（）()\\n\\r<、。,]{1,30})",
    r"([^\\s「」【】（）()\\n\\r<、。,]{1,30}(?:株式会社|合同会社|有限会社))",
]
```

**Phase 4 Step 2 で追加**: 除外文字に「（」「(」「）」「)」追加  
理由: 「こそが働きがいを育てる（三和建設株式会社」のような壊れた抽出を防ぐ

#### NUMERIC_PREFIX_PATTERN（Step 2.4 で追加）

```python
NUMERIC_PREFIX_PATTERN = re.compile(r'^[\\d０-９①-⑳][.．、)）]?')
```

**Phase 4 Step 2.4 で追加**: 数字+ピリオド始まりの断片を除外  
理由: 「１．株式会社」「②株式会社」などのゴミ抽出を防ぐ

### 3-2. ファイル対応

- PDF（pdfplumber）
- Word .docx（python-docx）
- Excel .xlsx（openpyxl）

ライブラリがなければスキップ（ログ出力）。

### 3-3. 公式HP検索

- DDGS（複数検索エンジン分散: DuckDuckGo / Brave / Yandex / Mojeek / Yahoo）
- 結果のタイトル/本文/URLに対して企業名一致を判定
- 除外ドメインリスト（SKIP_DOMAINS, NG_DOMAIN_KEYWORDS）に合致するものは除外

---

## 4. 実行例

```python
from agents.list_page_agent import scrape_company_list_page

results = scrape_company_list_page("https://kenko-keiei.jp/houjin_list/")
for r in results:
    print(r["url"], r["search_query"])
```

---

## 5. 運用上の注意

- リストページの構造が大きく変わると抽出ロジックが破綻する可能性
   → 企業数が極端に減った場合は extract_company_names_from_html() の正規表現を調整
- 企業名が複数行にまたがる場合や複雑な表形式では抽出漏れが発生しやすい
- 大規模法人リスト（daikibo / 大規模 など）は自動的に除外
   → 違う語句の場合は手動で DAIKIBO_KEYWORDS を追加

---

## 6. 関連ファイル

- `agents/list_page_agent.py`: 実装本体
- `agents/search_agent.py`: 公式HP検索（5エンジン分散）
- `tests/test_list_page_agent.py`: テスト10件（Phase 4 Step 2 で追加）

---

## 7. テスト（tests/test_list_page_agent.py）

Phase 4 Step 2 で新規作成・10件:

```
基本ケース（4件）:
- test_simple_kabushiki_kaisha
- test_simple_yugen_kaisha
- test_simple_godou_kaisha
- test_simple_shadanhojin

Step 2 修正ケース（3件）:
- test_paren_zenkaku_breakdown（全角括弧）
- test_paren_hankaku_breakdown（半角括弧）
- test_paren_close_zenkaku（閉じ括弧）

Step 2.4 修正ケース（3件）:
- test_numeric_prefix_zenkaku_excluded（全角数字）
- test_numeric_prefix_hankaku_excluded（半角数字）
- test_marusuji_prefix_excluded（丸囲み数字）
```
'''


KEYWORD_AGENT_NEW = '''# Agent: キーワードエージェント（keyword_agent.py）

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
'''


# ============================================================
# 注記のみ追加するファイル（残り）
# ============================================================

NOTICE_TOP = '''> ⚠️ **このファイルは Phase 1〜2 時点の仕様**（2026-04-30 確認）
> Phase 3+4 の最新情報は以下を参照:
> - docs/CLAUDE_LIST_TOOL.md（Claude指示書）
> - docs/PHASE_HISTORY.md（Phase 1〜4 実装履歴）
> - docs/DECISION_LOG.md（意思決定ログ）
> - docs/rank_criteria.md（最新Phase 1必須条件）
> - docs/agents/list_page_agent.md（Step 2修正反映済）
> - docs/agents/keyword_agent.md（Phase 3.3 v2.0反映済）

---

'''

NOTICE_TARGET_FILES = [
    "docs/agent_screener.md",
    "docs/agent_researcher.md",
    "docs/media_sources.md",
    "docs/search_patterns.md",
    "docs/agents/rank_agent.md",
    "docs/agents/scraper_agent.md",
    "docs/agents/search_agent.md",
    "docs/agents/hubspot_agent.md",
    "docs/agents/hubspot_auditor.md",
]


# ============================================================
# 完全置換ファイル
# ============================================================

REPLACE_FILES = {
    "docs/rank_criteria.md": RANK_CRITERIA_NEW,
    "docs/ng_conditions.md": NG_CONDITIONS_NEW,
    "docs/agents/list_page_agent.md": LIST_PAGE_AGENT_NEW,
    "docs/agents/keyword_agent.md": KEYWORD_AGENT_NEW,
}


def main():
    # 完全置換ファイル
    for path_str, new_content in REPLACE_FILES.items():
        p = Path(path_str)
        if not p.exists():
            print(f"⚠️ スキップ（存在しない）: {path_str}")
            continue
        # バックアップ
        backup = Path(str(p) + ".bak.before_phase4_docs")
        shutil.copy(p, backup)
        # 置換
        p.write_text(new_content, encoding="utf-8")
        print(f"✅ 完全更新: {path_str}（バックアップ: {backup}）")

    # 注記のみ追加
    for path_str in NOTICE_TARGET_FILES:
        p = Path(path_str)
        if not p.exists():
            print(f"⚠️ スキップ（存在しない）: {path_str}")
            continue
        text = p.read_text(encoding="utf-8")
        if "CLAUDE_LIST_TOOL.md" in text:
            print(f"⚠️ スキップ（既に注記あり）: {path_str}")
            continue
        p.write_text(NOTICE_TOP + text, encoding="utf-8")
        print(f"✅ 注記追加: {path_str}")

    print("\n✅ Phase 4 ドキュメント更新完了")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
