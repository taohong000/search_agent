import unittest

from search_agent.llm_client import build_prompt


class LlmClientTests(unittest.TestCase):
    def test_build_prompt_returns_user_message_content(self):
        prompt = build_prompt("上海公积金是如何缴存的", [], [], [])

        self.assertIsInstance(prompt, str)
        self.assertIn("用户问题：上海公积金是如何缴存的", prompt)
        self.assertIn("本地资料：", prompt)
        self.assertIn("搜索结果：", prompt)
        self.assertIn("网页正文：", prompt)


if __name__ == "__main__":
    unittest.main()
