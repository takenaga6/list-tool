"""
Offi-Stretch リストアップ管理
起動: streamlit run app.py
タブ: ダッシュボード / 取り込み / リストアップ / システム診断 / 利用者フィードバック

架電ツール（架電先リスト・見込みリスト・確認待ち・履歴・商談一覧）は
pages/1_架電ツール.py に分離済み。
"""

import os
import io
import subprocess
import sys
import re as _re
import pandas as pd
import streamlit as st
import altair as alt

from config import (
    FEEDBACK_FILE, RESULTS_FILE, MEETINGS_FILE,
    CALL_LIST_FILE, IMPORT_SETTINGS_FILE, USER_FEEDBACK_FILE, OUTPUT_DIR,
    record_feedback,
)
from call_tool_utils import (
    apply_global_styles,
    _APPROACH_OPTIONS,
    load_feedback, load_call_list, update_call_list_row,
    load_meetings,
    _auto_refill_from_hubspot,
    _load_import_settings, _save_import_settings,
    _load_team_members, _save_team_members,
    _load_listup_workers, _increment_listup_worker,
    _show_pending_review_ui,
    _LIST_TOOL_DIR,
)

# ──────────────────────────────
# リストアップのバックグラウンド実行状態
# ──────────────────────────────
import sys as _sys
_LU_MODULE_KEY = "__listup_state_v2__"
if _LU_MODULE_KEY not in _sys.modules:
    import types as _types
    _lu = _types.ModuleType(_LU_MODULE_KEY)
    _lu.STATE = {"lines": [], "running": False, "done": False, "proc": None, "return_code": None}
    _sys.modules[_LU_MODULE_KEY] = _lu
_LISTUP_STATE = _sys.modules[_LU_MODULE_KEY].STATE


def _listup_reader_thread(proc: "subprocess.Popen[str]") -> None:
    """バックグラウンドスレッドでサブプロセスの stdout を読み込む"""
    for _line in proc.stdout:
        _LISTUP_STATE["lines"].append(_line.rstrip())
    proc.wait()
    _LISTUP_STATE["running"]     = False
    _LISTUP_STATE["done"]        = True
    _LISTUP_STATE["return_code"] = proc.returncode


# ──────────────────────────────
# 媒体設定ファイル管理
# ──────────────────────────────
import json as _json

_MEDIA_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media_config.json")
_MEDIA_TYPE_LABELS = {
    "S1": "S1（PR有料媒体）",
    "S2": "S2（健康経営メディア）",
    "S3": "S3（その他シグナル）",
}


def _load_media_config() -> dict:
    """media_config.json を読み込む。存在しない場合は空の構造を返す。"""
    if os.path.exists(_MEDIA_CONFIG_FILE):
        try:
            with open(_MEDIA_CONFIG_FILE, "r", encoding="utf-8") as _f:
                return _json.load(_f)
        except Exception:
            pass
    return {"S1": [], "S2": [], "S3": []}


def _save_media_config(config: dict) -> None:
    """media_config.json に保存する。"""
    with open(_MEDIA_CONFIG_FILE, "w", encoding="utf-8") as _f:
        _json.dump(config, _f, ensure_ascii=False, indent=2)


def _get_merged_media_list() -> dict:
    """
    config.py のデフォルト媒体リストと media_config.json のカスタム媒体をマージして返す。
    返り値: {"S1": [...], "S2": [...], "S3": [...]}
    各エントリは {"name": str, "url": str, "source": "default"|"custom"}
    """
    from config import S1_MEDIA_LIST_URLS, S2_MEDIA_LIST_URLS
    custom = _load_media_config()
    return {
        "S1": [{"name": "（デフォルト）", "url": u, "source": "default"} for u in S1_MEDIA_LIST_URLS]
              + [{"source": "custom", **e} for e in custom.get("S1", [])],
        "S2": [{"name": "（デフォルト）", "url": u, "source": "default"} for u in S2_MEDIA_LIST_URLS]
              + [{"source": "custom", **e} for e in custom.get("S2", [])],
        "S3": [{"source": "custom", **e} for e in custom.get("S3", [])],
    }


# ──────────────────────────────
# ページ設定
# ──────────────────────────────
st.set_page_config(
    page_title="Offi-Stretch リスト管理",
    page_icon="🌿",
    layout="wide",
)

