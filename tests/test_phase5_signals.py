"""Phase 5 新規シグナル・必須条件緩和の単体テスト。

カバー範囲:
  1. Phase 1 必須条件緩和確認（③④⑤が削除されたこと）
  2. 新規シグナル S7/S8/S9/S10 の検出ロジック
  3. 相互作用ボーナスの判定ロジック
"""

import unittest

from agents.rank_agent import (
    check_phase1_must_conditions,
    check_s7_iso_cert,
    check_s8_sdgs,
    check_s9_president_message_health,
    check_s10_profitable_industry,
    check_interaction_bonus,
)


# ============================================================
# 共通テストデータ
# ============================================================

# 健康経営・採用・福利厚生を含む標準的なHP本文
_STD_PAGE_TEXT = (
    "私たちは健康経営を推進しています。健康経営優良法人2024に認定。"
    "従業員の健康を大切にし、ストレスチェック・産業医面談を実施。"
    "採用情報はこちら。新卒採用・中途採用ともに募集中。"
    "福利厚生として人間ドック、マッサージ、社員旅行、リフレッシュ休暇を提供。"
)

# 健康経営・採用・福利厚生をすべて含まないシンプルなHP本文
_BARE_PAGE_TEXT = "当社は東京都中央区に拠点を置くサービス企業です。製品についてはお問い合わせください。"


# ============================================================
# 1. Phase 1 必須条件緩和の確認（最優先）
# ============================================================


class TestPhase1Relaxation(unittest.TestCase):
    """Phase 5 で ③HP健康経営 / ④HP採用情報 / ⑤福利厚生 が必須条件から削除されたことを確認。"""

    def test_phase1_no_health_keiei_passes(self):
        """HP健康経営記載なし → Phase 1必須条件を通過する（③削除済み）."""
        company_info = {
            "company_name": "株式会社テスト",
            "industry": "サービス業",
            "employee_count": "50",
        }
        # 健康経営キーワードを含まないテキスト
        page_text = "採用情報。新卒・中途採用募集中。福利厚生としてマッサージ完備。"
        ok, reason = check_phase1_must_conditions(company_info, page_text)
        self.assertTrue(ok, f"健康経営記載なしで必須条件NGになった（③は削除済みのはず）: {reason}")

    def test_phase1_no_recruit_passes(self):
        """HP採用情報なし → Phase 1必須条件を通過する（④削除済み）."""
        company_info = {
            "company_name": "株式会社テスト",
            "industry": "サービス業",
            "employee_count": "50",
        }
        # 採用情報キーワードを含まないテキスト
        page_text = "健康経営に注力しています。福利厚生としてマッサージ・人間ドックを提供。"
        ok, reason = check_phase1_must_conditions(company_info, page_text)
        self.assertTrue(ok, f"採用情報なしで必須条件NGになった（④は削除済みのはず）: {reason}")

    def test_phase1_no_welfare_passes(self):
        """福利厚生記載なし（士業以外）→ Phase 1必須条件を通過する（⑤削除済み）."""
        company_info = {
            "company_name": "株式会社テスト",
            "industry": "製造業",
            "employee_count": "50",
        }
        # 福利厚生キーワードを含まないテキスト
        page_text = "健康経営優良法人に認定。新卒採用・中途採用を実施しています。"
        ok, reason = check_phase1_must_conditions(company_info, page_text)
        self.assertTrue(ok, f"福利厚生記載なしで必須条件NGになった（⑤は削除済みのはず）: {reason}")

    def test_phase1_ng_industry_still_blocks(self):
        """広告代理店・デジタルマーケ等は引き続き必須条件NGになる（①は維持）."""
        ng_cases = [
            ("広告代理店", "株式会社テスト広告"),
            ("デジタルマーケティング", "テストマーケ株式会社"),
            ("PR会社", "株式会社テストPR"),
        ]
        for industry, company_name in ng_cases:
            with self.subTest(industry=industry):
                company_info = {
                    "company_name": company_name,
                    "industry": industry,
                    "employee_count": "50",
                }
                ok, reason = check_phase1_must_conditions(company_info, _STD_PAGE_TEXT)
                self.assertFalse(ok, f"{industry} がNGにならなかった")
                self.assertIn("NG業種", reason)

    def test_phase1_employee_filter_still_blocks(self):
        """従業員500名以上は引き続きNGになる（⑥は維持）."""
        company_info = {
            "company_name": "株式会社テスト",
            "industry": "サービス業",
            "employee_count": "600",
        }
        ok, reason = check_phase1_must_conditions(company_info, _STD_PAGE_TEXT)
        self.assertFalse(ok, "600名がNGにならなかった")
        self.assertIn("600", reason)

        # 大手プライム子会社は例外: 600名でも通過する
        page_text_prime = _STD_PAGE_TEXT + " 当社は東証プライム上場の親会社の100%子会社です。"
        ok_prime, _ = check_phase1_must_conditions(company_info, page_text_prime)
        self.assertTrue(ok_prime, "プライム子会社例外が600名でも効かなかった")


