import unittest
from pathlib import Path

from search_agent.evidence_evaluator import EvidenceEvaluator
from search_agent.models import EvidenceDecision, LocalSearchResult, SearchPlan


class DirectLlmEvaluator:
    def evaluate_evidence(self, question, terms, local_sources, rounds, plan):
        return EvidenceDecision(
            is_sufficient=True,
            needs_web=False,
            next_terms=[],
            missing_facts=[],
            reason="大模型判断当前证据充分。",
        )


class EvidenceEvaluatorTests(unittest.TestCase):
    def test_llm_decision_is_used_directly_without_rule_merge(self):
        source = LocalSearchResult(
            path=Path("2018问答.md"),
            title="2018年度住房公积金基数调整问答",
            snippet="上海住房公积金缴存基数可以调整。",
            matched_terms=["住房公积金", "缴存基数"],
            score=10,
        )
        evaluator = EvidenceEvaluator(DirectLlmEvaluator())

        decision = evaluator.evaluate(
            "上海公积金是如何缴存的",
            ["上海", "公积金"],
            [source],
            [],
            SearchPlan(terms=["上海", "公积金"], needs_web=False),
        )

        self.assertTrue(decision.is_sufficient)
        self.assertFalse(decision.needs_web)
        self.assertEqual(decision.next_terms, [])
        self.assertEqual(decision.missing_facts, [])
        self.assertEqual(decision.reason, "大模型判断当前证据充分。")

    def test_fallback_generates_next_terms_when_llm_is_unavailable(self):
        evaluator = EvidenceEvaluator(None)

        decision = evaluator.evaluate(
            "现在上海灵活就业社保最低交多少钱",
            ["上海"],
            [],
            [],
            SearchPlan(terms=["上海"], needs_web=True),
        )

        self.assertFalse(decision.is_sufficient)
        self.assertTrue(decision.needs_web)
        self.assertGreater(len(decision.next_terms), 0)
        self.assertEqual(decision.missing_facts, ["领域不匹配"])


if __name__ == "__main__":
    unittest.main()
