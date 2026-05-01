import unittest

from search_agent.query_planner import QueryPlanner


class QueryPlannerTests(unittest.TestCase):
    def test_expands_unemployment_social_security_question(self):
        planner = QueryPlanner()

        plan = planner.initial_plan("我住在上海，现在失业了，我想问下怎么缴纳社保")

        self.assertIn("上海", plan.terms)
        self.assertIn("失业", plan.terms)
        self.assertIn("社保", plan.terms)
        self.assertIn("灵活就业", plan.terms)
        self.assertIn("参保缴费", plan.terms)
        self.assertTrue(plan.needs_web)

    def test_next_round_adds_missing_policy_terms(self):
        planner = QueryPlanner()

        next_terms = planner.next_terms(
            "失业后社保怎么交",
            previous_terms=["失业", "社保"],
            matched_terms={"失业"},
        )

        self.assertIn("灵活就业", next_terms)
        self.assertIn("养老保险", next_terms)
        self.assertIn("医疗保险", next_terms)

    def test_expands_social_insurance_fee_question(self):
        planner = QueryPlanner()

        plan = planner.initial_plan("现在上海灵活就业社会保险费缴费怎么办理")

        self.assertIn("上海", plan.terms)
        self.assertIn("灵活就业", plan.terms)
        self.assertIn("社会保险费", plan.terms)
        self.assertIn("社保", plan.terms)
        self.assertIn("参保缴费", plan.terms)
        self.assertTrue(plan.needs_web)

    def test_expands_social_policy_service_questions(self):
        planner = QueryPlanner()

        cases = [
            ("上海职工医保断缴后补缴，待遇会不会受影响？", ["医保", "医疗保险", "补缴", "待遇"]),
            ("在上海申领生育津贴需要什么条件和材料？", ["生育津贴", "生育保险", "申领", "材料"]),
            ("上海发生工伤后，单位和个人应该怎么申请工伤认定？", ["工伤", "工伤认定", "工伤保险", "申请"]),
            ("外地社保要转到上海，养老保险关系转移怎么办？", ["关系转移", "转移接续", "养老保险"]),
        ]

        for question, expected_terms in cases:
            with self.subTest(question=question):
                plan = planner.initial_plan(question)

            for term in expected_terms:
                self.assertIn(term, plan.terms)

    def test_expands_housing_fund_payment_question_to_core_policy_terms(self):
        planner = QueryPlanner()

        plan = planner.initial_plan("上海公积金是如何缴存的")

        for term in ["缴存基数", "缴存比例", "月缴存额", "基数调整"]:
            self.assertIn(term, plan.terms)


if __name__ == "__main__":
    unittest.main()
