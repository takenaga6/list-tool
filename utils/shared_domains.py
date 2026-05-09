"""
utils/shared_domains.py

複数プロセス間で処理済みドメインを共有するモジュール。
ファイルベース（JSON）でシンプルに実装し、Redis等の外部依存を不要にする。

データ構造:
{
  "domains": [
    {"domain": "example.com", "added_at": "2026-05-09T10:00:00"},
    ...
  ],
  "last_cleanup": "2026-05-09T08:00:00"
}
"""

import json
import os
from datetime import datetime, timezone, timedelta
from filelock import FileLock

import sys
_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, _ROOT)
from config import OUTPUT_DIR

_SHARED_DOMAINS_FILE = os.path.join(OUTPUT_DIR, "processed_domains_shared.json")
_SHARED_DOMAINS_LOCK = FileLock(_SHARED_DOMAINS_FILE + ".lock", timeout=10)

_MAX_ENTRIES = 10_000
_CLEANUP_DAYS = 7

# 環境変数 ENABLE_SHARED_DOMAINS=1 でのみ有効化（デフォルト無効）
# Render Dashboard で設定すること。未設定時は is_shared_domain / add_shared_domain は即リターンする。
_ENABLED = os.environ.get("ENABLE_SHARED_DOMAINS", "0") == "1"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_raw() -> dict:
    """ロックなしで生データを読む（ロック内から呼ぶこと）"""
    if not os.path.exists(_SHARED_DOMAINS_FILE):
        return {"domains": [], "last_cleanup": _now_iso()}
    try:
        with open(_SHARED_DOMAINS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 旧形式（配列のみ）→ 新形式に自動移行
        if isinstance(data, list):
            data = {
                "domains": [{"domain": d, "added_at": _now_iso()} for d in data],
                "last_cleanup": _now_iso(),
            }
        return data
    except Exception:
        return {"domains": [], "last_cleanup": _now_iso()}


def _save_raw(data: dict):
    """ロックなしで書き込む（ロック内から呼ぶこと）"""
    os.makedirs(os.path.dirname(_SHARED_DOMAINS_FILE), exist_ok=True)
    with open(_SHARED_DOMAINS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


def _cleanup(data: dict) -> dict:
    """7日超の古いエントリを削除し、10000件上限を適用する"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=_CLEANUP_DAYS)
    kept = []
    for entry in data.get("domains", []):
        try:
            added = datetime.fromisoformat(entry["added_at"])
            if added.tzinfo is None:
                added = added.replace(tzinfo=timezone.utc)
            if added >= cutoff:
                kept.append(entry)
        except Exception:
            kept.append(entry)  # パース失敗は保持
    # 上限超えは古い順から削除
    if len(kept) > _MAX_ENTRIES:
        kept = kept[-_MAX_ENTRIES:]
    data["domains"] = kept
    data["last_cleanup"] = _now_iso()
    return data


def startup_cleanup():
    """起動時に一度だけ呼ぶ。古いエントリを削除する。ENABLE_SHARED_DOMAINS=1 のときのみ動作。"""
    if not _ENABLED:
        return
    with _SHARED_DOMAINS_LOCK:
        data = _load_raw()
        data = _cleanup(data)
        _save_raw(data)


def is_shared_domain(domain: str) -> bool:
    """別プロセスが処理済みのドメインか確認する。ENABLE_SHARED_DOMAINS=1 のときのみ有効。"""
    if not _ENABLED or not domain:
        return False
    with _SHARED_DOMAINS_LOCK:
        data = _load_raw()
    domain_set = {entry["domain"] for entry in data.get("domains", [])}
    return domain in domain_set


def add_shared_domain(domain: str) -> bool:
    """ドメインを共有リストに追加する。ENABLE_SHARED_DOMAINS=1 のときのみ有効。既存なら False を返す。"""
    if not _ENABLED or not domain:
        return False
    with _SHARED_DOMAINS_LOCK:
        data = _load_raw()
        domain_set = {entry["domain"] for entry in data.get("domains", [])}
        if domain in domain_set:
            return False
        data.setdefault("domains", []).append({"domain": domain, "added_at": _now_iso()})
        _save_raw(data)
    return True
