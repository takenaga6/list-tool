"""Phase 6.2B: NG業種リスト追加のテスト

追加キーワード（出張ストレッチ・整体院等）が pre_screen() で NG 判定されること、
保険・産業医・健康器具等は NG にならないことを確認する。
"""
import unittest

from agents.rank_agent import pre_screen
from config import NG_INDUSTRY_KEYWORDS


def _make_result(title: str = "", snippet: str = "", url: str = "https://example.co.jp/") -> dict:
    return {
        "url": url,
        "title": title,
        "snippet": snippet,
        "search_query": "test",
        "is_media_page": False,
    }


class TestNewNgKeywordsRejected(unittest.TestCase):
    """Phase 6.2B.1 で追加したキーワードが pre_screen() でNG判定される"""

    # ── 出張・派遣ストレッチ系 ──────────────────────────

    def test_dejang_stretch_in_title_is_ng(self):
        passed, reason = pre_screen(_make_result(title="出張ストレッチサービス株式会社"))
        self.assertFalse(passed)
        self.assertIn("NG業種", reason)

    def test_office_stretch_in_snippet_is_ng(self):
        passed, reason = pre_screen(_make_result(snippet="オフィスストレッチを法人向けに提供しています"))
        self.assertFalse(passed)
        self.assertIn("NG業種", reason)

    def test_haken_stretch_is_ng(self):
        passed, reason = pre_screen(_make_result(snippet="派遣ストレッチで企業の健康支援"))
        self.assertFalse(passed)
        self.assertIn("NG業種", reason)

    # ── 出張・派遣マッサージ系 ──────────────────────────

    def test_dejang_massage_is_ng(self):
        passed, reason = pre_screen(_make_result(title="出張マッサージ 株式会社テスト"))
        self.assertFalse(passed)
        self.assertIn("NG業種", reason)

    def test_office_massage_is_ng(self):
        passed, reason = pre_screen(_make_result(snippet="オフィスマッサージを企業に出張提供"))
        self.assertFalse(passed)
        self.assertIn("NG業種", reason)

    def test_kigyo_massage_is_ng(self):
        passed, reason = pre_screen(_make_result(snippet="企業向けマッサージサービスを展開"))
        self.assertFalse(passed)
        self.assertIn("NG業種", reason)

    # ── 出張ヨガ・フィットネス系 ──────────────────────────

    def test_office_yoga_is_ng(self):
        passed, reason = pre_screen(_make_result(title="オフィスヨガ株式会社 企業向けヨガ"))
        self.assertFalse(passed)
        self.assertIn("NG業種", reason)

    def test_dejang_fitness_is_ng(self):
        passed, reason = pre_screen(_make_result(snippet="出張フィットネスで社員の運動不足解消"))
        self.assertFalse(passed)
        self.assertIn("NG業種", reason)

    def test_kigyo_fitness_is_ng(self):
        passed, reason = pre_screen(_make_result(snippet="企業向けフィットネスサービスを提供"))
        self.assertFalse(passed)
        self.assertIn("NG業種", reason)

    # ── 整体・整骨系 ──────────────────────────────────

    def test_seitai_in_is_ng(self):
        passed, reason = pre_screen(_make_result(title="○○整体院 渋谷院"))
        self.assertFalse(passed)
        self.assertIn("NG業種", reason)

    def test_seikotsu_in_is_ng(self):
        passed, reason = pre_screen(_make_result(snippet="整骨院を運営する株式会社"))
        self.assertFalse(passed)
        self.assertIn("NG業種", reason)

    def test_setsukotsu_in_is_ng(self):
        passed, reason = pre_screen(_make_result(snippet="接骨院チェーンを運営"))
        self.assertFalse(passed)
        self.assertIn("NG業種", reason)

    def test_chiropractic_is_ng(self):
        passed, reason = pre_screen(_make_result(snippet="カイロプラクティックの専門院"))
        self.assertFalse(passed)
        self.assertIn("NG業種", reason)


