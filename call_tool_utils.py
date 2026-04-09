"""
call_tool_utils.py
共有ユーティリティ — app.py と pages/1_架電ツール.py の両方から import して使う。

含まれるもの:
  - グローバルCSS定数 (_GLOBAL_CSS)
  - apply_global_styles()  : CSS注入 + ロゴヘッダー描画
  - 全カラム定数           : _CALL_LIST_COLS / _MEETING_COLS 等
  - データ読み書き関数      : load_call_list / update_call_list_row 等
  - HubSpot連携関数        : _hubspot_find_company_id 等
  - 担当者・インポート設定  : _load_team_members / _save_import_settings 等
  - pending review UI      : _show_pending_review_ui / _normalize_pending_items 等
  - GSheets ローダーUI     : _render_gsheets_loader
  - 商談読み書き            : load_meetings / _save_meeting_row
"""

import os
import json as _json_mod
import pandas as pd
import streamlit as st

from config import (
    FEEDBACK_FILE, RESULTS_FILE, MEETINGS_FILE,
    CALL_LIST_FILE, IMPORT_SETTINGS_FILE, OUTPUT_DIR,
)

_LIST_TOOL_DIR = os.path.dirname(os.path.abspath(__file__))

# ──────────────────────────────
# グローバルCSS（SaaSライクなUIデザイン）
# ──────────────────────────────
_GLOBAL_CSS = """
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
[data-baseweb="select"],
[data-baseweb="select"] > div,
[data-baseweb="select"] > div > div {
    background-color: #ffffff !important;
    color: #111827 !important;
    border-color: #d1d5db !important;
    border-radius: 6px !important;
    font-size: 0.875rem !important;
}
[data-baseweb="select"] [class*="singleValue"],
[data-baseweb="select"] [class*="placeholder"],
[data-baseweb="select"] span {
    color: #111827 !important;
}
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
"""


def apply_global_styles(page_title: str = "リスト管理") -> None:
    """CSSを注入し、ロゴヘッダーを描画する。page_title でページ名を変える。"""
    import base64 as _b64

    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)

    _logo_path = os.path.join(_LIST_TOOL_DIR, "Offi-Stretch_280px.jpg")
    if os.path.exists(_logo_path):
        with open(_logo_path, "rb") as _lf:
            _logo_b64 = _b64.b64encode(_lf.read()).decode()
        st.markdown(f"""
<div class="app-header">
  <img src="data:image/jpeg;base64,{_logo_b64}" style="height:40px;width:auto;object-fit:contain;" />
  <div>
    <div class="app-header-title">{page_title}</div>
    <div class="app-header-sub">Well Body株式会社 — テレアポ営業支援ツール</div>
  </div>
</div>
""", unsafe_allow_html=True)
    else:
        st.markdown(f"""
<div class="app-header">
  <div class="app-header-logo">O</div>
  <div>
    <div class="app-header-title">Offi-Stretch {page_title}</div>
    <div class="app-header-sub">Well Body株式会社 — テレアポ営業支援ツール</div>
  </div>
</div>
""", unsafe_allow_html=True)


# ──────────────────────────────
# 架電先リスト 全カラム定義
# ──────────────────────────────

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

# 商談一覧 全カラム定義
_MEETING_COLS = [
    "記録日", "アポ獲得月", "アポ獲得者", "リストアップ", "会社名",
    "アポ獲得概要", "アポ担当", "前確認実施済", "アポ獲得日", "アポ実施予定日",
    "実施の有無", "商談結果", "契約", "責任者の有無", "アポ実施担当者",
    "失注理由", "失注理由（詳細）", "業種", "企業URL",
    "再アプローチ担当", "アプローチ担当名", "役職", "電話番号",
    "ステータス", "見込み", "アプローチ内容", "次回アプローチ日",
]


# ──────────────────────────────
# データ読み書き
# ──────────────────────────────

def load_feedback() -> pd.DataFrame:
    if os.path.exists(FEEDBACK_FILE):
        try:
            df = pd.read_csv(FEEDBACK_FILE, encoding="utf-8-sig")
            df["記録日"] = pd.to_datetime(df["記録日"], errors="coerce")
            if "担当名" not in df.columns:
                df["担当名"] = ""
            return df
        except Exception:
            pass
    return pd.DataFrame(columns=["記録日", "会社名", "アプローチ結果", "アポ獲得", "規模", "NG理由", "断り理由", "温度感", "検索クエリ", "反応が良かったポイント", "メモ", "担当名"])


def load_company_list() -> list:
    """results.csv から会社名リストを取得"""
    if os.path.exists(RESULTS_FILE):
        try:
            df = pd.read_csv(RESULTS_FILE, encoding="utf-8-sig")
            if "会社名" in df.columns:
                return sorted(df["会社名"].dropna().unique().tolist())
        except Exception:
            pass
    return []


