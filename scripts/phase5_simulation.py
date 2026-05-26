"""
Phase 5 シミュレーションスクリプト v2.0

変更点（v1.0からの差分）:
  - check_interaction_bonus のバグ修正
      旧: 49社データで未検証の「健康経営+SDGs+福利厚生」を追加していた → 偽陽性の原因
      新: 49社データで100%確認済みの6組み合わせのみに絞る（全てISO or 採用高を含む）
  - S10キーワード追加（継続社の未検出企業を救済）
  - S10を2段階判定に変更
      Stage1のみ（キーワードマッチ）: +1点
      Stage1+Stage2（キーワード+企業規模/親会社）: +3点

実行方法:
  cd list_tool
  python scripts/phase5_simulation.py

出力:
  output/phase5_sim_result.csv  各社スコア・ランク詳細
"""

import sys, os, re
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")


# ============================================================
# S10: PROFITABLE_INDUSTRY_KEYWORDS（v2.0追加分）
# ============================================================
PROFITABLE_INDUSTRY_KEYWORDS = [
    # 金融サービス（SBI証券・FBモーゲージ等を救済）
    "投資", "ファンド", "VC", "ベンチャーキャピタル",
    "アセットマネジメント", "資産運用",
    "証券",                         # v2.0追加: SBI証券
    "金融サービス",                  # v2.0追加
    "金融",                          # v2.0追加
    "モーゲージ",                    # v2.0追加: FBモーゲージ
    # 保険（SOMPOヘルスサポート等を救済）
    "保険",                          # v2.0追加
    "保険代理店",                    # v2.0追加
    # 法律・士業
    "法律事務所", "弁護士法人", "税理士法人", "監査法人",
    "士業",                          # v2.0追加
    # コンサルティング
    "コンサルティング", "経営コンサル", "戦略コンサル",
    # IT/SaaS（成熟した会社）
    "SaaS", "クラウドサービス",
    # 商社（伊藤忠モードパル等を救済）
    "総合商社", "専門商社",
    "商社",                          # v2.0追加
    # 不動産（高単価系）
    "不動産投資", "プライベートバンキング",
    # 製造業の中でも高付加価値領域
    "精密機器", "半導体製造装置", "医療機器製造",
    "医療機器",                      # v2.0追加
    "製薬",                          # v2.0追加
]

# Phase 1 プロキシ用NG業種
NG_INDUSTRY_PHASE1 = [
    "広告代理店", "総合広告", "PR会社", "マーケティング会社",
    "クリエイティブエージェンシー", "メディア運営", "出版社",
    "デジタルマーケティング", "デジタルエージェンシー",
]
REDOG_INDUSTRY = ["受託開発", "システム開発", "SIer", "システムインテグレ"]
FUKURI_EXCEPTION_KEYWORDS = [
    "法律事務所", "弁護士法人", "税理士法人", "会計", "士業",
    "投資運用", "資産運用", "ファンド",
]


# ============================================================
# 資本金パーサー
# ============================================================
def parse_capital_yen(val: str) -> float | None:
    """
    資本金文字列を「円単位の数値」に変換。
    変換できない場合は None を返す。
    例: '1億円' → 1e8, '150百万円' → 1.5e8, '不明' → None
    """
    s = str(val).strip().replace(",", "").replace("、", "")
    if not s or s in ("不明", "nan", "None", "不明（弁護士法人）", "不明（中小オーナー企業）"):
        return None
    # 「数億円程度（VC出資）」のような概算は「あり」と見なす
    if "数億" in s:
        return 3e8  # 3億で保守的に推定
    try:
        # 億円
        m = re.search(r"([\d.]+)億", s)
        if m:
            return float(m.group(1)) * 1e8
        # 百万円
        m = re.search(r"([\d.]+)百万", s)
        if m:
            return float(m.group(1)) * 1e6
        # 千万円
        m = re.search(r"([\d.]+)千万", s)
        if m:
            return float(m.group(1)) * 1e7
        # 万円
        m = re.search(r"([\d.]+)万", s)
        if m:
            return float(m.group(1)) * 1e4
        # 千円
        m = re.search(r"([\d.]+)千円", s)
        if m:
            return float(m.group(1)) * 1e3
    except Exception:
        pass
    return None


