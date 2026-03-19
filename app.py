"""
Offi-Stretch テレアポ管理アプリ
起動: streamlit run app.py
"""

import os
import subprocess
import sys
import pandas as pd
import streamlit as st

import io as _io_mod
import json as _json_mod
from config import FEEDBACK_FILE, RESULTS_FILE, MEETINGS_FILE, IMPORT_SETTINGS_FILE, OUTPUT_DIR, record_feedback, record_meeting

_LIST_TOOL_DIR = os.path.dirname(os.path.abspath(__file__))

# ──────────────────────────────
# ページ設定
# ──────────────────────────────
st.set_page_config(
    page_title="Offi-Stretch テレアポ管理",
    page_icon="📞",
    layout="wide",
)

st.title("📞 Offi-Stretch テレアポ管理")

tab_call, tab_history, tab_analysis, tab_import, tab_listup, tab_meeting = st.tabs(
    ["📞 コール記録", "📋 履歴", "📊 分析", "📥 取り込み", "🔍 リストアップ", "🤝 商談記録"]
)


# ──────────────────────────────
# ユーティリティ
# ──────────────────────────────

def load_feedback() -> pd.DataFrame:
    if os.path.exists(FEEDBACK_FILE):
        try:
            df = pd.read_csv(FEEDBACK_FILE, encoding="utf-8-sig")
            df["記録日"] = pd.to_datetime(df["記録日"], errors="coerce")
            return df
        except Exception:
            pass
    return pd.DataFrame(columns=["記録日", "会社名", "アプローチ結果", "アポ獲得", "規模", "NG理由", "断り理由", "温度感", "検索クエリ", "反応が良かったポイント", "メモ"])


def load_company_list() -> list[str]:
    """results.csv から会社名リストを取得"""
    if os.path.exists(RESULTS_FILE):
        try:
            df = pd.read_csv(RESULTS_FILE, encoding="utf-8-sig")
            if "会社名" in df.columns:
                return sorted(df["会社名"].dropna().unique().tolist())
        except Exception:
            pass
    return []


def _load_import_settings(key: str) -> dict:
    """インポート設定（ファイルパス・列マッピング）をJSONから読み込む"""
    try:
        if os.path.exists(IMPORT_SETTINGS_FILE):
            with open(IMPORT_SETTINGS_FILE, "r", encoding="utf-8") as f:
                return _json_mod.load(f).get(key, {})
    except Exception:
        pass
    return {}


