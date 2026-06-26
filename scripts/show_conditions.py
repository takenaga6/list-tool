#!/usr/bin/env python3
"""現在ツールに設定されている「リスト条件」を1コマンドで全部ダンプする。

config.py と agents/rank_agent.py の両方を参照する（キーワード定義は
rank_agent.py 側にあるものも多いため、config だけ見ると「空」に誤認する）。

加点/減点の点数とランク閾値は rank_agent.py 内のロジックにハードコードされて
いるため、ここでは「ドキュメント値」として明示する（変更時はこの定数も更新する）。

使い方（リポジトリroot / Render Shell どちらでも可）:
    python scripts/show_conditions.py
"""

import os
import sys

# どこから実行してもリポジトリrootを import パスに入れる
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config as c
from agents import rank_agent as r


def _section(title: str) -> None:
    print("\n" + "─" * 60)
    print(f"■ {title}")
    print("─" * 60)


def _kv_list(label: str, values) -> None:
    values = list(values or [])
    print(f"\n{label}（{len(values)}件）")
    print("  " + "、".join(map(str, values)) if values else "  （空）")


def main() -> int:
    print("=" * 60)
    print("現在のリスト条件まとめ（config.py + rank_agent.py）")
    print("=" * 60)
    print(f"\nランクロジック版 RANK_LOGIC_VERSION = {getattr(c, 'RANK_LOGIC_VERSION', '(未設定)')}")

    # ── 必須NG / 除外条件 ────────────────────────────────
    _section("必須NG・除外条件")
    print(f"\n従業員数帯 EMPLOYEE_RANGE_CONFIG\n  {getattr(c, 'EMPLOYEE_RANGE_CONFIG', '(未設定)')}")
    _kv_list("NG業種 NG_INDUSTRY_KEYWORDS", getattr(c, "NG_INDUSTRY_KEYWORDS", []))
    _kv_list("NG業種(広告/メディア) NG_INDUSTRY_KEYWORDS_PHASE1", getattr(c, "NG_INDUSTRY_KEYWORDS_PHASE1", []))
    _kv_list("レッドオーシャン必須NG INDUSTRY_PROFIT_MEDIUM_KEYWORDS", getattr(c, "INDUSTRY_PROFIT_MEDIUM_KEYWORDS", []))
    _kv_list("福利厚生・士業例外 FUKURI_LEGAL_ONLY_OK_INDUSTRY", getattr(c, "FUKURI_LEGAL_ONLY_OK_INDUSTRY", []))
    _kv_list("プライム子会社キーワード PARENT_PRIME_KEYWORDS", getattr(c, "PARENT_PRIME_KEYWORDS", []))

    # ── シグナル判定キーワード（rank_agent.py 側）────────────
    _section("シグナル判定キーワード（rank_agent.py）")
    _kv_list("S1 PR有料媒体 PR_MEDIA_KEYWORDS", getattr(r, "PR_MEDIA_KEYWORDS", []))
    _kv_list("S1 PR有料媒体ドメイン PR_MEDIA_DOMAINS", getattr(r, "PR_MEDIA_DOMAINS", getattr(c, "PR_MEDIA_DOMAINS", [])))
    _kv_list("S2 健康経営メディア HEALTH_MEDIA_KEYWORDS", getattr(r, "HEALTH_MEDIA_KEYWORDS", []))
    _kv_list("S2 健康経営メディアドメイン HEALTH_MEDIA_DOMAINS", getattr(r, "HEALTH_MEDIA_DOMAINS", getattr(c, "HEALTH_MEDIA_DOMAINS", [])))
    _kv_list("S3 法定外福利厚生 WELFARE_KEYWORDS", getattr(r, "WELFARE_KEYWORDS", []))
    _kv_list("S4 健康経営注力 HEALTH_KEIEI_REQUIRED_KEYWORDS", getattr(c, "HEALTH_KEIEI_REQUIRED_KEYWORDS", []))

    # ── 加点 / 減点 / ランク閾値（rank_agent.py にハードコード）──
    _section("加点・減点・ランク閾値  ※rank_agent.py のロジック内ハードコード")
    print("""
加点 evaluate_useful_conditions:
  +2  業種=商社/卸売・金融・教育ソフト ／ 利益率「高」 ／ 大手プライム子会社
       ／ 採用媒体3つ以上 ／ ISO認定(S7)
  +1  業種=人材派遣・投資運用・士業 ／ 利益率「中-高/低-中」 ／ 採用媒体1-2
       ／ HP健康経営(S4) ／ 法定外福利厚生(S3) ／ 都心一等地 ／ SDGs(S8)
       ／ 社長メッセージ健康(S9)
  +1〜3  儲かる業界(S10)
  +3  相互作用ボーナス（3点セット or 5シグナル以上）

減点 evaluate_negative_conditions:
  -2  業種=製造業・IT/通信・コンサル/サービス ／ 利益率「中」 ／ 離職率「中」
  -1  立地=地方/都市部 ／ 創業家オーナー

ランク閾値 evaluate_rank_v2（合計点 = 加点 − 減点）:
  A ≥ 8点 ／ B 5〜7点 ／ C 1〜4点 ／ NG ≤ 0点
  （登録/スキップ閾値は main.py 側）
""".rstrip())

    print("\n" + "=" * 60)
    print("※ 加点/減点/閾値の数値を変えたら、この説明文も更新すること")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
