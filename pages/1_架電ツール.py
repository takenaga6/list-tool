"""
架電ツール — Offi-Stretch
タブ: 架電先リスト / 見込みリスト / 確認待ち / 履歴 / 商談一覧
"""

import os
import io as _io_mod
import pandas as pd
import altair as alt
import streamlit as st

from config import (
    FEEDBACK_FILE, RESULTS_FILE, MEETINGS_FILE,
    CALL_LIST_FILE, IMPORT_SETTINGS_FILE, OUTPUT_DIR,
    record_feedback,
)
from call_tool_utils import (
    apply_global_styles,
    _CALL_LIST_COLS, _CALL_LIST_STATIC_COLS, _CALL_LIST_ACTIVITY_COLS,
    _HS_PROP_MAP, _APPROACH_OPTIONS, _MEETING_COLS,
    load_feedback, load_call_list, update_call_list_row,
    load_meetings, _save_meeting_row,
    _auto_refill_from_hubspot,
    _hubspot_push_call_note, _hubspot_push_deal,
    _load_import_settings, _save_import_settings,
    _load_team_members, _save_team_members,
    _read_file_to_df,
    _show_pending_review_ui,
    _render_gsheets_loader,
)

# ──────────────────────────────
# ページ設定
# ──────────────────────────────
st.set_page_config(
    page_title="架電ツール — Offi-Stretch",
    page_icon="📞",
    layout="wide",
)

apply_global_styles("架電ツール")

# 架電先リストをページロード時に1回だけ読み込む
_df_call_list = load_call_list()

# ──────────────────────────────
# タブ定義
# ──────────────────────────────
tab_calllist, tab_kaiden_zumi, tab_pending, tab_history, tab_meeting = st.tabs(
    ["架電先リスト", "見込みリスト", "確認待ち", "履歴", "商談一覧"]
)