apply_global_styles("リスト管理")

# ──────────────────────────────
# タブ定義
# ──────────────────────────────
tab_analysis, tab_import, tab_listup, tab_monitor, tab_user_fb = st.tabs(
    ["ダッシュボード", "取り込み", "リストアップ", "システム診断", "利用者フィードバック"]
)

# 架電先リストをスクリプト実行ごとに1回だけ読み込む
_df_call_list = load_call_list()


# ──────────────────────────────
# TAB: ダッシュボード
# ──────────────────────────────
with tab_analysis:
    st.subheader("ダッシュボード")

    dash_integrated, = st.tabs(["📊 統合"])

    # ── 統合ダッシュボード ──────────────────────────────────────────
    with dash_integrated:
        _df_fb_d = load_feedback()
        _df_mt_d = load_meetings() if os.path.exists(MEETINGS_FILE) else pd.DataFrame()

        _total_calls  = len(_df_fb_d)
        _total_mtgs   = len(_df_mt_d) if not _df_mt_d.empty else 0
        _apo_d        = (_df_fb_d["アポ獲得"] == "はい").sum() if not _df_fb_d.empty else 0
        _contract_d   = (_df_mt_d["契約"] == "はい").sum() if (not _df_mt_d.empty and "契約" in _df_mt_d.columns) else 0

        dk1, dk2, dk3, dk4 = st.columns(4)
        dk1.metric("総架電数",    f"{_total_calls}件")
        dk2.metric("アポ獲得数",  f"{_apo_d}件")
        dk3.metric("総商談数",    f"{_total_mtgs}件")
        dk4.metric("契約件数",    f"{_contract_d}件")

        if not _df_fb_d.empty and "担当名" in _df_fb_d.columns:
            _tanto_col = _df_fb_d[_df_fb_d["担当名"].notna() & (_df_fb_d["担当名"] != "")]
            if not _tanto_col.empty:
                st.divider()
                st.markdown("**担当者別サマリー**")
                _tanto_summary = _tanto_col.groupby("担当名").agg(
                    架電数=("会社名", "count"),
                    アポ数=("アポ獲得", lambda x: (x == "はい").sum()),
                ).reset_index()
                _tanto_summary["アポ率(%)"] = (_tanto_summary["アポ数"] / _tanto_summary["架電数"] * 100).round(1)

                if not _df_mt_d.empty and "担当名" in _df_mt_d.columns:
                    _mt_tanto = _df_mt_d[_df_mt_d["担当名"].notna() & (_df_mt_d["担当名"] != "")].groupby("担当名").agg(
                        商談数=("会社名", "count"),
                        契約数=("契約", lambda x: (x == "はい").sum()),
                    ).reset_index()
                    _tanto_summary = _tanto_summary.merge(_mt_tanto, on="担当名", how="left").fillna(0)
                    _tanto_summary["商談数"] = _tanto_summary["商談数"].astype(int)
                    _tanto_summary["契約数"] = _tanto_summary["契約数"].astype(int)

                st.dataframe(_tanto_summary, width="stretch", hide_index=True)

                _tanto_chart = alt.Chart(_tanto_summary).mark_bar(color="#4C78A8").encode(
                    x=alt.X("担当名:N", axis=alt.Axis(labelAngle=0, labelFontSize=13)),
                    y=alt.Y("架電数:Q"),
                    tooltip=["担当名", "架電数", "アポ数", "アポ率(%)"],
                ).properties(height=220, title="担当者別 架電数")
                st.altair_chart(_tanto_chart, width="stretch")



