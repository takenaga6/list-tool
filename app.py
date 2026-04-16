"""
Offi-Stretch リストアップ管理
起動: streamlit run app.py
タブ: リストアップ / システム診断 / 利用者フィードバック

架電ツール（架電先リスト・見込みリスト・確認待ち・履歴・商談一覧）は
pages/1_架電ツール.py に分離済み。
"""

import os
import subprocess
import sys
import pandas as pd
import streamlit as st

from config import (
    USER_FEEDBACK_FILE, OUTPUT_DIR,
)
from call_tool_utils import (
    apply_global_styles,
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
tab_listup, tab_monitor, tab_user_fb = st.tabs(
    ["リストアップ", "システム診断", "利用者フィードバック"]
)


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