# ============================================================
# 2. 新規シグナル S7/S8/S9/S10 の検出テスト（高優先）
# ============================================================


class TestS7IsoCert(unittest.TestCase):
    """S7: ISO認定キーワードの検出。"""

    def test_s7_iso_detected(self):
        """ISO9001 / ISO27001 / ISMS / プライバシーマーク → True."""
        cases = [
            "ISO9001認証を取得しています。",
            "ISO 27001認定を取得済みです。",
            "ISMSを導入しました。",
            "プライバシーマーク（Pマーク）取得済み。",
            "ISO14001・ISO45001を取得しています。",
        ]
        for text in cases:
            with self.subTest(text=text[:30]):
                matched, hits = check_s7_iso_cert(text)
                self.assertTrue(matched, f"ISO認定が検出されなかった: {text}")
                self.assertTrue(len(hits) > 0)

    def test_s7_iso_general_terms_excluded(self):
        """一般語「情報セキュリティ」「品質マネジメント」「環境マネジメント」は検出しない（v2.0で除外）."""
        cases = [
            "情報セキュリティに取り組んでいます。",
            "品質マネジメントを徹底しています。",
            "環境マネジメントシステムを導入しています。",
            "情報セキュリティポリシーを定めています。",
        ]
        for text in cases:
            with self.subTest(text=text[:30]):
                matched, hits = check_s7_iso_cert(text)
                self.assertFalse(
                    matched,
                    f"一般語なのにISO認定と判定された（v2.0除外済みのはず）: {text} / hits={hits}",
                )


class TestS8Sdgs(unittest.TestCase):
    """S8: SDGs/サステナビリティキーワードの検出。"""

    def test_s8_sdgs_detected(self):
        """SDGs / ESG経営 / サステナビリティ → True."""
        cases = [
            "SDGsへの取り組みを推進しています。",
            "ESG経営を実践しています。",
            "サステナビリティレポートを公開しています。",
            "持続可能な社会の実現に向けて取り組んでいます。",
            "TCFD提言に基づく情報開示を行っています。",
        ]
        for text in cases:
            with self.subTest(text=text[:30]):
                matched, hits = check_s8_sdgs(text)
                self.assertTrue(matched, f"SDGsキーワードが検出されなかった: {text}")
                self.assertTrue(len(hits) > 0)

    def test_s8_carbon_neutral_excluded(self):
        """「カーボンニュートラル」「脱炭素」だけでは SDGs と判定しない（v2.0で除外）."""
        cases = [
            "カーボンニュートラルを目指しています。",
            "脱炭素社会の実現に向けて取り組んでいます。",
            "CO2削減に取り組んでいます。",
        ]
        for text in cases:
            with self.subTest(text=text[:30]):
                matched, _ = check_s8_sdgs(text)
                self.assertFalse(
                    matched,
                    f"カーボンニュートラルのみなのにSDGsと判定された（除外済みのはず）: {text}",
                )