# ──────────────────────────────
# TAB: 取り込み（営業分析シートCSV → feedback.csv）
# ──────────────────────────────
with tab_import:
    st.subheader("営業シートCSVをインポート")
    st.caption("「2025営業分析シート」などの商談記録CSVをfeedback.csvに一括取り込みします。")

    uploaded = st.file_uploader("CSVファイルを選択", type=["csv"])

    if uploaded:
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
            lines = text.splitlines()

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
                st.dataframe(df_raw.head(5), width="stretch", hide_index=True)

                st.divider()
                st.markdown("### 列マッピング設定")

                cols = ["（使わない）"] + df_raw.columns.tolist()

                def pick(label, default_keywords, idx_fallback="（使わない）"):
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

                st.markdown("**アポ獲得と判定するキーワード**（商談結果列の値）")
                apo_keywords_input = st.text_input(
                    "カンマ区切りで入力",
                    value="体験会確定,体験会決定,契約",
                )
                apo_keywords = [k.strip() for k in apo_keywords_input.split(",") if k.strip()]

                st.divider()

                def convert_row(row):
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
                    st.dataframe(pd.DataFrame(preview_rows[:5]), width="stretch", hide_index=True)

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
                        st.success(f"✅ {len(new_rows)}件を取り込みました。「ダッシュボード」タブで確認できます。")
                        st.rerun()


