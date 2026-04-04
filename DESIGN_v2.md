# リストアップツール 再設計仕様書 v2

**作成日**: 2026-04-04
**目的**: 複雑・重い現行システムを、シンプルで精度の高い構造に刷新する

---

## 1. 設計方針

### 基本方針
> **S1またはS2に該当した時点でBランク確定。問答無用。**
> スクレイピングを追加してAランクを狙うのではなく、S1/S2ソースから効率よく量産する。

### 地域制限
**なし。全国対象。**

---

## 2. NG条件（Notion公式定義）

以下のいずれかに該当したら即除外。スコアに関係なく登録しない。

| 条件 | 内容 |
|---|---|
| 上場企業 | 東証・NYSE・証券コード・プライム市場等 |
| 従業員数 | 201名以上 または 9名以下 |
| 拠点数 | 3拠点以上 |
| NG業種① | 店舗展開型toC（飲食・小売・美容等） |
| NG業種② | 医療系（病院・クリニック・薬局・介護・保育） |
| NG業種③ | 建設・土木 |
| NG業種④ | 運送・運輸 |

---

## 3. シグナル定義（6本に削減）

S7（従業員数20〜40名）とS8（単一拠点）は**廃止**。
規模・拠点はNG条件側で絞るため、シグナルとして加点する必要がない。

| # | シグナル | 確認方法 | Bランク即確定 |
|---|---|---|---|
| **S1** | **PR有料媒体掲載実績あり** | ソース経由で確定 | **✅ S1単独でB確定** |
| **S2** | **健康経営メディア掲載実績あり** | ソース経由で確定 | **✅ S2単独でB確定** |
| S3 | 法定外福利厚生の記載あり | スクレイピング or 採用媒体 | — |
| S4 | 健康経営への注力が明確 | スクレイピング | — |
| S5 | 半年以内のHPリニューアル | スクレイピング | — |
| S6 | 自社ビル保有 | スクレイピング | — |

### ランク基準

| ランク | 条件 |
|---|---|
| **A** | S1またはS2 ＋ S3〜S6のうち2つ以上 |
| **B** | **S1またはS2に該当（即確定）**  または  S3〜S6のうち3つ以上 |
| **C** | S3〜S6のうち1〜2つ（S1/S2なし） |
| **NG** | NG条件いずれかに該当 |

> **HubSpot登録対象: B以上のみ**（Cはpending_review.jsonに蓄積・後で確認）

---

## 4. ソース体系（S1/S2に集中投資）

### S1ソース：PR有料媒体（掲載＝即B確定）

Notionの「※優先」媒体を最優先で処理する。

| 媒体名 | ドメイン | 取得方法 |
|---|---|---|
| KENJA GLOBAL | kenja.tv | キーワード検索 |
| エコノミストビジネスクロニクル | business-chronicle.com | キーワード検索 |
| エコノミストREC | weekly-economist.com | キーワード検索 |
| Newsweek WEB | newsweekjapan.jp | キーワード検索 |
| 時代のニューウェーブ | j-newwave.com | キーワード検索 |
| For JAPAN | forjapan-project.com | キーワード検索 |
| Leaders AWARD | leaders-award.jp | キーワード検索 |
| SMB Excellent AWARD | smbexcellentcompany.com | キーワード検索（SPA・一部制限あり） |
| B-PLUS | business-plus.net | リストページスクレイプ |
| SUPER CEO | superceo.jp | リストページスクレイプ |
| ベンチャー通信 | v-tsushin.jp | キーワード検索 |
| カンパニータンク | challenge-plus.jp | キーワード検索 |

### S2ソース：健康経営メディア（掲載＝即B確定）

S2は「媒体内のリスト」から企業を一括抽出するのが効率的。
キーワード検索に頼らず、媒体ページを直接スクレイプする。

| 媒体名 | URL | 取得方法 |
|---|---|---|
| **健康経営優良法人リスト（経産省）** | kenko-keiei.jp/houjin_list/ | Excel自動DL・一括抽出 ✅既対応 |
| **アクサ生命ボイスレポート** | voice-report.jp | 一覧ページスクレイプ ✅既対応 |
| 健康経営の広場 | kenkoukeiei-media.com | 一覧ページスクレイプ |
| 大同生命 | daido-kenco-award.jp | 一覧ページスクレイプ |

> **S2は媒体内のリストが宝の山。** 1回スクレイプするだけで数百〜数千社のB確定企業が取得できる。
> 健康経営優良法人は現行で対応済み。他3媒体は新規対応。

