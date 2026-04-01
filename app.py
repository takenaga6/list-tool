"""
Offi-Stretch テレアポ管理アプリ
起動: streamlit run app.py
"""

import os
import subprocess
import sys
import pandas as pd
import streamlit as st
import altair as alt

import io as _io_mod
import json as _json_mod
from config import FEEDBACK_FILE, RESULTS_FILE, MEETINGS_FILE, CALL_LIST_FILE, IMPORT_SETTINGS_FILE, USER_FEEDBACK_FILE, OUTPUT_DIR, record_feedback, record_meeting

_LIST_TOOL_DIR = os.path.dirname(os.path.abspath(__file__))

# リストアップのバックグラウンド実行状態（サーバー起動中に持続するモジュール変数）
_LISTUP_STATE: dict = {
    "proc":        None,   # subprocess.Popen オブジェクト
    "lines":       [],     # stdout バッファ
    "running":     False,  # 実行中フラグ
    "done":        False,  # 完了フラグ
    "return_code": None,   # 終了コード
}


def _listup_reader_thread(proc: "subprocess.Popen[str]") -> None:
    """バックグラウンドスレッドでサブプロセスの stdout を読み込む"""
    import subprocess as _sp
    for _line in proc.stdout:
        _LISTUP_STATE["lines"].append(_line.rstrip())
    proc.wait()
    _LISTUP_STATE["running"]     = False
    _LISTUP_STATE["done"]        = True
    _LISTUP_STATE["return_code"] = proc.returncode


# ──────────────────────────────
# ページ設定
# ──────────────────────────────
st.set_page_config(
    page_title="Offi-Stretch リスト管理",
    page_icon="🌿",
    layout="wide",
)