# ──────────────────────────────
# TAB: リストアップ実行
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

    _lu_workers = _load_listup_workers()
    _lu_worker_names = sorted(_lu_workers.keys())

    with st.expander("👤 担当者設定（複数人で同時実行する場合に設定）", expanded=bool(_lu_worker_names)):
        _lu_col_a, _lu_col_b = st.columns([2, 1])
        with _lu_col_a:
            lu_worker_name = st.text_input(
                "担当者名",
                placeholder="例: 野村",
                help="担当者ごとにリストアップ回数を記録し、キーワードの検索順序をずらして重複を防ぎます。",
                key="lu_worker_name",
            )
        with _lu_col_b:
            if _lu_worker_names:
                st.markdown("**過去の実行回数**")
                for _wn, _wc in sorted(_lu_workers.items()):
                    st.caption(f"{_wn}: {_wc}回")

        if lu_worker_name and _lu_workers:
            _my_count = _lu_workers.get(lu_worker_name, 0)
            _total_workers = len({n for n in _lu_workers if _lu_workers[n] > 0})
            if _total_workers > 1:
                st.info(
                    f"💡 **{lu_worker_name}**さんの実行回数: {_my_count}回 → "
                    f"キーワードを {_my_count} 番目からオフセットして検索します。"
                    " 他の担当者とキーワードが重なりにくくなります。"
                )

    st.divider()

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
        run_btn = st.button("🚀 リストアップ開始", type="primary", width="stretch")

    if run_btn:
        keywords  = [k.strip() for k in keywords_input.splitlines() if k.strip()]
        auto_mode = search_mode.startswith("🤖")
        period_keys = [_PERIOD_OPTIONS[lbl] for lbl in period_labels if lbl in _PERIOD_OPTIONS]
        extra_list_urls = [u.strip() for u in list_urls_input.splitlines() if u.strip()]

        _lu_offset = 0
        if lu_worker_name:
            _lu_offset = _increment_listup_worker(lu_worker_name)
            if keywords and _lu_offset > 1:
                _shift = (_lu_offset - 1) % max(len(keywords), 1)
                keywords = keywords[_shift:] + keywords[:_shift]

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
            _lu_env_offset = str(_lu_offset)

            st.info(f"実行コマンド: `{' '.join(cmd)}`")

            _lu_should_rerun = False
            try:
                _env = os.environ.copy()
                _env["PYTHONIOENCODING"] = "utf-8"
                _env["PYTHONUTF8"] = "1"
                _env["LISTUP_WORKER_NAME"] = lu_worker_name or ""
                _env["LISTUP_WORKER_OFFSET"] = _lu_env_offset
                _lu_proc = subprocess.Popen(
                    cmd,
                    cwd=_LIST_TOOL_DIR,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=_env,
                )
                import threading as _thr
                _LISTUP_STATE.update({
                    "proc": _lu_proc, "lines": [],
                    "running": True, "done": False, "return_code": None,
                })
                _thr.Thread(target=_listup_reader_thread, args=(_lu_proc,), daemon=True).start()
                _lu_should_rerun = True
            except Exception as _lu_e:
                st.session_state["_lu_last_error"] = str(_lu_e)
            if _lu_should_rerun:
                st.rerun()

    if st.session_state.get("_lu_last_error"):
        st.error(f"実行エラー: {st.session_state['_lu_last_error']}")
        if st.button("エラーをクリア", key="lu_clear_err"):
            del st.session_state["_lu_last_error"]
            st.rerun()

    if _LISTUP_STATE["running"] or _LISTUP_STATE["done"]:
        from streamlit_autorefresh import st_autorefresh as _lu_refresh
        if _LISTUP_STATE["running"]:
            _lu_refresh(interval=2000, key="listup_autorefresh")
            st.info("🔄 リストアップ実行中… 画面は2秒ごとに自動更新されます。このまま他のタブで架電記録できます。")
        elif _LISTUP_STATE["done"]:
            if _LISTUP_STATE["return_code"] == 0:
                st.success("✅ リストアップ完了！ 架電先リストに追加されました。")
            else:
                st.error(f"異常終了しました（終了コード: {_LISTUP_STATE['return_code']}）")
            if st.button("ログをクリア", key="lu_clear_log"):
                _LISTUP_STATE.update({"lines": [], "done": False, "return_code": None})
                st.rerun()

        if _LISTUP_STATE["lines"]:
            st.code("\n".join(_LISTUP_STATE["lines"][-200:]), language=None)
        elif _LISTUP_STATE["done"] and _LISTUP_STATE["return_code"] != 0:
            st.warning("サブプロセスの出力がありません。Renderログを確認してください。")

    _pending_path_check = os.path.join(OUTPUT_DIR, "pending_review.json")
    if os.path.exists(_pending_path_check) and not run_btn:
        st.divider()
        st.caption("前回の確認モード結果が残っています。")
        _show_pending_review_ui()

    st.divider()
    with st.expander("📞 架電記録（リストアップ中でも入力できます）", expanded=False):
        _lu_df_cl = _df_call_list
        if _lu_df_cl.empty:
            st.info("架電先リストが空です。リストアップ後に入力できます。")
        else:
            _lu_il_persons = ["全員"] + sorted(
                _lu_df_cl["架電担当者名"].dropna().replace("", pd.NA).dropna().unique().tolist()
            )
            _lu_il_person_filt = st.selectbox("架電担当者名で絞り込む", _lu_il_persons, key="lu_il_person_filt")
            if _lu_il_person_filt == "全員":
                _lu_company_opts = _lu_df_cl["会社名"].tolist()
            else:
                _lu_company_opts = _lu_df_cl[_lu_df_cl["架電担当者名"] == _lu_il_person_filt]["会社名"].tolist()

            if not _lu_company_opts:
                st.caption("該当する会社がありません。")
            else:
                _lu_selected = st.selectbox("会社を選択", _lu_company_opts, key="lu_il_company")
                _lu_row = _lu_df_cl[_lu_df_cl["会社名"] == _lu_selected].iloc[0]

                _lu_phone = _lu_row.get("電話番号", "") or "―"
                _lu_rank  = _lu_row.get("リストランク", "") or "―"
                st.info(f"📞 **{_lu_phone}**　ランク: {_lu_rank}　前回: {_lu_row.get('アプローチ内容','') or 'なし'}")

                _lu_c1, _lu_c2 = st.columns(2)
                with _lu_c1:
                    from datetime import date as _lu_date
                    _lu_ap_date = st.date_input("アプローチ日", value=_lu_date.today(), key="lu_il_apdate")
                    _lu_tanto = st.text_input(
                        "架電担当者名",
                        value=_lu_row.get("架電担当者名", ""),
                        key="lu_il_tanto",
                    )
                    _lu_apo = st.selectbox("アポ獲得", ["", "○", "×"], key="lu_il_apo")
                with _lu_c2:
                    _lu_result = st.selectbox(
                        "アプローチ内容（架電結果）",
                        options=_APPROACH_OPTIONS,
                        key="lu_il_result",
                    )
                    _lu_mikomi = st.selectbox("見込み", ["", "A", "B", "C", "D"], key="lu_il_mikomi")
                    _lu_memo = st.text_area("備考", height=80, key="lu_il_memo")
                _lu_next = st.date_input("次回アプローチ日（任意）", value=None, key="lu_il_next")

                if st.button("✅ 架電を記録する", type="primary", key="lu_il_submit"):
                    update_call_list_row(_lu_selected, {
                        "アプローチ日":    str(_lu_ap_date),
                        "架電担当者名":    _lu_tanto,
                        "アポ獲得":        _lu_apo,
                        "アプローチ内容":  _lu_result,
                        "見込み":          _lu_mikomi,
                        "アプローチ備考":  _lu_memo,
                        "次回アプローチ日": str(_lu_next) if _lu_next else "",
                    })
                    record_feedback(
                        company_name=_lu_selected,
                        approach_result=_lu_result,
                        got_appointment=_lu_apo in ("○", "〇"),
                        temperature=_lu_mikomi,
                        memo=_lu_memo,
                        tantosha=_lu_tanto,
                    )
                    if _lu_tanto:
                        with st.spinner(f"「{_lu_tanto}」のリスト残数を確認中..."):
                            _lu_added, _lu_err = _auto_refill_from_hubspot(_lu_tanto)
                        if _lu_err:
                            st.warning(f"記録しました。自動補充エラー: {_lu_err}")
                        elif _lu_added > 0:
                            st.info(f"🔄 「{_lu_tanto}」のリスト残数が少ないため {_lu_added}件を自動補充しました")
                        else:
                            st.success(f"記録しました: **{_lu_selected}** — {_lu_result}")
                    else:
                        st.success(f"記録しました: **{_lu_selected}** — {_lu_result}")

    st.divider()
    with st.expander("📡 媒体管理（S1/S2/S3 媒体リストの確認・追加）", expanded=False):
        _mm_merged = _get_merged_media_list()

        # ── 現在の媒体一覧 ──────────────────────
        st.markdown("#### 現在の媒体一覧")
        for _mm_type, _mm_label in _MEDIA_TYPE_LABELS.items():
            _mm_entries = _mm_merged[_mm_type]
            st.markdown(f"**{_mm_label}**　{len(_mm_entries)}件")
            if _mm_entries:
                for _mm_e in _mm_entries:
                    _mm_badge = "🔒" if _mm_e.get("source") == "default" else "✏️"
                    _mm_name  = _mm_e.get("name", "（名称なし）")
                    _mm_url   = _mm_e.get("url", "")
                    st.caption(f"{_mm_badge} {_mm_name}　{_mm_url}")
            else:
                st.caption("（登録なし）")

        st.divider()

        # ── 媒体追加フォーム ─────────────────────
        st.markdown("#### 媒体を追加")
        _mm_col1, _mm_col2 = st.columns([3, 1])
        with _mm_col1:
            _mm_new_name = st.text_input(
                "媒体名",
                placeholder="例: 健康経営の広場",
                key="mm_new_name",
            )
            _mm_new_url = st.text_input(
                "URL",
                placeholder="例: https://kenkoukeiei-media.com/",
                key="mm_new_url",
            )
        with _mm_col2:
            _mm_new_type = st.selectbox(
                "タイプ",
                options=list(_MEDIA_TYPE_LABELS.values()),
                key="mm_new_type",
            )
            st.write("")
            st.write("")
            _mm_add_btn = st.button("➕ 追加", key="mm_add_btn", use_container_width=True)

        if _mm_add_btn:
            if not _mm_new_name or not _mm_new_url:
                st.error("媒体名と URL の両方を入力してください。")
            else:
                # "S1（PR有料媒体）" → "S1" を取り出す
                _mm_type_key = _mm_new_type[:2]
                _mm_cfg = _load_media_config()
                _mm_cfg.setdefault(_mm_type_key, [])
                # 同一 URL の重複登録を防止
                _mm_existing_urls = [e.get("url", "") for e in _mm_cfg[_mm_type_key]]
                if _mm_new_url in _mm_existing_urls:
                    st.warning(f"このURLはすでに {_mm_type_key} に登録されています。")
                else:
                    _mm_cfg[_mm_type_key].append({"name": _mm_new_name, "url": _mm_new_url})
                    _save_media_config(_mm_cfg)
                    st.success(f"追加しました: {_mm_new_name}（{_mm_type_key}）")
                    st.rerun()


