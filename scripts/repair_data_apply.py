# -*- coding: utf-8 -*-
"""
HubSpot登録済み企業の修復適用スクリプト（Phase 7-A Step 4）

- output/repair_dryrun_report.csv を読み込み
- 変更フラグ=True かつスキップリスト外のレコードを HubSpot に PATCH
- 実行前に確認プロンプトあり（"yes" 入力で続行）
- 結果を output/repair_apply_log.csv に記録

実行: python scripts/repair_data_apply.py
"""
import csv
import logging
import os
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv
load_dotenv()

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── 定数 ──────────────────────────────────────────────────────────────────────
HUBSPOT_BASE  = "https://api.hubapi.com"
IN_CSV        = os.path.join(ROOT, "output", "repair_dryrun_report.csv")
OUT_LOG_CSV   = os.path.join(ROOT, "output", "repair_apply_log.csv")

# 明示的スキップリスト: 法人格なし等でPhase 7-B対応予定のレコード
_SKIP_IDS: set[str] = {"321669733093"}

_LOG_FIELDS = [
    "実行日時",
    "hubspot_id", "会社名_元", "会社名_新",
    "都道府県_元", "都道府県_新",
    "所在地_元", "所在地_新",
    "適用結果", "HTTPステータス", "備考",
]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ── PATCH 実行（リトライつき）──────────────────────────────────────────────────

def _patch_company(token: str, company_id: str, props: dict) -> tuple[int | None, str]:
    """
    HubSpot へ PATCH を送信する。
    戻り値: (status_code, error_message)
      成功時:   (200, "")
      失敗時:   (status_code or None, 理由文字列)
    """
    url = f"{HUBSPOT_BASE}/crm/v3/objects/companies/{company_id}"
    payload = {"properties": props}

    def _do_request() -> requests.Response:
        return requests.patch(url, json=payload, headers=_headers(token), timeout=15)

    try:
        resp = _do_request()
    except requests.Timeout:
        # タイムアウト → 1回リトライ
        logger.warning(f"  [{company_id}] タイムアウト、リトライ中...")
        try:
            resp = _do_request()
        except requests.Timeout:
            return None, "タイムアウト（リトライも失敗）"
        except Exception as e:
            return None, f"例外（リトライ）: {e}"
    except Exception as e:
        return None, f"例外: {e}"

    # 429 Too Many Requests → 2秒待ってリトライ
    if resp.status_code == 429:
        logger.warning(f"  [{company_id}] 429 Rate Limit、2秒待ちリトライ...")
        time.sleep(2)
        try:
            resp = _do_request()
        except Exception as e:
            return 429, f"429リトライ中に例外: {e}"

    # 5xx → 1回リトライ
    if resp.status_code >= 500:
        logger.warning(f"  [{company_id}] {resp.status_code} サーバーエラー、リトライ中...")
        try:
            resp = _do_request()
        except Exception as e:
            return resp.status_code, f"5xxリトライ中に例外: {e}"

    if resp.ok:
        return resp.status_code, ""
    else:
        return resp.status_code, resp.text[:200]


# ── CSV読み込み ────────────────────────────────────────────────────────────────

def load_dryrun_csv(path: str) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


# ── プロパティ差分の組み立て ──────────────────────────────────────────────────

def build_patch_props(row: dict) -> dict:
    """
    変更があったフィールドのみ含む PATCH 用プロパティ辞書を返す。
    city は絶対に含めない（登録時のバグとの混同を避けるため）。
    address の空文字は「クリア」として明示的に送信する。
    """
    props: dict[str, str] = {}

    name_old = row.get("会社名_元", "")
    name_new = row.get("会社名_新", "")
    pref_old = row.get("都道府県_元", "")
    pref_new = row.get("都道府県_新", "")
    addr_old = row.get("所在地_元", "")
    addr_new = row.get("所在地_新", "")

    if name_new != name_old:
        props["name"] = name_new

    if pref_new != pref_old:
        props["state"] = pref_new

    if addr_new != addr_old:
        # 空文字の場合も明示送信（HubSpot v3 は空文字でフィールドをクリアする）
        props["address"] = addr_new

    return props


# ── ログ書き込み（即書き込み方式）────────────────────────────────────────────

def init_log_file() -> None:
    """ログファイルが存在しない場合のみヘッダー行を書き込む。"""
    if not os.path.exists(OUT_LOG_CSV):
        with open(OUT_LOG_CSV, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_LOG_FIELDS, extrasaction="ignore")
            writer.writeheader()
        logger.info(f"ログファイル作成: {OUT_LOG_CSV}")


