import unittest
from pathlib import Path

from search_agent.llm_client import build_evaluation_prompt, build_prompt
from search_agent.models import LocalSearchResult, SearchPlan


class LlmClientTests(unittest.TestCase):
    def test_build_prompt_returns_user_message_content(self):
        prompt = build_prompt("上海公积金是如何缴存的", [], [], [])

        self.assertIsInstance(prompt, str)
        self.assertIn("用户问题：上海公积金是如何缴存的", prompt)
        self.assertIn("本地资料：", prompt)
        self.assertIn("搜索结果：", prompt)
        self.assertIn("网页正文：", prompt)

    def test_build_evaluation_prompt_contains_llm_decision_rubric(self):
        prompt = build_evaluation_prompt(
            "帮我查询一下我个人公积金账户现在余额是多少？",
            ["个人", "公积金"],
            [
                LocalSearchResult(
                    path=Path("公积金.md"),
                    title="公积金办事指南",
                    snippet="介绍住房公积金缴存和提取政策。",
                    matched_terms=["公积金"],
                    score=10,
                )
            ],
            [],
            SearchPlan(terms=["个人", "公积金"], needs_web=False),
        )

        self.assertIn("逐项判断", prompt)
        self.assertIn("用户个人账户", prompt)
        self.assertIn("不要因为命中数量", prompt)
        self.assertIn("每个词尽量 2-6 个汉字", prompt)
        self.assertIn("不要写完整问句或自然语言查询句", prompt)
        self.assertIn("缴费基数", prompt)
        self.assertIn("保留业务领域锚点", prompt)
        self.assertIn("社保", prompt)
        self.assertIn("\"is_sufficient\"", prompt)


if __name__ == "__main__":
    unittest.main()