# ──────────────────────────────
# TAB: システム診断
# ──────────────────────────────
with tab_monitor:
    st.subheader("システム診断")
    # ── チームメンバー設定 ──────────────────────────────────────────
    st.divider()
    st.markdown("#### チームメンバー設定（架電担当者の自動割り振り）")
    st.caption("登録したメンバーに、HubSpot自動補充の新規リストをラウンドロビンで割り当てます。未登録の場合はトリガーした担当者に全件割り当てられます。")

    _tm_current = _load_team_members()

    if _tm_current:
        st.markdown("**登録済みメンバー：**")
        for _tm_name in _tm_current:
            _tm_col_name, _tm_col_del = st.columns([4, 1])
            with _tm_col_name:
                st.markdown(f"・{_tm_name}")
            with _tm_col_del:
                if st.button("削除", key=f"tm_del_{_tm_name}"):
                    _tm_new = [n for n in _tm_current if n != _tm_name]
                    _save_team_members(_tm_new)
                    st.rerun()
    else:
        st.caption("メンバーが登録されていません。")

    _tm_add_col, _tm_btn_col = st.columns([3, 1])
    with _tm_add_col:
        _tm_new_name = st.text_input("メンバー名を追加", placeholder="例: 野村", key="tm_new_name")
    with _tm_btn_col:
        st.markdown("　")
        if st.button("追加", type="primary", key="tm_add_btn"):
            _tm_new_name_stripped = _tm_new_name.strip()
            if _tm_new_name_stripped and _tm_new_name_stripped not in _tm_current:
                _save_team_members(_tm_current + [_tm_new_name_stripped])
                st.success(f"「{_tm_new_name_stripped}」を追加しました。")
                st.rerun()
            elif _tm_new_name_stripped in _tm_current:
                st.warning("すでに登録されています。")
            else:
                st.warning("名前を入力してください。")

    # ── 自動補充リスト設定 ──────────────────────────────────────────
    st.divider()
    st.markdown("#### 自動補充リスト設定")
    st.caption("架電担当者のリスト残数が50件を切ったとき、どのHubSpotリストから補充するかを設定します。未設定の場合はHubSpot全企業が対象になります。")

    from config import HUBSPOT_TOKEN as _MON_HS_TOKEN
    if not _MON_HS_TOKEN:
        st.info("💡 HubSpot連携には環境変数 `HUBSPOT_TOKEN` の設定が必要です。")
    else:
        _cur_refill = _load_import_settings("auto_refill_list")
        _cur_list_id = _cur_refill.get("list_id", "")
        _cur_list_name = _cur_refill.get("list_name", "")

        if "mon_hs_lists_cache" not in st.session_state:
            import requests as _mon_req
            _mon_h = {"Authorization": f"Bearer {_MON_HS_TOKEN}", "Content-Type": "application/json"}
            try:
                _mon_lr = _mon_req.post(
                    "https://api.hubapi.com/crm/v3/lists/search",
                    headers=_mon_h,
                    json={"objectTypeId": "0-2", "processingTypes": ["DYNAMIC", "MANUAL", "SNAPSHOT"], "count": 200, "offset": 0},
                    timeout=15,
                )
                if _mon_lr.ok:
                    _mon_raw = _mon_lr.json().get("lists") or _mon_lr.json().get("results", [])
                    st.session_state["mon_hs_lists_cache"] = [
                        {"listId": str(l.get("listId") or l.get("id") or ""), "name": l.get("name") or ""}
                        for l in _mon_raw if (l.get("name") and (l.get("listId") or l.get("id")))
                    ]
                else:
                    st.session_state["mon_hs_lists_cache"] = []
            except Exception:
                st.session_state["mon_hs_lists_cache"] = []

        _mon_lists = st.session_state.get("mon_hs_lists_cache", [])
        _mon_options = ["全企業（指定なし）"] + [f"{l['name']}  [{l['listId']}]" for l in _mon_lists]

        _mon_default_idx = 0
        if _cur_list_id:
            for _i, _opt in enumerate(_mon_options):
                if f"[{_cur_list_id}]" in _opt:
                    _mon_default_idx = _i
                    break

        _mon_col1, _mon_col2 = st.columns([3, 1])
        with _mon_col1:
            _mon_selected = st.selectbox(
                "補充元リスト",
                options=_mon_options,
                index=_mon_default_idx,
                key="mon_refill_list_select",
            )
        with _mon_col2:
            st.markdown("　")
            if st.button("🔄 リスト更新", key="mon_refresh_lists", width="stretch"):
                del st.session_state["mon_hs_lists_cache"]
                st.rerun()

        if _cur_list_id:
            st.caption(f"現在の設定: **{_cur_list_name}** （ID: {_cur_list_id}）")
        else:
            st.caption("現在の設定: **全企業（指定なし）**")

        if st.button("💾 設定を保存", type="primary", key="mon_save_refill_list"):
            if _mon_selected == "全企業（指定なし）":
                _save_import_settings("auto_refill_list", {"list_id": "", "list_name": ""})
                st.success("設定を保存しました（全企業モード）")
            elif "[" in _mon_selected:
                _save_lid = _mon_selected.split("[")[-1].rstrip("]").strip()
                _save_lname = _mon_selected.split("  [")[0].strip()
                _save_import_settings("auto_refill_list", {"list_id": _save_lid, "list_name": _save_lname})
                st.success(f"設定を保存しました → **{_save_lname}** から補充します")
            st.rerun()


