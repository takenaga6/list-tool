"""
tests/conftest.py — テスト共通フィクスチャ

shared_domains ファイルを各テスト後にクリアし、テスト間の状態汚染を防ぐ。
"""
import os
import sys
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.fixture(autouse=True)
def cleanup_shared_domains():
    """各テスト後に processed_domains_shared.json とそのロックファイルをクリアする"""
    yield
    try:
        from config import OUTPUT_DIR
        shared_file = os.path.join(OUTPUT_DIR, "processed_domains_shared.json")
        lock_file = shared_file + ".lock"
        for path in (shared_file, lock_file):
            if os.path.exists(path):
                os.remove(path)
    except Exception:
        pass
