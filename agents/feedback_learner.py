"""
フィードバック学習エージェント
架電結果・商談結果からシグナルウェイトを自動更新する。

学習フロー:
  1. call_list.csv → アポ獲得○・見込みA = 成功、NG系 = 失敗
  2. meetings.csv  → 契約=はい = 最強ポジティブ
  3. results.csv   → 会社名で突合してランク理由（シグナル）を取得
  4. シグナルごとの成功率を計算 → signal_weights.json を更新
"""

import json
import os
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# ファイルパス（OUTPUT_DIR環境変数対応）
import sys as _sys
_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(_DIR, "..")
_sys.path.insert(0, _ROOT)
from config import OUTPUT_DIR as _OUTPUT_DIR
RESULTS_FILE       = os.path.join(_OUTPUT_DIR, "results.csv")
CALL_LIST_FILE     = os.path.join(_OUTPUT_DIR, "call_list.csv")
MEETINGS_FILE      = os.path.join(_OUTPUT_DIR, "meetings.csv")
WEIGHTS_FILE       = os.path.join(_OUTPUT_DIR, "signal_weights.json")

# 架電結果の分類
APO_SUCCESS_PATTERNS = ["社長アポ", "担当アポ", "日程調整中"]
APO_NG_PATTERNS      = ["受付NG", "担当NG", "社長NG", "取材NG", "追わない", "不通リスト", "触るな危険"]

# signal_weights.json のキー一覧（rank_agent.py と同期）
SIGNAL_KEYS = [
    "PR媒体掲載",
    "健康経営メディア掲載",
    "法定外福利厚生",
    "フィジカルケア未着手",
    "健康経営注力",
    "健康推進・セミナー",
    "経営者の健康意識",
    "PR広告投資",
    "成長・自社ビル",
    "高利益率B2B業種",
    "契約実績サイズ",
    "単一拠点",
]

# ウェイトのクランプ範囲
WEIGHT_MIN = 0.4
WEIGHT_MAX = 2.5
# 学習に必要な最低サンプル数（少なすぎると誤学習）
MIN_SAMPLES = 3