def load_data(path: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name="契約企業分析", header=0)
    mask = df.iloc[:, 100].isin(["優良継続中", "解約済み"])
    df38 = df[mask].copy().reset_index(drop=True)
    df38["is_cont"] = df38.iloc[:, 100] == "優良継続中"
    return df38


def flag_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    各シグナルのフラグ列を追加する。

    シグナル一覧（列番号は1-based）:
      S1 [12]: PR有料媒体出稿_区分 == 'あり'
      S2 [27]: 健康経営メディア掲載_あり == True
      S3 [21]: 法定外福利厚生あり == True（必須から降格）
      S4 [73]: 健康経営認定あり == True（健康経営注力のプロキシ）
      S5 [13]: HPリニューアル1年以内 == 'あり'
      S6 [58]: 自社ビル/自社施設保有_区分 == 'あり'
      S7 [86]: ISO認定 != 'なし'
      S8 [87]: SDGs/サステナ宣言 != 'なし'
      S9 [23]: 社長メッセージに健康記載_区分 == True
      S10: 業種列へのキーワードマッチ（2段階判定）
           Stage1（+1点）: PROFITABLE_INDUSTRY_KEYWORDS にマッチ
           Stage2（+3点）: Stage1 AND (資本金≥1億 OR 親会社あり OR 従業員≥50名)
    """
    df["s1_pr"] = df.iloc[:, 11].astype(str).str.strip() == "あり"
    df["s2_kenko_media"] = df.iloc[:, 26] == True
    df["s3_welfare"] = df.iloc[:, 20] == True
    df["s4_kenko_keiei"] = df.iloc[:, 72] == True
    df["s5_renewal"] = df.iloc[:, 12].astype(str).str.strip() == "あり"
    df["s6_bldg"] = df.iloc[:, 57].astype(str).str.strip() == "あり"
    df["s7_iso"] = df.iloc[:, 85].astype(str).str.strip() != "なし"
    df["s8_sdgs"] = ~df.iloc[:, 86].astype(str).str.strip().isin(
        ["なし", "", "nan", "None", "False"]
    )
    df["s9_president"] = df.iloc[:, 22] == True

    # S10 Stage1: キーワードマッチ（本番と同じロジック）
    industry_text = (
        df.iloc[:, 29].astype(str).fillna("")   # 業種_日本語_カテゴリ
        + " "
        + df.iloc[:, 30].astype(str).fillna("")  # 業種_日本語_詳細
        + " "
        + df.iloc[:, 2].astype(str).fillna("")   # 業種(HubSpot)
    )
    df["s10_stage1"] = industry_text.apply(
        lambda t: any(kw in t for kw in PROFITABLE_INDUSTRY_KEYWORDS)
    )

    # S10 Stage2: 企業規模・親会社条件
    # 従業員数 [4]: 数値として直接比較
    emp_raw = pd.to_numeric(df.iloc[:, 3], errors="coerce")
    emp_ok = emp_raw >= 50

    # 親会社有 [69]: True/False
    parent_ok = df.iloc[:, 68] == True

    # 資本金 [59]: パーサーを使って1億円以上判定
    capital_vals = df.iloc[:, 58].astype(str).apply(parse_capital_yen)
    capital_ok = capital_vals.apply(lambda v: v is not None and v >= 1e8)

    df["s10_stage2"] = emp_ok | parent_ok | capital_ok

    # S10スコア計算（+3 or +1 or 0）
    df["s10_score"] = 0
    df.loc[df["s10_stage1"] & df["s10_stage2"], "s10_score"] = 3
    df.loc[df["s10_stage1"] & ~df["s10_stage2"], "s10_score"] = 1

    # Phase 1 必須条件プロキシ
    df["ph1_health"] = df["s4_kenko_keiei"] | df["s2_kenko_media"] | df["s9_president"]
    df["ph1_recruit"] = df.iloc[:, 16].astype(str).str.strip().isin(["S", "A", "B", "B　　", "C"])
    combined_text = (
        df.iloc[:, 29].astype(str).fillna("") + " " + df.iloc[:, 2].astype(str).fillna("")
    )
    is_fukuri_exception = combined_text.apply(
        lambda t: any(kw in t for kw in FUKURI_EXCEPTION_KEYWORDS)
    )
    df["ph1_welfare"] = df["s3_welfare"] | is_fukuri_exception

    # 採用高フラグ（相互作用チェック用）
    df["s_hire"] = df.iloc[:, 16].astype(str).str.strip().isin(["S", "A"])

    return df


def calc_score_a(row: pd.Series) -> tuple[int, str, list[str]]:
    """シナリオA: 現行 Phase 4。Phase 1必須条件③④⑤あり + S1〜S6 各+1点。閾値: A≥5/B=2-4/C=0-1/NG≤-1"""
    reasons_ng = []
    if not row["ph1_health"]:
        reasons_ng.append("③健康経営記載なし")
    if not row["ph1_recruit"]:
        reasons_ng.append("④採用情報なし")
    if not row["ph1_welfare"]:
        reasons_ng.append("⑤福利厚生なし")

    if reasons_ng:
        return (-99, "NG", reasons_ng)

    score, hits = 0, []
    for col, label in [
        ("s1_pr", "S1_PR"), ("s2_kenko_media", "S2_健康メディア"),
        ("s3_welfare", "S3_福利厚生"), ("s4_kenko_keiei", "S4_健康経営"),
        ("s5_renewal", "S5_HP更新"), ("s6_bldg", "S6_自社ビル"),
    ]:
        if row[col]:
            score += 1; hits.append(label)

    rank = "A" if score >= 5 else "B" if score >= 2 else "C"
    return (score, rank, hits)


def calc_score_b(row: pd.Series) -> tuple[int, str, list[str]]:
    """
    シナリオB: Phase 5 基本。必須条件③④⑤削除 + S1〜S10加点。
    S7+2点, S10は2段階（+3 or +1）, 他は+1点。
    閾値（暫定）: A≥8 / B=5-7 / C=1-4 / NG≤0
    """
    score, hits = 0, []
    for col, label, pts in [
        ("s1_pr", "S1_PR", 1), ("s2_kenko_media", "S2_健康メディア", 1),
        ("s3_welfare", "S3_福利厚生", 1), ("s4_kenko_keiei", "S4_健康経営", 1),
        ("s5_renewal", "S5_HP更新", 1), ("s6_bldg", "S6_自社ビル", 1),
        ("s7_iso", "S7_ISO(+2)", 2), ("s8_sdgs", "S8_SDGs", 1),
        ("s9_president", "S9_社長健康記載", 1),
    ]:
        if row[col]:
            score += pts; hits.append(label)

    # S10: 2段階判定
    s10_pts = int(row["s10_score"])
    if s10_pts == 3:
        score += 3; hits.append("S10_儲かる業界(+3)")
    elif s10_pts == 1:
        score += 1; hits.append("S10_儲かる業界_S1のみ(+1)")

    rank = "A" if score >= 8 else "B" if score >= 5 else "C" if score >= 1 else "NG"
    return (score, rank, hits)


def check_interaction_bonus(row: pd.Series) -> tuple[int, str]:
    """
    相互作用ボーナス（v2.0修正版）

    ★修正内容★
      旧: 49社データで未検証の「健康経営+SDGs+福利厚生」を含む10パターン
      新: 49社データで継続率100%が確認された6パターンのみ
          → 全て「ISO(S7)」または「採用高」のいずれかを含む

    3点セット達成 or シグナル全10個のうち5個以上保有 → +3点
    重複加算なし。
    """
    s = dict(row)

    # ★ 49社データで100%確認済みの6組み合わせのみ（ISO or 採用高 を必ず含む）★
    triple_sets_validated = [
        ("s4_kenko_keiei", "s7_iso", "s_hire",    "健康経営+ISO+採用高(5/5=100%)"),
        ("s4_kenko_keiei", "s7_iso", "s8_sdgs",   "健康経営+ISO+SDGs(4/4=100%)"),
        ("s4_kenko_keiei", "s7_iso", "s9_president", "健康経営+ISO+社長詳細(4/4=100%)"),
        ("s7_iso", "s9_president", "s_hire",      "ISO+社長詳細+採用高(4/4=100%)"),
        ("s7_iso", "s9_president", "s3_welfare",  "ISO+社長詳細+福利厚生(4/4=100%)"),
        ("s4_kenko_keiei", "s8_sdgs", "s_hire",   "健康経営+SDGs+採用高(4/4=100%)"),
    ]
    # S10絡みの拡張（S10_fullが確認できた場合のみ）
    # S10は新規シグナルで49社データには直接ないが、ISO/採用高を含む組み合わせに限定
    triple_sets_s10 = [
        ("s4_kenko_keiei", "s7_iso", "s10_full",  "健康経営+ISO+儲かる業界"),
        ("s7_iso", "s9_president", "s10_full",    "ISO+社長詳細+儲かる業界"),
        ("s4_kenko_keiei", "s8_sdgs", "s10_full", "健康経営+SDGs+儲かる業界 (採用高代替はS10_fullのみ許可)"),
    ]

    # s10_full = Stage1 AND Stage2 の企業のみボーナス対象
    s["s10_full"] = (int(row.get("s10_score", 0)) == 3)

    for a, b, c, label in triple_sets_validated + triple_sets_s10:
        if s.get(a, False) and s.get(b, False) and s.get(c, False):
            return (3, f"3点セット: {label}")

    # シグナル5個以上保有チェック（S1〜S10の全フラグ）
    sig_cols_10 = [
        "s1_pr", "s2_kenko_media", "s3_welfare", "s4_kenko_keiei",
        "s5_renewal", "s6_bldg", "s7_iso", "s8_sdgs", "s9_president",
    ]
    # s10は+1以上あれば「1個」とカウント
    s10_count = 1 if int(row.get("s10_score", 0)) > 0 else 0
    total = sum(1 for c in sig_cols_10 if s.get(c, False)) + s10_count
    if total >= 5:
        return (3, f"シグナル{total}個保有")

    return (0, "")


def calc_score_c(row: pd.Series) -> tuple[int, str, list[str]]:
    """シナリオC: Phase 5 + 相互作用ボーナス（v2.0修正版）"""
    base_score, _, hits = calc_score_b(row)
    bonus, bonus_reason = check_interaction_bonus(row)
    total = base_score + bonus
    if bonus_reason:
        hits.append(f"ボーナス+3({bonus_reason})")
    rank = "A" if total >= 8 else "B" if total >= 5 else "C" if total >= 1 else "NG"
    return (total, rank, hits)


def print_sep(title: str) -> None:
    print(); print("=" * 68); print(f"  {title}"); print("=" * 68)


def verify_signals(df: pd.DataFrame) -> None:
    """PART 1: 個別シグナルの継続率を web Claude 集計と照合。"""
    print_sep("PART 1: 個別シグナル検証（web Claude 集計との一致確認）")

    df["cp_hi"] = df.iloc[:, 93].astype(str).str.startswith(("A ", "B "))
    df["bi_cm"] = df.iloc[:, 60].astype(str) == "あり"
    df["am_hi"] = df.iloc[:, 38].isin(["高", "極高", "中-高"])
    df["ca_lo"] = df.iloc[:, 78].isin(["低", "低-中"])
    df["br_mfg"] = df.iloc[:, 69].astype(str).str.strip() == "あり"
    df["ai_owner"] = df.iloc[:, 34].astype(str) == "創業家オーナー"

    expected = {
        "年収B以上(CP)":      ("cp_hi",          "73%(8/11)"),
        "テレビCM(BI)":       ("bi_cm",           "100%(3/3)"),
        "利益率高め(AM)":     ("am_hi",           "67%(8/12)"),
        "離職率低め(CA)":     ("ca_lo",           "62%(8/13)"),
        "社長詳細(S9)":       ("s9_president",    "71%(5/7)"),
        "ISO(S7)":            ("s7_iso",          "67%(6/9)"),
        "健康経営(S4)":       ("s4_kenko_keiei",  "55%(6/11)"),
        "SDGs(S8)":           ("s8_sdgs",         "55%(6/11)"),
        "採用S/A":            ("s_hire",          "50%(6/12)"),
        "法定外福利(S3)":     ("s3_welfare",      "38%(10/26)"),
        "自社ビル(S6)":       ("s6_bldg",         "33%(4/12)"),
        "製造業":             ("br_mfg",          "18%(2/11)"),
        "創業家オーナー(AI)": ("ai_owner",        "20%(4/20)"),
    }

    all_ok = True
    print(f"{'シグナル':<16} {'あり':<20} {'なし':<20} {'倍率':>5}  {'一致'}")
    print("-" * 70)
    for label, (col, exp_str) in expected.items():
        hi = df[df[col] == True]; lo = df[df[col] == False]
        hc = hi["is_cont"].sum(); ht = len(hi)
        lc = lo["is_cont"].sum(); lt = len(lo)
        hr = hc / ht * 100 if ht else 0
        lr = lc / lt * 100 if lt else 0
        ratio = hr / lr if lr else float("inf")
        exp_hi = float(exp_str.split("%")[0])
        ok = "✓" if abs(hr - exp_hi) < 2 else "✗"
        if ok == "✗":
            all_ok = False
        print(f"{label:<16} {hr:>4.0f}%({hc:>2}/{ht:>2})  {lr:>4.0f}%({lc:>2}/{lt:>2})  {ratio:>4.2f}倍  {ok}")
    print(f"\n検証結果: {'全シグナル一致 ✓' if all_ok else '不一致あり ✗'}")


def verify_interactions(df: pd.DataFrame) -> None:
    """PART 2: 相互作用（3点セット・シグナル保有数別継続率）を検証。"""
    print_sep("PART 2: 相互作用検証")

    combos = [
        ("s4_kenko_keiei", "s7_iso", "s_hire",    "健康経営+ISO+採用高"),
        ("s4_kenko_keiei", "s7_iso", "s8_sdgs",   "健康経営+ISO+SDGs"),
        ("s4_kenko_keiei", "s7_iso", "s9_president", "健康経営+ISO+社長詳細"),
        ("s7_iso", "s9_president", "s_hire",      "ISO+社長詳細+採用高"),
        ("s7_iso", "s9_president", "s3_welfare",  "ISO+社長詳細+福利厚生"),
        ("s4_kenko_keiei", "s8_sdgs", "s_hire",   "健康経営+SDGs+採用高"),
    ]
    print("3シグナル組み合わせ継続率（期待値 100%）:")
    print(f"{'組み合わせ':<22} 継続/合計  継続率  一致")
    print("-" * 50)
    all_ok = True
    for a, b, c, label in combos:
        sub = df[df[a] & df[b] & df[c]]
        n = len(sub); cont = sub["is_cont"].sum()
        rate = cont / n * 100 if n else 0
        ok = "✓" if n >= 3 and rate >= 90 else ("△n小" if n < 3 else "✗")
        if ok == "✗": all_ok = False
        print(f"{label:<22} {cont}/{n:<5}   {rate:>5.0f}%   {ok}")

    # シグナル保有数別
    sig_6 = ["s4_kenko_keiei", "s7_iso", "s_hire", "s8_sdgs", "s9_president", "s3_welfare"]
    df["sig6_count"] = df[sig_6].sum(axis=1)
    expected_by_n = {0:(36,4,11), 1:(25,2,8), 2:(17,1,6), 3:(25,1,4), 4:(25,1,4), 5:(100,2,2), 6:(100,3,3)}
    print("\nシグナル保有数別継続率（6シグナル: 健康経営/ISO/採用高/SDGs/社長詳細/福利厚生）:")
    print(f"{'N':>3}個  継続/合計  継続率   期待値     一致")
    print("-" * 48)
    for cnt in range(7):
        g = df[df["sig6_count"] == cnt]
        n = len(g); cont = g["is_cont"].sum()
        rate = cont / n * 100 if n else 0
        exp_r, exp_c, exp_t = expected_by_n.get(cnt, (None, None, None))
        ok = "✓" if (exp_r and abs(rate - exp_r) < 5 and cont == exp_c and n == exp_t) else "✗"
        if ok == "✗": all_ok = False
        exp_str = f"{exp_r}%({exp_c}/{exp_t})" if exp_r else "-"
        print(f"{cnt:>3}個  {cont:>2}/{n:<5}   {rate:>5.0f}%   {exp_str:<12} {ok}")
    print(f"\n相互作用検証: {'全一致 ✓' if all_ok else '不一致あり ✗'}")


def verify_s10(df: pd.DataFrame) -> None:
    """PART 3: S10「儲かっている業界フラグ」2段階判定の検証。"""
    print_sep("PART 3: S10「儲かっている業界フラグ」v2.0 判定結果")

    # 旧バージョン（v1.0）との比較用: キーワードマッチのみ
    old_kw = [
        "投資", "ファンド", "VC", "ベンチャーキャピタル", "アセットマネジメント", "資産運用",
        "法律事務所", "弁護士法人", "税理士法人", "監査法人", "コンサルティング", "経営コンサル",
        "戦略コンサル", "SaaS", "クラウドサービス", "総合商社", "専門商社", "不動産投資",
        "プライベートバンキング", "精密機器", "半導体製造装置", "医療機器製造",
    ]
    industry_text = (
        df.iloc[:, 29].astype(str).fillna("") + " "
        + df.iloc[:, 30].astype(str).fillna("") + " "
        + df.iloc[:, 2].astype(str).fillna("")
    )
    df["s10_old"] = industry_text.apply(lambda t: any(kw in t for kw in old_kw))

    # 継続率の比較
    patterns = [
        ("v1.0 キーワード(旧)", "s10_old"),
        ("v2.0 Stage1(新KW)", "s10_stage1"),
        ("v2.0 Stage1+Stage2(+3点)", lambda r: r["s10_score"] == 3),
        ("v2.0 Stage1のみ(+1点)", lambda r: r["s10_score"] == 1),
    ]
    print(f"{'判定方法':<26} {'該当':>4}社  {'あり継続率':>11}  {'なし継続率':>11}  {'倍率':>6}")
    print("-" * 68)
    for label, col_or_fn in patterns:
        if callable(col_or_fn):
            mask = df.apply(col_or_fn, axis=1)
        else:
            mask = df[col_or_fn]
        hi = df[mask]; lo = df[~mask]
        hc = hi["is_cont"].sum(); ht = len(hi)
        lc = lo["is_cont"].sum(); lt = len(lo)
        hr = hc / ht * 100 if ht else 0
        lr = lc / lt * 100 if lt else 0
        ratio = hr / lr if lr else float("inf")
        print(f"{label:<26} {ht:>4}  {hr:>5.0f}%({hc}/{ht})  {lr:>5.0f}%({lc}/{lt})  {ratio:>5.2f}倍")

    # Stage2条件の内訳確認
    emp_raw = pd.to_numeric(df.iloc[:, 3], errors="coerce")
    emp_ok = emp_raw >= 50
    parent_ok = df.iloc[:, 68] == True
    capital_vals = df.iloc[:, 58].astype(str).apply(parse_capital_yen)
    capital_ok = capital_vals.apply(lambda v: v is not None and v >= 1e8)

    s10_s1 = df["s10_stage1"]
    print(f"\nStage2条件 内訳（Stage1該当{s10_s1.sum()}社中）:")
    print(f"  従業員50名以上: {(s10_s1 & emp_ok).sum()}社")
    print(f"  親会社あり:     {(s10_s1 & parent_ok).sum()}社")
    print(f"  資本金1億以上:  {(s10_s1 & capital_ok).sum()}社")
    print(f"  Stage1+Stage2:  {(df['s10_score'] == 3).sum()}社（+3点）")
    print(f"  Stage1のみ:     {(df['s10_score'] == 1).sum()}社（+1点）")

    # 各社の判定一覧
    print(f"\n各社S10判定（継続/解約別）:")
    print(f"{'企業名':<20} {'旧':>3} {'新KW':>4} {'Stg2':>4} {'点':>3}  {'業種カテゴリ'}")
    print("-" * 72)
    for _, row in df.iterrows():
        old_v = "○" if row["s10_old"] else "×"
        s1_v  = "○" if row["s10_stage1"] else "×"
        s2_v  = "○" if row["s10_stage2"] else "×"
        pts   = int(row["s10_score"])
        name  = str(df.iloc[row.name, 0])[:18]
        cat   = str(df.iloc[row.name, 29])[:25]
        flag  = "継続" if row["is_cont"] else "解約"
        print(f"{name:<20} {old_v:>3} {s1_v:>4} {s2_v:>4} {pts:>3}点  [{flag}] {cat}")


def run_simulation(df: pd.DataFrame) -> pd.DataFrame:
    """3シナリオのスコアリングを実行。"""
    results = []
    for _, row in df.iterrows():
        sa, ra, ha = calc_score_a(row)
        sb, rb, hb = calc_score_b(row)
        sc, rc, hc = calc_score_c(row)
        results.append({
            "企業名": str(df.iloc[row.name, 0]),
            "契約状態": str(df.iloc[row.name, 100]),
            "is_cont": row["is_cont"],
            "score_A": sa if sa != -99 else "NG",
            "rank_A": ra, "hits_A": " | ".join(ha),
            "score_B": sb, "rank_B": rb, "hits_B": " | ".join(hb),
            "score_C": sc, "rank_C": rc, "hits_C": " | ".join(hc),
            # 個別フラグ
            "S1_PR": row["s1_pr"], "S2_健康メディア": row["s2_kenko_media"],
            "S3_福利厚生": row["s3_welfare"], "S4_健康経営": row["s4_kenko_keiei"],
            "S5_HP更新": row["s5_renewal"], "S6_自社ビル": row["s6_bldg"],
            "S7_ISO": row["s7_iso"], "S8_SDGs": row["s8_sdgs"],
            "S9_社長健康": row["s9_president"],
            "S10_score": int(row["s10_score"]),
            "S10_Stage1": row["s10_stage1"], "S10_Stage2": row["s10_stage2"],
        })
    return pd.DataFrame(results)


def print_summary(result_df: pd.DataFrame) -> None:
    print_sep("PART 4: スコアリングシミュレーション（3シナリオ比較）")
    cont = result_df[result_df["is_cont"]]
    diss = result_df[~result_df["is_cont"]]

    print(f"{'':32} {'シナリオA':>11} {'シナリオB':>11} {'シナリオC':>11}")
    print(f"{'':32} {'(現行Phase4)':>11} {'(P5 基本)':>11} {'(P5+ボーナス)':>11}")
    print("-" * 68)
    for label, grp, total in [("【継続社14社】", cont, 14), ("【解約社24社】", diss, 24)]:
        print(f"\n{label}")
        for rank in ["A", "B", "C", "NG"]:
            na = (grp["rank_A"] == rank).sum()
            nb = (grp["rank_B"] == rank).sum()
            nc = (grp["rank_C"] == rank).sum()
            print(f"  {rank}ランク:   {na:>3}社/{total}社    {nb:>3}社/{total}社    {nc:>3}社/{total}社")

    print("\n【精度指標】")
    for tag, rc in [("A", "rank_A"), ("B", "rank_B"), ("C", "rank_C")]:
        ab_c = ((cont[rc] == "A") | (cont[rc] == "B")).sum()
        cng_d = ((diss[rc] == "C") | (diss[rc] == "NG")).sum()
        print(
            f"  シナリオ{tag}: 継続社A/B率={ab_c}/14={ab_c/14*100:.0f}%  "
            f"解約社C/NG率={cng_d}/24={cng_d/24*100:.0f}%"
        )


def print_detail(result_df: pd.DataFrame) -> None:
    print_sep("PART 5: 各社詳細")
    for label, filt in [("▼ 継続社14社", result_df["is_cont"]), ("▼ 解約社24社", ~result_df["is_cont"])]:
        print(f"\n{label}")
        print(f"{'企業名':<18} {'A':>4} {'B':>4} {'C':>4}  シグナル(C案)")
        print("-" * 82)
        for _, row in result_df[filt].iterrows():
            print(
                f"{str(row['企業名'])[:16]:<18} {str(row['rank_A']):>4} "
                f"{str(row['rank_B']):>4} {str(row['rank_C']):>4}  "
                f"{str(row['hits_C'])[:48]}"
            )


def main() -> None:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    excel_path = os.path.join(base, "data", "2026年営業分析シート.xlsx")
    if not os.path.exists(excel_path):
        print(f"ERROR: {excel_path} が見つかりません")
        return

    print("Phase 5 シミュレーション v2.0 開始...")
    df = load_data(excel_path)
    print(f"  読み込み: {len(df)}社 (継続{df['is_cont'].sum()} / 解約{(~df['is_cont']).sum()})")
    df = flag_signals(df)

    verify_signals(df)
    verify_interactions(df)
    verify_s10(df)
    result_df = run_simulation(df)
    print_summary(result_df)
    print_detail(result_df)

    out_dir = os.path.join(base, "output")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "phase5_sim_result.csv")
    result_df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n✓ CSV出力: {out_path}")
    print("完了。")


if __name__ == "__main__":
    main()