def append_log_row(row: dict, result: str, status: int | None, note: str) -> None:
    """PATCH 結果を1行ずつ追記モードで書き込む。"""
    log_row = {
        "実行日時":      datetime.now().isoformat(timespec="seconds"),
        "hubspot_id":   row.get("hubspot_id", ""),
        "会社名_元":     row.get("会社名_元", ""),
        "会社名_新":     row.get("会社名_新", ""),
        "都道府県_元":   row.get("都道府県_元", ""),
        "都道府県_新":   row.get("都道府県_新", ""),
        "所在地_元":     row.get("所在地_元", ""),
        "所在地_新":     row.get("所在地_新", ""),
        "適用結果":      result,
        "HTTPステータス": str(status) if status is not None else "",
        "備考":          note,
    }
    with open(OUT_LOG_CSV, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_LOG_FIELDS, extrasaction="ignore")
        writer.writerow(log_row)


# ── メイン ────────────────────────────────────────────────────────────────────

def main() -> None:
    # 1. 環境確認
    token = os.environ.get("HUBSPOT_TOKEN", "")
    if not token:
        logger.error("HUBSPOT_TOKEN が未設定です。.env を確認してください。")
        sys.exit(1)
    logger.info(f"HUBSPOT_TOKEN: 確認OK（長さ {len(token)} 文字）")

    # 2. CSVロード
    if not os.path.exists(IN_CSV):
        logger.error(f"ドライランCSVが見つかりません: {IN_CSV}")
        sys.exit(1)
    rows = load_dryrun_csv(IN_CSV)
    logger.info(f"ドライランCSV読み込み: {len(rows)} 件")

    # 3. 対象レコードの抽出
    targets = [
        r for r in rows
        if r.get("変更フラグ", "").strip().lower() in ("true",)
        and r.get("hubspot_id", "").strip() not in _SKIP_IDS
    ]
    skipped_flag_false = sum(
        1 for r in rows if r.get("変更フラグ", "").strip().lower() != "true"
    )
    skipped_skiplist = sum(
        1 for r in rows
        if r.get("hubspot_id", "").strip() in _SKIP_IDS
    )

    print("\n── 適用対象 ────────────────────────────────────────")
    print(f"  全レコード数     : {len(rows)} 件")
    print(f"  変更フラグFalse  : {skipped_flag_false} 件（スキップ）")
    print(f"  スキップリスト   : {skipped_skiplist} 件（{sorted(_SKIP_IDS)}）")
    print(f"  PATCH 適用対象   : {len(targets)} 件")
    print("────────────────────────────────────────────────────\n")

    if not targets:
        print("適用対象が0件です。終了します。")
        sys.exit(0)

    # 4. 確認プロンプト
    answer = input(
        f"上記 {len(targets)} 件を HubSpot に PATCH します。\n"
        "続行するには「yes」と入力してください: "
    ).strip().lower()

    if answer != "yes":
        print("キャンセルしました。")
        sys.exit(0)

    print()

    # 5. ログファイル初期化（ヘッダー書き込み、ファイル新規作成時のみ）
    init_log_file()

    # 6. 順次 PATCH（1件ごとに即書き込み）
    ok_count    = 0
    skip_count  = 0
    error_count = 0

    for i, row in enumerate(targets, 1):
        hub_id = row.get("hubspot_id", "").strip()
        props  = build_patch_props(row)

        if not props:
            # 差分なし（安全策: 変更フラグTrueなのに差分ゼロは想定外だが念のため）
            logger.warning(f"  [{hub_id}] 差分プロパティが0件、スキップ")
            append_log_row(row, result="skipped", status=None, note="差分プロパティなし（想定外）")
            skip_count += 1
            continue

        logger.info(f"[{i}/{len(targets)}] PATCH {hub_id}: {list(props.keys())}")

        try:
            status, err = _patch_company(token, hub_id, props)
        except Exception as e:
            # _patch_company が想定外の例外を投げた場合（基本的にはありえないが安全策）
            note = f"予期せぬ例外: {e}"
            logger.error(f"  [{hub_id}] {note}")
            append_log_row(row, result="exception", status=None, note=note)
            error_count += 1
            raise

        if err == "" and status and 200 <= status < 300:
            result = "OK"
            ok_count += 1
            logger.info(f"  → 成功 {status}")
        else:
            result = "failed"
            error_count += 1
            logger.error(f"  → 失敗 status={status} : {err}")

        append_log_row(row, result=result, status=status, note=err)

        # レート制限対策: 0.2秒スリープ（最後のレコード以外）
        if i < len(targets):
            time.sleep(0.2)

    # 7. サマリー表示
    print("\n── 適用完了 ────────────────────────────────────────")
    print(f"  成功    : {ok_count} 件")
    print(f"  失敗    : {error_count} 件")
    print(f"  スキップ: {skip_count} 件")
    print(f"  ログ    : {OUT_LOG_CSV}")
    print("────────────────────────────────────────────────────\n")

    if error_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