# ──────────────────────────────
# TAB: 架電先リスト
# ──────────────────────────────
with tab_calllist:
    st.subheader("架電先リスト")
    st.caption("会社情報（電話番号・代表者）を見ながら、このツールだけで架電記録を完結できます。")

    cl_view, cl_import, cl_inline = st.tabs(["📋 リスト表示", "📥 インポート", "📞 インライン架電記録"])

    # ── リスト表示 ─────────────────────────────────────────────────
    with cl_view:
        # 自動保存（常時ON・30分ごと）
        from streamlit_autorefresh import st_autorefresh
        from datetime import datetime as _dt
        _refresh_count = st_autorefresh(interval=30 * 60 * 1000, key="cl_autorefresh")
        if _refresh_count != st.session_state.get("_last_refresh_count", 0):
            st.session_state["_last_refresh_count"] = _refresh_count
            st.session_state["_trigger_autosave"] = True
        _last_save_ts = st.session_state.get("last_autosave_ts")
        if _last_save_ts:
            st.caption(f"最終自動保存: {_last_save_ts}")

        df_clist = _df_call_list.copy()
        df_fb_join = load_feedback()

        if df_clist.empty:
            st.info("架電先リストがありません。「インポート」タブからリストを登録してください。")
        else:
            # フィルター
            clf1, clf2, clf3, clf4 = st.columns(4)
            with clf1:
                cl_persons = ["全員"] + sorted(df_clist["架電担当者名"].dropna().replace("", pd.NA).dropna().unique().tolist())
                cl_filt_person = st.selectbox("架電担当者名で絞り込み", cl_persons, key="cl_filt_person")
            with clf2:
                cl_filt_mikomi = st.selectbox("見込みで絞り込み", ["全て", "A", "B", "C", "なし"], key="cl_filt_mikomi")
            with clf3:
                cl_filt_apo = st.selectbox("アポ獲得", ["全て", "獲得済み", "未獲得"], key="cl_filt_apo")
            with clf4:
                cl_filt_search = st.text_input("会社名で検索", key="cl_filt_search")

            filtered_cl = df_clist.copy()
            if cl_filt_person != "全員":
                filtered_cl = filtered_cl[filtered_cl["架電担当者名"] == cl_filt_person]
            if cl_filt_mikomi != "全て":
                if cl_filt_mikomi == "なし":
                    filtered_cl = filtered_cl[filtered_cl["見込み"].replace("", pd.NA).isna()]
                else:
                    filtered_cl = filtered_cl[filtered_cl["見込み"] == cl_filt_mikomi]
            if cl_filt_apo != "全て":
                if cl_filt_apo == "獲得済み":
                    filtered_cl = filtered_cl[filtered_cl["アポ獲得"].str.strip().isin(["○", "〇", "済", "1", "true", "True", "アポ"])]
                else:
                    filtered_cl = filtered_cl[~filtered_cl["アポ獲得"].str.strip().isin(["○", "〇", "済", "1", "true", "True", "アポ"])]
            if cl_filt_search:
                filtered_cl = filtered_cl[filtered_cl["会社名"].str.contains(cl_filt_search, na=False)]

            uncalled = (filtered_cl["アプローチ日"].replace("", pd.NA).isna().sum())
            st.caption(f"表示: {len(filtered_cl)}件 / 未架電（アプローチ日なし）: {uncalled}件")

            # 表示列: 重要度順（hs_idは非表示）
            show_cols = [c for c in [
                "会社名", "電話番号", "代表者", "アプローチ日", "架電担当者名", "パスアポ者名",
                "アポ獲得", "アプローチ内容", "見込み", "次回アプローチ日", "アプローチ備考",
                "HPリンク", "業種", "従業員数", "地域", "リストランク", "リストアップ担当者", "条件NG",
            ] if c in filtered_cl.columns]

            _display_cl = filtered_cl[show_cols].copy()
            for _bc in ["アポ獲得", "条件NG"]:
                if _bc in _display_cl.columns:
                    _display_cl[_bc] = _display_cl[_bc].isin(["○", "〇", "1", "true", "True"])

            _editable_cols = {
                "架電担当者名", "パスアポ者名", "アポ獲得", "アプローチ内容",
                "見込み", "次回アプローチ日", "アプローチ日", "アプローチ備考", "条件NG",
            }
            _column_config = {
                col: st.column_config.TextColumn(col, disabled=(col not in _editable_cols))
                for col in show_cols
            }
            _column_config["見込み"] = st.column_config.SelectboxColumn(
                "見込み", options=["", "A", "B", "C"], disabled=False)
            _column_config["アポ獲得"] = st.column_config.CheckboxColumn("アポ獲得", disabled=False)
            _column_config["条件NG"]   = st.column_config.CheckboxColumn("条件NG",   disabled=False)
            _column_config["アプローチ内容"] = st.column_config.SelectboxColumn(
                "アプローチ内容", options=_APPROACH_OPTIONS, disabled=False)
            if "アプローチ備考" in show_cols:
                _column_config["アプローチ備考"] = st.column_config.TextColumn("アプローチ備考", disabled=False)

            edited_cl = st.data_editor(
                _display_cl,
                width="stretch",
                hide_index=True,
                column_config=_column_config,
                key="cl_data_editor",
                num_rows="fixed",
            )

            # 保存ボタン（変更検知）
            _has_changes = not edited_cl.equals(_display_cl)
            _sv_col, _ = st.columns([1, 3])
            with _sv_col:
                _save_btn = st.button("💾 HubSpotに保存", type="primary", key="cl_save_hs",
                                      disabled=not _has_changes)

            if _save_btn and _has_changes:
                _save_df = edited_cl.copy()
                for _bc in ["アポ獲得", "条件NG"]:
                    if _bc in _save_df.columns:
                        _save_df[_bc] = _save_df[_bc].apply(lambda v: "○" if v is True else "")

                df_clist_updated = df_clist.copy()
                for i, orig_idx in enumerate(filtered_cl.index):
                    for col in _editable_cols:
                        if col in show_cols and col in _save_df.columns:
                            df_clist_updated.at[orig_idx, col] = _save_df.iloc[i][col]
                df_clist_updated.to_csv(CALL_LIST_FILE, index=False, encoding="utf-8-sig")

                from config import HUBSPOT_TOKEN as _HS_TOKEN
                _hs_id_col_exists = "hs_id" in df_clist_updated.columns
                if _HS_TOKEN and _hs_id_col_exists:
                    import requests as _req
                    _hs_headers = {
                        "Authorization": f"Bearer {_HS_TOKEN}",
                        "Content-Type": "application/json",
                    }
                    _hs_ok = 0
                    _hs_errors = 0
                    with st.spinner("HubSpotに保存中..."):
                        for i, orig_idx in enumerate(filtered_cl.index):
                            _hs_id = df_clist_updated.at[orig_idx, "hs_id"]
                            if not _hs_id:
                                continue
                            _props = {}
                            for jp_col, hs_prop in _HS_PROP_MAP.items():
                                if jp_col in show_cols and jp_col in _save_df.columns:
                                    _props[hs_prop] = str(_save_df.iloc[i][jp_col])
                            if not _props:
                                continue
                            try:
                                _r = _req.patch(
                                    f"https://api.hubapi.com/crm/v3/objects/companies/{_hs_id}",
                                    headers=_hs_headers,
                                    json={"properties": _props},
                                    timeout=10,
                                )
                                if _r.ok:
                                    _hs_ok += 1
                                else:
                                    _hs_errors += 1
                            except Exception:
                                _hs_errors += 1
                    if _hs_errors == 0:
                        st.success(f"保存しました（HubSpot {_hs_ok}件反映）")
                    else:
                        st.warning(f"保存しました（HubSpot {_hs_ok}件反映、{_hs_errors}件エラー）")
                else:
                    st.success("CSVに保存しました")

                _saved_tantos = (
                    _save_df["架電担当者名"].dropna().replace("", pd.NA).dropna().unique().tolist()
                    if "架電担当者名" in _save_df.columns else []
                )
                for _st_name in _saved_tantos:
                    with st.spinner(f"「{_st_name}」のリスト残数を確認中..."):
                        _st_added, _st_err = _auto_refill_from_hubspot(_st_name)
                    if _st_err:
                        st.warning(f"自動補充エラー（{_st_name}）: {_st_err}")
                    elif _st_added > 0:
                        st.info(f"🔄 「{_st_name}」のリスト残数が少ないため {_st_added}件を自動補充しました（A/B/C均等）")
                st.rerun()

            # 自動保存トリガー
            if st.session_state.pop("_trigger_autosave", False):
                _auto_save_df = edited_cl.copy()
                for _bc in ["アポ獲得", "条件NG"]:
                    if _bc in _auto_save_df.columns:
                        _auto_save_df[_bc] = _auto_save_df[_bc].apply(lambda v: "○" if v is True else "")
                _auto_updated = df_clist.copy()
                for i, orig_idx in enumerate(filtered_cl.index):
                    for col in _editable_cols:
                        if col in show_cols and col in _auto_save_df.columns:
                            _auto_updated.at[orig_idx, col] = _auto_save_df.iloc[i][col]
                _auto_updated.to_csv(CALL_LIST_FILE, index=False, encoding="utf-8-sig")
                from config import HUBSPOT_TOKEN as _AS_TOKEN
                if _AS_TOKEN and "hs_id" in _auto_updated.columns:
                    import requests as _ar
                    _ah = {"Authorization": f"Bearer {_AS_TOKEN}", "Content-Type": "application/json"}
                    for i, orig_idx in enumerate(filtered_cl.index):
                        _aid = _auto_updated.at[orig_idx, "hs_id"]
                        if not _aid:
                            continue
                        _ap = {hs_prop: str(_auto_save_df.iloc[i][jp_col])
                               for jp_col, hs_prop in _HS_PROP_MAP.items()
                               if jp_col in show_cols and jp_col in _auto_save_df.columns}
                        if _ap:
                            try:
                                _ar.patch(f"https://api.hubapi.com/crm/v3/objects/companies/{_aid}",
                                          headers=_ah, json={"properties": _ap}, timeout=10)
                            except Exception:
                                pass
                st.session_state["last_autosave_ts"] = _dt.now().strftime("%H:%M")
                st.session_state.pop("cl_data_editor", None)
                st.toast(f"自動保存しました（{st.session_state['last_autosave_ts']}）")
                st.rerun()

            csv_cl = filtered_cl[show_cols].to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button("📥 CSVダウンロード", data=csv_cl, file_name="call_list_export.csv", mime="text/csv", key="cl_dl")

    # ── インポート ─────────────────────────────────────────────────
    with cl_import:
        cl_saved = _load_import_settings("calllist")

        from config import HUBSPOT_TOKEN
        if HUBSPOT_TOKEN:
            st.markdown("### 🔗 HubSpotから読み込む（推奨）")
            st.caption("リストアップで登録した企業を自動取得します。新規登録分も随時反映できます。")

            def _fetch_hs_lists():
                import requests as _req2
                _hs_h2 = {"Authorization": f"Bearer {HUBSPOT_TOKEN}", "Content-Type": "application/json"}
                _lr = _req2.post(
                    "https://api.hubapi.com/crm/v3/lists/search",
                    headers=_hs_h2,
                    json={
                        "objectTypeId": "0-2",
                        "processingTypes": ["DYNAMIC", "MANUAL", "SNAPSHOT"],
                        "count": 200,
                        "offset": 0,
                    },
                    timeout=15,
                )
                if not _lr.ok:
                    return None, f"HTTP {_lr.status_code}: {_lr.text[:200]}"
                _resp_json = _lr.json()
                _raw_lists = _resp_json.get("lists") or _resp_json.get("results", [])
                _parsed = []
                for l in _raw_lists:
                    _lid = str(l.get("listId") or l.get("hs_list_id") or l.get("id") or "")
                    _lname = l.get("name") or l.get("listName") or ""
                    if _lname and _lid:
                        _parsed.append({"listId": _lid, "name": _lname})
                return _parsed, None

            if "hs_lists_cache" not in st.session_state:
                with st.spinner("HubSpotリスト一覧を取得中..."):
                    _auto_lists, _auto_err = _fetch_hs_lists()
                if _auto_err:
                    st.warning(f"リスト自動取得に失敗しました: {_auto_err}")
                    st.session_state["hs_lists_cache"] = []
                else:
                    st.session_state["hs_lists_cache"] = _auto_lists or []

            hs_list_col1, hs_list_col2 = st.columns([3, 1])
            with hs_list_col1:
                hs_list_label = st.selectbox(
                    "取得対象（HubSpotリスト）",
                    options=["（指定なし：全企業）"] + [
                        f"{l['name']}  [{l['listId']}]"
                        for l in st.session_state.get("hs_lists_cache", [])
                    ],
                    key="hs_list_select",
                )
            with hs_list_col2:
                st.markdown("　")
                _load_lists_btn = st.button("🔄 更新", key="hs_load_lists", width="stretch")

            if _load_lists_btn:
                with st.spinner("取得中..."):
                    _manual_lists, _manual_err = _fetch_hs_lists()
                if _manual_err:
                    st.error(f"リスト取得エラー: {_manual_err}")
                elif _manual_lists is not None:
                    st.session_state["hs_lists_cache"] = _manual_lists
                    st.success(f"リスト {len(_manual_lists)}件 取得しました")
                    st.rerun()

            hs_col1, hs_col2 = st.columns([2, 1])
            with hs_col1:
                hs_max = st.number_input("最大取得件数", min_value=50, max_value=2000, value=500, step=50, key="hs_max")
                hs_overwrite = st.radio("取り込みモード", ["追加（既存に追加）", "上書き（全て置き換え）"], horizontal=True, key="hs_overwrite")
            with hs_col2:
                st.markdown("　")
                hs_btn = st.button("📥 HubSpotから取得", type="primary", key="hs_fetch_btn", width="stretch")

            _selected_list_id = None
            _hs_list_label_val = st.session_state.get("hs_list_select", "")
            if _hs_list_label_val and "[" in _hs_list_label_val:
                _selected_list_id = _hs_list_label_val.split("[")[-1].rstrip("]").strip()

            if hs_btn:
                import requests as _req
                _hs_headers = {
                    "Authorization": f"Bearer {HUBSPOT_TOKEN}",
                    "Content-Type": "application/json",
                }
                _hs_companies = []
                _hs_after = None
                _hs_base = "https://api.hubapi.com"

                _HS_PROPS = (
                    "name,phone,website,state,city,industry,numberofemployees,zip,"
                    "kaiden_tanto,pass_apo,apo_acquired,approach_content,"
                    "prospect_rank,approach_date,next_approach_date,approach_memo,joken_ng"
                )

                with st.spinner("HubSpotから企業情報を取得中..."):
                    try:
                        if _selected_list_id:
                            _member_ids = []
                            _list_after = None
                            while len(_member_ids) < hs_max:
                                _lm_params = {"limit": min(250, hs_max - len(_member_ids))}
                                if _list_after:
                                    _lm_params["after"] = _list_after
                                _lm_resp = _req.get(
                                    f"{_hs_base}/crm/v3/lists/{_selected_list_id}/memberships/join-order",
                                    headers=_hs_headers,
                                    params=_lm_params,
                                    timeout=15,
                                )
                                if not _lm_resp.ok:
                                    st.error(f"リストメンバー取得エラー: {_lm_resp.status_code}")
                                    break
                                _lm_data = _lm_resp.json()
                                _member_ids += [r["recordId"] for r in _lm_data.get("results", [])]
                                _list_after = _lm_data.get("paging", {}).get("next", {}).get("after")
                                if not _list_after:
                                    break
                            for _bi in range(0, len(_member_ids), 100):
                                _batch_ids = _member_ids[_bi:_bi+100]
                                _br = _req.post(
                                    f"{_hs_base}/crm/v3/objects/companies/batch/read",
                                    headers=_hs_headers,
                                    json={
                                        "inputs": [{"id": i} for i in _batch_ids],
                                        "properties": _HS_PROPS.split(","),
                                    },
                                    timeout=20,
                                )
                                if _br.ok:
                                    _hs_companies.extend(_br.json().get("results", []))
                                else:
                                    st.warning(f"バッチ取得エラー: {_br.status_code}")
                        else:
                            while len(_hs_companies) < hs_max:
                                _hs_params = {
                                    "limit": min(100, hs_max - len(_hs_companies)),
                                    "properties": _HS_PROPS,
                                }
                                if _hs_after:
                                    _hs_params["after"] = _hs_after
                                _hs_resp = _req.get(
                                    f"{_hs_base}/crm/v3/objects/companies",
                                    headers=_hs_headers,
                                    params=_hs_params,
                                    timeout=15,
                                )
                                if not _hs_resp.ok:
                                    st.error(f"HubSpot APIエラー: {_hs_resp.status_code} — {_hs_resp.text[:200]}")
                                    break
                                _hs_data = _hs_resp.json()
                                _hs_companies.extend(_hs_data.get("results", []))
                                _hs_paging = _hs_data.get("paging", {}).get("next", {})
                                _hs_after = _hs_paging.get("after")
                                if not _hs_after:
                                    break

                        if _hs_companies:
                            _hs_rows = []
                            for _c in _hs_companies:
                                _p = _c.get("properties", {})
                                _name = (_p.get("name") or "").strip()
                                if not _name:
                                    continue
                                _hs_rows.append({
                                    "hs_id":            _c.get("id", ""),
                                    "会社名":           _name,
                                    "電話番号":         (_p.get("phone") or "").strip(),
                                    "代表者":           "",
                                    "HPリンク":         (_p.get("website") or "").strip(),
                                    "説明リンク":        "",
                                    "地域":             (_p.get("state") or _p.get("city") or "").strip(),
                                    "業種":             (_p.get("industry") or "").strip(),
                                    "従業員数":         (_p.get("numberofemployees") or "").strip(),
                                    "リストランク":      "",
                                    "リストアップ担当者": "",
                                    "条件NG":           "○" if (_p.get("joken_ng") or "").lower() in ("true", "1", "yes") else "",
                                    "リストアップ更新日": "",
                                    "架電担当者名":     (_p.get("kaiden_tanto") or "").strip(),
                                    "パスアポ者名":     (_p.get("pass_apo") or "").strip(),
                                    "アポ獲得":         "○" if (_p.get("apo_acquired") or "").lower() in ("true", "1", "yes", "○") else "",
                                    "アプローチ内容":   (_p.get("approach_content") or "").strip(),
                                    "見込み":           (_p.get("prospect_rank") or "").strip(),
                                    "アプローチ日":     (_p.get("approach_date") or "").strip(),
                                    "次回アプローチ日": (_p.get("next_approach_date") or "").strip(),
                                    "アプローチ備考":   (_p.get("approach_memo") or "").strip(),
                                })

                            _hs_df = pd.DataFrame(_hs_rows)
                            st.success(f"✅ {len(_hs_df)}件取得しました")
                            st.dataframe(_hs_df.head(5), width="stretch", hide_index=True)

                            os.makedirs(OUTPUT_DIR, exist_ok=True)
                            if hs_overwrite.startswith("追加"):
                                _existing_cl = _df_call_list
                                if not _existing_cl.empty:
                                    _existing_names = set(_existing_cl["会社名"].tolist())
                                    _hs_df = _hs_df[~_hs_df["会社名"].isin(_existing_names)]
                                _mode = "a"
                                _header = not os.path.exists(CALL_LIST_FILE) or os.path.getsize(CALL_LIST_FILE) == 0
                            else:
                                _mode = "w"
                                _header = True

                            _hs_df.to_csv(CALL_LIST_FILE, mode=_mode, index=False, encoding="utf-8-sig", header=_header)
                            st.success(f"架電先リストに{len(_hs_df)}件を保存しました。「リスト表示」タブで確認できます。")
                            st.rerun()
                        else:
                            st.warning("取得できた企業が0件でした。HubSpotに企業が登録されているか確認してください。")
                    except Exception as _e:
                        st.error(f"取得エラー: {_e}")

            st.divider()
        else:
            st.info("💡 HubSpot連携を使うには、環境変数 `HUBSPOT_TOKEN` を設定してください。設定後はHubSpotから直接取得できます。")
            st.divider()

        st.markdown("### 📁 ファイルから読み込む")
        cl_src_mode = st.radio(
            "ファイルの指定方法",
            ["📂 パスを直接入力", "⬆️ アップロード", "🔗 Googleスプレッドシート"],
            horizontal=True,
            key="cl_src_mode",
        )

        cl_df_raw = None
        cl_filepath_val = ""

        if cl_src_mode.startswith("📂"):
            cl_filepath_val = st.text_input(
                "ファイルパス（CSV または .xlsx）",
                value=cl_saved.get("filepath", ""),
                placeholder=r"C:\Users\user\Desktop\アプローチリスト.xlsx",
                key="cl_filepath",
            )
            if cl_filepath_val and os.path.exists(cl_filepath_val):
                cl_df_raw = _read_file_to_df(cl_filepath_val)
                if cl_df_raw is None:
                    st.error("ファイルを読み込めませんでした。")
            elif cl_filepath_val:
                st.warning("ファイルが見つかりません。パスを確認してください。")
        elif cl_src_mode.startswith("⬆️"):
            cl_uploaded = st.file_uploader("CSV / Excel を選択", type=["csv", "xlsx", "xls"], key="cl_upload")
            if cl_uploaded:
                ext = os.path.splitext(cl_uploaded.name)[1].lower()
                if ext in (".xlsx", ".xls"):
                    cl_df_raw = pd.read_excel(cl_uploaded, dtype=str).fillna("")
                else:
                    raw_cl = cl_uploaded.read()
                    for enc in ("utf-8-sig", "shift-jis", "cp932", "utf-8"):
                        try:
                            cl_df_raw = pd.read_csv(_io_mod.StringIO(raw_cl.decode(enc)), dtype=str).fillna("")
                            break
                        except Exception:
                            pass
                cl_filepath_val = cl_uploaded.name
        else:
            cl_df_raw = _render_gsheets_loader("calllist_gs", cl_saved)

        if cl_df_raw is not None:
            st.markdown(f"**読み込み: {len(cl_df_raw)}行 / {len(cl_df_raw.columns)}列**")
            st.dataframe(cl_df_raw.head(3), width="stretch", hide_index=True)

            st.markdown("### 列マッピング")
            cl_all_cols = ["（使わない）"] + cl_df_raw.columns.tolist()
            cl_map_saved = cl_saved.get("mapping", {})

            def cl_pick(label, keywords):
                saved_val = cl_map_saved.get(label)
                if saved_val and saved_val in cl_all_cols:
                    default = saved_val
                else:
                    default = next((col for kw in keywords for col in cl_df_raw.columns if kw in col), "（使わない）")
                return st.selectbox(label, cl_all_cols, index=cl_all_cols.index(default), key=f"clmap_{label}")

            st.markdown("**会社情報（静的）**")
            clc1, clc2, clc3 = st.columns(3)
            with clc1:
                cl_c_company   = cl_pick("会社名",           ["会社名"])
                cl_c_phone     = cl_pick("電話番号",         ["電話番号", "電話", "TEL", "tel"])
                cl_c_daihyo    = cl_pick("代表者",           ["代表者", "代表", "社長"])
                cl_c_hp        = cl_pick("HPリンク",         ["HP", "URL", "url", "ホームページ"])
            with clc2:
                cl_c_desc      = cl_pick("説明リンク",        ["説明リンク", "説明", "資料"])
                cl_c_rank      = cl_pick("リストランク",      ["ランク", "rank"])
                cl_c_region    = cl_pick("地域",             ["地域", "都道府県", "prefecture"])
                cl_c_industry  = cl_pick("業種",             ["業種", "industry"])
            with clc3:
                cl_c_employee  = cl_pick("従業員数",         ["従業員数", "従業員", "employee"])
                cl_c_listowner = cl_pick("リストアップ担当者", ["リストアップ担当者", "リストアップ", "担当名", "担当者"])
                cl_c_condng    = cl_pick("条件NG",           ["条件NG", "条件", "NG"])
                cl_c_listdate  = cl_pick("リストアップ更新日", ["リストアップ更新日", "更新日", "登録日"])

            st.markdown("**架電活動記録（既存スプレッドシートから移行する場合に設定）**")
            st.caption("スプレッドシートで架電していた場合、架電記録列もここでマッピングすると履歴ごと移行できます。")
            clact1, clact2, clact3 = st.columns(3)
            with clact1:
                cl_c_apdate    = cl_pick("アプローチ日",    ["アプローチ日", "架電日", "日付"])
                cl_c_tanto_call = cl_pick("架電担当者名",   ["架電担当者名", "架電担当", "担当名"])
            with clact2:
                cl_c_pasapo    = cl_pick("パスアポ者名",    ["パスアポ者名", "パスアポ", "アポ担当"])
                cl_c_apo       = cl_pick("アポ獲得",        ["アポ獲得", "アポ"])
                cl_c_content   = cl_pick("アプローチ内容",  ["アプローチ内容", "架電結果", "結果"])
            with clact3:
                cl_c_mikomi    = cl_pick("見込み",          ["見込み", "温度感"])
                cl_c_apbiko    = cl_pick("アプローチ備考",  ["アプローチ備考", "備考", "メモ"])
                cl_c_nextdate  = cl_pick("次回アプローチ日", ["次回アプローチ日", "次回架電日", "次回"])

            cl_overwrite = st.radio("インポートモード", ["追加（既存データに追加）", "上書き（全て置き換え）"], horizontal=True, key="cl_import_mode")

            if st.button("✅ 架電先リストに取り込む", type="primary", key="cl_import_btn"):
                os.makedirs(OUTPUT_DIR, exist_ok=True)

                def _cl_v(row, col):
                    return str(row.get(col, "")).strip() if col != "（使わない）" else ""

                new_cl_rows = []
                for _, row in cl_df_raw.iterrows():
                    company = _cl_v(row, cl_c_company)
                    if not company:
                        continue
                    new_cl_rows.append({
                        "会社名":           company,
                        "電話番号":         _cl_v(row, cl_c_phone),
                        "代表者":           _cl_v(row, cl_c_daihyo),
                        "HPリンク":         _cl_v(row, cl_c_hp),
                        "説明リンク":        _cl_v(row, cl_c_desc),
                        "リストランク":      _cl_v(row, cl_c_rank),
                        "地域":             _cl_v(row, cl_c_region),
                        "業種":             _cl_v(row, cl_c_industry),
                        "従業員数":         _cl_v(row, cl_c_employee),
                        "リストアップ担当者": _cl_v(row, cl_c_listowner),
                        "条件NG":           _cl_v(row, cl_c_condng),
                        "リストアップ更新日": _cl_v(row, cl_c_listdate),
                        "アプローチ日":     _cl_v(row, cl_c_apdate),
                        "架電担当者名":     _cl_v(row, cl_c_tanto_call),
                        "パスアポ者名":     _cl_v(row, cl_c_pasapo),
                        "アポ獲得":        _cl_v(row, cl_c_apo),
                        "アプローチ内容":   _cl_v(row, cl_c_content),
                        "見込み":          _cl_v(row, cl_c_mikomi),
                        "アプローチ備考":   _cl_v(row, cl_c_apbiko),
                        "次回アプローチ日":  _cl_v(row, cl_c_nextdate),
                    })

                new_cl_df = pd.DataFrame(new_cl_rows)

                if cl_overwrite.startswith("追加"):
                    existing_cl = _df_call_list
                    if not existing_cl.empty:
                        existing_names = set(existing_cl["会社名"].tolist())
                        new_cl_df = new_cl_df[~new_cl_df["会社名"].isin(existing_names)]
                    mode = "a"
                    header = not os.path.exists(CALL_LIST_FILE) or os.path.getsize(CALL_LIST_FILE) == 0
                else:
                    mode = "w"
                    header = True

                new_cl_df.to_csv(CALL_LIST_FILE, mode=mode, index=False, encoding="utf-8-sig", header=header)
                _save_import_settings("calllist", {
                    "filepath": cl_filepath_val if cl_src_mode.startswith("📂") else "",
                    "mapping": {
                        "会社名": cl_c_company, "電話番号": cl_c_phone, "代表者": cl_c_daihyo,
                        "HPリンク": cl_c_hp, "説明リンク": cl_c_desc, "リストランク": cl_c_rank,
                        "地域": cl_c_region, "業種": cl_c_industry, "従業員数": cl_c_employee,
                        "リストアップ担当者": cl_c_listowner, "条件NG": cl_c_condng,
                        "リストアップ更新日": cl_c_listdate,
                        "アプローチ日": cl_c_apdate, "架電担当者名": cl_c_tanto_call,
                        "パスアポ者名": cl_c_pasapo, "アポ獲得": cl_c_apo,
                        "アプローチ内容": cl_c_content, "見込み": cl_c_mikomi,
                        "アプローチ備考": cl_c_apbiko, "次回アプローチ日": cl_c_nextdate,
                    },
                })
                st.success(f"✅ {len(new_cl_df)}件を取り込みました。架電記録も含めて移行完了です。")
                st.rerun()

    # ── インライン架電記録 ─────────────────────────────────────────
    with cl_inline:
        df_clist_inline = _df_call_list
        if df_clist_inline.empty:
            st.info("架電先リストが空です。「インポート」タブからリストを読み込んでください。")
        else:
            st.caption("リストから会社を選んで架電結果をすぐに記録できます。別のシートに切り替える必要はありません。")

            cl_inline_persons = ["全員"] + sorted(df_clist_inline["架電担当者名"].dropna().replace("", pd.NA).dropna().unique().tolist())
            il_person_filter = st.selectbox("架電担当者名で絞り込む", cl_inline_persons, key="il_person_filter")

            if il_person_filter != "全員":
                il_companies = df_clist_inline[df_clist_inline["架電担当者名"] == il_person_filter]["会社名"].tolist()
            else:
                il_companies = df_clist_inline["会社名"].tolist()

            il_selected = st.selectbox("架電する会社を選択", il_companies, key="il_company_select")

            if il_selected:
                il_row = df_clist_inline[df_clist_inline["会社名"] == il_selected].iloc[0]

                _il_phone   = il_row.get("電話番号", "") or "―"
                _il_daihyo  = il_row.get("代表者", "") or "―"
                _il_rank    = il_row.get("リストランク", "") or "―"
                _il_region  = il_row.get("地域", "") or ""
                _il_ind     = il_row.get("業種", "") or ""
                _il_emp     = il_row.get("従業員数", "") or ""
                st.info(
                    f"📞 **{_il_phone}**　　👤 代表: {_il_daihyo}　　"
                    f"ランク: {_il_rank}"
                    + (f"　　地域: {_il_region}" if _il_region else "")
                    + (f"　　業種: {_il_ind}" if _il_ind else "")
                    + (f"　　従業員: {_il_emp}" if _il_emp else "")
                )
                _il_hp = il_row.get("HPリンク", "")
                _il_desc = il_row.get("説明リンク", "")
                _il_links = []
                if _il_hp:
                    _il_links.append(f"[🌐 HP]({_il_hp})")
                if _il_desc:
                    _il_links.append(f"[📄 説明リンク]({_il_desc})")
                if _il_links:
                    st.markdown("　".join(_il_links))

                st.markdown("---")
                st.markdown("#### 架電記録を入力")

                il_col1, il_col2 = st.columns(2)
                with il_col1:
                    from datetime import date as _il_date
                    il_approach_date = st.date_input(
                        "アプローチ日",
                        value=_il_date.today(),
                        key="il_approach_date",
                    )
                    il_tantosha = st.text_input(
                        "架電担当者名",
                        value=il_row.get("架電担当者名", ""),
                        placeholder="例: 野村",
                        key="il_tantosha",
                    )
                    il_pasapo = st.text_input(
                        "パスアポ者名（アポ相手）",
                        value=il_row.get("パスアポ者名", ""),
                        placeholder="例: 橘爪",
                        key="il_pasapo",
                    )
                    il_apo = st.selectbox(
                        "アポ獲得",
                        ["", "○", "×"],
                        index=0,
                        key="il_apo",
                    )
                with il_col2:
                    il_result = st.selectbox(
                        "アプローチ内容（架電結果）",
                        ["社長NG", "受付NG", "取材NG", "担当NG", "社長アポ", "担当アポ", "資料送付", "追客", "不通リスト", "追わない", "日程調整中", "触るな危険"],
                        key="il_result",
                    )
                    il_mikomi = st.selectbox(
                        "見込み",
                        ["", "A", "B", "C"],
                        key="il_mikomi",
                    )
                    il_memo = st.text_area(
                        "アプローチ備考",
                        value=il_row.get("アプローチ備考", ""),
                        height=90,
                        key="il_memo",
                    )
                    il_next_date = st.date_input(
                        "次回アプローチ日（任意）",
                        value=None,
                        key="il_next_date",
                    )

                from config import HUBSPOT_TOKEN as _IL_HS_TOKEN
                _il_sync_hs = st.checkbox(
                    "HubSpotにも記録を反映する",
                    value=bool(_IL_HS_TOKEN),
                    key="il_sync_hs",
                    disabled=not _IL_HS_TOKEN,
                    help="架電結果をHubSpotのノートとして登録します。" if _IL_HS_TOKEN else "HubSpot連携には HUBSPOT_TOKEN の設定が必要です",
                )

                if st.button("✅ 架電を記録する", type="primary", key="il_submit"):
                    _il_apo_str = str(il_approach_date)
                    _il_next_str = str(il_next_date) if il_next_date else ""

                    update_call_list_row(il_selected, {
                        "アプローチ日":    _il_apo_str,
                        "架電担当者名":    il_tantosha,
                        "パスアポ者名":    il_pasapo,
                        "アポ獲得":       il_apo,
                        "アプローチ内容":  il_result,
                        "見込み":         il_mikomi,
                        "アプローチ備考":  il_memo,
                        "次回アプローチ日": _il_next_str,
                    })

                    record_feedback(
                        company_name=il_selected,
                        approach_result=il_result,
                        got_appointment=il_apo in ("○", "〇"),
                        temperature=il_mikomi,
                        memo=il_memo,
                        tantosha=il_tantosha,
                    )

                    if _il_sync_hs and _IL_HS_TOKEN:
                        _ok = _hubspot_push_call_note(il_selected, il_result, il_memo, il_tantosha, _IL_HS_TOKEN)
                        if _ok:
                            st.success(f"記録しました: **{il_selected}** — {il_result}　✅ HubSpotにも同期済み")
                        else:
                            st.warning(f"記録しました: **{il_selected}** — {il_result}　⚠️ HubSpot同期に失敗しました")
                    else:
                        st.success(f"記録しました: **{il_selected}** — {il_result}")

                    if il_tantosha:
                        with st.spinner(f"「{il_tantosha}」のリスト残数を確認中..."):
                            _il_added, _il_refill_err = _auto_refill_from_hubspot(il_tantosha)
                        if _il_refill_err:
                            st.warning(f"自動補充エラー: {_il_refill_err}")
                        elif _il_added > 0:
                            st.info(f"🔄 「{il_tantosha}」のリスト残数が少ないため {_il_added}件を自動補充しました（A/B/C均等）")
                    st.rerun()