# ──────────────────────────────
# TAB: 利用者フィードバック
# ──────────────────────────────
with tab_user_fb:
    st.subheader("利用者フィードバック")
    st.caption("ツールへの要望・バグ報告・改善提案などを自由にメモしてください。")

    _UF_COLS = ["日付", "投稿者", "カテゴリ", "内容", "ステータス"]
    _UF_CATEGORIES = ["機能要望", "バグ報告", "改善提案", "使い方質問", "その他"]
    _UF_STATUSES   = ["未対応", "確認中", "対応済み"]

    def _load_user_feedback() -> pd.DataFrame:
        if os.path.exists(USER_FEEDBACK_FILE):
            try:
                df = pd.read_csv(USER_FEEDBACK_FILE, encoding="utf-8-sig", dtype=str).fillna("")
                for c in _UF_COLS:
                    if c not in df.columns:
                        df[c] = ""
                return df[_UF_COLS]
            except Exception:
                pass
        return pd.DataFrame(columns=_UF_COLS)

    def _save_user_feedback(df: pd.DataFrame) -> None:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        df.to_csv(USER_FEEDBACK_FILE, index=False, encoding="utf-8-sig")

    _uf_df = _load_user_feedback()

    with st.expander("＋ 新しいフィードバックを投稿", expanded=_uf_df.empty):
        from datetime import date as _uf_date
        _uf_c1, _uf_c2 = st.columns(2)
        with _uf_c1:
            _uf_author   = st.text_input("投稿者名", placeholder="例: 野村", key="uf_author")
            _uf_category = st.selectbox("カテゴリ", _UF_CATEGORIES, key="uf_category")
        with _uf_c2:
            _uf_content = st.text_area("内容", placeholder="例: 〇〇タブで△△すると…", height=100, key="uf_content")

        if st.button("投稿する", type="primary", key="uf_submit"):
            if not _uf_content.strip():
                st.warning("内容を入力してください。")
            else:
                _new_row = pd.DataFrame([{
                    "日付":     str(_uf_date.today()),
                    "投稿者":   _uf_author.strip(),
                    "カテゴリ": _uf_category,
                    "内容":     _uf_content.strip(),
                    "ステータス": "未対応",
                }])
                _uf_df = pd.concat([_new_row, _uf_df], ignore_index=True)
                _save_user_feedback(_uf_df)
                st.success("投稿しました。")
                st.rerun()

    if _uf_df.empty:
        st.info("フィードバックはまだありません。上のフォームから投稿してください。")
    else:
        st.caption("ステータスはここで直接変更できます。変更後「保存」を押してください。")
        _uf_edited = st.data_editor(
            _uf_df,
            width="stretch",
            hide_index=True,
            num_rows="dynamic",
            column_config={
                "日付":     st.column_config.TextColumn("日付",     width="small"),
                "投稿者":   st.column_config.TextColumn("投稿者",   width="small"),
                "カテゴリ": st.column_config.SelectboxColumn("カテゴリ", options=_UF_CATEGORIES, width="medium"),
                "内容":     st.column_config.TextColumn("内容",     width="large"),
                "ステータス": st.column_config.SelectboxColumn("ステータス", options=_UF_STATUSES, width="small"),
            },
            key="uf_editor",
        )
        if st.button("💾 変更を保存", key="uf_save"):
            _save_user_feedback(_uf_edited)
            st.success("保存しました。")
            st.rerun()
