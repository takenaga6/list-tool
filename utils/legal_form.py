# -*- coding: utf-8 -*-
"""法人格マスタ（会社名クリーニング・判定に使用）"""
import logging

logger = logging.getLogger(__name__)

LEGAL_FORMS = [
    "株式会社", "有限会社", "合同会社", "合資会社", "合名会社",
    "一般社団法人", "一般財団法人", "公益社団法人", "公益財団法人",
    "NPO法人", "特定非営利活動法人",
    "(株)", "(有)", "㈱", "㈲",
    "Inc.", "Corp.", "Co., Ltd.", "Co.,Ltd.", "LLC", "Ltd.",
]


def has_legal_form(text: str) -> bool:
    """テキストに法人格が含まれるか判定する。"""
    return any(lf in text for lf in LEGAL_FORMS)