class TestNotNgIndustries(unittest.TestCase):
    """業種NG にしない企業（Well Body のターゲット候補・連携先）"""

    def test_insurance_agency_not_ng(self):
        # 保険代理店は業種NG にならない（業種としての保険・金融は除外しない）
        passed, _ = pre_screen(_make_result(
            title="やさしいほけん相談室 株式会社",
            snippet="保険相談室として地域の皆様に寄り添います"
        ))
        self.assertTrue(passed, "保険代理店は業種NGにならないこと")

    def test_industrial_doctor_service_not_ng(self):
        # 産業医サービスは連携先候補のため NG にしない
        passed, _ = pre_screen(_make_result(
            title="○○産業医サービス株式会社",
            snippet="産業医の派遣・選任サポート、産業保健を支援"
        ))
        self.assertTrue(passed, "産業医サービスは業種NGにならないこと")

    def test_health_equipment_maker_not_ng(self):
        # 健康器具メーカーは物販会社であり競合でない
        passed, _ = pre_screen(_make_result(
            title="健康器具製造株式会社",
            snippet="オフィス向け健康器具の製造販売"
        ))
        self.assertTrue(passed, "健康器具製造は業種NGにならないこと")

    def test_normal_manufacturing_not_ng(self):
        passed, _ = pre_screen(_make_result(
            title="株式会社テスト製造",
            snippet="精密部品を製造する会社です"
        ))
        self.assertTrue(passed)

    def test_yoga_studio_chain_not_ng_if_no_office_keyword(self):
        # 「ヨガ」単体はNGではない（オフィス・出張が付く場合のみNG）
        passed, _ = pre_screen(_make_result(
            title="ヨガスタジオ株式会社",
            snippet="全国にヨガスタジオを展開"
        ))
        self.assertTrue(passed, "ヨガスタジオ（出張/オフィスなし）は業種NGにならないこと")

    def test_fitness_gym_not_ng_if_no_office_keyword(self):
        # 「フィットネス」単体もNG不対象（「企業向け・オフィス・出張」がある場合のみ）
        passed, _ = pre_screen(_make_result(
            title="フィットネスクラブ株式会社",
            snippet="全国にスポーツジムを展開"
        ))
        self.assertTrue(passed, "フィットネスジム（出張/オフィスなし）は業種NGにならないこと")


class TestNgKeywordsInConfig(unittest.TestCase):
    """config.py に追加されたキーワードが正しく含まれている"""

    def test_added_keywords_present(self):
        added = [
            "出張ストレッチ", "オフィスストレッチ", "派遣ストレッチ",
            "出張マッサージ", "オフィスマッサージ", "派遣マッサージ",
            "訪問マッサージ", "企業向けマッサージ",
            "出張ヨガ", "オフィスヨガ",
            "出張フィットネス", "オフィスフィットネス", "企業向けフィットネス",
            "整体院", "整骨院", "接骨院",
            "カイロプラクティック", "リフレクソロジー",
        ]
        for kw in added:
            with self.subTest(kw=kw):
                self.assertIn(kw, NG_INDUSTRY_KEYWORDS, f"{kw!r} が NG_INDUSTRY_KEYWORDS にない")

    def test_existing_keywords_preserved(self):
        # 既存キーワードが削除されていないこと
        existing = ["建設", "病院", "介護", "警備", "SES", "清掃業"]
        for kw in existing:
            with self.subTest(kw=kw):
                self.assertIn(kw, NG_INDUSTRY_KEYWORDS, f"{kw!r} が削除されてしまっている")

    def test_insurance_not_in_ng_keywords(self):
        # 保険・金融は業種NGリストに含まれていないこと（事業判断）
        for kw in ["保険", "金融", "銀行"]:
            with self.subTest(kw=kw):
                self.assertNotIn(kw, NG_INDUSTRY_KEYWORDS, f"{kw!r} が誤ってNG業種に含まれている")


if __name__ == "__main__":
    unittest.main()