# ──────────────────────────────
# TAB: 見込みリスト
# ──────────────────────────────
with tab_kaiden_zumi:
    st.subheader("見込みリスト")
    st.caption("次回アプローチ日が過ぎた企業を表示します。日程が近い順 × ランク（A→B→C）で並べています。")

    from datetime import date as _kz_date
    _kz_today = str(_kz_date.today())

    _kz_df = _df_call_list.copy()

    _kz_mask = (
        (_kz_df["次回アプローチ日"] != "") &
        (_kz_df["次回アプローチ日"] <= _kz_today)
    )
    _kz_list = _kz_df[_kz_mask].copy()

    _RANK_ORDER = {"A": 1, "B": 2, "C": 3}
    _kz_list["_rank_order"] = (
        _kz_list["リストランク"].str.upper().map(_RANK_ORDER).fillna(4).astype(int)
    )
    _kz_list = (
        _kz_list
        .sort_values(["次回アプローチ日", "_rank_order"], ascending=[True, True])
        .drop(columns=["_rank_order"])
        .reset_index(drop=True)
    )

    if _kz_list.empty:
        st.info("次回アプローチ日が過ぎた企業はありません。")
    else:
        _kz_f1, _kz_f2 = st.columns([1, 2])
        with _kz_f1:
            _kz_persons = ["全員"] + sorted(
                _kz_list["架電担当者名"].dropna().replace("", pd.NA).dropna().unique().tolist()
            )
            _kz_filt = st.selectbox("架電担当者名", _kz_persons, key="kz_filt_person")
        with _kz_f2:
            _kz_search = st.text_input("会社名で検索", placeholder="例: 株式会社〇〇", key="kz_search")

        if _kz_filt != "全員":
            _kz_list = _kz_list[_kz_list["架電担当者名"] == _kz_filt]
        if _kz_search:
            _kz_list = _kz_list[_kz_list["会社名"].str.contains(_kz_search, na=False)]

        st.caption(f"**{len(_kz_list)}件** 表示中")

        _kz_show_cols = [
            "リストランク", "次回アプローチ日", "会社名", "電話番号",
            "架電担当者名", "見込み", "アプローチ内容", "アプローチ備考",
        ]
        st.dataframe(
            _kz_list[[c for c in _kz_show_cols if c in _kz_list.columns]],
            width="stretch",
            hide_index=True,
        )

        st.divider()
        st.markdown("#### 架電記録（担当者変更・結果入力）")

        _kz_company_options = _kz_list["会社名"].tolist()
        _kz_selected = st.selectbox("会社を選択", _kz_company_options, key="kz_company_select")

        if _kz_selected:
            _kz_row = _kz_list[_kz_list["会社名"] == _kz_selected].iloc[0]

            _kz_col1, _kz_col2 = st.columns(2)
            with _kz_col1:
                st.markdown(f"**電話番号:** {_kz_row.get('電話番号', '') or '―'}")
                st.markdown(f"**リストランク:** {_kz_row.get('リストランク', '') or '―'}")
                st.markdown(f"**前回アプローチ内容:** {_kz_row.get('アプローチ内容', '') or '―'}")
            with _kz_col2:
                st.markdown(f"**次回アプローチ日:** {_kz_row.get('次回アプローチ日', '') or '―'}")
                st.markdown(f"**見込み:** {_kz_row.get('見込み', '') or '―'}")
                st.markdown(f"**前回備考:** {_kz_row.get('アプローチ備考', '') or '―'}")

            st.markdown("---")

            _kz_tanto = st.text_input(
                "架電担当者名（変更可能）",
                value=_kz_row.get("架電担当者名", ""),
                key="kz_tanto",
            )
            _kz_result = st.selectbox(
                "アプローチ内容（架電結果）",
                options=_APPROACH_OPTIONS,
                index=_APPROACH_OPTIONS.index(_kz_row.get("アプローチ内容", ""))
                if _kz_row.get("アプローチ内容", "") in _APPROACH_OPTIONS else 0,
                key="kz_result",
            )
            _kz_mikomi = st.selectbox(
                "見込み",
                options=["", "A", "B", "C", "D", "受注済み", "失注"],
                index=["", "A", "B", "C", "D", "受注済み", "失注"].index(_kz_row.get("見込み", ""))
                if _kz_row.get("見込み", "") in ["", "A", "B", "C", "D", "受注済み", "失注"] else 0,
                key="kz_mikomi",
            )
            _kz_memo = st.text_area("備考", value=_kz_row.get("アプローチ備考", ""), height=70, key="kz_memo")
            _kz_next_date = st.date_input("次回アプローチ日（任意）", value=None, key="kz_next_date")

            if st.button("✅ 記録を更新する", type="primary", key="kz_submit"):
                _kz_next_str = str(_kz_next_date) if _kz_next_date else ""
                from datetime import date as _kz_today_d
                update_call_list_row(_kz_selected, {
                    "架電担当者名":    _kz_tanto,
                    "アプローチ内容":  _kz_result,
                    "見込み":         _kz_mikomi,
                    "アプローチ備考":  _kz_memo,
                    "アプローチ日":   str(_kz_today_d.today()),
                    "次回アプローチ日": _kz_next_str,
                })

                if _kz_tanto:
                    with st.spinner(f"「{_kz_tanto}」のリスト残数を確認中..."):
                        _kz_added, _kz_err = _auto_refill_from_hubspot(_kz_tanto)
                    if _kz_err:
                        st.warning(f"記録しました。自動補充エラー: {_kz_err}")
                    elif _kz_added > 0:
                        st.success(f"記録しました ✅ — 「{_kz_tanto}」のリスト残数が少ないため {_kz_added}件を自動補充しました")
                    else:
                        st.success(f"記録しました: **{_kz_selected}** — {_kz_result}")
                else:
                    st.success(f"記録しました: **{_kz_selected}** — {_kz_result}")
                st.rerun()