### S3ソース：採用媒体（法定外福利厚生の確認）

S1/S2なしでもS3が確定できれば採点対象になる。

| 媒体名 | URL | 検索キーワード |
|---|---|---|
| **ベネフィッツ** | bene-fits.jp/company/search | マッサージ・酸素カプセル・整体 |
| doda | doda.jp | 福利厚生充実（フィルタ設定済みURL） |
| マイナビ転職 | tenshoku.mynavi.jp | 福利厚生 |

---

## 5. パイプライン（シンプル3ステップ）

```
[STEP1] ソース収集（優先順位付き）

  S2ソース（最優先・一括取得）
    健康経営優良法人Excel → 数百〜千社を一括取得
    アクサ生命ボイスレポート → 一覧スクレイプ
    健康経営の広場 / 大同生命 → 一覧スクレイプ

  S1ソース（PR媒体・キーワード検索）
    「KENJA GLOBAL 株式会社」等のクエリで検索
    B-PLUS / SUPER CEO リストページをスクレイプ

  S3ソース（採用媒体）
    ベネフィッツで「マッサージ」「酸素カプセル」検索
    doda「福利厚生充実」フィルタ

  キーワード検索（S1/S2で目標件数未達の場合のみ）
    DuckDuckGo / Google CSE

[STEP2] ハードフィルター（HTTP不要・高速）

  以下のいずれかでスキップ:
    上場企業（スニペット/タイトルで判定）
    NG業種（スニペットで判定）
    従業員数201名超（スニペットに記載がある場合）
    拠点3以上（スニペットに記載がある場合）
    除外ドメインリスト

[STEP3] S1/S2確定企業は最小スクレイピング

  必須取得のみ:
    電話番号（テレアポ必須・なければpending）
    従業員数（NG判定用・スニペットで取れていれば省略可）

  → B確定 → HubSpot登録

  S1/S2なし企業はフルスクレイピング（S3〜S6確認）
    法定外福利厚生（S3）
    健康経営認証・セミナー（S4）
    HPリニューアル（S5）
    自社ビル（S6）
    → 3シグナル以上でB確定 → HubSpot登録
    → 1〜2シグナルでC → pending_review.json
```

---

## 6. ファイル構成

### 変更・新設するファイル

| ファイル | 内容 | 種別 |
|---|---|---|
| `config.py` | 6シグナル定数・NG業種修正・S2媒体リスト追加 | 変更 |
| `agents/rank_agent.py` | 12→6シグナル・ウェイト廃止・S1/S2即B判定 | 変更（大幅簡略化） |
| `agents/list_page_agent.py` | S2媒体3件追加（健康経営の広場・大同生命・大幅拡張） | 変更 |
| `agents/scraper_agent.py` | S1/S2確定企業は電話番号のみ取得に絞る | 変更（簡略化） |
| `agents/keyword_agent.py` | S1クエリに集中（S2はリスト直取得のため不要） | 変更（簡略化） |
| `main.py` | フロー整理・廃止エージェント参照削除 | 変更（簡略化） |

### 廃止するファイル

| ファイル | 廃止理由 |
|---|---|
| `agents/feedback_learner.py` | シグナルウェイト学習廃止 |
| `agents/monitor_agent.py` | 当面不要 |
| `agents/hubspot_auditor.py` | 当面不要 |
| `agents/supplement_agent.py` | 廃止 |
| `listup_state.py` | main.pyに統合 |
| `output/signal_weights.json` | ウェイト学習廃止 |

---

## 7. config.py 変更内容