def _save_import_settings(key: str, data: dict):
    """インポート設定をJSONに保存する"""
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        all_settings = {}
        if os.path.exists(IMPORT_SETTINGS_FILE):
            with open(IMPORT_SETTINGS_FILE, "r", encoding="utf-8") as f:
                all_settings = _json_mod.load(f)
        all_settings[key] = data
        with open(IMPORT_SETTINGS_FILE, "w", encoding="utf-8") as f:
            _json_mod.dump(all_settings, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _read_file_to_df(filepath: str) -> pd.DataFrame | None:
    """CSV / Excel を自動判定して DataFrame で返す"""
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext in (".xlsx", ".xls"):
            return pd.read_excel(filepath, dtype=str).fillna("")
        else:
            for enc in ("utf-8-sig", "shift-jis", "cp932", "utf-8"):
                try:
                    df = pd.read_csv(filepath, encoding=enc, dtype=str).fillna("")
                    return df
                except UnicodeDecodeError:
                    continue
    except Exception:
        pass
    return None


def _clean_pending_df(df: pd.DataFrame) -> pd.DataFrame:
    """pending_review.json を表示用に整形する"""
    # null / 空文字ヘッダーの列を除去
    df = df[[c for c in df.columns if c and c != "null"]].copy()

    # 都道府県 + 所在地 を結合して「所在地」に統合
    if "都道府県" in df.columns and "所在地" in df.columns:
        df["所在地"] = df["都道府県"].fillna("") + df["所在地"].fillna("")
        df = df.drop(columns=["都道府県"])
    elif "都道府県" in df.columns:
        df = df.rename(columns={"都道府県": "所在地"})

    # 「ランク」→「リストランク」にリネーム
    if "ランク" in df.columns:
        df = df.rename(columns={"ランク": "リストランク"})

    # 「説明」列を生成: 備考（ランク理由）+ 元URL
    col_biko  = df["備考"].fillna("")  if "備考"  in df.columns else pd.Series([""] * len(df))
    col_url   = df["元URL"].fillna("") if "元URL" in df.columns else pd.Series([""] * len(df))
    df["説明"] = col_biko
    has_url = (col_url != "") & (~col_biko.str.contains(col_url, regex=False, na=False))
    df.loc[has_url, "説明"] = df.loc[has_url, "説明"] + " | 元URL: " + col_url[has_url]

    # 備考が郵便番号のみの場合（旧フォーマット残滓）は郵便番号列に移す
    if "郵便番号" in df.columns and "備考" in df.columns:
        mask_zip = df["備考"].str.match(r"^\d{3}-?\d{4}$", na=False)
        df.loc[mask_zip, "郵便番号"] = df.loc[mask_zip, "備考"]
        df.loc[mask_zip, "備考"] = ""
        df.loc[mask_zip, "説明"] = ""

    return df


def _show_pending_review_ui():
    """確認モードの承認UI: pending_review.json を読み込み、チェック付きテーブルで表示・保存する"""
    import json as _jr
    _LIST_TOOL_DIR_local = os.path.dirname(os.path.abspath(__file__))
    pending_path = os.path.join(_LIST_TOOL_DIR_local, "output", "pending_review.json")

    if not os.path.exists(pending_path):
        st.info("pending_review.json が見つかりません。")
        return

    with open(pending_path, "r", encoding="utf-8") as _f:
        pending = _jr.load(_f)

    if not pending:
        st.info("確認待ちの候補がありません。")
        return

    df_raw = pd.DataFrame(pending)
    df_clean = _clean_pending_df(df_raw)

    # 表示列の順序を固定（存在する列のみ）
    _DISPLAY_COLS = [
        "リストランク", "会社名", "企業URL", "所在地", "郵便番号",
        "電話番号", "代表氏名", "業種", "従業員数", "説明", "日時",
    ]
    show_cols = [c for c in _DISPLAY_COLS if c in df_clean.columns]
    # 上記に含まれない列も末尾に追加（null/元URLなど除く）
    show_cols += [c for c in df_clean.columns if c not in show_cols and c not in ("備考", "元URL")]

    df_view = df_clean[show_cols].copy()

    # 承認チェックボックス列を先頭に追加
    df_view.insert(0, "承認", True)

    st.subheader(f"確認待ち: {len(df_view)}件")
    st.caption("「承認」列のチェックを外した企業は保存されません。確認後「承認した企業を保存」ボタンを押してください。")

    edited = st.data_editor(
        df_view,
        use_container_width=True,
        hide_index=True,
        column_config={
            "承認":       st.column_config.CheckboxColumn("承認", default=True, width="small"),
            "リストランク": st.column_config.TextColumn("リストランク", width="small"),
            "会社名":     st.column_config.TextColumn("会社名", width="medium"),
            "企業URL":    st.column_config.LinkColumn("企業URL", width="medium"),
            "所在地":     st.column_config.TextColumn("所在地", width="medium"),
            "電話番号":   st.column_config.TextColumn("電話番号", width="small"),
            "代表氏名":   st.column_config.TextColumn("代表氏名", width="small"),
            "説明":       st.column_config.TextColumn("説明（ランク理由・掲載媒体）", width="large"),
        },
        key="pending_editor",
    )

    approved = edited[edited["承認"] == True].drop(columns=["承認"])
    rejected = len(df_view) - len(approved)
    st.caption(f"承認: {len(approved)}件 / 却下: {rejected}件")

    col_save, col_clear = st.columns([1, 1])
    with col_save:
        if st.button("承認した企業を保存", type="primary", use_container_width=True):
            # 承認分だけ pending_review.json に上書き保存
            with open(pending_path, "w", encoding="utf-8") as _f:
                _jr.dump(approved.to_dict(orient="records"), _f, ensure_ascii=False, indent=2)
            # approved_companies.csv にも追記
            approved_csv = os.path.join(_LIST_TOOL_DIR_local, "output", "approved_companies.csv")
            header = not os.path.exists(approved_csv)
            approved.to_csv(approved_csv, mode="a", index=False, encoding="utf-8-sig", header=header)
            st.success(f"{len(approved)}件を approved_companies.csv に保存しました。")
    with col_clear:
        if st.button("クリア（リストを消去）", use_container_width=True):
            os.remove(pending_path)
            st.rerun()


def _render_gsheets_loader(widget_key: str, saved: dict) -> "pd.DataFrame | None":
    """
    Googleスプレッドシート連携UI を描画し、読み込んだ DataFrame を返す。
    gspread / google-auth 未インストール時はセットアップ手順を表示する。
    """
    with st.expander("🔧 Googleスプレッドシート 接続手順", expanded=False):
        st.markdown("""
**初回セットアップ（1回のみ）**

1. [Google Cloud Console](https://console.cloud.google.com/) でプロジェクトを作成
2. **Google Sheets API** と **Google Drive API** を有効化
3. 「IAMと管理」→「サービスアカウント」でサービスアカウントを作成し、JSONキーをダウンロード
4. 共有したいスプレッドシートを開き、「共有」からサービスアカウントのメールアドレスに「閲覧者」権限を付与
5. JSONキーファイルのパスを下に入力して接続

**依存ライブラリのインストール（未実施の場合）:**
```
pip install gspread google-auth
```
""")

    gs_key_path = st.text_input(
        "サービスアカウント JSONキー ファイルパス",
        value=saved.get("gs_key_path", ""),
        placeholder=r"C:\Users\user\Downloads\my-project-xxxx.json",
        key=f"{widget_key}_keypath",
    )
    gs_sheet_url = st.text_input(
        "スプレッドシートURL",
        value=saved.get("gs_sheet_url", ""),
        placeholder="https://docs.google.com/spreadsheets/d/XXXXX/edit",
        key=f"{widget_key}_url",
    )
    gs_sheet_name = st.text_input(
        "シート名（空欄で1枚目）",
        value=saved.get("gs_sheet_name", ""),
        placeholder="Sheet1",
        key=f"{widget_key}_sheetname",
    )

    if st.button("🔗 スプレッドシートを読み込む", key=f"{widget_key}_load"):
        if not gs_key_path or not gs_sheet_url:
            st.warning("JSONキーのパスとスプレッドシートURLを入力してください。")
            return None
        try:
            import gspread
            from google.oauth2.service_account import Credentials

            scopes = [
                "https://www.googleapis.com/auth/spreadsheets.readonly",
                "https://www.googleapis.com/auth/drive.readonly",
            ]
            creds = Credentials.from_service_account_file(gs_key_path, scopes=scopes)
            gc = gspread.authorize(creds)
            sh = gc.open_by_url(gs_sheet_url)
            ws = sh.worksheet(gs_sheet_name) if gs_sheet_name else sh.get_worksheet(0)
            records = ws.get_all_values()
            if not records:
                st.warning("シートが空です。")
                return None
            df = pd.DataFrame(records[1:], columns=records[0]).fillna("")
            st.success(f"✅ 読み込み完了: {len(df)}行 / {len(df.columns)}列")
            # 設定を記憶
            _save_import_settings(widget_key.split("_")[0], {
                **saved,
                "gs_key_path":   gs_key_path,
                "gs_sheet_url":  gs_sheet_url,
                "gs_sheet_name": gs_sheet_name,
            })
            return df
        except ImportError:
            st.error("gspread / google-auth がインストールされていません。`pip install gspread google-auth` を実行してください。")
        except FileNotFoundError:
            st.error("JSONキーファイルが見つかりません。パスを確認してください。")
        except Exception as e:
            st.error(f"接続エラー: {e}")
    return None


# ──────────────────────────────
# TAB1: コール記録
# ──────────────────────────────
with tab_call:
    st.subheader("テレアポ結果を記録する")
    ctab_manual, ctab_csv = st.tabs(["✏️ 手動入力", "📥 CSVインポート"])

    with ctab_manual:
        companies = load_company_list()

        col1, col2 = st.columns([2, 1])

        with col1:
            if companies:
                input_mode = st.radio("会社名の入力方法", ["リストから選択", "直接入力"], horizontal=True, label_visibility="collapsed")
            else:
                input_mode = "直接入力"

            if input_mode == "リストから選択" and companies:
                company_name = st.selectbox("会社名", companies)
            else:
                company_name = st.text_input("会社名", placeholder="株式会社〇〇")

            approach_result = st.selectbox(
                "アポ結果",
                ["断り", "アポ獲得", "留守", "後日折り返し", "その他"],
            )

            rejection_reason = ""
            if approach_result == "断り":
                rejection_reason = st.selectbox(
                    "断り理由",
                    ["既導入", "興味なし", "予算なし", "タイミング", "担当不在", "その他"],
                )

            temperature = st.select_slider(
                "温度感",
                options=["低", "中", "高"],
                value="低",
            )

            company_scale = st.selectbox(
                "企業規模（目安）",
                ["不明", "小", "中", "大"],
                index=0,
                help="ざっくりで構いません。小規模は従業員数10〜50程度など。",
            )

            ng_reason = st.selectbox(
                "NG理由（該当があれば）",
                ["なし", "規模NG", "業種NG", "メディアNG", "その他"],
                index=0,
            )

        with col2:
            st.markdown("　")
            good_points = st.text_input("反応が良かったポイント", placeholder="健康経営に興味あり 等")
            memo = st.text_area("メモ", placeholder="折り返し希望・担当者名 等", height=120)

        got_appointment = approach_result == "アポ獲得"
        submitted = st.button("✅ 記録する", type="primary", disabled=not company_name)

        if submitted and company_name:
            record_feedback(
                company_name=company_name,
                approach_result=approach_result,
                got_appointment=got_appointment,
                rejection_reason=rejection_reason,
                temperature=temperature,
                company_scale=company_scale,
                ng_reason=ng_reason,
                good_points=good_points,
                memo=memo,
            )
            st.success(f"記録しました: **{company_name}** — {approach_result}")
            st.rerun()

        st.divider()
        st.caption("直近の記録")
        df_fb = load_feedback()
        if not df_fb.empty:
            recent = df_fb.sort_values("記録日", ascending=False).head(10)
            display_cols = [
                c for c in ["記録日", "会社名", "アプローチ結果", "規模", "NG理由", "断り理由", "温度感", "メモ"]
                if c in recent.columns
            ]
            st.dataframe(
                recent[display_cols],
                use_container_width=True,
                hide_index=True,
        )
        else:
            st.caption("まだ記録がありません")

    # ── コール記録 インポート（ファイルパス記憶・Excel対応）────────
    with ctab_csv:
        c_saved = _load_import_settings("call")
        st.caption("CSV / Excel (.xlsx) / Googleスプレッドシート を読み込んでコール記録に取り込みます。")

        # ── ファイル指定（パス直接入力 or アップロード or Google Sheets）─────────
        c_src_mode = st.radio(
            "ファイルの指定方法",
            ["📂 パスを直接入力（毎回開く不要）", "⬆️ アップロード", "🔗 Googleスプレッドシート"],
            horizontal=True,
            key="c_src_mode",
        )

        c_df_raw: pd.DataFrame | None = None
        c_filepath = ""

        if c_src_mode.startswith("📂"):
            c_default_path = c_saved.get("filepath", "")
            c_filepath = st.text_input(
                "ファイルパス（CSV または .xlsx）",
                value=c_default_path,
                placeholder=r"C:\Users\user\Desktop\テレアポ記録.xlsx",
                key="c_filepath",
            )
            if c_filepath and os.path.exists(c_filepath):
                c_df_raw = _read_file_to_df(c_filepath)
                if c_df_raw is None:
                    st.error("ファイルを読み込めませんでした。")
            elif c_filepath:
                st.warning("ファイルが見つかりません。パスを確認してください。")
        elif c_src_mode.startswith("⬆️"):
            c_uploaded = st.file_uploader("CSV / Excel を選択", type=["csv", "xlsx", "xls"], key="call_file_upload")
            if c_uploaded:
                ext = os.path.splitext(c_uploaded.name)[1].lower()
                if ext in (".xlsx", ".xls"):
                    c_df_raw = pd.read_excel(c_uploaded, dtype=str).fillna("")
                else:
                    raw = c_uploaded.read()
                    for enc in ("utf-8-sig", "shift-jis", "cp932", "utf-8"):
                        try:
                            c_df_raw = pd.read_csv(_io_mod.StringIO(raw.decode(enc)), dtype=str).fillna("")
                            break
                        except Exception:
                            pass
                c_filepath = c_uploaded.name
        else:
            # ── Google Sheets 連携 ──────────────────────────────────
            c_df_raw = _render_gsheets_loader("call_gs", c_saved)

        if c_df_raw is not None:
            st.markdown(f"**読み込み: {len(c_df_raw)}行 / {len(c_df_raw.columns)}列**")
            st.dataframe(c_df_raw.head(3), use_container_width=True, hide_index=True)

            st.markdown("### 列マッピング")
            c_cols = ["（使わない）"] + c_df_raw.columns.tolist()
            c_map = c_saved.get("mapping", {})

            def c_pick(label, keywords):
                saved_val = c_map.get(label)
                if saved_val and saved_val in c_cols:
                    default = saved_val
                else:
                    default = next((col for kw in keywords for col in c_df_raw.columns if kw in col), "（使わない）")
                return st.selectbox(label, c_cols, index=c_cols.index(default), key=f"cmap_{label}")

            cc1, cc2 = st.columns(2)
            with cc1:
                c_col_date    = c_pick("記録日",           ["日付", "記録日", "date"])
                c_col_company = c_pick("会社名",           ["会社名"])
                c_col_result  = c_pick("アポ結果",         ["結果", "アポ", "商談結果"])
                c_col_reject  = c_pick("断り理由",         ["断り", "理由"])
                c_col_scale   = c_pick("規模",             ["規模", "社員数", "従業員"])
                c_col_ng      = c_pick("NG理由",          ["NG", "理由"])
            with cc2:
                c_col_temp    = c_pick("温度感",           ["温度"])
                c_col_good    = c_pick("反応が良かったポイント", ["ポイント", "反応"])
                c_col_memo    = c_pick("メモ",             ["メモ", "備考"])

            c_apo_kw = st.text_input(
                "アポ獲得と判定するキーワード（カンマ区切り）",
                value=c_saved.get("apo_keywords", "アポ獲得,アポ,体験会確定,契約"),
                key="c_apo_kw",
            )
            c_apo_keywords = [k.strip() for k in c_apo_kw.split(",") if k.strip()]

            def c_convert(row) -> dict | None:
                company = row.get(c_col_company, "").strip() if c_col_company != "（使わない）" else ""
                if not company:
                    return None
                result = row.get(c_col_result, "").strip() if c_col_result != "（使わない）" else ""
                return {
                    "記録日":   row.get(c_col_date,  "").strip() if c_col_date  != "（使わない）" else "",
                    "会社名":   company,
                    "アプローチ結果": result,
                    "アポ獲得":  "はい" if any(kw in result for kw in c_apo_keywords) else "いいえ",
                    "規模":     row.get(c_col_scale, "").strip() if c_col_scale != "（使わない）" else "",
                    "NG理由":  row.get(c_col_ng,    "").strip() if c_col_ng    != "（使わない）" else "",
                    "断り理由":  row.get(c_col_reject, "").strip() if c_col_reject != "（使わない）" else "",
                    "温度感":   row.get(c_col_temp,   "").strip() if c_col_temp   != "（使わない）" else "",
                    "反応が良かったポイント": row.get(c_col_good, "").strip() if c_col_good != "（使わない）" else "",
                    "メモ":     row.get(c_col_memo,   "").strip() if c_col_memo   != "（使わない）" else "",
                }

            c_preview = [r for r in (c_convert(row) for _, row in c_df_raw.iterrows()) if r]
            st.markdown(f"**変換プレビュー（先頭3件）** ※合計 {len(c_preview)} 件")
            if c_preview:
                st.dataframe(pd.DataFrame(c_preview[:3]), use_container_width=True, hide_index=True)

                df_fb_ex = load_feedback()
                existing = set(df_fb_ex["会社名"].dropna().tolist()) if not df_fb_ex.empty else set()
                c_new = [r for r in c_preview if r["会社名"] not in existing]
                if len(c_preview) - len(c_new):
                    st.info(f"既存と重複: {len(c_preview) - len(c_new)}件スキップ")

                if st.button(f"✅ {len(c_new)}件をコール記録に取り込む", type="primary", disabled=len(c_new) == 0, key="c_import_btn"):
                    import csv as _csv2
                    os.makedirs(OUTPUT_DIR, exist_ok=True)
                    f_exists = os.path.exists(FEEDBACK_FILE) and os.path.getsize(FEEDBACK_FILE) > 0
                    fields = ["記録日", "会社名", "アプローチ結果", "アポ獲得", "規模", "NG理由", "断り理由", "温度感", "反応が良かったポイント", "メモ"]
                    with open(FEEDBACK_FILE, "a", newline="", encoding="utf-8-sig") as f:
                        w = _csv2.DictWriter(f, fieldnames=fields)
                        if not f_exists:
                            w.writeheader()
                        for r in c_new:
                            w.writerow(r)
                    # 設定を記憶
                    _save_import_settings("call", {
                        "filepath": c_filepath if c_src_mode.startswith("📂") else "",
                        "mapping": {
                            "記録日": c_col_date, "会社名": c_col_company, "アポ結果": c_col_result,
                            "規模": c_col_scale, "NG理由": c_col_ng,
                            "断り理由": c_col_reject, "温度感": c_col_temp,
                            "反応が良かったポイント": c_col_good, "メモ": c_col_memo,
                        },
                        "apo_keywords": c_apo_kw,
                    })
                    st.success(f"✅ {len(c_new)}件を取り込みました。設定を記憶しました。")
                    st.rerun()


# ──────────────────────────────
# TAB2: 履歴
# ──────────────────────────────
with tab_history:
    st.subheader("コール履歴")

    df_fb = load_feedback()

    if df_fb.empty:
        st.info("まだ記録がありません。「コール記録」タブから入力してください。")
    else:
        # フィルター
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            filter_result = st.multiselect(
                "アポ結果で絞り込み",
                options=df_fb["アプローチ結果"].dropna().unique().tolist(),
            )
        with col_f2:
            filter_temp = st.multiselect(
                "温度感で絞り込み",
                options=["高", "中", "低"],
            )
        with col_f3:
            search_name = st.text_input("会社名で検索")

        filtered = df_fb.copy()
        if filter_result:
            filtered = filtered[filtered["アプローチ結果"].isin(filter_result)]
        if filter_temp:
            filtered = filtered[filtered["温度感"].isin(filter_temp)]
        if search_name:
            filtered = filtered[filtered["会社名"].str.contains(search_name, na=False)]

        st.dataframe(
            filtered.sort_values("記録日", ascending=False),
            use_container_width=True,
            hide_index=True,
        )

        # CSVダウンロード
        csv_bytes = filtered.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button(
            "📥 CSVダウンロード",
            data=csv_bytes,
            file_name="feedback_export.csv",
            mime="text/csv",
        )


# ──────────────────────────────
# TAB3: 分析
# ──────────────────────────────
with tab_analysis:
    st.subheader("テレアポ傾向分析")

    df_fb = load_feedback()

    if df_fb.empty:
        st.info("データが溜まったら分析できます。まずコール記録を入力してください。")
    else:
        total = len(df_fb)
        apo_count = (df_fb["アポ獲得"] == "はい").sum()
        apo_rate = apo_count / total * 100 if total > 0 else 0

        # KPI
        col_k1, col_k2, col_k3, col_k4 = st.columns(4)
        col_k1.metric("総コール数", f"{total}件")
        col_k2.metric("アポ獲得数", f"{apo_count}件")
        col_k3.metric("アポ獲得率", f"{apo_rate:.1f}%")
        high_temp = (df_fb["温度感"] == "高").sum()
        col_k4.metric("温度感「高」", f"{high_temp}件")

        st.divider()

        col_g1, col_g2 = st.columns(2)

        with col_g1:
            st.markdown("**アポ結果の内訳**")
            result_counts = df_fb["アプローチ結果"].value_counts()
            st.bar_chart(result_counts)

        with col_g2:
            st.markdown("**断り理由の内訳**")
            rejection_df = df_fb[df_fb["断り理由"].notna() & (df_fb["断り理由"] != "")]
            if not rejection_df.empty:
                rejection_counts = rejection_df["断り理由"].value_counts()
                st.bar_chart(rejection_counts)
            else:
                st.caption("断りデータなし")

        st.divider()

        # ── results.csv との突合分析 ──────────────────────────────────
        st.markdown("### ランク・シグナル別アポ率")

        import re as _re

        def _build_signal_analysis(df_feedback: pd.DataFrame) -> dict:
            """feedback と results.csv を突合してシグナル別アポ率を計算"""
            if not os.path.exists(RESULTS_FILE):
                return {}
            try:
                df_res = pd.read_csv(RESULTS_FILE, encoding="utf-8-sig")
            except Exception:
                return {}

            results_by_name = {
                row["会社名"].strip(): row
                for _, row in df_res.iterrows()
                if pd.notna(row.get("会社名"))
            }

            rank_stats: dict[str, dict] = {}
            signal_stats: dict[str, dict] = {}

            for _, fb in df_feedback.iterrows():
                name = str(fb.get("会社名", "")).strip()
                got_apo = fb.get("アポ獲得") == "はい"
                result = results_by_name.get(name)
                if result is None:
                    continue

                rank = str(result.get("ランク", "")).strip()
                if rank:
                    s = rank_stats.setdefault(rank, {"apo": 0, "total": 0})
                    s["total"] += 1
                    if got_apo:
                        s["apo"] += 1

                notes = str(result.get("備考", ""))
                m = _re.search(r"理由: (.+?)(?:\s*\||$)", notes)
                if m:
                    for sig in [s.strip() for s in m.group(1).split(",")]:
                        key = sig[:35]
                        s = signal_stats.setdefault(key, {"apo": 0, "total": 0})
                        s["total"] += 1
                        if got_apo:
                            s["apo"] += 1

            return {"rank_stats": rank_stats, "signal_stats": signal_stats}

        analysis = _build_signal_analysis(df_fb)

        if not analysis:
            st.caption("results.csv が見つからないか、まだ突合できるデータがありません。")
        else:
            rank_stats = analysis.get("rank_stats", {})
            signal_stats = analysis.get("signal_stats", {})
            matched = sum(s["total"] for s in rank_stats.values())
            st.caption(f"results.csv との突合: {matched}/{total}件")

            # ランク別アポ率
            if rank_stats:
                rank_data = {
                    rank: round(s["apo"] / s["total"] * 100, 1) if s["total"] > 0 else 0
                    for rank, s in rank_stats.items()
                }
                rank_df = pd.DataFrame.from_dict(
                    rank_data, orient="index", columns=["アポ率(%)"]
                ).reindex(["A", "B", "C"]).dropna()
                col_r1, col_r2 = st.columns([1, 2])
                with col_r1:
                    st.markdown("**ランク別アポ率**")
                    for rank in ["A", "B", "C"]:
                        if rank in rank_stats:
                            s = rank_stats[rank]
                            r = s["apo"] / s["total"] * 100 if s["total"] > 0 else 0
                            st.metric(f"{rank}ランク", f"{r:.1f}%", f"{s['apo']}/{s['total']}件")
                with col_r2:
                    if not rank_df.empty:
                        st.bar_chart(rank_df)

            # シグナル別アポ率
            if signal_stats:
                sig_rates = sorted(
                    [(sig, s["apo"] / s["total"] * 100, s["apo"], s["total"])
                     for sig, s in signal_stats.items() if s["total"] >= 3],
                    key=lambda x: -x[1],
                )
                if sig_rates:
                    st.markdown("**シグナル別アポ率（3件以上）**")
                    sig_df = pd.DataFrame(sig_rates, columns=["シグナル", "アポ率(%)", "アポ数", "件数"])
                    sig_df["アポ率(%)"] = sig_df["アポ率(%)"].round(1)
                    st.dataframe(sig_df, use_container_width=True, hide_index=True)

                    # 低効果シグナルの警告
                    low = sig_df[sig_df["アポ率(%)"] < 10]
                    if not low.empty:
                        st.warning(
                            f"アポ率10%未満のシグナル: "
                            + "、".join(f"「{r}」" for r in low["シグナル"].tolist()[:3])
                            + " → 採点ウェイント削減を検討"
                        )
                else:
                    st.caption("シグナル分析には各シグナルで3件以上のコール記録が必要です。")

        st.divider()

        # 温度感「高」「中」の企業一覧（次のフォロー候補）
        st.markdown("**温度感「高」「中」の企業（フォロー候補）**")
        warm = df_fb[df_fb["温度感"].isin(["高", "中"])].sort_values("温度感", ascending=False)
        if not warm.empty:
            st.dataframe(
                warm[["記録日", "会社名", "アプローチ結果", "温度感", "断り理由", "反応が良かったポイント", "メモ"]],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("温度感「高」「中」の記録なし")

        # アポ獲得企業一覧
        st.markdown("**アポ獲得企業一覧**")
        apo_df = df_fb[df_fb["アポ獲得"] == "はい"]
        if not apo_df.empty:
            st.dataframe(
                apo_df[["記録日", "会社名", "反応が良かったポイント", "メモ"]],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("アポ獲得記録なし")


# ──────────────────────────────
# TAB4: 取り込み（営業分析シートCSV → feedback.csv）
# ──────────────────────────────
with tab_import:
    st.subheader("営業シートCSVをインポート")
    st.caption("「2025営業分析シート」などの商談記録CSVをfeedback.csvに一括取り込みします。")

    uploaded = st.file_uploader("CSVファイルを選択", type=["csv"])

    if uploaded:
        # 文字コードを自動検出（Shift-JIS / UTF-8 両対応）
        raw = uploaded.read()
        for enc in ("utf-8-sig", "shift-jis", "cp932", "utf-8"):
            try:
                text = raw.decode(enc)
                break
            except Exception:
                text = None

        if not text:
            st.error("文字コードを判別できませんでした。UTF-8またはShift-JIS形式で保存してください。")
        else:
            import io
            lines = text.splitlines()

            # ヘッダー行を探す（「会社名」を含む行）
            header_idx = next(
                (i for i, line in enumerate(lines) if "会社名" in line),
                None,
            )
            if header_idx is None:
                st.error("「会社名」列が見つかりません。ヘッダー行を確認してください。")
            else:
                df_raw = pd.read_csv(
                    io.StringIO("\n".join(lines[header_idx:])),
                    dtype=str,
                ).fillna("")

                st.markdown(f"**読み込み: {len(df_raw)}行 / {len(df_raw.columns)}列**")
                st.dataframe(df_raw.head(5), use_container_width=True, hide_index=True)

                st.divider()
                st.markdown("### 列マッピング設定")

                cols = ["（使わない）"] + df_raw.columns.tolist()

                def pick(label, default_keywords, idx_fallback="（使わない）"):
                    """デフォルトをキーワード一致で自動選択"""
                    default = idx_fallback
                    for kw in default_keywords:
                        match = next((c for c in df_raw.columns if kw in c), None)
                        if match:
                            default = match
                            break
                    return st.selectbox(label, cols, index=cols.index(default))

                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    col_date    = pick("日付列",     ["日付", "date"])
                    col_company = pick("会社名列",   ["会社名"])
                    col_result  = pick("商談結果列", ["商談結果", "結果"])
                    col_reject  = pick("断り理由列", ["断り", "懸念"])
                with col_m2:
                    col_temp    = pick("温度感列",   ["温度感", "温度"])
                    col_memo    = pick("メモ列",     ["リスト課題詳細", "メモ", "備考"])
                    col_url     = pick("URL列",      ["URL", "url"])

                # アポ獲得と判定する商談結果キーワード
                st.markdown("**アポ獲得と判定するキーワード**（商談結果列の値）")
                apo_keywords_input = st.text_input(
                    "カンマ区切りで入力",
                    value="体験会確定,体験会決定,契約",
                )
                apo_keywords = [k.strip() for k in apo_keywords_input.split(",") if k.strip()]

                st.divider()

                # プレビュー変換
                def convert_row(row) -> dict | None:
                    company = row.get(col_company, "").strip() if col_company != "（使わない）" else ""
                    if not company or company in ("会社名", "No.", ""):
                        return None
                    result  = row.get(col_result, "").strip()  if col_result  != "（使わない）" else ""
                    reject  = row.get(col_reject, "").strip()  if col_reject  != "（使わない）" else ""
                    temp    = row.get(col_temp,   "").strip()  if col_temp    != "（使わない）" else ""
                    memo    = row.get(col_memo,   "").strip()  if col_memo    != "（使わない）" else ""
                    url     = row.get(col_url,    "").strip()  if col_url     != "（使わない）" else ""
                    date    = row.get(col_date,   "").strip()  if col_date    != "（使わない）" else ""

                    got_apo = any(kw in result for kw in apo_keywords)

                    # メモにURLを付加（tracability）
                    memo_parts = [p for p in [memo, f"URL: {url}" if url else ""] if p]

                    return {
                        "記録日":              date or "",
                        "会社名":              company,
                        "アプローチ結果":       result,
                        "アポ獲得":            "はい" if got_apo else "いいえ",
                        "断り理由":            reject,
                        "温度感":              temp,
                        "反応が良かったポイント": "",
                        "メモ":               " / ".join(memo_parts),
                    }

                preview_rows = [r for r in (convert_row(row) for _, row in df_raw.iterrows()) if r]

                st.markdown(f"**変換プレビュー（先頭5件）**  ※合計 {len(preview_rows)} 件")
                if preview_rows:
                    st.dataframe(pd.DataFrame(preview_rows[:5]), use_container_width=True, hide_index=True)

                    # リスト課題のサマリー表示
                    if col_memo != "（使わない）" and col_memo in df_raw.columns:
                        issues = [
                            r[col_memo] for _, r in df_raw.iterrows()
                            if r.get(col_memo, "").strip() not in ("", "FALSE", "False")
                        ]
                        if issues:
                            st.warning(
                                f"⚠️ **リスト課題あり: {len(issues)}件**  \n"
                                "→ 以下の理由はNG条件の改善ヒントです（`config.py` の `NG_INDUSTRY_KEYWORDS` 追加を検討）\n\n"
                                + "\n".join(f"- {i}" for i in issues[:10])
                            )

                    # 既存データとの重複チェック
                    df_fb = load_feedback()
                    existing_names = set(df_fb["会社名"].dropna().tolist()) if not df_fb.empty else set()
                    new_rows = [r for r in preview_rows if r["会社名"] not in existing_names]
                    dup_count = len(preview_rows) - len(new_rows)
                    if dup_count:
                        st.info(f"既にfeedback.csvに存在する会社名: {dup_count}件（スキップ）")

                    if st.button(f"✅ {len(new_rows)}件をfeedback.csvに取り込む", type="primary", disabled=len(new_rows) == 0):
                        import csv as _csv
                        os.makedirs(OUTPUT_DIR, exist_ok=True)
                        file_exists = os.path.exists(FEEDBACK_FILE) and os.path.getsize(FEEDBACK_FILE) > 0
                        fieldnames = ["記録日", "会社名", "アプローチ結果", "アポ獲得", "断り理由", "温度感", "反応が良かったポイント", "メモ"]
                        with open(FEEDBACK_FILE, "a", newline="", encoding="utf-8-sig") as f:
                            writer = _csv.DictWriter(f, fieldnames=fieldnames)
                            if not file_exists:
                                writer.writeheader()
                            for r in new_rows:
                                writer.writerow(r)
                        st.success(f"✅ {len(new_rows)}件を取り込みました。「分析」タブで確認できます。")
                        st.rerun()


# ──────────────────────────────
# TAB5: リストアップ実行
# ──────────────────────────────
_PERIOD_OPTIONS = {
    "1週間":   "1",
    "2週間":   "2",
    "1カ月以内": "3",
    "2カ月以内": "4",
    "3カ月以内": "5",
    "6カ月以内": "6",
    "9カ月以内": "7",
    "1年以内":  "8",
}

with tab_listup:
    st.subheader("企業リストアップを実行")
    st.caption("Google検索 → スクレイピング → ランク判定 → HubSpot登録 を自動実行します。実行中はこのタブを開いたままにしてください。")

    col_l1, col_l2 = st.columns([2, 1])

    with col_l1:
        search_mode = st.radio(
            "検索モード",
            ["🤖 自動モード（媒体リスト＋学習クエリ）", "✏️ 手動モード（入力キーワードのみ）"],
            horizontal=True,
        )
        keywords_input = st.text_area(
            "追加キーワード（1行1つ）",
            placeholder="健康経営 株式会社\nオフィス ストレッチ 法定外福利厚生",
            help="自動モードでは学習済みクエリに追加されます。手動モードではここで入力したキーワードのみ使用します。",
            height=100,
        )

    with col_l2:
        target_count  = st.number_input("目標件数", min_value=5, max_value=200, value=50, step=5)
        period_labels = st.multiselect(
            "検索期間（複数選択可）",
            list(_PERIOD_OPTIONS.keys()),
            default=["3カ月以内"],
            help="複数選択すると各期間を順番に検索します",
        )
        confirm_mode = st.checkbox(
            "✅ 確認モード（HubSpot登録前にレビュー）",
            help="チェックを入れると、検索結果を pending_review.json に書き出し、画面で承認/却下できます",
        )

    st.divider()

    list_urls_input = st.text_area(
        "📋 追加リストページURL（1行1つ）",
        placeholder="https://example.com/companies\nhttps://example2.com/members",
        help="指定URLの企業リストページを先行スクレイピングします。空欄の場合はデフォルト媒体リストのみ使用。",
        height=80,
    )

    run_col, status_col = st.columns([1, 3])
    with run_col:
        run_btn = st.button("🚀 リストアップ開始", type="primary", use_container_width=True)

    if run_btn:
        keywords  = [k.strip() for k in keywords_input.splitlines() if k.strip()]
        auto_mode = search_mode.startswith("🤖")
        period_keys = [_PERIOD_OPTIONS[lbl] for lbl in period_labels if lbl in _PERIOD_OPTIONS]
        extra_list_urls = [u.strip() for u in list_urls_input.splitlines() if u.strip()]

        if not period_keys:
            st.warning("検索期間を1つ以上選択してください。")
            st.stop()

        if not auto_mode and not keywords:
            st.warning("手動モードではキーワードを1つ以上入力してください。")
        else:
            cmd = [sys.executable, "main.py", "--batch", "--count", str(target_count), "--periods"] + period_keys
            if auto_mode:
                cmd.append("--auto")
            if keywords:
                cmd += ["--keywords"] + keywords
            if extra_list_urls:
                cmd += ["--list-urls"] + extra_list_urls
            if confirm_mode:
                cmd.append("--confirm")

            st.info(f"実行コマンド: `{' '.join(cmd)}`")
            output_placeholder = st.empty()
            lines: list[str] = []

            try:
                _env = os.environ.copy()
                _env["PYTHONIOENCODING"] = "utf-8"
                _env["PYTHONUTF8"] = "1"
                proc = subprocess.Popen(
                    cmd,
                    cwd=_LIST_TOOL_DIR,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=_env,
                )

                for raw_line in proc.stdout:
                    lines.append(raw_line.rstrip())
                    # 最新100行を表示
                    output_placeholder.code("\n".join(lines[-100:]), language=None)

                proc.wait()

                if proc.returncode == 0:
                    st.success("リストアップ完了！ 「コール記録」タブの会社名リストが更新されました。")
                    if confirm_mode:
                        _show_pending_review_ui()
                else:
                    st.error(f"異常終了しました (終了コード: {proc.returncode})")

            except Exception as e:
                st.error(f"実行エラー: {e}")

    # ── 前回の確認待ちが残っていれば常に表示 ──────────────────────
    _pending_path_check = os.path.join(_LIST_TOOL_DIR, "output", "pending_review.json")
    if os.path.exists(_pending_path_check) and not run_btn:
        st.divider()
        st.caption("前回の確認モード結果が残っています。")
        _show_pending_review_ui()


# ──────────────────────────────
# TAB6: 商談記録
# ──────────────────────────────

def load_meetings() -> pd.DataFrame:
    if os.path.exists(MEETINGS_FILE):
        try:
            df = pd.read_csv(MEETINGS_FILE, encoding="utf-8-sig")
            df["商談日"] = pd.to_datetime(df["商談日"], errors="coerce")
            df["記録日"] = pd.to_datetime(df["記録日"], errors="coerce")
            return df
        except Exception:
            pass
    return pd.DataFrame(columns=[
        "記録日", "商談日", "会社名", "担当者名", "フェーズ",
        "商談結果", "契約", "次のアクション", "規模感・金額", "メモ"
    ])


with tab_meeting:
    st.subheader("商談記録")

    mtab_input, mtab_list, mtab_pipeline, mtab_csv = st.tabs(["✏️ 新規入力", "📋 一覧・検索", "📊 パイプライン", "📥 CSVインポート"])

    # ── 新規入力 ───────────────────────────────────────────────
    with mtab_input:
        companies = load_company_list()

        col_m1, col_m2 = st.columns([2, 1])

        with col_m1:
            if companies:
                m_input_mode = st.radio(
                    "会社名", ["リストから選択", "直接入力"], horizontal=True, label_visibility="collapsed"
                )
            else:
                m_input_mode = "直接入力"

            if m_input_mode == "リストから選択" and companies:
                m_company = st.selectbox("会社名", companies, key="m_company_select")
            else:
                m_company = st.text_input("会社名", placeholder="株式会社〇〇", key="m_company_text")

            m_contact = st.text_input("担当者名", placeholder="山田 太郎（役職）")

            m_phase = st.selectbox(
                "フェーズ",
                ["初回商談", "2回目商談", "提案・デモ", "見積提出", "クロージング", "その他"],
            )

            m_result = st.selectbox(
                "商談結果",
                ["検討中", "次回アポあり", "契約", "保留", "NG（競合）", "NG（予算）", "NG（タイミング）", "その他"],
            )

        with col_m2:
            m_date = st.date_input("商談日", value="today")
            m_contracted = m_result == "契約"
            if m_contracted:
                st.success("🎉 契約！")
            m_deal_size = st.text_input("規模感・金額", placeholder="月額 5万円 / 50名")
            m_next_action = st.text_input("次のアクション", placeholder="来週再提案 / 稟議待ち")

        m_memo = st.text_area("メモ", placeholder="ヒアリング内容・懸念点・提案内容など", height=100)

        m_submitted = st.button("✅ 商談を記録する", type="primary", disabled=not m_company)

        if m_submitted and m_company:
            record_meeting(
                company_name=m_company,
                contact_name=m_contact,
                meeting_date=str(m_date),
                phase=m_phase,
                result=m_result,
                contracted=m_contracted,
                next_action=m_next_action,
                deal_size=m_deal_size,
                memo=m_memo,
            )
            st.success(f"記録しました: **{m_company}** — {m_phase} / {m_result}")
            st.rerun()

        # 直近5件
        st.divider()
        st.caption("直近の商談記録")
        df_mt = load_meetings()
        if not df_mt.empty:
            recent_mt = df_mt.sort_values("商談日", ascending=False).head(5)
            st.dataframe(
                recent_mt[["商談日", "会社名", "担当者名", "フェーズ", "商談結果", "次のアクション"]],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("まだ記録がありません")

    # ── 一覧・検索 ─────────────────────────────────────────────
    with mtab_list:
        df_mt = load_meetings()
        if df_mt.empty:
            st.info("まだ商談記録がありません。「新規入力」から登録してください。")
        else:
            col_f1, col_f2, col_f3 = st.columns(3)
            with col_f1:
                filter_phase = st.multiselect("フェーズで絞り込み", options=df_mt["フェーズ"].dropna().unique().tolist())
            with col_f2:
                filter_result = st.multiselect("商談結果で絞り込み", options=df_mt["商談結果"].dropna().unique().tolist())
            with col_f3:
                m_search = st.text_input("会社名で検索", key="m_search")

            filtered_mt = df_mt.copy()
            if filter_phase:
                filtered_mt = filtered_mt[filtered_mt["フェーズ"].isin(filter_phase)]
            if filter_result:
                filtered_mt = filtered_mt[filtered_mt["商談結果"].isin(filter_result)]
            if m_search:
                filtered_mt = filtered_mt[filtered_mt["会社名"].str.contains(m_search, na=False)]

            st.dataframe(
                filtered_mt.sort_values("商談日", ascending=False),
                use_container_width=True,
                hide_index=True,
            )

            csv_mt = filtered_mt.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button("📥 CSVダウンロード", data=csv_mt, file_name="meetings_export.csv", mime="text/csv")

    # ── パイプライン ────────────────────────────────────────────
    with mtab_pipeline:
        df_mt = load_meetings()
        if df_mt.empty:
            st.info("データが溜まったら分析できます。")
        else:
            total_mt   = len(df_mt)
            contracted = (df_mt["契約"] == "はい").sum()
            cv_rate    = contracted / total_mt * 100 if total_mt > 0 else 0

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("総商談数", f"{total_mt}件")
            k2.metric("契約件数", f"{contracted}件")
            k3.metric("成約率", f"{cv_rate:.1f}%")
            pending = df_mt[df_mt["商談結果"].isin(["検討中", "次回アポあり", "提案・デモ", "見積提出", "クロージング"])].shape[0]
            k4.metric("進行中", f"{pending}件")

            st.divider()

            col_p1, col_p2 = st.columns(2)
            with col_p1:
                st.markdown("**フェーズ別件数**")
                phase_counts = df_mt["フェーズ"].value_counts()
                st.bar_chart(phase_counts)

            with col_p2:
                st.markdown("**商談結果の内訳**")
                result_counts = df_mt["商談結果"].value_counts()
                st.bar_chart(result_counts)

            # 次のアクションが必要な案件
            st.divider()
            st.markdown("**次のアクションが必要な案件**")
            action_needed = df_mt[
                df_mt["商談結果"].isin(["検討中", "次回アポあり", "保留"]) &
                df_mt["次のアクション"].notna() &
                (df_mt["次のアクション"] != "")
            ].sort_values("商談日", ascending=False)
            if not action_needed.empty:
                st.dataframe(
                    action_needed[["商談日", "会社名", "担当者名", "フェーズ", "商談結果", "次のアクション", "規模感・金額"]],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.caption("対象なし")

    # ── 商談記録 インポート（ファイルパス記憶・Excel対応）────────
    with mtab_csv:
        m_saved = _load_import_settings("meeting")
        st.caption("CSV / Excel (.xlsx) / Googleスプレッドシート を読み込んで商談記録に取り込みます。")

        m_src_mode = st.radio(
            "ファイルの指定方法",
            ["📂 パスを直接入力（毎回開く不要）", "⬆️ アップロード", "🔗 Googleスプレッドシート"],
            horizontal=True,
            key="m_src_mode",
        )

        m_df_raw: pd.DataFrame | None = None
        m_filepath = ""

        if m_src_mode.startswith("📂"):
            m_default_path = m_saved.get("filepath", "")
            m_filepath = st.text_input(
                "ファイルパス（CSV または .xlsx）",
                value=m_default_path,
                placeholder=r"C:\Users\user\Desktop\商談管理.xlsx",
                key="m_filepath",
            )
            if m_filepath and os.path.exists(m_filepath):
                m_df_raw = _read_file_to_df(m_filepath)
                if m_df_raw is None:
                    st.error("ファイルを読み込めませんでした。")
            elif m_filepath:
                st.warning("ファイルが見つかりません。パスを確認してください。")
        elif m_src_mode.startswith("⬆️"):
            m_uploaded2 = st.file_uploader("CSV / Excel を選択", type=["csv", "xlsx", "xls"], key="meeting_file_upload")
            if m_uploaded2:
                ext = os.path.splitext(m_uploaded2.name)[1].lower()
                if ext in (".xlsx", ".xls"):
                    m_df_raw = pd.read_excel(m_uploaded2, dtype=str).fillna("")
                else:
                    raw = m_uploaded2.read()
                    for enc in ("utf-8-sig", "shift-jis", "cp932", "utf-8"):
                        try:
                            m_df_raw = pd.read_csv(_io_mod.StringIO(raw.decode(enc)), dtype=str).fillna("")
                            break
                        except Exception:
                            pass
                m_filepath = m_uploaded2.name
        else:
            # ── Google Sheets 連携 ──────────────────────────────────
            m_df_raw = _render_gsheets_loader("meeting_gs", m_saved)

        if m_df_raw is not None:
            st.markdown(f"**読み込み: {len(m_df_raw)}行 / {len(m_df_raw.columns)}列**")
            st.dataframe(m_df_raw.head(3), use_container_width=True, hide_index=True)

            st.markdown("### 列マッピング")
            m_cols = ["（使わない）"] + m_df_raw.columns.tolist()
            m_map = m_saved.get("mapping", {})

            def m_pick(label, keywords):
                saved_val = m_map.get(label)
                if saved_val and saved_val in m_cols:
                    default = saved_val
                else:
                    default = next((col for kw in keywords for col in m_df_raw.columns if kw in col), "（使わない）")
                return st.selectbox(label, m_cols, index=m_cols.index(default), key=f"mmap_{label}")

            mc1, mc2 = st.columns(2)
            with mc1:
                m_col_mdate   = m_pick("商談日",       ["商談日", "日付", "date"])
                m_col_company = m_pick("会社名",       ["会社名"])
                m_col_contact = m_pick("担当者名",     ["担当者", "氏名", "名前"])
                m_col_phase   = m_pick("フェーズ",     ["フェーズ", "段階"])
                m_col_result  = m_pick("商談結果",     ["結果", "商談結果"])
            with mc2:
                m_col_deal    = m_pick("規模感・金額", ["金額", "規模", "単価"])
                m_col_next    = m_pick("次のアクション", ["次", "アクション", "todo"])
                m_col_memo    = m_pick("メモ",         ["メモ", "備考", "内容"])

            m_contract_kw = st.text_input(
                "契約と判定するキーワード（カンマ区切り）",
                value=m_saved.get("contract_keywords", "契約,成約,クロージング完了"),
                key="m_contract_kw",
            )
            m_contract_keywords = [k.strip() for k in m_contract_kw.split(",") if k.strip()]

            def m_convert(row) -> dict | None:
                company = row.get(m_col_company, "").strip() if m_col_company != "（使わない）" else ""
                if not company:
                    return None
                result = row.get(m_col_result, "").strip() if m_col_result != "（使わない）" else ""
                from datetime import date as _date
                return {
                    "記録日":   str(_date.today()),
                    "商談日":   row.get(m_col_mdate,   "").strip() if m_col_mdate   != "（使わない）" else "",
                    "会社名":   company,
                    "担当者名": row.get(m_col_contact, "").strip() if m_col_contact != "（使わない）" else "",
                    "フェーズ": row.get(m_col_phase,   "").strip() if m_col_phase   != "（使わない）" else "",
                    "商談結果": result,
                    "契約":     "はい" if any(kw in result for kw in m_contract_keywords) else "いいえ",
                    "次のアクション": row.get(m_col_next,  "").strip() if m_col_next  != "（使わない）" else "",
                    "規模感・金額":   row.get(m_col_deal,  "").strip() if m_col_deal  != "（使わない）" else "",
                    "メモ":     row.get(m_col_memo,    "").strip() if m_col_memo    != "（使わない）" else "",
                }

            m_preview = [r for r in (m_convert(row) for _, row in m_df_raw.iterrows()) if r]
            st.markdown(f"**変換プレビュー（先頭3件）** ※合計 {len(m_preview)} 件")
            if m_preview:
                st.dataframe(pd.DataFrame(m_preview[:3]), use_container_width=True, hide_index=True)

                df_mt_ex = load_meetings()
                m_existing = set(df_mt_ex["会社名"].dropna().tolist()) if not df_mt_ex.empty else set()
                m_new = [r for r in m_preview if r["会社名"] not in m_existing]
                if len(m_preview) - len(m_new):
                    st.info(f"既存と重複: {len(m_preview) - len(m_new)}件スキップ")

                if st.button(f"✅ {len(m_new)}件を商談記録に取り込む", type="primary", disabled=len(m_new) == 0, key="m_import_btn"):
                    import csv as _csv3
                    os.makedirs(OUTPUT_DIR, exist_ok=True)
                    m_exists = os.path.exists(MEETINGS_FILE) and os.path.getsize(MEETINGS_FILE) > 0
                    m_fields = ["記録日", "商談日", "会社名", "担当者名", "フェーズ", "商談結果", "契約", "次のアクション", "規模感・金額", "メモ"]
                    with open(MEETINGS_FILE, "a", newline="", encoding="utf-8-sig") as f:
                        w = _csv3.DictWriter(f, fieldnames=m_fields)
                        if not m_exists:
                            w.writeheader()
                        for r in m_new:
                            w.writerow(r)
                    # 設定を記憶
                    _save_import_settings("meeting", {
                        "filepath": m_filepath if m_src_mode.startswith("📂") else "",
                        "mapping": {
                            "商談日": m_col_mdate, "会社名": m_col_company, "担当者名": m_col_contact,
                            "フェーズ": m_col_phase, "商談結果": m_col_result,
                            "規模感・金額": m_col_deal, "次のアクション": m_col_next, "メモ": m_col_memo,
                        },
                        "contract_keywords": m_contract_kw,
                    })
                    st.success(f"✅ {len(m_new)}件を取り込みました。設定を記憶しました。")
                    st.rerun()