class TestS9PresidentHealth(unittest.TestCase):
    """S9: 社長メッセージ × 健康記載（簡易版）の検出。"""

    def test_s9_president_health_detected(self):
        """社長メッセージページキーワード AND 健康ワード → True."""
        cases = [
            "社長メッセージ 健康経営を推進することが私の使命です。",
            "代表挨拶 従業員の健康を最優先に考えています。",
            "トップメッセージ ウェルビーイングの実現に向けて。",
            # 英語キーワードは URL パス文字列（小文字）として登場する想定
            "Link: /message 健康経営への取り組みをご紹介します。",
        ]
        for text in cases:
            with self.subTest(text=text[:30]):
                self.assertTrue(
                    check_s9_president_message_health(text),
                    f"社長メッセージ×健康が検出されなかった: {text}",
                )

    def test_s9_no_president_page_returns_false(self):
        """社長メッセージページキーワードがない場合 → False."""
        # 健康ワードはあるが社長メッセージキーワードなし
        text = "当社は健康経営を推進しています。従業員の健康を大切にしています。"
        self.assertFalse(
            check_s9_president_message_health(text),
            "社長メッセージページキーワードなしなのにTrueになった",
        )

    def test_s9_no_health_keyword_returns_false(self):
        """社長メッセージページキーワードはあるが健康ワードがない場合 → False."""
        text = "社長メッセージ 当社の製品・サービスについてご紹介します。売上拡大を目指しています。"
        self.assertFalse(
            check_s9_president_message_health(text),
            "健康ワードなしなのにTrueになった",
        )

    def test_s9_empty_text_returns_false(self):
        """空テキスト → False."""
        self.assertFalse(check_s9_president_message_health(""))
        self.assertFalse(check_s9_president_message_health(None))  # type: ignore


class TestS10ProfitableIndustry(unittest.TestCase):
    """S10: 儲かっている業界フラグの2段階判定。"""

    def test_s10_profitable_industry_detected(self):
        """PROFITABLE_INDUSTRY_KEYWORDS に含まれる業種 → 0より大きいポイントを返す."""
        cases = [
            ("弁護士法人として運営", "弁護士法人"),
            ("コンサルティング会社です", "経営コンサル"),
            ("SaaSプロダクトを提供しています", "SaaS"),
            ("総合商社として活動", "総合商社"),
            ("保険代理店業務", "保険代理店"),
        ]
        for text, industry in cases:
            with self.subTest(industry=industry):
                pts, hits = check_s10_profitable_industry(text, industry_text=industry)
                self.assertGreater(pts, 0, f"{industry} が 0点になった")
                self.assertTrue(len(hits) > 0)

    def test_s10_stage1_only_returns_1pt(self):
        """Stage1（KWマッチ）のみ・Stage2フィルター未通過 → +1点."""
        # 弁護士法人・従業員5名・親会社なし・資本金低い → Stage2未通過
        pts, hits = check_s10_profitable_industry(
            text="弁護士法人として運営しています",
            industry_text="弁護士法人",
            company_info={"employee_count": "5"},
        )
        self.assertEqual(pts, 1, f"Stage1のみのはずが {pts}点になった / hits={hits}")

    def test_s10_stage2_via_employee_count(self):
        """Stage2: 従業員50名以上 → +3点."""
        pts, hits = check_s10_profitable_industry(
            text="コンサルティングサービスを提供しています",
            industry_text="経営コンサル",
            company_info={"employee_count": "80"},
        )
        self.assertEqual(pts, 3, f"従業員80名でStage2通過 → 3点のはずが {pts}点 / hits={hits}")

    def test_s10_stage2_via_capital(self):
        """Stage2: 資本金1億円以上（page_text から抽出）→ +3点."""
        pts, hits = check_s10_profitable_industry(
            text="SaaSプロダクトを提供。資本金1億5,000万円。",
            industry_text="SaaS",
            company_info={"employee_count": "30"},  # 50名未満
        )
        self.assertEqual(pts, 3, f"資本金1.5億でStage2通過 → 3点のはずが {pts}点 / hits={hits}")

    def test_s10_no_match_returns_0(self):
        """PROFITABLE_INDUSTRY_KEYWORDS に含まれない業種 → 0点."""
        pts, hits = check_s10_profitable_industry(
            text="金属加工の工場です",
            industry_text="金属加工",
            company_info={"employee_count": "100"},
        )
        self.assertEqual(pts, 0, f"マッチなしのはずが {pts}点 / hits={hits}")


