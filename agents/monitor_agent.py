"""
モニターエージェント
システムの健全性チェック（案A）と自動修復（案B・部分）を行う。

チェック項目:
  1. OUTPUT_DIRディレクトリの存在      → なければ自動作成
  2. signal_weights.json の整合性      → 破損なら自動再生成 / 長期未更新なら警告
  3. signal_weights のウェイト異常     → 全値がMIN/MAXに張り付いたらリセット
  4. CSVファイルのカラム整合性         → 必須カラム欠落を検知
  5. keyword_stats.json の異常値       → NaN/Inf を検知
  6. feedback学習の未実行チェック      → 24時間以上未実行なら自動実行
  7. ログファイルのエラー件数          → 直近100行に ERROR が多ければ警告

返り値:
  {
    "checks": [{"name": str, "status": "ok"|"warn"|"error"|"fixed", "message": str}],
    "repairs": [str],    # 実行した修復内容
    "has_error": bool,
    "has_warn": bool,
  }
"""

import json
import logging
import math
import os
import sys as _sys
from datetime import datetime, timedelta

_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(_DIR, "..")
_sys.path.insert(0, _ROOT)
from config import OUTPUT_DIR, SIGNAL_KEYS, WEIGHT_MIN, WEIGHT_MAX, DEFAULT_WEIGHT

logger = logging.getLogger(__name__)

# CSVの必須カラム定義
CSV_REQUIRED_COLS = {
    "call_list.csv":  ["会社名", "アポ獲得", "見込み", "アプローチ内容"],
    "results.csv":    ["会社名", "ランク", "企業URL"],
    "meetings.csv":   ["会社名", "商談結果"],
}

# feedback学習の再実行間隔（時間）
FEEDBACK_RERUN_HOURS = 24


# ────────────────────────────────────────
# 内部ユーティリティ
# ────────────────────────────────────────

def _ok(name: str, msg: str = "") -> dict:
    return {"name": name, "status": "ok", "message": msg or "正常"}

def _warn(name: str, msg: str) -> dict:
    return {"name": name, "status": "warn", "message": msg}

def _error(name: str, msg: str) -> dict:
    return {"name": name, "status": "error", "message": msg}

def _fixed(name: str, msg: str) -> dict:
    return {"name": name, "status": "fixed", "message": msg}


# ────────────────────────────────────────
# チェック関数
# ────────────────────────────────────────

def _check_output_dir(repairs: list) -> dict:
    """OUTPUT_DIRが存在するか。なければ自動作成。"""
    if os.path.isdir(OUTPUT_DIR):
        return _ok("OUTPUT_DIR", f"{OUTPUT_DIR} 存在確認 OK")
    # 自動修復
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    repairs.append(f"OUTPUT_DIR を作成しました: {OUTPUT_DIR}")
    return _fixed("OUTPUT_DIR", f"ディレクトリを自動作成しました: {OUTPUT_DIR}")


def _check_signal_weights(repairs: list) -> dict:
    """signal_weights.json の存在・JSON有効性・更新日時・値異常をチェック。"""
    path = os.path.join(OUTPUT_DIR, "signal_weights.json")
    name = "signal_weights.json"

    # ── 存在しない場合: デフォルト生成 ──
    if not os.path.exists(path):
        _repair_generate_default_weights(path)
        repairs.append("signal_weights.json が存在しないためデフォルト値で生成しました")
        return _fixed(name, "ファイルが存在しないためデフォルト生成")

    # ── JSON破損チェック ──
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        _repair_generate_default_weights(path)
        repairs.append(f"signal_weights.json が破損していたためデフォルト値にリセットしました（原因: {e}）")
        return _fixed(name, f"JSONが破損 → デフォルト値でリセット（{e}）")

    weights = data.get("weights", {})

    # ── ウェイト値の異常チェック（全値がMIN or MAXに張り付き）──
    vals = [weights.get(k, DEFAULT_WEIGHT) for k in SIGNAL_KEYS]
    pinned_min = sum(1 for v in vals if v <= WEIGHT_MIN + 0.01)
    pinned_max = sum(1 for v in vals if v >= WEIGHT_MAX - 0.01)
    if pinned_min >= len(SIGNAL_KEYS) * 0.8 or pinned_max >= len(SIGNAL_KEYS) * 0.8:
        # 80%以上が端値 → 学習が偏りすぎているのでリセット
        _repair_generate_default_weights(path)
        repairs.append("signal_weights がほぼ全てMIN/MAXに張り付いていたためリセットしました")
        return _fixed(name, f"ウェイトが偏りすぎ（MIN張り付き{pinned_min}件 / MAX張り付き{pinned_max}件）→ リセット")

    # ── 更新日時チェック ──
    updated_str = data.get("_updated", "")
    if updated_str:
        try:
            updated_dt = datetime.strptime(updated_str, "%Y-%m-%d %H:%M")
            age_hours = (datetime.now() - updated_dt).total_seconds() / 3600
            if age_hours > 72:
                return _warn(name, f"最終更新から {age_hours:.0f}h 経過（フィードバック学習が実行されていない可能性）")
        except ValueError:
            pass

    return _ok(name, f"正常（{len(weights)}シグナル / 最終更新: {updated_str or '不明'}）")