def load_call_list() -> pd.DataFrame:
    """架電先リストをCSVから読み込む"""
    if os.path.exists(CALL_LIST_FILE):
        try:
            df = pd.read_csv(CALL_LIST_FILE, encoding="utf-8-sig", dtype=str).fillna("")
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


def load_meetings() -> pd.DataFrame:
    """商談記録をCSVから読み込む（後方互換: 不足列がない場合は空列追加）"""
    if os.path.exists(MEETINGS_FILE):
        try:
            df = pd.read_csv(MEETINGS_FILE, encoding="utf-8-sig")
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
        query   = _find_query_for_company(company)

        if query:
            if "受注" in result or "契約" in result:
                record_rank_result(query, "A")
            elif "失注" in result or "NG" in result:
                record_ng(query)

        if "失注" in result or "NG" in result:
            domain = _find_domain_for_company(company)
            if domain and domain not in load_exclude_list_csv():
                add_to_exclude_csv(domain, f"商談失注: {result}")
    except Exception:
        pass


# ──────────────────────────────
# HubSpot 活動記録同期
# ──────────────────────────────

def _hubspot_find_company_id(name: str, token: str):
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
    """架電結果をHubSpotにNoteとして登録し、会社に紐付ける。"""
    import requests as _r
    from datetime import datetime as _dt
    if not token:
        return False

    company_id = _hubspot_find_company_id(company_name, token)
    body_lines = [
        "【架電記録】",
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
    """商談一覧データをHubSpotの取引（Deal）として登録し、会社と紐付ける。"""
    import requests as _r
    if not token:
        return False

    company_name = deal_data.get("企業名", "")
    company_id = _hubspot_find_company_id(company_name, token) if company_name else None

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
# 自動補充（HubSpot → call_list.csv）
# ──────────────────────────────

def _auto_refill_from_hubspot(tanto_name: str) -> tuple:
    """
    指定担当者のアプローチ内容ブランクが50件未満になったら、
    HubSpotから100件（リストランクA/B/C均等）を自動追加する。
    戻り値: (追加件数, エラーメッセージ or None)
    """
    from config import HUBSPOT_TOKEN
    if not HUBSPOT_TOKEN or not tanto_name:
        return 0, None

    df_cl = load_call_list()
    tanto_rows = df_cl[df_cl["架電担当者名"] == tanto_name]
    blank_count = len(tanto_rows[tanto_rows["アプローチ内容"] == ""])
    if blank_count >= 50:
        return 0, None

    existing_names = set(df_cl["会社名"].tolist())

    rank_map: dict = {}
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

    _refill_list_id = _load_import_settings("auto_refill_list").get("list_id", "")

    import requests as _refill_req
    _refill_headers = {
        "Authorization": f"Bearer {HUBSPOT_TOKEN}",
        "Content-Type": "application/json",
    }
    _REFILL_PROPS = "name,phone,website,state,city,industry,numberofemployees,zip,joken_ng"
    _hs_base = "https://api.hubapi.com"

    def _to_candidate(c: dict):
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

    candidates: list = []
    try:
        if _refill_list_id:
            _member_ids: list = []
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

    TARGET = 100
    PER_RANK = TARGET // 3

    buckets: dict = {"A": [], "B": [], "C": [], "other": []}
    for _cand in candidates:
        _rank = _cand["リストランク"].upper()
        if _rank in ("A", "B", "C"):
            buckets[_rank].append(_cand)
        else:
            buckets["other"].append(_cand)

    selected: list = []
    for _r in ("A", "B", "C"):
        selected.extend(buckets[_r][:PER_RANK])

    if len(selected) < TARGET:
        _extra_pool: list = []
        for _r in ("A", "B", "C"):
            _extra_pool.extend(buckets[_r][PER_RANK:])
        _extra_pool.extend(buckets["other"])
        _shortage = TARGET - len(selected)
        selected.extend(_extra_pool[:_shortage])

    selected = selected[:TARGET]
    if not selected:
        return 0, None

    _team = _load_team_members()
    if _team:
        selected = _assign_members_roundrobin(selected, _team)

    _new_df = pd.DataFrame(selected)
    for _col in _CALL_LIST_COLS:
        if _col not in _new_df.columns:
            _new_df[_col] = ""
    _new_df = _new_df[_CALL_LIST_COLS]
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    _header = not os.path.exists(CALL_LIST_FILE) or os.path.getsize(CALL_LIST_FILE) == 0
    _new_df.to_csv(CALL_LIST_FILE, mode="a", index=False, encoding="utf-8-sig", header=_header)

    return len(_new_df), None


# ──────────────────────────────
# リストアップ担当者カウント管理
# ──────────────────────────────

_LISTUP_WORKERS_FILE = os.path.join(OUTPUT_DIR, "listup_workers.json")


def _load_listup_workers() -> dict:
    try:
        if os.path.exists(_LISTUP_WORKERS_FILE):
            with open(_LISTUP_WORKERS_FILE, "r", encoding="utf-8") as f:
                return _json_mod.load(f)
    except Exception:
        pass
    return {}


def _increment_listup_worker(name: str) -> int:
    workers = _load_listup_workers()
    workers[name] = workers.get(name, 0) + 1
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        with open(_LISTUP_WORKERS_FILE, "w", encoding="utf-8") as f:
            _json_mod.dump(workers, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return workers[name]


# ──────────────────────────────
# インポート設定・チームメンバー管理
# ──────────────────────────────

def _load_import_settings(key: str) -> dict:
    try:
        if os.path.exists(IMPORT_SETTINGS_FILE):
            with open(IMPORT_SETTINGS_FILE, "r", encoding="utf-8") as f:
                return _json_mod.load(f).get(key, {})
    except Exception:
        pass
    return {}


def _save_import_settings(key: str, data: dict):
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


def _load_team_members() -> list:
    return _load_import_settings("team_members").get("names", [])


def _save_team_members(names: list) -> None:
    _save_import_settings("team_members", {"names": names})


def _assign_members_roundrobin(entries: list, members: list) -> list:
    """entriesの各行にメンバーをラウンドロビンで架電担当者名として割り当てる。"""
    if not members or not entries:
        return entries
    start_idx = _load_import_settings("team_members_rr").get("next_idx", 0) % len(members)
    for i, entry in enumerate(entries):
        entry["架電担当者名"] = members[(start_idx + i) % len(members)]
    next_idx = (start_idx + len(entries)) % len(members)
    _save_import_settings("team_members_rr", {"next_idx": next_idx})
    return entries


def _read_file_to_df(filepath: str):
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


# ──────────────────────────────
# pending_review UI
# ──────────────────────────────

def _normalize_pending_items(items: list) -> list:
    """daemon形式（ネスト）とbatch形式（フラット）を統一してフラットリストに変換する"""
    result = []
    for item in items:
        if "company_info" in item:
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
            result.append(item)
    return result


def _clean_pending_df(df: pd.DataFrame) -> pd.DataFrame:
    """pending_review.json を表示用に整形する"""
    df = df[[c for c in df.columns if c and c != "null"]].copy()

    if "都道府県" in df.columns and "所在地" in df.columns:
        df["所在地"] = df["都道府県"].fillna("") + df["所在地"].fillna("")
        df = df.drop(columns=["都道府県"])
    elif "都道府県" in df.columns:
        df = df.rename(columns={"都道府県": "所在地"})

    if "ランク" in df.columns:
        df = df.rename(columns={"ランク": "リストランク"})

    col_biko  = df["備考"].fillna("")  if "備考"  in df.columns else pd.Series([""] * len(df))
    col_url   = df["元URL"].fillna("") if "元URL" in df.columns else pd.Series([""] * len(df))
    df["説明"] = col_biko
    has_url = (col_url != "") & (~col_biko.str.contains(col_url, regex=False, na=False))
    df.loc[has_url, "説明"] = df.loc[has_url, "説明"] + " | 元URL: " + col_url[has_url]

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

    pending = _normalize_pending_items(pending_raw)

    df_raw = pd.DataFrame(pending)
    df_clean = _clean_pending_df(df_raw)

    _DISPLAY_COLS = [
        "リストランク", "会社名", "企業URL", "所在地", "郵便番号",
        "電話番号", "代表氏名", "業種", "従業員数", "説明", "日時",
    ]
    show_cols = [c for c in _DISPLAY_COLS if c in df_clean.columns]
    show_cols += [c for c in df_clean.columns if c not in show_cols and c not in ("備考", "元URL")]

    df_view = df_clean[show_cols].copy()
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
            # 承認した企業を OUTPUT_DIR/approved_companies.csv に追記
            approved_csv = os.path.join(OUTPUT_DIR, "approved_companies.csv")
            header = not os.path.exists(approved_csv)
            approved.to_csv(approved_csv, mode="a", index=False, encoding="utf-8-sig", header=header)
            rejected_df = edited[edited["承認"] == False].drop(columns=["承認"])
            with open(pending_path, "w", encoding="utf-8") as _f:
                _jr.dump(rejected_df.to_dict(orient="records"), _f, ensure_ascii=False, indent=2)
            st.success(f"{len(approved)}件を approved_companies.csv に保存しました。残り: {len(rejected_df)}件")
            st.rerun()
    with col_clear:
        if st.button("クリア（リストを消去）", width="stretch"):
            os.remove(pending_path)
            st.rerun()


def _render_gsheets_loader(widget_key: str, saved: dict):
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