# ============================================================
# 3. 相互作用ボーナスのテスト（中優先）
# ============================================================


class TestInteractionBonus(unittest.TestCase):
    """相互作用ボーナス: 3点セット6種 + シグナル5個以上 → +3点。"""

    def test_interaction_bonus_triple_set(self):
        """3点セット達成（s4+s7+s8）→ +3点."""
        signals = {
            "s4_kenko_keiei": True,
            "s7_iso": True,
            "s8_sdgs": True,
        }
        pts, reason = check_interaction_bonus(signals)
        self.assertEqual(pts, 3, f"3点セットで +3点のはずが {pts}点 / reason={reason}")
        self.assertIn("3点セット", reason)

    def test_interaction_bonus_all_triple_sets(self):
        """6種の3点セットそれぞれが +3点を返す."""
        triple_sets = [
            {"s4_kenko_keiei": True, "s7_iso": True, "s10_profitable": True},
            {"s4_kenko_keiei": True, "s7_iso": True, "s8_sdgs": True},
            {"s4_kenko_keiei": True, "s7_iso": True, "s9_president_health": True},
            {"s7_iso": True, "s9_president_health": True, "s10_profitable": True},
            {"s7_iso": True, "s9_president_health": True, "s3_welfare": True},
            {"s4_kenko_keiei": True, "s8_sdgs": True, "s10_profitable": True},
        ]
        for sigs in triple_sets:
            with self.subTest(signals=list(sigs.keys())):
                pts, reason = check_interaction_bonus(sigs)
                self.assertEqual(pts, 3, f"3点セット未達成: {sigs} / reason={reason}")

    def test_interaction_bonus_5plus_signals(self):
        """シグナル5個以上保有 → +3点."""
        signals = {
            "s1_pr": True,
            "s3_welfare": True,
            "s4_kenko_keiei": True,
            "s6_jisha_bldg": True,
            "s8_sdgs": True,
        }
        pts, reason = check_interaction_bonus(signals)
        self.assertEqual(pts, 3, f"シグナル5個以上で +3点のはずが {pts}点 / reason={reason}")
        self.assertIn("5", reason)

    def test_interaction_bonus_no_double_counting(self):
        """3点セット達成 AND 5個以上両方該当 → +3点のみ（重複加算なし）."""
        signals = {
            "s4_kenko_keiei": True,
            "s7_iso": True,
            "s8_sdgs": True,   # 3点セット達成
            "s3_welfare": True,
            "s1_pr": True,
            "s10_profitable": True,  # 6個保有（5個以上も達成）
        }
        pts, reason = check_interaction_bonus(signals)
        self.assertEqual(pts, 3, f"重複加算されて3点超になった: {pts}点 / reason={reason}")

    def test_interaction_bonus_4signals_no_triple(self):
        """4個保有・3点セット未達成 → +0点."""
        signals = {
            "s1_pr": True,
            "s3_welfare": True,
            "s5_renewal": True,
            "s6_jisha_bldg": True,
        }
        pts, reason = check_interaction_bonus(signals)
        self.assertEqual(pts, 0, f"4個・3点セット未達成は0点のはずが {pts}点 / reason={reason}")

    def test_interaction_bonus_empty_signals(self):
        """シグナル0個 → +0点."""
        pts, reason = check_interaction_bonus({})
        self.assertEqual(pts, 0)
        self.assertEqual(reason, "")

    def test_interaction_bonus_undefined_keys_are_false(self):
        """未定義キーは False 扱い → 部分的な dict でも安全に動作する."""
        # s8_sdgs が未定義 → 3点セット未達成
        signals = {"s4_kenko_keiei": True, "s7_iso": True}
        pts, _ = check_interaction_bonus(signals)
        self.assertEqual(pts, 0, "未定義キーがFalseになっていない")


if __name__ == "__main__":
    unittest.main()