# ──────────────────────────────
# グローバルCSS（SaaSライクなUIデザイン）
# ──────────────────────────────
st.markdown("""
<style>
/* ══════════════════════════════════════════════
   CSS変数（Streamlit内部テーマ変数を上書き）
   ══════════════════════════════════════════════ */
:root {
    --primary-color: #40b680 !important;
    --background-color: #ffffff !important;
    --secondary-background-color: #f9fafb !important;
    --text-color: #111827 !important;
    --font: 'Inter', 'Hiragino Sans', 'Yu Gothic', sans-serif !important;
}

/* ══════════════════════════════════════════════
   ベース：背景・文字色
   ══════════════════════════════════════════════ */
html, body,
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
[data-testid="stMainBlockContainer"],
section[data-testid="stSidebar"] ~ div {
    background-color: #ffffff !important;
    color: #111827 !important;
    font-family: 'Inter', 'Hiragino Sans', 'Yu Gothic', sans-serif !important;
}
[data-testid="stHeader"] {
    background-color: #ffffff !important;
    border-bottom: 1px solid #e5e7eb !important;
}
[data-testid="block-container"] {
    padding-top: 0.75rem !important;
    padding-bottom: 1rem !important;
}

/* ── テキスト要素を濃い色に統一（divは除外 — GDGのJS色計算に影響するため） ── */
p, li, td, th, pre, code,
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] span,
[data-testid="stMarkdownContainer"] li,
[data-testid="stText"] {
    color: #111827 !important;
}

/* ══════════════════════════════════════════════
   セクション間余白
   ══════════════════════════════════════════════ */
div[data-testid="stVerticalBlock"] { gap: 0.5rem !important; }
.element-container { margin-bottom: 0.25rem !important; }

/* ══════════════════════════════════════════════
   ヘッダーロゴエリア
   ══════════════════════════════════════════════ */
.app-header {
    display: flex; align-items: center; gap: 12px;
    padding: 0 0 1.2rem 0;
    border-bottom: 2px solid #40b680;
    margin-bottom: 1.5rem;
}
.app-header-title {
    font-size: 1.25rem; font-weight: 700;
    color: #111827 !important; letter-spacing: -0.02em;
}
.app-header-sub { font-size: 0.75rem; color: #9ca3af !important; margin-top: 1px; }

/* ══════════════════════════════════════════════
   タブナビゲーション
   ══════════════════════════════════════════════ */
[data-testid="stTabs"] [role="tablist"] {
    gap: 0 !important;
    border-bottom: 1px solid #e5e7eb !important;
    background: transparent !important;
}
[data-testid="stTabs"] [role="tab"] {
    border: none !important;
    border-bottom: 2px solid transparent !important;
    background: transparent !important;
    color: #6b7280 !important;
    font-size: 0.875rem !important; font-weight: 500 !important;
    padding: 0.6rem 1rem !important; border-radius: 0 !important;
}
[data-testid="stTabs"] [role="tab"]:hover {
    color: #40b680 !important; background: #f0fdf4 !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: #40b680 !important;
    border-bottom: 2px solid #40b680 !important;
    font-weight: 600 !important; background: transparent !important;
}

/* ══════════════════════════════════════════════
   ボタン
   ══════════════════════════════════════════════ */
[data-testid="stButton"] > button {
    background-color: #ffffff !important; color: #374151 !important;
    border: 1px solid #d1d5db !important; border-radius: 6px !important;
    font-size: 0.875rem !important; font-weight: 500 !important;
    padding: 0.4rem 0.9rem !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04) !important;
}
[data-testid="stButton"] > button:hover {
    background-color: #f9fafb !important; border-color: #9ca3af !important;
}
[data-testid="stButton"] > button[kind="primary"] {
    background-color: #40b680 !important; color: #ffffff !important;
    border: none !important; box-shadow: 0 1px 3px rgba(64,182,128,0.3) !important;
}
[data-testid="stButton"] > button[kind="primary"]:hover { background-color: #34a370 !important; }
[data-testid="stButton"] > button:disabled {
    background-color: #f3f4f6 !important; color: #9ca3af !important;
    border-color: #e5e7eb !important;
}
[data-testid="stDownloadButton"] button {
    background: #ffffff !important; color: #40b680 !important;
    border: 1px solid #40b680 !important; border-radius: 6px !important;
    font-size: 0.875rem !important; font-weight: 500 !important;
}
[data-testid="stDownloadButton"] button:hover { background: #f0fdf4 !important; }

/* ══════════════════════════════════════════════
   入力フォーム
   ══════════════════════════════════════════════ */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stTextArea"] textarea {
    background: #ffffff !important; color: #111827 !important;
    border: 1px solid #d1d5db !important; border-radius: 6px !important;
    font-size: 0.875rem !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {
    border-color: #40b680 !important;
    box-shadow: 0 0 0 3px rgba(64,182,128,0.1) !important;
}

/* ══════════════════════════════════════════════
   セレクトボックス・マルチセレクト
   ══════════════════════════════════════════════ */
/* コントロール本体 */
[data-baseweb="select"],
[data-baseweb="select"] > div,
[data-baseweb="select"] > div > div {
    background-color: #ffffff !important;
    color: #111827 !important;
    border-color: #d1d5db !important;
    border-radius: 6px !important;
    font-size: 0.875rem !important;
}
/* 選択済み値テキスト */
[data-baseweb="select"] [class*="singleValue"],
[data-baseweb="select"] [class*="placeholder"],
[data-baseweb="select"] span {
    color: #111827 !important;
}
/* ドロップダウンリスト */
[data-baseweb="popover"] [data-baseweb="menu"],
[data-baseweb="popover"] ul,
[data-baseweb="menu"] {
    background-color: #ffffff !important;
    border: 1px solid #e5e7eb !important;
    border-radius: 6px !important;
    box-shadow: 0 4px 12px rgba(0,0,0,0.08) !important;
}
[data-baseweb="option"],
[data-baseweb="menu-item"],
[role="option"] {
    background-color: #ffffff !important;
    color: #111827 !important;
    font-size: 0.875rem !important;
}
[data-baseweb="option"]:hover,
[data-baseweb="menu-item"]:hover,
[role="option"]:hover,
[aria-selected="true"][data-baseweb="option"] {
    background-color: #f0fdf4 !important;
    color: #111827 !important;
}
/* マルチセレクトタグ */
[data-baseweb="tag"] {
    background-color: #e6f7ef !important;
    color: #111827 !important;
}
[data-baseweb="tag"] span { color: #111827 !important; }

/* ══════════════════════════════════════════════
   data_editor / dataframe
   ══════════════════════════════════════════════ */
/* 外枠のみ。内部(canvas)はテーマに任せる — CSS上書き厳禁 */
[data-testid="stDataFrame"],
[data-testid="stDataEditor"] {
    border: 1px solid #e5e7eb !important;
    border-radius: 8px !important;
}

/* ══════════════════════════════════════════════
   見出し
   ══════════════════════════════════════════════ */
h1 { color: #111827 !important; font-weight: 700 !important; font-size: 1.5rem !important; }
h2 { color: #1f2937 !important; font-weight: 600 !important; font-size: 1.2rem !important; }
h3 { color: #374151 !important; font-weight: 600 !important; font-size: 1rem !important; }

/* ══════════════════════════════════════════════
   ラベル・キャプション
   ══════════════════════════════════════════════ */
label { color: #374151 !important; font-size: 0.875rem !important; font-weight: 500 !important; }
[data-testid="stCaptionContainer"] p { color: #6b7280 !important; font-size: 0.78rem !important; }
[data-testid="stCheckbox"] label { color: #374151 !important; font-size: 0.875rem !important; }
[data-testid="stRadio"] label { color: #374151 !important; font-size: 0.875rem !important; }
[data-testid="stToggle"] label { font-size: 0.875rem !important; }

/* ══════════════════════════════════════════════
   メトリクスカード
   ══════════════════════════════════════════════ */
[data-testid="stMetric"] {
    background: #f9fafb !important; border: 1px solid #e5e7eb !important;
    border-radius: 8px !important; padding: 1rem !important;
}
[data-testid="stMetricValue"] { color: #111827 !important; font-weight: 700 !important; }
[data-testid="stMetricLabel"] { color: #6b7280 !important; font-size: 0.8rem !important; }
[data-testid="stMetricDelta"] span { font-size: 0.8rem !important; }

/* ══════════════════════════════════════════════
   アラート・エクスパンダー・その他
   ══════════════════════════════════════════════ */
[data-testid="stAlert"] { border-radius: 6px !important; font-size: 0.875rem !important; }
[data-testid="stAlert"] p { color: inherit !important; }
[data-testid="stExpander"] {
    border: 1px solid #e5e7eb !important;
    border-radius: 8px !important; background: #f9fafb !important;
}
hr { border-color: #e5e7eb !important; margin: 1rem 0 !important; }

/* ══════════════════════════════════════════════
   フッター・メニュー非表示
   ══════════════════════════════════════════════ */
footer { visibility: hidden; }
#MainMenu { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ── ヘッダー（ロゴ画像） ──
import base64 as _b64
_logo_path = os.path.join(_LIST_TOOL_DIR, "Offi-Stretch_280px.jpg")
if os.path.exists(_logo_path):
    with open(_logo_path, "rb") as _lf:
        _logo_b64 = _b64.b64encode(_lf.read()).decode()
    st.markdown(f"""
<div class="app-header">
  <img src="data:image/jpeg;base64,{_logo_b64}" style="height:40px;width:auto;object-fit:contain;" />
  <div>
    <div class="app-header-title">リスト管理</div>
    <div class="app-header-sub">Well Body株式会社 — テレアポ営業支援ツール</div>
  </div>
</div>
""", unsafe_allow_html=True)
else:
    st.markdown("""
<div class="app-header">
  <div class="app-header-logo">O</div>
  <div>
    <div class="app-header-title">Offi-Stretch リスト管理</div>
    <div class="app-header-sub">Well Body株式会社 — テレアポ営業支援ツール</div>
  </div>
</div>
""", unsafe_allow_html=True)

tab_calllist, tab_kaiden_zumi, tab_pending, tab_history, tab_analysis, tab_import, tab_listup, tab_meeting, tab_monitor, tab_user_fb = st.tabs(
    ["架電先リスト", "見込みリスト", "確認待ち", "履歴", "ダッシュボード", "取り込み", "リストアップ", "商談一覧", "システム診断", "利用者フィードバック"]
)


# ──────────────────────────────
# ユーティリティ
# ──────────────────────────────

def load_feedback() -> pd.DataFrame:
    if os.path.exists(FEEDBACK_FILE):
        try:
            df = pd.read_csv(FEEDBACK_FILE, encoding="utf-8-sig")
            df["記録日"] = pd.to_datetime(df["記録日"], errors="coerce")
            # 後方互換: 担当名列がない古いCSVに対応
            if "担当名" not in df.columns:
                df["担当名"] = ""
            return df
        except Exception:
            pass
    return pd.DataFrame(columns=["記録日", "会社名", "アプローチ結果", "アポ獲得", "規模", "NG理由", "断り理由", "温度感", "検索クエリ", "反応が良かったポイント", "メモ", "担当名"])


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


# 架電先リスト 全カラム定義
# ── 会社情報（HubSpot/インポートで入る静的データ）──
_CALL_LIST_STATIC_COLS = [
    "hs_id", "会社名", "HPリンク", "説明リンク", "電話番号", "代表者",
    "リストランク", "地域", "業種", "従業員数",
    "リストアップ担当者", "条件NG", "リストアップ更新日",
]
# ── 架電記録（架電するたびに更新される動的データ）──
_CALL_LIST_ACTIVITY_COLS = [
    "アプローチ日", "架電担当者名", "パスアポ者名",
    "アポ獲得", "アプローチ内容", "見込み", "アプローチ備考", "次回アプローチ日",
]
_CALL_LIST_COLS = _CALL_LIST_STATIC_COLS + _CALL_LIST_ACTIVITY_COLS

# HubSpotカスタムプロパティ ↔ 日本語カラム名 マッピング
_HS_PROP_MAP = {
    "架電担当者名":     "kaiden_tanto",
    "パスアポ者名":     "pass_apo",
    "アポ獲得":         "apo_acquired",
    "アプローチ内容":   "approach_content",
    "見込み":           "prospect_rank",
    "アプローチ日":     "approach_date",
    "次回アプローチ日": "next_approach_date",
    "アプローチ備考":   "approach_memo",
    "条件NG":           "joken_ng",
}

_APPROACH_OPTIONS = [
    "", "受付NG", "担当NG", "社長NG", "取材NG", "追客", "社長アポ", "担当アポ",
    "資料送付", "不通リスト", "追わない", "ナーチャリング", "日程調整中", "触るな危険！",
]


def load_call_list() -> pd.DataFrame:
    """架電先リストをCSVから読み込む"""
    if os.path.exists(CALL_LIST_FILE):
        try:
            df = pd.read_csv(CALL_LIST_FILE, encoding="utf-8-sig", dtype=str).fillna("")
            # 後方互換: 不足列を空文字で補完
            for col in _CALL_LIST_COLS:
                if col not in df.columns:
                    df[col] = ""
            return df
        except Exception:
            pass
    return pd.DataFrame(columns=_CALL_LIST_COLS)


def update_call_list_row(company_name: str, update_data: dict):
    """call_list.csv の特定会社行を更新する。会社が存在しない場合は新規追加。"""
    from datetime import date as _date
    df = load_call_list()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if df.empty or company_name not in df["会社名"].values:
        # 新規行として追加
        new_row = {col: "" for col in _CALL_LIST_COLS}
        new_row["会社名"] = company_name
        new_row.update(update_data)
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    else:
        idx = df[df["会社名"] == company_name].index[0]
        for key, val in update_data.items():
            if key not in df.columns:
                df[key] = ""
            df.at[idx, key] = val

    df.to_csv(CALL_LIST_FILE, index=False, encoding="utf-8-sig")


def _auto_refill_from_hubspot(tanto_name: str) -> tuple[int, str | None]:
    """
    指定担当者のアプローチ内容ブランクが50件未満になったら、
    HubSpotから100件（リストランクA/B/C均等）を自動追加する。
    設定で特定リストIDが保存されていればそのリストから取得、なければ全企業が対象。
    戻り値: (追加件数, エラーメッセージ or None)
    """
    from config import HUBSPOT_TOKEN
    if not HUBSPOT_TOKEN or not tanto_name:
        return 0, None

    # 現在のcall_listをロードし、担当者のブランク件数をチェック
    df_cl = load_call_list()
    tanto_rows = df_cl[df_cl["架電担当者名"] == tanto_name]
    blank_count = len(tanto_rows[tanto_rows["アプローチ内容"] == ""])
    if blank_count >= 50:
        return 0, None  # まだ十分あるので補充不要

    # 既存のcall_listにある会社名セット（重複除外用）
    existing_names = set(df_cl["会社名"].tolist())

    # results.csvからランク情報を取得（会社名→ランクの辞書を作成）
    rank_map: dict[str, str] = {}
    if os.path.exists(RESULTS_FILE):
        try:
            df_results = pd.read_csv(RESULTS_FILE, encoding="utf-8-sig", dtype=str).fillna("")
            rank_col = "ランク" if "ランク" in df_results.columns else "リストランク"
            for _, row in df_results.iterrows():
                _rname = str(row.get("会社名", "")).strip()
                _rrank = str(row.get(rank_col, "")).strip().upper()
                if _rname:
                    rank_map[_rname] = _rrank
        except Exception:
            pass

    # 自動補充対象リストIDを設定から取得（未設定なら全企業モード）
    _refill_list_id = _load_import_settings("auto_refill_list").get("list_id", "")

    import requests as _refill_req
    _refill_headers = {
        "Authorization": f"Bearer {HUBSPOT_TOKEN}",
        "Content-Type": "application/json",
    }
    _REFILL_PROPS = "name,phone,website,state,city,industry,numberofemployees,zip,joken_ng"
    _hs_base = "https://api.hubapi.com"

    # HubSpotオブジェクト → candidateエントリに変換するヘルパー
    def _to_candidate(c: dict) -> dict | None:
        _p = c.get("properties", {})
        _name = (_p.get("name") or "").strip()
        if not _name or _name in existing_names:
            return None
        return {
            "hs_id":             c.get("id", ""),
            "会社名":            _name,
            "電話番号":          (_p.get("phone") or "").strip(),
            "代表者":            "",
            "HPリンク":          (_p.get("website") or "").strip(),
            "説明リンク":        "",
            "地域":              (_p.get("state") or _p.get("city") or "").strip(),
            "業種":              (_p.get("industry") or "").strip(),
            "従業員数":          (_p.get("numberofemployees") or "").strip(),
            "リストランク":      rank_map.get(_name, ""),
            "リストアップ担当者": "",
            "条件NG":            "○" if (_p.get("joken_ng") or "").lower() in ("true", "1", "yes") else "",
            "リストアップ更新日": "",
            "架電担当者名":      tanto_name,
            "パスアポ者名":      "",
            "アポ獲得":          "",
            "アプローチ内容":    "",
            "見込み":            "",
            "アプローチ日":      "",
            "次回アプローチ日":  "",
            "アプローチ備考":    "",
        }

    candidates: list[dict] = []
    try:
        if _refill_list_id:
            # ── 特定リスト指定モード: メンバーIDを取得 → バッチで詳細取得 ──
            _member_ids: list[str] = []
            _list_after = None
            while len(_member_ids) < 300:
                _lm_params: dict = {"limit": min(250, 300 - len(_member_ids))}
                if _list_after:
                    _lm_params["after"] = _list_after
                _lm_resp = _refill_req.get(
                    f"{_hs_base}/crm/v3/lists/{_refill_list_id}/memberships/join-order",
                    headers=_refill_headers,
                    params=_lm_params,
                    timeout=15,
                )
                if not _lm_resp.ok:
                    return 0, f"リストメンバー取得エラー: {_lm_resp.status_code}"
                _lm_data = _lm_resp.json()
                _member_ids += [r["recordId"] for r in _lm_data.get("results", [])]
                _list_after = _lm_data.get("paging", {}).get("next", {}).get("after")
                if not _list_after:
                    break
            # バッチで企業詳細を取得（100件ずつ）
            for _bi in range(0, len(_member_ids), 100):
                _batch_ids = _member_ids[_bi:_bi + 100]
                _br = _refill_req.post(
                    f"{_hs_base}/crm/v3/objects/companies/batch/read",
                    headers=_refill_headers,
                    json={
                        "inputs": [{"id": i} for i in _batch_ids],
                        "properties": _REFILL_PROPS.split(","),
                    },
                    timeout=20,
                )
                if _br.ok:
                    for _c in _br.json().get("results", []):
                        _entry = _to_candidate(_c)
                        if _entry:
                            candidates.append(_entry)
        else:
            # ── 全企業モード: ページングで最大300件取得 ──
            _after = None
            while len(candidates) < 300:
                _params: dict = {"limit": 100, "properties": _REFILL_PROPS}
                if _after:
                    _params["after"] = _after
                _resp = _refill_req.get(
                    f"{_hs_base}/crm/v3/objects/companies",
                    headers=_refill_headers,
                    params=_params,
                    timeout=15,
                )
                if not _resp.ok:
                    return 0, f"HubSpot APIエラー: {_resp.status_code}"
                _data = _resp.json()
                for _c in _data.get("results", []):
                    _entry = _to_candidate(_c)
                    if _entry:
                        candidates.append(_entry)
                _after = _data.get("paging", {}).get("next", {}).get("after")
                if not _after:
                    break
    except Exception as _e:
        return 0, str(_e)

    if not candidates:
        return 0, None

    # A/B/C均等配分（各33件 → 合計99件、残り1枠はA優先で補完）
    TARGET = 100
    PER_RANK = TARGET // 3  # 33

    buckets: dict[str, list[dict]] = {"A": [], "B": [], "C": [], "other": []}
    for _cand in candidates:
        _rank = _cand["リストランク"].upper()
        if _rank in ("A", "B", "C"):
            buckets[_rank].append(_cand)
        else:
            buckets["other"].append(_cand)

    # 各ランクから33件ずつ選択
    selected: list[dict] = []
    for _r in ("A", "B", "C"):
        selected.extend(buckets[_r][:PER_RANK])

    # 100件に満たない場合はA/B/Cの余り→otherで補完
    if len(selected) < TARGET:
        _extra_pool: list[dict] = []
        for _r in ("A", "B", "C"):
            _extra_pool.extend(buckets[_r][PER_RANK:])
        _extra_pool.extend(buckets["other"])
        _shortage = TARGET - len(selected)
        selected.extend(_extra_pool[:_shortage])

    selected = selected[:TARGET]
    if not selected:
        return 0, None

    # チームメンバーが登録されていればラウンドロビンで担当者を割り当て
    # 未登録の場合はトリガーした担当者名（tanto_name）がそのまま入っている
    _team = _load_team_members()
    if _team:
        selected = _assign_members_roundrobin(selected, _team)

    # call_list.csvに追記
    _new_df = pd.DataFrame(selected)
    # 全カラム揃える
    for _col in _CALL_LIST_COLS:
        if _col not in _new_df.columns:
            _new_df[_col] = ""
    _new_df = _new_df[_CALL_LIST_COLS]
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    _header = not os.path.exists(CALL_LIST_FILE) or os.path.getsize(CALL_LIST_FILE) == 0
    _new_df.to_csv(CALL_LIST_FILE, mode="a", index=False, encoding="utf-8-sig", header=_header)

    return len(_new_df), None


# 商談一覧 全カラム定義
_MEETING_COLS = [
    "記録日", "アポ獲得月", "アポ獲得者", "リストアップ", "会社名",
    "アポ獲得概要", "アポ担当", "前確認実施済", "アポ獲得日", "アポ実施予定日",
    "実施の有無", "商談結果", "契約", "責任者の有無", "アポ実施担当者",
    "失注理由", "失注理由（詳細）", "業種", "企業URL",
    "再アプローチ担当", "アプローチ担当名", "役職", "電話番号",
    "ステータス", "見込み", "アプローチ内容", "次回アプローチ日",
]


def load_meetings() -> pd.DataFrame:
    """商談記録をCSVから読み込む（後方互換: 不足列がない場合は空列追加）"""
    if os.path.exists(MEETINGS_FILE):
        try:
            df = pd.read_csv(MEETINGS_FILE, encoding="utf-8-sig")
            # 旧カラム名「企業名」→「会社名」に自動マイグレーション
            if "企業名" in df.columns and "会社名" not in df.columns:
                df = df.rename(columns={"企業名": "会社名"})
                df.to_csv(MEETINGS_FILE, index=False, encoding="utf-8-sig")
            for col in _MEETING_COLS:
                if col not in df.columns:
                    df[col] = ""
            return df
        except Exception:
            pass
    return pd.DataFrame(columns=_MEETING_COLS)


# ──────────────────────────────
# HubSpot 活動記録同期
# ──────────────────────────────

def _hubspot_find_company_id(name: str, token: str) -> str | None:
    """会社名でHubSpot社IDを検索して返す。見つからなければNone。"""
    import requests as _r
    try:
        resp = _r.post(
            "https://api.hubapi.com/crm/v3/objects/companies/search",
            json={"filterGroups": [{"filters": [{"propertyName": "name", "operator": "EQ", "value": name}]}], "limit": 1},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=10,
        )
        if resp.ok:
            results = resp.json().get("results", [])
            if results:
                return results[0]["id"]
    except Exception:
        pass
    return None


def _hubspot_push_call_note(company_name: str, result: str, memo: str, tantosha: str, token: str) -> bool:
    """
    架電結果をHubSpotにNoteとして登録し、会社に紐付ける。
    戻り値: 成功=True / 失敗=False
    """
    import requests as _r
    from datetime import datetime as _dt
    if not token:
        return False

    # ① 会社IDを検索
    company_id = _hubspot_find_company_id(company_name, token)

    # ② ノート本文を組み立て
    body_lines = [
        f"【架電記録】",
        f"担当: {tantosha}" if tantosha else "",
        f"結果: {result}",
        f"備考: {memo}" if memo else "",
    ]
    note_body = "\n".join(l for l in body_lines if l)
    ts_ms = int(_dt.now().timestamp() * 1000)

    try:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        resp = _r.post(
            "https://api.hubapi.com/crm/v3/objects/notes",
            json={"properties": {"hs_note_body": note_body, "hs_timestamp": str(ts_ms)}},
            headers=headers,
            timeout=10,
        )
        if not resp.ok:
            return False
        note_id = resp.json().get("id")

        # ③ 会社に紐付け（会社が見つかった場合のみ）
        if company_id and note_id:
            _r.put(
                f"https://api.hubapi.com/crm/v3/objects/notes/{note_id}/associations/companies/{company_id}/note_to_company",
                headers=headers,
                timeout=10,
            )
        return True
    except Exception:
        return False


def _hubspot_push_meeting_note(company_name: str, contact: str, phase: str, result: str, memo: str, tantosha: str, token: str) -> bool:
    """商談記録をHubSpotにNoteとして登録し、会社に紐付ける。"""
    import requests as _r
    from datetime import datetime as _dt
    if not token:
        return False

    company_id = _hubspot_find_company_id(company_name, token)
    body_lines = [
        "【商談記録】",
        f"パスアポ者: {tantosha}" if tantosha else "",
        f"相手担当者: {contact}" if contact else "",
        f"フェーズ: {phase}",
        f"結果: {result}",
        f"備考: {memo}" if memo else "",
    ]
    note_body = "\n".join(l for l in body_lines if l)
    ts_ms = int(_dt.now().timestamp() * 1000)

    try:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        resp = _r.post(
            "https://api.hubapi.com/crm/v3/objects/notes",
            json={"properties": {"hs_note_body": note_body, "hs_timestamp": str(ts_ms)}},
            headers=headers,
            timeout=10,
        )
        if not resp.ok:
            return False
        note_id = resp.json().get("id")
        if company_id and note_id:
            _r.put(
                f"https://api.hubapi.com/crm/v3/objects/notes/{note_id}/associations/companies/{company_id}/note_to_company",
                headers=headers,
                timeout=10,
            )
        return True
    except Exception:
        return False


def _hubspot_push_deal(deal_data: dict, token: str) -> bool:
    """
    商談一覧データをHubSpotの取引（Deal）として登録し、会社と紐付ける。
    """
    import requests as _r
    from datetime import datetime as _dt
    if not token:
        return False

    company_name = deal_data.get("企業名", "")
    company_id = _hubspot_find_company_id(company_name, token) if company_name else None

    # HubSpotのDealステージをマッピング
    result = deal_data.get("商談結果", "")
    jisshi = deal_data.get("実施の有無", "")
    if "受注" in result or "契約" in result:
        stage = "closedwon"
    elif "失注" in result or "NG" in result:
        stage = "closedlost"
    elif jisshi and jisshi not in ("", "未実施"):
        stage = "qualifiedtobuy"
    else:
        stage = "appointmentscheduled"

    deal_name = f"{company_name} - {deal_data.get('アポ獲得概要', '')}" if deal_data.get('アポ獲得概要') else company_name
    props = {
        "dealname":  deal_name,
        "dealstage": stage,
        "pipeline":  "default",
    }
    if deal_data.get("アポ実施予定日"):
        props["closedate"] = deal_data["アポ実施予定日"]
    if deal_data.get("アポ獲得月"):
        props["description"] = f"アポ獲得月: {deal_data['アポ獲得月']}"

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        resp = _r.post(
            "https://api.hubapi.com/crm/v3/objects/deals",
            json={"properties": props},
            headers=headers,
            timeout=10,
        )
        if not resp.ok:
            return False
        deal_id = resp.json().get("id")

        # 会社に紐付け
        if company_id and deal_id:
            _r.put(
                f"https://api.hubapi.com/crm/v3/objects/deals/{deal_id}/associations/companies/{company_id}/deal_to_company",
                headers=headers,
                timeout=10,
            )
        return True
    except Exception:
        return False


# ──────────────────────────────
# リストアップ担当者カウント管理
# ──────────────────────────────

_LISTUP_WORKERS_FILE = os.path.join(OUTPUT_DIR, "listup_workers.json")


def _load_listup_workers() -> dict:
    """担当者ごとのリストアップ回数を返す。"""
    try:
        if os.path.exists(_LISTUP_WORKERS_FILE):
            with open(_LISTUP_WORKERS_FILE, "r", encoding="utf-8") as f:
                return _json_mod.load(f)
    except Exception:
        pass
    return {}


def _increment_listup_worker(name: str) -> int:
    """担当者のリストアップ回数を1増やし、新しい回数を返す。"""
    workers = _load_listup_workers()
    workers[name] = workers.get(name, 0) + 1
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        with open(_LISTUP_WORKERS_FILE, "w", encoding="utf-8") as f:
            _json_mod.dump(workers, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return workers[name]


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


def _load_team_members() -> list[str]:
    """登録済みチームメンバー名のリストを返す"""
    return _load_import_settings("team_members").get("names", [])


def _save_team_members(names: list[str]) -> None:
    """チームメンバー名のリストを保存する"""
    _save_import_settings("team_members", {"names": names})


def _assign_members_roundrobin(entries: list[dict], members: list[str]) -> list[dict]:
    """
    entriesの各行にメンバーをラウンドロビンで架電担当者名として割り当てる。
    割り当て開始位置はimport_settings.jsonに記録し、次回はその続きから始める。
    """
    if not members or not entries:
        return entries
    # 前回の終了インデックスを読み込む（続きから割り当てるため）
    start_idx = _load_import_settings("team_members_rr").get("next_idx", 0) % len(members)
    for i, entry in enumerate(entries):
        entry["架電担当者名"] = members[(start_idx + i) % len(members)]
    # 次回の開始インデックスを保存
    next_idx = (start_idx + len(entries)) % len(members)
    _save_import_settings("team_members_rr", {"next_idx": next_idx})
    return entries


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


def _normalize_pending_items(items: list[dict]) -> list[dict]:
    """daemon形式（ネスト）とbatch形式（フラット）を統一してフラットリストに変換する"""
    result = []
    for item in items:
        if "company_info" in item:
            # daemon形式: {"company_info": {...}, "rank_result": {...}, "search_query": "..."}
            info = item["company_info"]
            rank_result = item.get("rank_result", {})
            flat = {
                "日時":    info.get("scraped_at", ""),
                "ランク":   rank_result.get("rank", ""),
                "会社名":   info.get("company_name", ""),
                "企業URL":  info.get("company_url", ""),
                "代表氏名":  info.get("representative", ""),
                "電話番号":  info.get("phone", ""),
                "郵便番号":  info.get("zip_code", ""),
                "都道府県":  info.get("prefecture", ""),
                "所在地":   info.get("address", ""),
                "業種":    info.get("industry", ""),
                "従業員数":  info.get("employee_count", ""),
                "備考":    info.get("notes", ""),
                "元URL":   info.get("source_url", ""),
            }
            result.append(flat)
        else:
            # batch形式: すでにフラット
            result.append(item)
    return result


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
    pending_path = os.path.join(OUTPUT_DIR, "pending_review.json")

    if not os.path.exists(pending_path):
        st.info("pending_review.json が見つかりません。デーモンを起動するとここにリストが溜まります。")
        return

    with open(pending_path, "r", encoding="utf-8") as _f:
        pending_raw = _jr.load(_f)

    if not pending_raw:
        st.info("確認待ちの候補がありません。")
        return

    # daemon形式（ネスト）とbatch形式（フラット）を統一
    pending = _normalize_pending_items(pending_raw)

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
        width="stretch",
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
        if st.button("承認した企業を保存", type="primary", width="stretch"):
            # 承認した企業を approved_companies.csv に追記
            approved_csv = os.path.join(_LIST_TOOL_DIR_local, "output", "approved_companies.csv")
            header = not os.path.exists(approved_csv)
            approved.to_csv(approved_csv, mode="a", index=False, encoding="utf-8-sig", header=header)
            # 却下した企業だけ pending_review.json に残す（承認済みは削除）
            rejected = edited[edited["承認"] == False].drop(columns=["承認"])
            with open(pending_path, "w", encoding="utf-8") as _f:
                _jr.dump(rejected.to_dict(orient="records"), _f, ensure_ascii=False, indent=2)
            st.success(f"{len(approved)}件を approved_companies.csv に保存しました。残り: {len(rejected)}件")
            st.rerun()
    with col_clear:
        if st.button("クリア（リストを消去）", width="stretch"):
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
# call_list.csv をスクリプト実行ごとに1回だけ読み込む
# （全タブで使い回し、書き込み後は st.rerun() で再読み込みされる）
# ──────────────────────────────
_df_call_list = load_call_list()


# ──────────────────────────────
# TAB: 見込みリスト
# 次回アプローチ日が過去になった企業を「日程近い順 × リストランク」で表示する
# ──────────────────────────────
with tab_kaiden_zumi:
    st.subheader("見込みリスト")
    st.caption("次回アプローチ日が過ぎた企業を表示します。日程が近い順 × ランク（A→B→C）で並べています。")

    from datetime import date as _kz_date
    _kz_today = str(_kz_date.today())

    _kz_df = _df_call_list.copy()

    # 次回アプローチ日が空でなく、今日以前のものを抽出
    _kz_mask = (
        (_kz_df["次回アプローチ日"] != "") &
        (_kz_df["次回アプローチ日"] <= _kz_today)
    )
    _kz_list = _kz_df[_kz_mask].copy()

    # ランクを数値に変換してソートキーに使う（A=1, B=2, C=3, その他=4）
    _RANK_ORDER = {"A": 1, "B": 2, "C": 3}
    _kz_list["_rank_order"] = (
        _kz_list["リストランク"].str.upper().map(_RANK_ORDER).fillna(4).astype(int)
    )
    # 次回アプローチ日（近い順）→ ランク（A優先）の2段ソート
    _kz_list = (
        _kz_list
        .sort_values(["次回アプローチ日", "_rank_order"], ascending=[True, True])
        .drop(columns=["_rank_order"])
        .reset_index(drop=True)
    )

    if _kz_list.empty:
        st.info("次回アプローチ日が過ぎた企業はありません。")
    else:
        # ── フィルター行（担当者・会社名検索）──
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

        # ── テーブル表示（ランク・日程が一目でわかる列順）──
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

        # ── 会社選択（表示順のまま選べるように）──
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

            # ── 入力フォーム ──
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

                # 担当者のブランク件数チェック → 50件未満なら自動補充
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
# TAB2: 履歴
# ──────────────────────────────
with tab_history:
    st.subheader("架電履歴")

    df_fb = load_feedback()

    if df_fb.empty:
        st.info("まだ記録がありません。「コール記録」タブから入力してください。")
    else:
        # フィルター
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

        # CSVダウンロード
        csv_bytes = filtered.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button(
            "📥 CSVダウンロード",
            data=csv_bytes,
            file_name="feedback_export.csv",
            mime="text/csv",
        )


# ──────────────────────────────
# TAB3: ダッシュボード
# ──────────────────────────────
with tab_analysis:
    st.subheader("ダッシュボード")

    dash_integrated, dash_call, dash_meeting = st.tabs(["📊 統合", "📞 架電", "🤝 商談"])

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

        # 担当者別サマリー
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

                # 商談・契約データを結合
                if not _df_mt_d.empty and "担当名" in _df_mt_d.columns:
                    _mt_tanto = _df_mt_d[_df_mt_d["担当名"].notna() & (_df_mt_d["担当名"] != "")].groupby("担当名").agg(
                        商談数=("会社名", "count"),
                        契約数=("契約", lambda x: (x == "はい").sum()),
                    ).reset_index()
                    _tanto_summary = _tanto_summary.merge(_mt_tanto, on="担当名", how="left").fillna(0)
                    _tanto_summary["商談数"] = _tanto_summary["商談数"].astype(int)
                    _tanto_summary["契約数"] = _tanto_summary["契約数"].astype(int)

                st.dataframe(_tanto_summary, width="stretch", hide_index=True)

                # 担当者別架電数グラフ
                _tanto_chart = alt.Chart(_tanto_summary).mark_bar(color="#4C78A8").encode(
                    x=alt.X("担当名:N", axis=alt.Axis(labelAngle=0, labelFontSize=13)),
                    y=alt.Y("架電数:Q"),
                    tooltip=["担当名", "架電数", "アポ数", "アポ率(%)"],
                ).properties(height=220, title="担当者別 架電数")
                st.altair_chart(_tanto_chart, width="stretch")

    # ── 架電ダッシュボード ─────────────────────────────────────────
    with dash_call:
        df_fb = load_feedback()

        if df_fb.empty:
            st.info("データが溜まったら分析できます。まずコール記録を入力してください。")
        else:
            total = len(df_fb)
            apo_count = (df_fb["アポ獲得"] == "はい").sum()
            apo_rate = apo_count / total * 100 if total > 0 else 0

            # KPI
            col_k1, col_k2, col_k3, col_k4 = st.columns(4)
            col_k1.metric("総架電数", f"{total}件")
            col_k2.metric("アポ獲得数", f"{apo_count}件")
            col_k3.metric("アポ獲得率", f"{apo_rate:.1f}%")
            rank_a = (df_fb["温度感"] == "A").sum()
            col_k4.metric("見込みランクA", f"{rank_a}件")

            st.divider()

            col_g1, col_g2 = st.columns(2)

            with col_g1:
                st.markdown("**架電結果の内訳**")
                result_counts = df_fb["アプローチ結果"].value_counts().reset_index()
                result_counts.columns = ["結果", "件数"]
                chart_r = alt.Chart(result_counts).mark_bar(color="#4C78A8").encode(
                    x=alt.X("結果:N", sort="-y", axis=alt.Axis(labelAngle=0, labelFontSize=12)),
                    y=alt.Y("件数:Q"),
                    tooltip=["結果", "件数"],
                ).properties(height=250)
                st.altair_chart(chart_r, width="stretch")

            with col_g2:
                st.markdown("**断り理由の内訳**")
                rejection_df = df_fb[df_fb["断り理由"].notna() & (df_fb["断り理由"] != "")]
                if not rejection_df.empty:
                    rejection_counts = rejection_df["断り理由"].value_counts().reset_index()
                    rejection_counts.columns = ["理由", "件数"]
                    chart_rej = alt.Chart(rejection_counts).mark_bar(color="#F58518").encode(
                        x=alt.X("理由:N", sort="-y", axis=alt.Axis(labelAngle=0, labelFontSize=12)),
                        y=alt.Y("件数:Q"),
                        tooltip=["理由", "件数"],
                    ).properties(height=250)
                    st.altair_chart(chart_rej, width="stretch")
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
                            rank_chart_df = rank_df.reset_index()
                            rank_chart_df.columns = ["ランク", "アポ率(%)"]
                            chart_rank = alt.Chart(rank_chart_df).mark_bar(color="#54A24B").encode(
                                x=alt.X("ランク:N", sort=None, axis=alt.Axis(labelAngle=0, labelFontSize=14)),
                                y=alt.Y("アポ率(%):Q"),
                                tooltip=["ランク", "アポ率(%)"],
                            ).properties(height=200)
                            st.altair_chart(chart_rank, width="stretch")

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
                        st.dataframe(sig_df, width="stretch", hide_index=True)

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

            # 見込みランクA・Bの企業一覧（次のフォロー候補）
            st.markdown("**見込みランクA・Bの企業（フォロー候補）**")
            warm = df_fb[df_fb["温度感"].isin(["A", "B"])].sort_values("温度感")
            if not warm.empty:
                st.dataframe(
                    warm[["記録日", "会社名", "アプローチ結果", "温度感", "断り理由", "反応が良かったポイント", "メモ"]].rename(
                        columns={"温度感": "見込みランク", "アプローチ結果": "架電結果"}
                    ),
                    width="stretch",
                    hide_index=True,
                )
            else:
                st.caption("見込みランクA・Bの記録なし")

            # アポ獲得企業一覧
            st.markdown("**アポ獲得企業一覧**")
            apo_df = df_fb[df_fb["アポ獲得"] == "はい"]
            if not apo_df.empty:
                st.dataframe(
                    apo_df[["記録日", "会社名", "反応が良かったポイント", "メモ"]],
                    width="stretch",
                    hide_index=True,
                )
            else:
                st.caption("アポ獲得記録なし")

            # 担当者別 架電分析（担当名データがある場合）
            if "担当名" in df_fb.columns:
                _tanto_fb = df_fb[df_fb["担当名"].notna() & (df_fb["担当名"] != "")]
                if not _tanto_fb.empty:
                    st.divider()
                    st.markdown("**担当者別 架電数・アポ率**")
                    _tanto_fb_grp = _tanto_fb.groupby("担当名").agg(
                        架電数=("会社名", "count"),
                        アポ数=("アポ獲得", lambda x: (x == "はい").sum()),
                    ).reset_index()
                    _tanto_fb_grp["アポ率(%)"] = (_tanto_fb_grp["アポ数"] / _tanto_fb_grp["架電数"] * 100).round(1)
                    _tc1, _tc2 = st.columns(2)
                    with _tc1:
                        st.dataframe(_tanto_fb_grp, width="stretch", hide_index=True)
                    with _tc2:
                        _tanto_chart2 = alt.Chart(_tanto_fb_grp).mark_bar(color="#54A24B").encode(
                            x=alt.X("担当名:N", axis=alt.Axis(labelAngle=0, labelFontSize=13)),
                            y=alt.Y("アポ率(%):Q"),
                            tooltip=["担当名", "架電数", "アポ数", "アポ率(%)"],
                        ).properties(height=200)
                        st.altair_chart(_tanto_chart2, width="stretch")

    # ── 商談ダッシュボード ─────────────────────────────────────────
    with dash_meeting:
        _df_mt_dash2 = load_meetings() if os.path.exists(MEETINGS_FILE) else pd.DataFrame()
        if _df_mt_dash2.empty:
            st.info("商談データが溜まったら分析できます。「商談記録」タブから入力してください。")
        else:
            _total_mt2   = len(_df_mt_dash2)
            _contract_mt = (_df_mt_dash2["契約"] == "はい").sum()
            _cv_mt       = _contract_mt / _total_mt2 * 100 if _total_mt2 > 0 else 0
            _pending_mt  = _df_mt_dash2[_df_mt_dash2["商談結果"].isin(["検討中", "次回アポあり", "保留"])].shape[0]

            mk1, mk2, mk3, mk4 = st.columns(4)
            mk1.metric("総商談数",  f"{_total_mt2}件")
            mk2.metric("契約件数",  f"{_contract_mt}件")
            mk3.metric("成約率",    f"{_cv_mt:.1f}%")
            mk4.metric("進行中",    f"{_pending_mt}件")

            st.divider()
            _mdc1, _mdc2 = st.columns(2)
            with _mdc1:
                _ph_col = "フェーズ" if "フェーズ" in _df_mt_dash2.columns else "商談結果"
                _ph_label = _ph_col + "別件数"
                st.markdown(f"**{_ph_label}**")
                _ph_df = _df_mt_dash2[_ph_col].value_counts().reset_index()
                _ph_df.columns = [_ph_col, "件数"]
                _chart_ph = alt.Chart(_ph_df).mark_bar(color="#4C78A8").encode(
                    x=alt.X(f"{_ph_col}:N", sort="-y", axis=alt.Axis(labelAngle=0, labelFontSize=11)),
                    y=alt.Y("件数:Q"),
                    tooltip=[_ph_col, "件数"],
                ).properties(height=250)
                st.altair_chart(_chart_ph, width="stretch")
            with _mdc2:
                st.markdown("**商談結果の内訳**")
                _mr_df = _df_mt_dash2["商談結果"].value_counts().reset_index()
                _mr_df.columns = ["商談結果", "件数"]
                _chart_mr2 = alt.Chart(_mr_df).mark_bar(color="#72B7B2").encode(
                    x=alt.X("商談結果:N", sort="-y", axis=alt.Axis(labelAngle=0, labelFontSize=11)),
                    y=alt.Y("件数:Q"),
                    tooltip=["商談結果", "件数"],
                ).properties(height=250)
                st.altair_chart(_chart_mr2, width="stretch")

            # 担当者別成約率
            if "担当名" in _df_mt_dash2.columns:
                _mt_tanto2 = _df_mt_dash2[_df_mt_dash2["担当名"].notna() & (_df_mt_dash2["担当名"] != "")]
                if not _mt_tanto2.empty:
                    st.divider()
                    st.markdown("**担当者別 商談数・成約率**")
                    _mt_grp = _mt_tanto2.groupby("担当名").agg(
                        商談数=("会社名", "count"),
                        契約数=("契約", lambda x: (x == "はい").sum()),
                    ).reset_index()
                    _mt_grp["成約率(%)"] = (_mt_grp["契約数"] / _mt_grp["商談数"] * 100).round(1)
                    st.dataframe(_mt_grp, width="stretch", hide_index=True)

            # 次のアクションが必要な案件
            st.divider()
            st.markdown("**進行中案件**")
            _prog_mask = _df_mt_dash2["商談結果"].isin(["検討中", "次回アポあり", "保留"])
            if "次のアクション" in _df_mt_dash2.columns:
                _prog_mask = _prog_mask & _df_mt_dash2["次のアクション"].notna() & (_df_mt_dash2["次のアクション"] != "")
            _action_needed = _df_mt_dash2[_prog_mask]
            _sort_col = "商談日" if "商談日" in _action_needed.columns else "記録日"
            if _sort_col in _action_needed.columns:
                _action_needed = _action_needed.sort_values(_sort_col, ascending=False)
            if not _action_needed.empty:
                _show_mt_cols = [c for c in ["記録日", "会社名", "アポ担当", "商談結果", "アプローチ内容", "次回アプローチ日"] if c in _action_needed.columns]
                st.dataframe(_action_needed[_show_mt_cols], width="stretch", hide_index=True)
            else:
                st.caption("対象なし")


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
                st.dataframe(df_raw.head(5), width="stretch", hide_index=True)

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
                    st.dataframe(pd.DataFrame(preview_rows[:5]), width="stretch", hide_index=True)

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

    # ── フィードバック学習 ──────────────────────────────────────────
    with st.expander("🧠 精度学習（架電・商談フィードバックを反映）", expanded=False):
        st.caption("架電結果・商談結果を分析してシグナルウェイトを自動更新します。リストアップ開始時にも自動実行されます。")
        _fl_col1, _fl_col2 = st.columns([1, 3])
        with _fl_col1:
            _fl_btn = st.button("学習を実行", key="run_feedback_learning", type="primary")
        with _fl_col2:
            # 前回の学習日時を表示
            _wf_path = os.path.join(_LIST_TOOL_DIR, "output", "signal_weights.json")
            if os.path.exists(_wf_path):
                try:
                    import json as _wj
                    with open(_wf_path, encoding="utf-8") as _wf:
                        _wd = _wj.load(_wf)
                    st.caption(f"前回学習: {_wd.get('_updated', '未実行')}")
                except Exception:
                    pass

        if _fl_btn:
            with st.spinner("フィードバック学習中..."):
                try:
                    from agents.feedback_learner import run_learning as _run_fl
                    _fl_result = _run_fl()
                    _fl_stats = _fl_result.get("stats", {})
                    _fl_updates = _fl_result.get("signal_updates", {})
                    st.success(
                        f"学習完了 — 成功{_fl_stats.get('success',0)}社 / 失敗{_fl_stats.get('failure',0)}社 / "
                        f"成約{_fl_stats.get('contract',0)}社 → {len(_fl_updates)}シグナル更新"
                    )
                    if _fl_updates:
                        import pandas as _fl_pd
                        _fl_rows = []
                        for sig, upd in _fl_updates.items():
                            direction = "↑" if upd["new"] > upd["old"] else ("↓" if upd["new"] < upd["old"] else "→")
                            _fl_rows.append({
                                "シグナル": sig,
                                "変化": direction,
                                "旧ウェイト": upd["old"],
                                "新ウェイト": upd["new"],
                                "アポ率": f"{upd['apo_rate']:.0%}",
                                "サンプル数": upd["samples"],
                            })
                        st.dataframe(_fl_pd.DataFrame(_fl_rows), width="stretch", hide_index=True)
                    if _fl_stats.get("unmatched", 0) > 0:
                        st.caption(f"※ {_fl_stats['unmatched']}社はresults.csvと突合できませんでした（リストアップ前の手動インポート分など）")
                    # rank_agentのウェイトキャッシュをリロード
                    import agents.rank_agent as _ra_reload
                    _ra_reload._W = _ra_reload._load_weights()
                except Exception as _fle:
                    st.error(f"学習エラー: {_fle}")

    # ── 担当者設定（複数人同時実行時のキーワード分散）────────────────
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

        # 担当者カウントを更新してキーワードオフセットを決定
        _lu_offset = 0
        if lu_worker_name:
            _lu_offset = _increment_listup_worker(lu_worker_name)
            # オフセット分キーワードを後ろにずらす（手動モードのみ即効）
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
            # キーワードオフセットを環境変数で渡す（main.pyが対応している場合に活用）
            _lu_env_offset = str(_lu_offset)

            st.info(f"実行コマンド: `{' '.join(cmd)}`")

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
                # バックグラウンドで起動し、スレッドで出力を読み込む
                import threading as _thr
                _LISTUP_STATE.update({
                    "proc": _lu_proc, "lines": [],
                    "running": True, "done": False, "return_code": None,
                })
                _thr.Thread(target=_listup_reader_thread, args=(_lu_proc,), daemon=True).start()
                st.rerun()
            except Exception as _lu_e:
                st.error(f"実行エラー: {_lu_e}")

    # ── 実行中・完了時の出力表示（2秒ごとに自動更新）──────────────
    if _LISTUP_STATE["running"] or _LISTUP_STATE["done"]:
        from streamlit_autorefresh import st_autorefresh as _lu_refresh
        if _LISTUP_STATE["running"]:
            _lu_refresh(interval=2000, key="listup_autorefresh")
            st.info("🔄 リストアップ実行中… 画面は2秒ごとに自動更新されます。このまま他のタブで架電記録できます。")
        elif _LISTUP_STATE["done"]:
            if _LISTUP_STATE["return_code"] == 0:
                st.success("✅ リストアップ完了！ 架電先リストに追加されました。")
                if st.button("ログをクリア", key="lu_clear_log"):
                    _LISTUP_STATE.update({"lines": [], "done": False, "return_code": None})
                    st.rerun()
            else:
                st.error(f"異常終了しました（終了コード: {_LISTUP_STATE['return_code']}）")

        if _LISTUP_STATE["lines"]:
            st.code("\n".join(_LISTUP_STATE["lines"][-100:]), language=None)

    # ── 前回の確認待ちが残っていれば常に表示 ──────────────────────
    _pending_path_check = os.path.join(OUTPUT_DIR, "pending_review.json")
    if os.path.exists(_pending_path_check) and not run_btn:
        st.divider()
        st.caption("前回の確認モード結果が残っています。")
        _show_pending_review_ui()

    # ── インライン架電記録（リストアップ中でも使える）────────────
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

                # 会社情報を表示
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
                    # 担当者のブランク件数チェック → 50件未満なら自動補充
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

            # チェックボックス列をbool型に変換して表示
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
                # bool → 文字列に戻す
                _save_df = edited_cl.copy()
                for _bc in ["アポ獲得", "条件NG"]:
                    if _bc in _save_df.columns:
                        _save_df[_bc] = _save_df[_bc].apply(lambda v: "○" if v is True else "")

                # CSVに保存
                df_clist_updated = df_clist.copy()
                for i, orig_idx in enumerate(filtered_cl.index):
                    for col in _editable_cols:
                        if col in show_cols and col in _save_df.columns:
                            df_clist_updated.at[orig_idx, col] = _save_df.iloc[i][col]
                df_clist_updated.to_csv(CALL_LIST_FILE, index=False, encoding="utf-8-sig")

                # HubSpotに反映（hs_idがある行のみ）
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

                # 保存された担当者ごとにブランク件数をチェック → 50件未満なら自動補充
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

            # 自動保存トリガー（30分ごとのオートリフレッシュで発火）
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
                # data_editorのセッション状態をクリアして保存済みデータと整合させる
                st.session_state.pop("cl_data_editor", None)
                st.toast(f"自動保存しました（{st.session_state['last_autosave_ts']}）")
                st.rerun()

            csv_cl = filtered_cl[show_cols].to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button("📥 CSVダウンロード", data=csv_cl, file_name="call_list_export.csv", mime="text/csv", key="cl_dl")

    # ── インポート ─────────────────────────────────────────────────
    with cl_import:
        cl_saved = _load_import_settings("calllist")

        # ── HubSpotから直接読み込む ────────────────────────────────
        from config import HUBSPOT_TOKEN
        if HUBSPOT_TOKEN:
            st.markdown("### 🔗 HubSpotから読み込む（推奨）")
            st.caption("リストアップで登録した企業を自動取得します。新規登録分も随時反映できます。")

            # ── HubSpotリスト一覧を取得する関数 ──────────────────────
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

            # ── 初回ロード時に自動取得 ────────────────────────────────
            if "hs_lists_cache" not in st.session_state:
                with st.spinner("HubSpotリスト一覧を取得中..."):
                    _auto_lists, _auto_err = _fetch_hs_lists()
                if _auto_err:
                    st.warning(f"リスト自動取得に失敗しました: {_auto_err}")
                    st.session_state["hs_lists_cache"] = []
                else:
                    st.session_state["hs_lists_cache"] = _auto_lists or []

            # ── リスト選択 ──────────────────────────────────────────
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

            # 選択リストIDを解析
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
                            # ── リスト指定：メンバーIDを取得してバッチで詳細取得 ──
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
                            # バッチで企業詳細取得（100件ずつ）
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
                            # ── 指定なし：全企業を取得 ──
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
                                    # 架電記録カスタムプロパティ
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

        cl_df_raw: pd.DataFrame | None = None
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
                import csv as _csv_cl
                os.makedirs(OUTPUT_DIR, exist_ok=True)

                def _cl_v(row, col):
                    return str(row.get(col, "")).strip() if col != "（使わない）" else ""

                new_cl_rows = []
                for _, row in cl_df_raw.iterrows():
                    company = _cl_v(row, cl_c_company)
                    if not company:
                        continue
                    new_cl_rows.append({
                        # 静的列
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
                        # 活動列（既存スプレッドシートからの移行）
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

            # フィルター（架電担当者名で絞り込んでから会社を選択）
            cl_inline_persons = ["全員"] + sorted(df_clist_inline["架電担当者名"].dropna().replace("", pd.NA).dropna().unique().tolist())
            il_person_filter = st.selectbox("架電担当者名で絞り込む", cl_inline_persons, key="il_person_filter")

            if il_person_filter != "全員":
                il_companies = df_clist_inline[df_clist_inline["架電担当者名"] == il_person_filter]["会社名"].tolist()
            else:
                il_companies = df_clist_inline["会社名"].tolist()

            il_selected = st.selectbox("架電する会社を選択", il_companies, key="il_company_select")

            if il_selected:
                il_row = df_clist_inline[df_clist_inline["会社名"] == il_selected].iloc[0]

                # 会社情報パネル
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

                    # call_list.csv を更新（最新状態を上書き）
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

                    # feedback.csv にも追記（PDCA履歴）
                    record_feedback(
                        company_name=il_selected,
                        approach_result=il_result,
                        got_appointment=il_apo in ("○", "〇"),
                        temperature=il_mikomi,
                        memo=il_memo,
                        tantosha=il_tantosha,
                    )

                    # HubSpot同期（オプション）
                    if _il_sync_hs and _IL_HS_TOKEN:
                        _ok = _hubspot_push_call_note(il_selected, il_result, il_memo, il_tantosha, _IL_HS_TOKEN)
                        if _ok:
                            st.success(f"記録しました: **{il_selected}** — {il_result}　✅ HubSpotにも同期済み")
                        else:
                            st.warning(f"記録しました: **{il_selected}** — {il_result}　⚠️ HubSpot同期に失敗しました")
                    else:
                        st.success(f"記録しました: **{il_selected}** — {il_result}")

                    # 担当者のアプローチ内容ブランクが50件未満なら自動補充
                    if il_tantosha:
                        with st.spinner(f"「{il_tantosha}」のリスト残数を確認中..."):
                            _il_added, _il_refill_err = _auto_refill_from_hubspot(il_tantosha)
                        if _il_refill_err:
                            st.warning(f"自動補充エラー: {_il_refill_err}")
                        elif _il_added > 0:
                            st.info(f"🔄 「{il_tantosha}」のリスト残数が少ないため {_il_added}件を自動補充しました（A/B/C均等）")
                    st.rerun()

# ──────────────────────────────
# TAB: 商談一覧
# ──────────────────────────────

def _save_meeting_row(row_data: dict):
    """商談一覧CSVに1行追記する。受注/失注はキーワード学習にも反映する。"""
    import csv as _csv_m
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    file_exists = os.path.exists(MEETINGS_FILE) and os.path.getsize(MEETINGS_FILE) > 0
    with open(MEETINGS_FILE, "a", newline="", encoding="utf-8-sig") as f:
        writer = _csv_m.DictWriter(f, fieldnames=_MEETING_COLS, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerow(row_data)

    # 商談結果をキーワード学習に反映
    try:
        from config import _find_query_for_company, _find_domain_for_company, load_exclude_list_csv, add_to_exclude_csv
        from agents.keyword_agent import record_ng, record_rank_result

        company = row_data.get("会社名", "")
        result  = row_data.get("商談結果", "")
        mikomi  = row_data.get("見込み", "")
        query   = _find_query_for_company(company)

        if query:
            if "受注" in result or "契約" in result:
                record_rank_result(query, "A")   # 受注 → Aランク学習
            elif "失注" in result or "NG" in result:
                record_ng(query)                  # 失注 → NGクエリ学習

        # 失注した場合はドメインを除外リストに追加
        if "失注" in result or "NG" in result:
            domain = _find_domain_for_company(company)
            if domain and domain not in load_exclude_list_csv():
                add_to_exclude_csv(domain, f"商談失注: {result}")
    except Exception:
        pass


with tab_meeting:
    st.subheader("商談一覧")

    mtab_input, mtab_list, mtab_pipeline, mtab_import = st.tabs(["✏️ 新規入力", "📋 一覧・検索", "📊 集計", "📥 インポート"])

    # ── 新規入力 ────────────────────────────────────────────────
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

    # ── 一覧・検索 ──────────────────────────────────────────────
    with mtab_list:
        df_mt = load_meetings()
        if df_mt.empty:
            st.info("まだ商談記録がありません。「新規入力」から登録してください。")
        else:
            # フィルター
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
                filtered_mt = filtered_mt[filtered_mt["企業名"].str.contains(mt_search, na=False)]

            st.caption(f"表示: {len(filtered_mt)}件")

            # 表示列（主要列を先に）
            _mt_show_cols = [c for c in [
                "記録日", "アポ獲得月", "企業名", "アポ獲得者", "アポ担当",
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

    # ── 集計 ───────────────────────────────────────────────────
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

            # 次回アプローチ要対応一覧
            st.divider()
            st.markdown("**次回アプローチ要対応**")
            _action_df = df_mt[
                df_mt["次回アプローチ日"].replace("", pd.NA).notna() &
                ~df_mt["商談結果"].str.contains("受注|失注", na=False)
            ].sort_values("次回アプローチ日")
            if not _action_df.empty:
                st.dataframe(
                    _action_df[[c for c in ["企業名", "アポ実施担当者", "商談結果", "見込み", "次回アプローチ日", "アプローチ内容"] if c in _action_df.columns]],
                    width="stretch", hide_index=True,
                )
            else:
                st.caption("対象なし")

    # ── インポート ──────────────────────────────────────────────
    with mtab_import:
        st.caption("CSV / Excel / Googleスプレッドシートから商談記録を一括取り込みできます。")

        mi_saved = _load_import_settings("meeting_import")

        mi_src_mode = st.radio(
            "ファイルの指定方法",
            ["📂 パスを直接入力", "⬆️ アップロード", "🔗 Googleスプレッドシート"],
            horizontal=True,
            key="mi_src_mode",
        )

        mi_df_raw: pd.DataFrame | None = None
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

                # インポートした会社を results.csv に自動補完（未登録分のみスクレイピング）
                _mi_names = [r.get("会社名", "") for r in new_mi_rows if r.get("会社名")]
                if _mi_names:
                    try:
                        from agents.supplement_agent import supplement_results_csv
                        with st.spinner(f"企業情報をスクレイピング中（{len(_mi_names)}社）..."):
                            _mi_added = supplement_results_csv(_mi_names, max_companies=50)
                        if _mi_added > 0:
                            st.info(f"📊 リストアップ情報を {_mi_added}社 補完しました（学習精度が向上します）")
                    except Exception as _mi_sup_e:
                        st.caption(f"補完スクレイピングをスキップ: {_mi_sup_e}")

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

# ──────────────────────────────
# TAB: システム診断
# ──────────────────────────────
with tab_monitor:
    st.subheader("システム診断")
    st.caption("ファイル整合性・ウェイト異常・学習状況をチェックし、問題があれば自動修復します。")

    if st.button("診断を実行", type="primary", key="run_monitor"):
        with st.spinner("チェック中..."):
            try:
                from agents.monitor_agent import run_check as _run_check
                _mc_result = _run_check()
                st.session_state["monitor_result"] = _mc_result
            except Exception as _me:
                st.error(f"モニターエラー: {_me}")

    _mr = st.session_state.get("monitor_result")
    if _mr:
        # サマリーバッジ
        _checked_at = _mr.get("checked_at", "")
        if _mr["has_error"]:
            st.error(f"エラーあり — {_checked_at}")
        elif _mr["has_warn"]:
            st.warning(f"警告あり — {_checked_at}")
        else:
            st.success(f"全て正常 — {_checked_at}")

        # チェック結果テーブル
        _status_icon = {"ok": "✅", "warn": "⚠️", "error": "❌", "fixed": "🔧"}
        for _c in _mr["checks"]:
            icon = _status_icon.get(_c["status"], "❓")
            st.markdown(f"{icon} **{_c['name']}** — {_c['message']}")

        # 自動修復ログ
        if _mr["repairs"]:
            st.divider()
            st.markdown("**自動修復した項目:**")
            for _r in _mr["repairs"]:
                st.markdown(f"- {_r}")

    # ── チームメンバー設定 ────────────────────────────────────────
    st.divider()
    st.markdown("#### チームメンバー設定（架電担当者の自動割り振り）")
    st.caption("登録したメンバーに、HubSpot自動補充の新規リストをラウンドロビンで割り当てます。未登録の場合はトリガーした担当者に全件割り当てられます。")

    _tm_current = _load_team_members()

    # 現在のメンバー表示 & 削除
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

    # 新規メンバー追加
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

    # ── 自動補充リスト設定 ────────────────────────────────────────
    st.divider()
    st.markdown("#### 自動補充リスト設定")
    st.caption("架電担当者のリスト残数が50件を切ったとき、どのHubSpotリストから補充するかを設定します。未設定の場合はHubSpot全企業が対象になります。")

    from config import HUBSPOT_TOKEN as _MON_HS_TOKEN
    if not _MON_HS_TOKEN:
        st.info("💡 HubSpot連携には環境変数 `HUBSPOT_TOKEN` の設定が必要です。")
    else:
        # 現在の設定を読み込む
        _cur_refill = _load_import_settings("auto_refill_list")
        _cur_list_id = _cur_refill.get("list_id", "")
        _cur_list_name = _cur_refill.get("list_name", "")

        # HubSpotリスト一覧を取得
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

        # 選択肢を作成（先頭に「全企業（指定なし）」）
        _mon_options = ["全企業（指定なし）"] + [f"{l['name']}  [{l['listId']}]" for l in _mon_lists]

        # 現在の設定に対応するインデックスを探す
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

        # 現在の設定を表示
        if _cur_list_id:
            st.caption(f"現在の設定: **{_cur_list_name}** （ID: {_cur_list_id}）")
        else:
            st.caption("現在の設定: **全企業（指定なし）**")

        if st.button("💾 設定を保存", type="primary", key="mon_save_refill_list"):
            if _mon_selected == "全企業（指定なし）":
                # 設定をクリア（全企業モードに戻す）
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

    # ── 新規投稿フォーム ──
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

    # ── 一覧（スプレッドシート形式で編集可能）──
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
