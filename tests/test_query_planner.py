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


if __name__ == "__main__":
    unittest.main()
