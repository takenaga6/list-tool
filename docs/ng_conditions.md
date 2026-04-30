# NG条件・除外ロジック詳細

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