```python
# ── シグナル（6本） ──────────────────────────────────────
SIGNAL_KEYS = [
    "PR有料媒体掲載",       # S1: これ単独でB確定
    "健康経営メディア掲載",  # S2: これ単独でB確定
    "法定外福利厚生",        # S3
    "健康経営注力",          # S4
    "HPリニューアル",        # S5
    "自社ビル",              # S6
]

# ── ランク閾値 ──────────────────────────────────────────
RANK_B_MIN_SIGNALS = 3        # S1/S2なしの場合のBランク最低ライン
RANK_A_MIN_SIGNALS = 3        # S1/S2あり + 追加シグナル数（合計でA判定）
MIN_REGISTER_SIGNALS = 3      # HubSpot登録最低ライン（or S1/S2あり）

# ── S2媒体リストURL ────────────────────────────────────
S2_MEDIA_LIST_URLS = [
    "https://kenko-keiei.jp/houjin_list/",       # 健康経営優良法人（Excel）
    "https://www.voice-report.jp/",               # アクサ生命ボイスレポート
    "https://kenkoukeiei-media.com/",             # 健康経営の広場
    "https://daido-kenco-award.jp/companies/",    # 大同生命
]

# ── S1媒体リストURL ────────────────────────────────────
S1_MEDIA_LIST_URLS = [
    "https://superceo.jp/list/company",           # SUPER CEO（静的HTML）
    "https://business-plus.net/interview/",       # B-PLUS（静的HTML）
]

# ── S1キーワード検索クエリ ─────────────────────────────
S1_MEDIA_NAMES = [
    "KENJA GLOBAL", "エコノミスト ビジネスクロニクル",
    "エコノミスト REC", "Newsweek WEB", "時代のニューウェーブ",
    "For JAPAN", "Leaders AWARD", "SMB Excellent AWARD",
    "ベンチャー通信", "カンパニータンク",
]

# ── NG業種 ─────────────────────────────────────────────
NG_INDUSTRY_KEYWORDS = [
    "飲食店", "レストラン", "居酒屋", "スーパー", "コンビニ",
    "小売", "量販店", "ドラッグストア",
    "美容院", "美容室", "ネイルサロン",
    "病院", "クリニック", "診療所", "薬局", "医療法人",
    "介護", "デイサービス", "保育", "幼稚園",
    "建設", "土木", "工務店", "ゼネコン",
    "運送", "運輸", "物流", "宅配",
    "SES", "常駐", "派遣エンジニア",
    "警備", "清掃業",
    "ファミリーマート", "セブンイレブン", "ローソン",
    "マクドナルド", "すき家", "吉野家",
]

# ── 削除する定数 ─────────────────────────────────────
# SIGNAL_KEYS（旧12本）→ 廃止
# WEIGHT_MIN / WEIGHT_MAX / DEFAULT_WEIGHT → 廃止
# AUTO_REGISTER_SCORE / AUTO_REGISTER_CONFIDENCE / MIN_PENDING_SCORE → 廃止
```

---

## 8. rank_agent.py の変更方針

```python
def evaluate_rank(company_info: dict, source_signals: dict) -> dict:
    """
    source_signals: ソース収集段階で確定したシグナル
      例: {"S1": True, "S2": False, "S3": True, ...}

    S1 or S2 → 即B確定（スクレイピング結果に関わらず）
    S1 or S2 + 追加2以上 → A確定
    S1/S2なし → S3〜S6を集計してランク判定
    """
    signals = source_signals.copy()

    # S1/S2即B確定ルール
    if signals.get("S1") or signals.get("S2"):
        # 追加シグナル数でA/B分岐
        extra = sum(signals.get(k, False) for k in ["S3","S4","S5","S6"])
        rank = "A" if extra >= 2 else "B"
        return {"rank": rank, "signals": signals, "score": 2 + extra}

    # S1/S2なし → 通常採点
    score = sum(signals.get(k, False) for k in ["S3","S4","S5","S6"])
    if score >= 3:   rank = "B"
    elif score >= 1: rank = "C"
    else:            rank = "C"
    return {"rank": rank, "signals": signals, "score": score}
```

### ウェイト機構は完全廃止
- `_load_weights()` / `_get_weights()` / `_w()` → 削除
- `signal_weights.json` → 削除対象

---

## 9. 実装ステップ

### Phase 1: config.py 整理（着手点）
- SIGNAL_KEYS を6本に変更
- S1/S2媒体リストを分離定義
- ウェイト関連定数を削除
- NG業種を修正

### Phase 2: rank_agent.py 書き直し
- 12シグナル評価 → 6シグナル
- S1/S2即B判定ロジック追加
- ウェイトキャッシュ機構を削除

### Phase 3: list_page_agent.py 拡張
- 健康経営の広場 / 大同生命 のスクレイプ追加
- アクサ生命ボイスレポートの一覧取得改善
- 各ページからの企業URL抽出精度向上

### Phase 4: scraper_agent.py 簡略化
- S1/S2確定企業は電話番号取得のみ
- S3〜S6確認は未確定企業のみ実行

### Phase 5: main.py / agents整理
- 廃止エージェント（feedback_learner等）の参照を削除
- フローをSTEP1〜3に対応

### Phase 6: app.py 修正
- シグナル表示を6本に変更
- ウェイト設定UIを削除

---

## 10. 架電機能の分離について → 別ドキュメント参照

架電機能（call_list / 架電記録 / 商談管理）は**別ツールとして分離**する方向で検討中。
詳細は `CALL_TOOL_DESIGN.md`（別途作成）を参照。
