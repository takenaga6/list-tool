# 優先媒体リスト詳細

---

## 媒体ソースの処理優先順序

自動モード起動時: **健康経営系 → PR媒体系 → キーワード検索**

```
[STEP1] 媒体リストスクレイプ（MEDIA_LIST_URLS 順に処理）
  ├─ 健康経営優良法人（経産省）
  └─ PR媒体（SUPER CEO / B-PLUS 等）

[STEP2] キーワード検索（STEP1で目標未達の場合）
  └─ keyword_agent が有効クエリを提案
```

---

## 現在の媒体リスト（`config.py` — `MEDIA_LIST_URLS`）

| 優先度 | URL | 媒体名 | 種別 | 備考 |
|---|---|---|---|---|
| 1 | https://kenko-keiei.jp/houjin_list/ | 健康経営優良法人（経産省） | 健康経営系 | Excel自動DL・中小規模のみ |
| 2 | https://superceo.jp/list/company | SUPER CEO | PR媒体 | 静的HTML・50音順一覧 |
| 3 | https://business-plus.net/interview/ | B-PLUS | PR媒体 | 静的HTML・インタビュー一覧 |

---

## PR有料媒体ドメイン（`PR_MEDIA_DOMAINS`）

以下のドメインからの掲載URLを検出した場合、ランク判定でAランク判定シグナル（+1点）。
クエリ経由の場合はボーナス+2点。

| 媒体名 | ドメイン |
|---|---|
| KENJA GLOBAL / 賢者グローバル | kenja.tv |
| エコノミスト ビジネスクロニクル | business-chronicle.com |
| エコノミスト REC | weekly-economist.com |
| Newsweek WEB | challenger.newsweekjapan.jp |
| 時代のニューウェーブ | j-newwave.com |
| For JAPAN | forjapan-project.com |
| Leaders AWARD | leaders-award.jp |
| SMB Excellent AWARD | smbexcellentcompany.com |
| B-PLUS | business-plus.net |
| SUPER CEO | superceo.jp |
| BS TIMES | bs-times.com |
| ベンチャー通信 | v-tsushin.jp |
| カンパニータンク | challenge-plus.jp |
| 社長名鑑 | shachomeikan.jp |
| 経営者プライム | keieisha-prime.com |
| リーダーナビ | leader-navi.com |
| Fanterview | fanterview.net |
| 経営者通信 | k-tsushin.jp |
| 先見経済 | senken-keizai.co.jp |
| 企業と経営 | kigyotokeiei.jp |

---

## 健康経営メディアドメイン（`HEALTH_MEDIA_DOMAINS`）

| 媒体名 | ドメイン |
|---|---|
| アクサ生命ボイスレポート | voice-report.jp |
| 健康経営の広場 | kenkoukeiei-media.com |
| 大同生命 | daido-kenco-award.jp |

---

## 経産省健康経営優良法人認定（`HEALTH_CERT_DOMAINS`）

| ドメイン | 用途 |
|---|---|
| kenko-keiei.jp | 経産省認定ポータル（Excel自動DL） |

このドメイン経由で発見した企業は **ランク判定で+2ボーナス**（認定確定のため）。

---

## 将来対応予定の媒体（Playwright対応後に追加）

| 媒体名 | URL | 備考 |
|---|---|---|
| SMB Excellent AWARD | https://smbexcellentcompany.com/2025/ | SPA（Nuxt.js）→ Playwright未対応 |
| KENJA GLOBAL | https://kenja.tv/ | SPA → 同上 |

---

## 媒体を追加する方法

1. `config.py` の `MEDIA_LIST_URLS` にURLを追加
2. 静的HTMLの場合は `list_page_agent.py` が自動対応
3. Excel配布の場合はExcelリンクを自動検出してDL（大規模法人ファイルは除外）
4. SPAの場合はPlaywright対応が必要（現在未対応）

PR媒体として採点に使う場合は `PR_MEDIA_DOMAINS` と `MEDIA_NAME_TO_DOMAIN` にも追加。