def _load_csv(path: str) -> list[dict]:
    """CSVをdictのリストとして読み込む。エラー時は空リストを返す。"""
    if not os.path.exists(path):
        return []
    try:
        import csv
        with open(path, encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    except Exception as e:
        logger.warning(f"CSV読み込み失敗 {path}: {e}")
        return []


def _load_weights() -> dict:
    """signal_weights.json を読み込む。なければデフォルト1.0を返す。"""
    if os.path.exists(WEIGHTS_FILE):
        try:
            with open(WEIGHTS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("weights", {})
        except Exception:
            pass
    return {k: 1.0 for k in SIGNAL_KEYS}


def _save_weights(weights: dict, summary: list[str]):
    """signal_weights.json に保存する。"""
    data = {
        "_updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "_note": "自動更新: フィードバック学習により架電・商談結果に基づきウェイトを調整。1.0=デフォルト、高いほどスコアが上がる",
        "_summary": summary,
        "weights": weights,
    }
    os.makedirs(os.path.dirname(WEIGHTS_FILE), exist_ok=True)
    with open(WEIGHTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _extract_signals_from_reasons(reasons_text: str) -> list[str]:
    """
    results.csv の備考列からシグナルキーを抽出する。
    例: "理由: PR媒体掲載, 健康経営注力, 単一拠点" → ["PR媒体掲載", "健康経営注力", "単一拠点"]
    """
    found = []
    for key in SIGNAL_KEYS:
        if key in reasons_text:
            found.append(key)
    return found


def _normalize_name(name: str) -> str:
    """
    会社名を正規化して突合精度を上げる。
    例: 「株式会社 ABC | サービス紹介」→「abc」
    """
    import unicodedata
    # タイトル文字列を除去（| や ｜ 以降）
    name = re.split(r"[|｜｜\-－―]", name)[0]
    # 法人格を除去
    for kw in ["株式会社", "有限会社", "合同会社", "合資会社", "一般社団法人",
               "公益社団法人", "医療法人", "学校法人", "社会福祉法人"]:
        name = name.replace(kw, "")
    # 全角→半角、大文字→小文字
    name = unicodedata.normalize("NFKC", name)
    name = name.lower()
    # 空白・記号を除去
    name = re.sub(r"[\s\u3000\.\-_（）()・　]+", "", name)
    return name.strip()


def _build_company_signal_map(results: list[dict]) -> dict[str, list[str]]:
    """
    results.csv から {会社名: [シグナルキー, ...]} のマップを作成する。
    """
    mapping = {}
    for row in results:
        name = (row.get("会社名") or "").strip()
        if not name:
            continue
        normalized = _normalize_name(name)
        備考 = row.get("備考") or ""
        signals = _extract_signals_from_reasons(備考)
        if normalized:
            mapping[normalized] = signals
    return mapping


def run_learning() -> dict:
    """
    フィードバック学習を実行してシグナルウェイトを更新する。

    Returns:
        {
          "signal_updates": {シグナル名: {"old": float, "new": float, "apo_rate": float}},
          "stats": {"success": int, "failure": int, "contract": int, "unmatched": int},
          "summary": [str, ...],  # 人間が読めるサマリー行
        }
    """
    import csv as _csv

    # ── データ読み込み ──────────────────────────────────────────
    call_list = _load_csv(CALL_LIST_FILE)
    meetings  = _load_csv(MEETINGS_FILE)
    results   = _load_csv(RESULTS_FILE)

    if not call_list and not meetings:
        return {"signal_updates": {}, "stats": {}, "summary": ["データなし（call_list.csvもmeetings.csvも空）"]}

    # ── results.csv から シグナルマップ構築 ──────────────────────
    signal_map = _build_company_signal_map(results)

    # ── 成功・失敗企業の分類 ──────────────────────────────────
    success_companies: set[str] = set()
    failure_companies: set[str] = set()

    for row in call_list:
        name = (row.get("会社名") or "").strip()
        if not name:
            continue
        apo        = (row.get("アポ獲得") or "").strip()
        mikomi     = (row.get("見込み") or "").strip()
        approach   = (row.get("アプローチ内容") or "").strip()
        joken_ng   = (row.get("条件NG") or "").strip()

        # 成功判定
        if apo == "○" or mikomi == "A" or any(p in approach for p in APO_SUCCESS_PATTERNS):
            success_companies.add(name)
        # 失敗判定
        if joken_ng == "○" or any(p in approach for p in APO_NG_PATTERNS):
            failure_companies.add(name)

    # 商談成約は最強シグナル（重複カウントを避けるため2回追加）
    contract_companies: set[str] = set()
    for row in meetings:
        name     = (row.get("会社名") or "").strip()
        contract = (row.get("契約") or "").strip()
        result   = (row.get("商談結果") or "").strip()
        if not name:
            continue
        if contract in ("はい", "yes", "○", "True", "true") or "成約" in result or "契約" in result:
            contract_companies.add(name)
            success_companies.add(name)

    # ── シグナルごとに成功/失敗カウント ──────────────────────
    signal_success: dict[str, int] = {k: 0 for k in SIGNAL_KEYS}
    signal_total:   dict[str, int] = {k: 0 for k in SIGNAL_KEYS}
    unmatched = 0

    all_classified = success_companies | failure_companies
    for name in all_classified:
        # 正規化してから突合
        normalized = _normalize_name(name)
        signals = signal_map.get(normalized)
        if signals is None:
            # 部分一致（正規化済み）
            for mapped_norm, sigs in signal_map.items():
                if len(normalized) >= 4 and (normalized in mapped_norm or mapped_norm in normalized):
                    signals = sigs
                    break
        if signals is None:
            unmatched += 1
            continue

        is_success = name in success_companies
        is_contract = name in contract_companies

        for sig in signals:
            signal_total[sig] += 1
            if is_success:
                signal_success[sig] += 1
            if is_contract:
                # 成約は追加で+1（重みを強調）
                signal_success[sig] += 1
                signal_total[sig]   += 1

    # ── 全体のアポ率（ベースライン）──────────────────────────
    total_all     = len(all_classified)
    total_success = len(success_companies)
    base_rate = total_success / total_all if total_all > 0 else 0.5

    # ── ウェイト計算 ──────────────────────────────────────────
    old_weights = _load_weights()
    new_weights = dict(old_weights)
    signal_updates = {}

    for sig in SIGNAL_KEYS:
        total = signal_total[sig]
        if total < MIN_SAMPLES:
            # サンプル不足 → 変更しない（前回値を引き継ぎ）
            continue
        apo_rate = signal_success[sig] / total
        # ベースラインに対する相対ウェイト
        relative = apo_rate / base_rate if base_rate > 0 else 1.0
        # 現在のウェイトと新ウェイトを7:3でブレンド（急激な変化を抑制）
        blended = old_weights.get(sig, 1.0) * 0.7 + relative * 0.3
        new_w = round(max(WEIGHT_MIN, min(WEIGHT_MAX, blended)), 3)

        old_w = old_weights.get(sig, 1.0)
        new_weights[sig] = new_w
        signal_updates[sig] = {
            "old": round(old_w, 3),
            "new": new_w,
            "apo_rate": round(apo_rate, 3),
            "samples": total,
        }

    # ── サマリー生成 ──────────────────────────────────────────
    summary = [
        f"学習日時: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"データ: 成功{len(success_companies)}社 / 失敗{len(failure_companies)}社 / 成約{len(contract_companies)}社",
        f"results.csv突合: {len(all_classified) - unmatched}件マッチ / {unmatched}件未突合",
        f"ベースライン アポ率: {base_rate:.1%}",
    ]
    for sig, upd in signal_updates.items():
        direction = "↑" if upd["new"] > upd["old"] else ("↓" if upd["new"] < upd["old"] else "→")
        summary.append(
            f"  {direction} {sig}: {upd['old']} → {upd['new']} (アポ率{upd['apo_rate']:.0%} / {upd['samples']}件)"
        )

    # ── 保存 ──────────────────────────────────────────────────
    _save_weights(new_weights, summary)

    stats = {
        "success":  len(success_companies),
        "failure":  len(failure_companies),
        "contract": len(contract_companies),
        "unmatched": unmatched,
    }

    logger.info(f"フィードバック学習完了: {len(signal_updates)}シグナル更新")
    return {
        "signal_updates": signal_updates,
        "stats": stats,
        "summary": summary,
    }