def _repair_generate_default_weights(path: str):
    """signal_weights.json をデフォルト値で再生成する。"""
    data = {
        "_updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "_note": "モニターエージェントによりデフォルト値で再生成",
        "_summary": ["monitor_agent: 自動修復"],
        "weights": {k: DEFAULT_WEIGHT for k in SIGNAL_KEYS},
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _check_csv_columns() -> dict:
    """CSVファイルの必須カラム存在チェック。"""
    import csv
    issues = []
    for filename, required in CSV_REQUIRED_COLS.items():
        path = os.path.join(OUTPUT_DIR, filename)
        if not os.path.exists(path):
            # ファイル未存在は初回起動時は正常なので warn 扱い
            issues.append(f"{filename}: ファイルなし（初回実行前）")
            continue
        try:
            with open(path, encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                cols = reader.fieldnames or []
            missing = [c for c in required if c not in cols]
            if missing:
                issues.append(f"{filename}: 必須カラム欠落 {missing}")
        except Exception as e:
            issues.append(f"{filename}: 読み込みエラー ({e})")

    if not issues:
        return _ok("CSVカラム整合性", f"{len(CSV_REQUIRED_COLS)}ファイル全て正常")
    # 全てが「ファイルなし」なら warn、それ以外は error
    has_real_issue = any("ファイルなし" not in i for i in issues)
    msg = " / ".join(issues)
    return _error("CSVカラム整合性", msg) if has_real_issue else _warn("CSVカラム整合性", msg)


def _check_keyword_stats() -> dict:
    """keyword_stats.json の異常値（NaN/Inf）チェック。"""
    path = os.path.join(OUTPUT_DIR, "keyword_stats.json")
    name = "keyword_stats.json"
    if not os.path.exists(path):
        return _ok(name, "ファイルなし（初回実行前）")
    try:
        with open(path, encoding="utf-8") as f:
            stats = json.load(f)
    except Exception as e:
        return _error(name, f"JSON読み込みエラー: {e}")

    abnormal = []
    for query, data in stats.items():
        for key, val in data.items():
            if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                abnormal.append(f"'{query}' の {key} = {val}")

    if abnormal:
        return _warn(name, f"異常値 {len(abnormal)}件: {', '.join(abnormal[:3])}")
    return _ok(name, f"{len(stats)}クエリ 正常")


def _check_feedback_learning(repairs: list) -> dict:
    """
    feedback学習の最終実行日時をチェック。
    FEEDBACK_RERUN_HOURS 以上経過していたら run_learning() を自動実行。
    """
    name = "フィードバック学習"
    path = os.path.join(OUTPUT_DIR, "signal_weights.json")
    if not os.path.exists(path):
        return _ok(name, "signal_weights.json 未生成のためスキップ")

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        updated_str = data.get("_updated", "")
        if not updated_str:
            return _warn(name, "最終実行日時が不明")
        updated_dt = datetime.strptime(updated_str, "%Y-%m-%d %H:%M")
        age_hours = (datetime.now() - updated_dt).total_seconds() / 3600
    except Exception as e:
        return _warn(name, f"最終実行日時の取得に失敗: {e}")

    if age_hours <= FEEDBACK_RERUN_HOURS:
        return _ok(name, f"最終実行: {updated_str}（{age_hours:.0f}h前）")

    # 24時間以上未実行 → 自動実行
    try:
        from agents.feedback_learner import run_learning
        result = run_learning()
        n = len(result.get("signal_updates", {}))
        repairs.append(f"フィードバック学習を自動実行しました（{n}シグナル更新）")
        return _fixed(name, f"{age_hours:.0f}h未実行だったため自動実行（{n}シグナル更新）")
    except Exception as e:
        return _warn(name, f"{age_hours:.0f}h未実行 / 自動実行に失敗: {e}")


def _check_log_errors() -> dict:
    """ログファイルの直近100行に ERROR が何件あるかチェック。"""
    name = "ログエラー件数"
    # config から LOG_FILE を取得
    try:
        from config import LOG_FILE
        log_path = LOG_FILE
    except ImportError:
        log_path = os.path.join(OUTPUT_DIR, "app.log")

    if not os.path.exists(log_path):
        return _ok(name, "ログファイルなし")

    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        recent = lines[-100:]
        error_lines = [l.strip() for l in recent if " [ERROR] " in l or " ERROR " in l]
        count = len(error_lines)
        if count == 0:
            return _ok(name, f"直近100行にERRORなし")
        if count <= 5:
            return _warn(name, f"直近100行に ERROR {count}件 | 例: {error_lines[-1][:80]}")
        return _error(name, f"直近100行に ERROR {count}件（多発）| 例: {error_lines[-1][:80]}")
    except Exception as e:
        return _warn(name, f"ログ読み込みエラー: {e}")


# ────────────────────────────────────────
# メイン
# ────────────────────────────────────────

def run_check() -> dict:
    """
    全チェックを実行してサマリーを返す。
    自動修復が発生した場合は repairs リストに記録する。
    """
    repairs: list[str] = []
    checks = [
        _check_output_dir(repairs),
        _check_signal_weights(repairs),
        _check_csv_columns(),
        _check_keyword_stats(),
        _check_feedback_learning(repairs),
        _check_log_errors(),
    ]

    has_error = any(c["status"] == "error" for c in checks)
    has_warn  = any(c["status"] in ("warn", "fixed") for c in checks)

    result = {
        "checks": checks,
        "repairs": repairs,
        "has_error": has_error,
        "has_warn": has_warn,
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    logger.info(
        f"モニターチェック完了: error={has_error} warn={has_warn} 修復={len(repairs)}件"
    )
    return result