# ──────────────────────────────
# TAB: 確認待ち
# ──────────────────────────────
with tab_pending:
    st.subheader("確認待ちリスト")
    st.caption("デーモンが自動収集した中間スコア企業の一覧です。承認した企業は approved_companies.csv に保存されます。")
    _show_pending_review_ui()


# ──────────────────────────────
# TAB: 履歴
# ──────────────────────────────
with tab_history:
    st.subheader("架電履歴")

    df_fb = load_feedback()

    if df_fb.empty:
        st.info("まだ記録がありません。「架電先リスト」タブのインライン架電記録から入力してください。")
    else:
        col_f1, col_f2, col_f3, col_f4 = st.columns(4)
        with col_f1:
            filter_result = st.multiselect(
                "架電結果で絞り込み",
                options=df_fb["アプローチ結果"].dropna().unique().tolist(),
            )
        with col_f2:
            filter_rank = st.multiselect(
                "見込みランクで絞り込み",
                options=["A", "B", "C", "なし"],
            )
        with col_f3:
            tantosha_opts = sorted(df_fb["担当名"].dropna().replace("", pd.NA).dropna().unique().tolist()) if "担当名" in df_fb.columns else []
            filter_tantosha = st.multiselect("担当名で絞り込み", options=tantosha_opts)
        with col_f4:
            search_name = st.text_input("会社名で検索")

        filtered = df_fb.copy()
        if filter_result:
            filtered = filtered[filtered["アプローチ結果"].isin(filter_result)]
        if filter_rank:
            filtered = filtered[filtered["温度感"].isin(filter_rank)]
        if filter_tantosha and "担当名" in filtered.columns:
            filtered = filtered[filtered["担当名"].isin(filter_tantosha)]
        if search_name:
            filtered = filtered[filtered["会社名"].str.contains(search_name, na=False)]

        st.dataframe(
            filtered.sort_values("記録日", ascending=False).rename(
                columns={"温度感": "見込みランク", "アプローチ結果": "架電結果"}
            ),
            width="stretch",
            hide_index=True,
        )

        csv_bytes = filtered.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button(
            "📥 CSVダウンロード",
            data=csv_bytes,
            file_name="feedback_export.csv",
            mime="text/csv",
        )


