# -*- coding: utf-8 -*-
"""
会社名の有効性判定（scraper_agent._clean_company_name から呼ばれる）

Phase 7-B C2: ドライランで発覚した以下パターンを除外する：
  - 句読点・感嘆符を含む文字列（ルール1）
  - 法人格の直後が助詞（「株式会社の〜」パターン）（ルール2）
  - 助詞が4個以上の文章的な文字列（ルール3）
"""
from utils.legal_form import LEGAL_FORMS

_SENTENCE_PARTICLES = frozenset("のでがをにとなは")


def _is_valid_company_name(name: str) -> bool:
    """
    クリーニング後の会社名文字列が正当な会社名かを判定する。

    Returns:
        True  = 有効（登録可）
        False = 無効（空文字を返して除外すべき）
    """
    if not name:
        return False

    # ルール1: 句読点・感嘆符を含む（商業登記規則5条により商号に使用不可）
    if any(c in name for c in "！？。、"):
        return False

    # ルール2: 法人格の直後が助詞（「株式会社の登録商標」等のパターン）
    for lf in LEGAL_FORMS:
        idx = name.find(lf)
        if idx != -1:
            after_idx = idx + len(lf)
            if after_idx < len(name) and name[after_idx] in _SENTENCE_PARTICLES:
                return False

    # ルール3: 助詞が4個以上（「株式会社こころとからだのクリニック」=3個は通過させる）
    if sum(1 for c in name if c in _SENTENCE_PARTICLES) >= 4:
        return False

    return True
