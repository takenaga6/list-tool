"""死んだクエリ判定（is_dead_query）の新旧比較・実データ検証スクリプト。

2026-06-04 の fix/query-death-filter（判定3廃止＋復活機構）の実データ検証用。
リポジトリの実装に依存せず、新旧ロジックを両方インラインで持つ自己完結版。
本番（Render）で旧コードが動いていても、stats ファイルさえ読めれば比較できる。

使い方:
    python scripts/verify_death_filter.py                      # DATA_DIR or /data or output から自動探索
    python scripts/verify_death_filter.py path/to/stats.json   # ファイル指定
"""
import json
import os
import sys
from datetime import datetime

RECOVERY_DAYS = 30


def _is_dead_old(s):
    """旧ロジック（判定1+2+3）。"""
    runs = s.get("runs", 0)
    total_hits = s.get("total_hits", 0)
    if runs >= 3 and total_hits == 0:
        return True
    if runs >= 5 and total_hits / runs < 0.05:
        return True
    if (runs >= 5 and total_hits > 0
            and s.get("a_rank", 0) == 0 and s.get("b_rank", 0) == 0
            and s.get("ng_count", 0) > 0):
        return True
    return False


def _days_since(last_run, now):
    if not last_run:
        return None
    try:
        dt = datetime.strptime(last_run, "%Y-%m-%d %H:%M")
    except ValueError:
        return None
    return (now - dt).total_seconds() / 86400.0


def _is_dead_new(s, now):
    """新ロジック（判定1+2のみ＋復活機構）。"""
    runs = s.get("runs", 0)
    total_hits = s.get("total_hits", 0)
    dead = False
    if runs >= 3 and total_hits == 0:
        dead = True
    elif runs >= 5 and total_hits / runs < 0.05:
        dead = True
    if not dead:
        return False
    days = _days_since(s.get("last_run", ""), now)
    if days is not None and days >= RECOVERY_DAYS:
        return False
    return True


def main():
    # ファイルパス決定
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        cands = []
        if os.environ.get("DATA_DIR"):
            cands.append(os.path.join(os.environ["DATA_DIR"], "keyword_stats.json"))
        cands += ["/data/keyword_stats.json", "output/keyword_stats.json"]
        path = next((p for p in cands if os.path.exists(p)), None)
    if not path or not os.path.exists(path):
        print(f"[ERROR] stats ファイルが見つからない: {path}")
        sys.exit(1)

    print(f"読込ファイル: {path}")
    raw = json.load(open(path, encoding="utf-8"))
    q = raw.get("queries", raw)
    now = datetime.now()

    total = len(q)
    old_dead = new_dead = 0
    recovered = 0          # 旧では死、新では生
    recovered_by_recovery = 0  # うち復活機構（30日経過）で生き返った分
    newly_dead = 0         # 旧では生、新では死（あってはならない）
    for k, s in q.items():
        od = _is_dead_old(s)
        nd = _is_dead_new(s, now)
        old_dead += od
        new_dead += nd
        if od and not nd:
            recovered += 1
            # 判定1/2に該当するのに生存＝復活機構で生き返った
            runs = s.get("runs", 0); th = s.get("total_hits", 0)
            crit12 = (runs >= 3 and th == 0) or (runs >= 5 and th / max(runs, 1) < 0.05)
            if crit12:
                recovered_by_recovery += 1
        if nd and not od:
            newly_dead += 1

    print(f"\n=== 新旧比較 ===")
    print(f"クエリ総数           : {total}")
    print(f"旧ロジックで死亡      : {old_dead}")
    print(f"新ロジックで死亡      : {new_dead}")
    print(f"復活（旧死→新生）     : {recovered}")
    print(f"  うち判定3廃止で復活 : {recovered - recovered_by_recovery}")
    print(f"  うち30日復活で復活  : {recovered_by_recovery}")
    print(f"新たに死亡（要調査）  : {newly_dead}  ← 0 であるべき")
    print(f"\n生きるクエリ: {total - old_dead} → {total - new_dead}  "
          f"(+{old_dead - new_dead})")


if __name__ == "__main__":
    main()