# ──────────────────────────────
# TAB: 商談一覧
# ──────────────────────────────
with tab_meeting:
    st.subheader("商談一覧")

    mtab_input, mtab_list, mtab_pipeline, mtab_import = st.tabs(["✏️ 新規入力", "📋 一覧・検索", "📊 集計", "📥 インポート"])

    # ── 新規入力 ──────────────────────────────────────────────────
    with mtab_input:
        from datetime import date as _mt_date
        from config import HUBSPOT_TOKEN as _MT_HS_TOKEN

        st.markdown("#### アポ情報")
        mt_col1, mt_col2, mt_col3 = st.columns(3)
        with mt_col1:
            mt_apo_month   = st.text_input("アポ獲得月", placeholder="2026-03", key="mt_apo_month")
            mt_apo_getter  = st.text_input("アポ獲得者", placeholder="野村", key="mt_apo_getter")
            mt_listup      = st.text_input("リストアップ（担当者）", placeholder="橘爪", key="mt_listup")
        with mt_col2:
            mt_company     = st.text_input("企業名 *", placeholder="株式会社〇〇", key="mt_company")
            mt_url         = st.text_input("企業URL", placeholder="https://", key="mt_url")
            mt_industry    = st.text_input("業種", placeholder="IT / 製造 等", key="mt_industry")
        with mt_col3:
            mt_summary     = st.text_area("アポ獲得概要", placeholder="社長と話せた。健康経営に興味あり。", height=90, key="mt_summary")
            mt_apo_tanto   = st.text_input("アポ担当（架電者）", placeholder="野村", key="mt_apo_tanto")

        st.markdown("#### 前確認・実施")
        mt_col4, mt_col5, mt_col6 = st.columns(3)
        with mt_col4:
            mt_pre_check   = st.selectbox("前確認実施済", ["", "済", "未"], key="mt_pre_check")
            mt_apo_date    = st.date_input("アポ獲得日", value=None, key="mt_apo_date")
        with mt_col5:
            mt_plan_date   = st.date_input("アポ実施予定日", value=None, key="mt_plan_date")
            mt_jisshi      = st.selectbox("実施の有無", ["", "実施済", "未実施", "延期", "キャンセル"], key="mt_jisshi")
        with mt_col6:
            mt_apo_exec    = st.text_input("アポ実施担当者", placeholder="橘爪", key="mt_apo_exec")
            mt_sekinin     = st.selectbox("責任者の有無", ["", "あり", "なし"], key="mt_sekinin")

        st.markdown("#### 商談結果")
        mt_col7, mt_col8, mt_col9 = st.columns(3)
        with mt_col7:
            mt_result      = st.selectbox("商談結果", ["", "検討中", "次回アポあり", "受注", "失注", "保留", "再アプローチ", "その他"], key="mt_result")
            mt_shissou_r   = st.text_input("失注理由", placeholder="予算なし / 競合 等", key="mt_shissou_r")
        with mt_col8:
            mt_shissou_d   = st.text_area("失注理由（詳細）", height=70, key="mt_shissou_d")
        with mt_col9:
            mt_status      = st.selectbox("ステータス", ["", "進行中", "完了", "保留", "クローズ"], key="mt_status")
            mt_mikomi      = st.selectbox("見込み", ["", "A", "B", "C"], key="mt_mikomi")

        st.markdown("#### 担当者・次回アクション")
        mt_col10, mt_col11, mt_col12 = st.columns(3)
        with mt_col10:
            mt_re_tanto    = st.text_input("再アプローチ担当", key="mt_re_tanto")
            mt_ap_tanto    = st.text_input("アプローチ担当名", key="mt_ap_tanto")
        with mt_col11:
            mt_yakusyoku   = st.text_input("役職", placeholder="社長 / 人事部長 等", key="mt_yakusyoku")
            mt_tel         = st.text_input("電話番号", key="mt_tel")
        with mt_col12:
            mt_ap_content  = st.text_area("アプローチ内容", height=70, key="mt_ap_content")
            mt_next_date   = st.date_input("次回アプローチ日", value=None, key="mt_next_date")

        _mt_sync_hs = st.checkbox(
            "HubSpotの取引（Deal）にも登録する",
            value=bool(_MT_HS_TOKEN),
            disabled=not _MT_HS_TOKEN,
            key="mt_sync_hs",
            help="商談をHubSpotのDealとして作成し、会社に紐付けます。" if _MT_HS_TOKEN else "HubSpot連携には HUBSPOT_TOKEN の設定が必要です",
        )

        if st.button("✅ 商談を記録する", type="primary", disabled=not mt_company, key="mt_submit"):
            from datetime import datetime as _mt_dt
            _mt_row = {
                "記録日":        _mt_dt.now().strftime("%Y-%m-%d"),
                "アポ獲得月":     mt_apo_month,
                "アポ獲得者":     mt_apo_getter,
                "リストアップ":   mt_listup,
                "会社名":         mt_company,
                "アポ獲得概要":   mt_summary,
                "アポ担当":       mt_apo_tanto,
                "前確認実施済":   mt_pre_check,
                "アポ獲得日":     str(mt_apo_date) if mt_apo_date else "",
                "アポ実施予定日":  str(mt_plan_date) if mt_plan_date else "",
                "実施の有無":     mt_jisshi,
                "商談結果":       mt_result,
                "契約":           "はい" if mt_result in ("受注",) else "",
                "責任者の有無":   mt_sekinin,
                "アポ実施担当者":  mt_apo_exec,
                "失注理由":       mt_shissou_r,
                "失注理由（詳細）": mt_shissou_d,
                "業種":           mt_industry,
                "企業URL":        mt_url,
                "再アプローチ担当": mt_re_tanto,
                "アプローチ担当名": mt_ap_tanto,
                "役職":           mt_yakusyoku,
                "電話番号":       mt_tel,
                "ステータス":     mt_status,
                "見込み":         mt_mikomi,
                "アプローチ内容":  mt_ap_content,
                "次回アプローチ日": str(mt_next_date) if mt_next_date else "",
            }
            _save_meeting_row(_mt_row)

            if _mt_sync_hs and _MT_HS_TOKEN:
                _ok = _hubspot_push_deal(_mt_row, _MT_HS_TOKEN)
                if _ok:
                    st.success(f"記録しました: **{mt_company}**　✅ HubSpot取引にも登録済み")
                else:
                    st.warning(f"記録しました: **{mt_company}**　⚠️ HubSpot取引登録に失敗しました")
            else:
                st.success(f"記録しました: **{mt_company}**")
            st.rerun()

    # ── 一覧・検索 ────────────────────────────────────────────────
    with mtab_list:
        df_mt = load_meetings()
        if df_mt.empty:
            st.info("まだ商談記録がありません。「新規入力」から登録してください。")
        else:
            mf1, mf2, mf3, mf4 = st.columns(4)
            with mf1:
                _mt_results = ["全て"] + [v for v in df_mt["商談結果"].dropna().unique().tolist() if v]
                mt_filt_result = st.selectbox("商談結果", _mt_results, key="mt_filt_result")
            with mf2:
                _mt_statuses = ["全て"] + [v for v in df_mt["ステータス"].dropna().unique().tolist() if v]
                mt_filt_status = st.selectbox("ステータス", _mt_statuses, key="mt_filt_status")
            with mf3:
                _mt_mikomi_vals = ["全て"] + [v for v in df_mt["見込み"].dropna().unique().tolist() if v]
                mt_filt_mikomi = st.selectbox("見込み", _mt_mikomi_vals, key="mt_filt_mikomi")
            with mf4:
                mt_search = st.text_input("企業名で検索", key="mt_search")

            filtered_mt = df_mt.copy()
            if mt_filt_result != "全て":
                filtered_mt = filtered_mt[filtered_mt["商談結果"] == mt_filt_result]
            if mt_filt_status != "全て":
                filtered_mt = filtered_mt[filtered_mt["ステータス"] == mt_filt_status]
            if mt_filt_mikomi != "全て":
                filtered_mt = filtered_mt[filtered_mt["見込み"] == mt_filt_mikomi]
            if mt_search:
                if "会社名" in filtered_mt.columns:
                    filtered_mt = filtered_mt[filtered_mt["会社名"].str.contains(mt_search, na=False)]

            st.caption(f"表示: {len(filtered_mt)}件")

            _mt_show_cols = [c for c in [
                "記録日", "アポ獲得月", "会社名", "アポ獲得者", "アポ担当",
                "アポ実施予定日", "実施の有無", "商談結果", "ステータス", "見込み",
                "アポ実施担当者", "失注理由", "次回アプローチ日", "アプローチ担当名",
            ] if c in filtered_mt.columns]
            st.dataframe(
                filtered_mt[_mt_show_cols].sort_values("記録日", ascending=False),
                width="stretch",
                hide_index=True,
            )

            with st.expander("全列表示"):
                st.dataframe(filtered_mt.sort_values("記録日", ascending=False), width="stretch", hide_index=True)

            csv_mt = filtered_mt.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button("📥 CSVダウンロード", data=csv_mt, file_name="meetings_export.csv", mime="text/csv", key="mt_dl")

    # ── 集計 ─────────────────────────────────────────────────────
    with mtab_pipeline:
        df_mt = load_meetings()
        if df_mt.empty:
            st.info("データが溜まったら集計できます。")
        else:
            total_mt    = len(df_mt)
            jisshi_cnt  = (df_mt["実施の有無"] == "実施済").sum()
            juchu_cnt   = df_mt["商談結果"].str.contains("受注|契約", na=False).sum()
            cv_rate     = juchu_cnt / total_mt * 100 if total_mt > 0 else 0

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("総商談数", f"{total_mt}件")
            k2.metric("実施済", f"{jisshi_cnt}件")
            k3.metric("受注件数", f"{juchu_cnt}件")
            k4.metric("成約率", f"{cv_rate:.1f}%")

            st.divider()
            col_p1, col_p2 = st.columns(2)
            with col_p1:
                st.markdown("**商談結果の内訳**")
                _mr_df = df_mt["商談結果"].replace("", "未記入").value_counts().reset_index()
                _mr_df.columns = ["商談結果", "件数"]
                chart_mr = alt.Chart(_mr_df).mark_bar(color="#4C78A8").encode(
                    x=alt.X("商談結果:N", sort="-y", axis=alt.Axis(labelAngle=-30, labelFontSize=11)),
                    y=alt.Y("件数:Q"),
                    tooltip=["商談結果", "件数"],
                ).properties(height=250)
                st.altair_chart(chart_mr, width="stretch")
            with col_p2:
                st.markdown("**見込み別件数**")
                _mk_df = df_mt["見込み"].replace("", "未記入").value_counts().reset_index()
                _mk_df.columns = ["見込み", "件数"]
                chart_mk = alt.Chart(_mk_df).mark_bar(color="#72B7B2").encode(
                    x=alt.X("見込み:N", sort="-y", axis=alt.Axis(labelAngle=0)),
                    y=alt.Y("件数:Q"),
                    tooltip=["見込み", "件数"],
                ).properties(height=250)
                st.altair_chart(chart_mk, width="stretch")

            st.divider()
            st.markdown("**次回アプローチ要対応**")
            _action_df = df_mt[
                df_mt["次回アプローチ日"].replace("", pd.NA).notna() &
                ~df_mt["商談結果"].str.contains("受注|失注", na=False)
            ].sort_values("次回アプローチ日")
            if not _action_df.empty:
                st.dataframe(
                    _action_df[[c for c in ["会社名", "アポ実施担当者", "商談結果", "見込み", "次回アプローチ日", "アプローチ内容"] if c in _action_df.columns]],
                    width="stretch", hide_index=True,
                )
            else:
                st.caption("対象なし")

    # ── インポート ────────────────────────────────────────────────
    with mtab_import:
        st.caption("CSV / Excel / Googleスプレッドシートから商談記録を一括取り込みできます。")

        mi_saved = _load_import_settings("meeting_import")

        mi_src_mode = st.radio(
            "ファイルの指定方法",
            ["📂 パスを直接入力", "⬆️ アップロード", "🔗 Googleスプレッドシート"],
            horizontal=True,
            key="mi_src_mode",
        )

        mi_df_raw = None
        mi_filepath_val = ""

        if mi_src_mode.startswith("📂"):
            mi_filepath_val = st.text_input(
                "ファイルパス（CSV または .xlsx）",
                value=mi_saved.get("filepath", ""),
                placeholder=r"C:\Users\user\Desktop\商談管理.xlsx",
                key="mi_filepath",
            )
            if mi_filepath_val and os.path.exists(mi_filepath_val):
                mi_df_raw = _read_file_to_df(mi_filepath_val)
                if mi_df_raw is None:
                    st.error("ファイルを読み込めませんでした。")
            elif mi_filepath_val:
                st.warning("ファイルが見つかりません。パスを確認してください。")
        elif mi_src_mode.startswith("⬆️"):
            mi_uploaded = st.file_uploader("CSV / Excel を選択", type=["csv", "xlsx", "xls"], key="mi_upload")
            if mi_uploaded:
                ext = os.path.splitext(mi_uploaded.name)[1].lower()
                if ext in (".xlsx", ".xls"):
                    mi_df_raw = pd.read_excel(mi_uploaded, dtype=str).fillna("")
                else:
                    raw_mi = mi_uploaded.read()
                    for enc in ("utf-8-sig", "shift-jis", "cp932", "utf-8"):
                        try:
                            mi_df_raw = pd.read_csv(_io_mod.StringIO(raw_mi.decode(enc)), dtype=str).fillna("")
                            break
                        except Exception:
                            pass
                mi_filepath_val = mi_uploaded.name
        else:
            mi_df_raw = _render_gsheets_loader("meeting_import_gs", mi_saved)

        if mi_df_raw is not None:
            st.markdown(f"**読み込み: {len(mi_df_raw)}行 / {len(mi_df_raw.columns)}列**")
            st.dataframe(mi_df_raw.head(3), width="stretch", hide_index=True)

            st.markdown("### 列マッピング")
            mi_all_cols = ["（使わない）"] + mi_df_raw.columns.tolist()
            mi_map_saved = mi_saved.get("mapping", {})

            def mi_pick(label, keywords):
                saved_val = mi_map_saved.get(label)
                if saved_val and saved_val in mi_all_cols:
                    default = saved_val
                else:
                    default = next((col for kw in keywords for col in mi_df_raw.columns if kw in col), "（使わない）")
                return st.selectbox(label, mi_all_cols, index=mi_all_cols.index(default), key=f"mimap_{label}")

            mic1, mic2, mic3 = st.columns(3)
            with mic1:
                mi_c_company   = mi_pick("企業名",         ["企業名", "会社名"])
                mi_c_month     = mi_pick("アポ獲得月",      ["アポ獲得月", "獲得月"])
                mi_c_getter    = mi_pick("アポ獲得者",      ["アポ獲得者", "獲得者"])
                mi_c_listup    = mi_pick("リストアップ",    ["リストアップ"])
                mi_c_summary   = mi_pick("アポ獲得概要",    ["アポ獲得概要", "概要"])
                mi_c_tanto     = mi_pick("アポ担当",        ["アポ担当", "担当"])
                mi_c_precheck  = mi_pick("前確認実施済",    ["前確認", "確認"])
                mi_c_apodate   = mi_pick("アポ獲得日",      ["アポ獲得日", "獲得日"])
            with mic2:
                mi_c_plandate  = mi_pick("アポ実施予定日",  ["アポ実施予定日", "実施予定日", "予定日"])
                mi_c_jisshi    = mi_pick("実施の有無",      ["実施の有無", "実施"])
                mi_c_result    = mi_pick("商談結果",        ["商談結果", "結果"])
                mi_c_sekinin   = mi_pick("責任者の有無",    ["責任者の有無", "責任者"])
                mi_c_exec      = mi_pick("アポ実施担当者",  ["アポ実施担当者", "実施担当者"])
                mi_c_shissou   = mi_pick("失注理由",        ["失注理由"])
                mi_c_shissoud  = mi_pick("失注理由（詳細）", ["失注理由（詳細）", "失注詳細"])
            with mic3:
                mi_c_industry  = mi_pick("業種",            ["業種"])
                mi_c_url       = mi_pick("企業URL",         ["企業URL", "URL", "HP"])
                mi_c_re_tanto  = mi_pick("再アプローチ担当", ["再アプローチ担当"])
                mi_c_ap_tanto  = mi_pick("アプローチ担当名", ["アプローチ担当名", "担当名"])
                mi_c_yakusyoku = mi_pick("役職",            ["役職"])
                mi_c_tel       = mi_pick("電話番号",        ["電話番号", "電話", "TEL"])
                mi_c_status    = mi_pick("ステータス",      ["ステータス"])
                mi_c_mikomi    = mi_pick("見込み",          ["見込み"])
                mi_c_content   = mi_pick("アプローチ内容",  ["アプローチ内容", "内容"])
                mi_c_nextdate  = mi_pick("次回アプローチ日", ["次回アプローチ日", "次回"])

            mi_overwrite = st.radio(
                "インポートモード",
                ["追加（既存データに追加）", "上書き（全て置き換え）"],
                horizontal=True,
                key="mi_import_mode",
            )

            if st.button("✅ 商談一覧に取り込む", type="primary", key="mi_import_btn"):
                from datetime import date as _mi_date

                def _mi_v(row, col):
                    return str(row.get(col, "")).strip() if col != "（使わない）" else ""

                new_mi_rows = []
                for _, row in mi_df_raw.iterrows():
                    company = _mi_v(row, mi_c_company)
                    if not company:
                        continue
                    new_mi_rows.append({
                        "記録日":         str(_mi_date.today()),
                        "アポ獲得月":      _mi_v(row, mi_c_month),
                        "アポ獲得者":      _mi_v(row, mi_c_getter),
                        "リストアップ":    _mi_v(row, mi_c_listup),
                        "会社名":          company,
                        "アポ獲得概要":    _mi_v(row, mi_c_summary),
                        "アポ担当":        _mi_v(row, mi_c_tanto),
                        "前確認実施済":    _mi_v(row, mi_c_precheck),
                        "アポ獲得日":      _mi_v(row, mi_c_apodate),
                        "アポ実施予定日":   _mi_v(row, mi_c_plandate),
                        "実施の有無":      _mi_v(row, mi_c_jisshi),
                        "商談結果":        _mi_v(row, mi_c_result),
                        "責任者の有無":    _mi_v(row, mi_c_sekinin),
                        "アポ実施担当者":   _mi_v(row, mi_c_exec),
                        "失注理由":        _mi_v(row, mi_c_shissou),
                        "失注理由（詳細）": _mi_v(row, mi_c_shissoud),
                        "業種":            _mi_v(row, mi_c_industry),
                        "企業URL":         _mi_v(row, mi_c_url),
                        "再アプローチ担当": _mi_v(row, mi_c_re_tanto),
                        "アプローチ担当名": _mi_v(row, mi_c_ap_tanto),
                        "役職":            _mi_v(row, mi_c_yakusyoku),
                        "電話番号":        _mi_v(row, mi_c_tel),
                        "ステータス":      _mi_v(row, mi_c_status),
                        "見込み":          _mi_v(row, mi_c_mikomi),
                        "アプローチ内容":   _mi_v(row, mi_c_content),
                        "次回アプローチ日": _mi_v(row, mi_c_nextdate),
                    })

                new_mi_df = pd.DataFrame(new_mi_rows)

                os.makedirs(OUTPUT_DIR, exist_ok=True)
                if mi_overwrite.startswith("追加"):
                    existing_mi = load_meetings()
                    if not existing_mi.empty and "会社名" in existing_mi.columns:
                        existing_companies = set(existing_mi["会社名"].dropna().tolist())
                        new_mi_df = new_mi_df[~new_mi_df["会社名"].isin(existing_companies)]
                    mode = "a"
                    header = not os.path.exists(MEETINGS_FILE) or os.path.getsize(MEETINGS_FILE) == 0
                else:
                    mode = "w"
                    header = True

                new_mi_df.to_csv(MEETINGS_FILE, mode=mode, index=False, encoding="utf-8-sig", header=header)

                _save_import_settings("meeting_import", {
                    "filepath": mi_filepath_val if mi_src_mode.startswith("📂") else "",
                    "mapping": {
                        "企業名": mi_c_company, "アポ獲得月": mi_c_month, "アポ獲得者": mi_c_getter,
                        "リストアップ": mi_c_listup, "アポ獲得概要": mi_c_summary, "アポ担当": mi_c_tanto,
                        "前確認実施済": mi_c_precheck, "アポ獲得日": mi_c_apodate,
                        "アポ実施予定日": mi_c_plandate, "実施の有無": mi_c_jisshi,
                        "商談結果": mi_c_result, "責任者の有無": mi_c_sekinin,
                        "アポ実施担当者": mi_c_exec, "失注理由": mi_c_shissou,
                        "失注理由（詳細）": mi_c_shissoud, "業種": mi_c_industry,
                        "企業URL": mi_c_url, "再アプローチ担当": mi_c_re_tanto,
                        "アプローチ担当名": mi_c_ap_tanto, "役職": mi_c_yakusyoku,
                        "電話番号": mi_c_tel, "ステータス": mi_c_status,
                        "見込み": mi_c_mikomi, "アプローチ内容": mi_c_content,
                        "次回アプローチ日": mi_c_nextdate,
                    },
                })
                st.success(f"✅ {len(new_mi_df)}件を取り込みました。")
                st.rerun()
