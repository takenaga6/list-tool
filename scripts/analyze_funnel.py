#!/usr/bin/env python3
"""本番ログ(tool.log)を解析し、リストアップ歩留まり（ファネル）の落ちどころを定量化する。

回収トラックの次テーマ(B): scraper_agent.check_company_fields が従業員数・TELを
ハード必須にしているため、トップに従業員数が無い企業が「企業HP項目不足」で脱落する。
これが本番リストアップの歩留まりをどれだけ削っているかをログから定量化する。

集計する段階（候補がどこで落ちたか）:
  screener_ng        : pre_screen でNG（スニペット段階・HTTP前）
  hp_fields_missing  : check_company_fields 不足（従業員数/TEL/日本語/IR等）
  rank_ng            : evaluate_rank_v2 でNG
  low_score          : スコア不足
  pending            : 保留（要確認リスト）
  registered         : 登録成功

特に hp_fields_missing は「未取得フィールド別」に内訳表示する。

使い方（Render Shell 推奨。tool.log は /data 等に出力されている）:
  python scripts/analyze_funnel.py                 # 既定パスを自動探索
  python scripts/analyze_funnel.py /data/tool.log  # パス指定
  python scripts/analyze_funnel.py --top 15        # 内訳の表示件数
"""

import os
import re
import sys
import argparse
from collections import Counter

# 候補パス（環境により異なる）
_CANDIDATE_LOGS = [
    os.environ.get("LOG_FILE", ""),
    "/data/tool.log",
    os.path.join(os.environ.get("DATA_DIR", ""), "tool.log") if os.environ.get("DATA_DIR") else "",
    os.path.join(os.environ.get("OUTPUT_DIR", "output"), "tool.log"),
    "output/tool.log",
]

_PATTERNS = {
    "screener_ng":  re.compile(r"\[FUNNEL\] screener_ng \[([^\]]*)\]"),
    "rank_ng":      re.compile(r"\[FUNNEL\] rank_ng \[([^\]]*)\]"),
    "low_score":    re.compile(r"\[FUNNEL\] low_score"),
    "pending":      re.compile(r"\[FUNNEL\] pending"),
    "registered":   re.compile(r"\[FUNNEL\] registered"),
    "scrape_ok":    re.compile(r"\[FUNNEL\] scrape_success"),
}
# check_company_fields 脱落（[FUNNEL]タグ無し・未取得リストを含む）
_HP_MISS = re.compile(r"企業HP項目不足（未取得: (\[[^\]]*\]|[^）]*)）")


def resolve_log_path(arg_path: str | None) -> str | None:
    if arg_path:
        return arg_path if os.path.exists(arg_path) else None
    for p in _CANDIDATE_LOGS:
        if p and os.path.exists(p):
            return p
    return None


def analyze(path: str) -> tuple[Counter, dict[str, Counter]]:
    stage = Counter()
    detail: dict[str, Counter] = {
        "screener_ng": Counter(),
        "rank_ng": Counter(),
        "hp_fields_missing": Counter(),
    }
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = _HP_MISS.search(line)
            if m:
                stage["hp_fields_missing"] += 1
                detail["hp_fields_missing"][m.group(1).strip()] += 1
                continue
            for name, pat in _PATTERNS.items():
                mm = pat.search(line)
                if mm:
                    stage[name] += 1
                    if name in detail:
                        detail[name][mm.group(1).strip()] += 1
                    break
    return stage, detail


def main() -> int:
    ap = argparse.ArgumentParser(description="リストアップ歩留まり(ファネル)解析")
    ap.add_argument("logpath", nargs="?", help="tool.log のパス（省略時は自動探索）")
    ap.add_argument("--top", type=int, default=12, help="内訳の表示件数")
    args = ap.parse_args()

    path = resolve_log_path(args.logpath)
    if not path:
        print("ERROR: tool.log が見つかりません。パスを指定してください。", file=sys.stderr)
        print(f"  探索候補: {[p for p in _CANDIDATE_LOGS if p]}", file=sys.stderr)
        return 1

    print(f"解析対象: {path}")
    stage, detail = analyze(path)

    print("\n" + "=" * 60)
    print("【ファネル集計】候補がどの段階で落ちたか")
    order = ["screener_ng", "hp_fields_missing", "rank_ng", "low_score", "pending", "registered"]
    labels = {
        "screener_ng": "pre_screen NG（スニペット段階）",
        "hp_fields_missing": "企業HP項目不足（従業員数/TEL等）",
        "rank_ng": "ランクNG",
        "low_score": "スコア不足",
        "pending": "保留(pending)",
        "registered": "登録成功",
    }
    total_drop = sum(stage[k] for k in order)
    for k in order:
        n = stage[k]
        pct = (n / total_drop * 100) if total_drop else 0
        print(f"  {labels[k]:32} {n:6}  ({pct:4.1f}%)")
    print(f"  {'(参考) スクレイプ成功 scrape_success':32} {stage['scrape_ok']:6}")

    print("\n■ 企業HP項目不足の内訳（未取得フィールド別）★今回の焦点")
    if not detail["hp_fields_missing"]:
        print("  （該当ログなし）")
    for reason, n in detail["hp_fields_missing"].most_common(args.top):
        print(f"  {n:6}  {reason}")

    print("\n■ pre_screen NG 理由 TOP")
    for reason, n in detail["screener_ng"].most_common(args.top):
        print(f"  {n:6}  {reason}")

    print("\n■ ランクNG 理由 TOP")
    for reason, n in detail["rank_ng"].most_common(args.top):
        print(f"  {n:6}  {reason}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
