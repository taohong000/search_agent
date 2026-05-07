import unittest

from search_agent.web_ui import merge_chat_update


class WebUiTests(unittest.TestCase):
    def test_merge_chat_update_preserves_previous_turns(self):
        current_display = [
            {"role": "user", "content": "上一问"},
            {"role": "assistant", "content": "上一答"},
            {"role": "user", "content": "当前问"},
            {"role": "assistant", "content": "正在分析问题，请稍候..."},
        ]
        current_update = [
            {"role": "user", "content": "当前问"},
            {"role": "assistant", "content": "当前答"},
        ]

        merged = merge_chat_update(current_display, current_update)

        self.assertEqual(
            merged,
            [
                {"role": "user", "content": "上一问"},
                {"role": "assistant", "content": "上一答"},
                {"role": "user", "content": "当前问"},
                {"role": "assistant", "content": "当前答"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
