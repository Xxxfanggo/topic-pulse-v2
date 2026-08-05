import unittest

from topic_pulse_v2.process import ReActAgent


class ReActResponseParserTests(unittest.TestCase):
    def test_parse_action_after_think_block(self):
        parsed = ReActAgent._parse_response(
            '<think>需要使用豆包搜索工具查询最新新闻</think>\n'
            '{"thought": "需要联网查询", '
            '"action": "doubao_search", '
            '"arguments": {"query": "韩红最近热点新闻"}}'
        )

        self.assertEqual(parsed["action"], "doubao_search")
        self.assertEqual(parsed["arguments"]["query"], "韩红最近热点新闻")

    def test_parse_prefers_last_react_json_object(self):
        parsed = ReActAgent._parse_response(
            '草稿：{"foo": "bar"}\n'
            '{"thought": "需要保存话题", '
            '"action": "topic_markdown_store", '
            '"arguments": {"topic_name": "韩红最近热点新闻"}}'
        )

        self.assertEqual(parsed["action"], "topic_markdown_store")
        self.assertEqual(parsed["arguments"]["topic_name"], "韩红最近热点新闻")

    def test_parse_final_answer_from_think_and_invalid_outer_json(self):
        parsed = ReActAgent._parse_response(
            '<think>用户说了"你好"</think>\n'
            '{"thought":"用户说了"你好"，需要引导",'
            '"final_answer":"{\\"summary\\":\\"你好，我可以帮你追踪热点。\\",'
            '\\"items\\":[],\\"next_action\\":\\"请补充具体话题。\\"}"}'
        )

        self.assertIn("你好，我可以帮你追踪热点", parsed["final_answer"])

    def test_parse_langchain_tool_call_args_and_id(self):
        parsed = ReActAgent._parse_response(
            "<think>需要使用 doubao_search 查询。</think>",
            [
                {
                    "name": "doubao_search",
                    "args": {"query": "韩红最近热点新闻"},
                    "id": "call-1",
                    "type": "tool_call",
                }
            ],
        )

        self.assertEqual(parsed["action"], "doubao_search")
        self.assertEqual(parsed["arguments"]["query"], "韩红最近热点新闻")
        self.assertEqual(parsed["tool_call_id"], "call-1")

    def test_parse_multiple_langchain_tool_calls(self):
        parsed = ReActAgent._parse_response(
            "",
            [
                {
                    "name": "doubao_search",
                    "args": {"query": "内存条价格走势"},
                    "id": "call-1",
                    "type": "tool_call",
                },
                {
                    "name": "topic_markdown_read_summary",
                    "args": {"query": "内存条价格走势"},
                    "id": "call-2",
                    "type": "tool_call",
                },
            ],
        )

        self.assertEqual(parsed["action"], "doubao_search")
        self.assertEqual(parsed["arguments"]["query"], "内存条价格走势")
        self.assertEqual(len(parsed["tool_calls"]), 2)
        self.assertEqual(parsed["tool_calls"][1]["name"], "topic_markdown_read_summary")

    def test_repair_doubao_search_arguments_uses_user_query(self):
        repaired = ReActAgent._repair_tool_arguments(
            "doubao_search",
            {},
            "查询一下韩红最近的热点新闻",
        )

        self.assertEqual(repaired["query"], "查询一下韩红最近的热点新闻")

    def test_builds_synthetic_tool_call_for_json_action(self):
        tool_call_id = ReActAgent._tool_call_id(
            {"action": "doubao_search"},
            "session-1",
            2,
        )
        tool_calls = ReActAgent._assistant_tool_calls(
            [
                {
                    "id": tool_call_id,
                    "name": "doubao_search",
                    "args": {"query": "测试"},
                    "type": "tool_call",
                }
            ],
        )

        self.assertEqual(tool_call_id, "call_session-1_2")
        self.assertEqual(tool_calls[0]["id"], "call_session-1_2")
        self.assertEqual(tool_calls[0]["name"], "doubao_search")
        self.assertEqual(tool_calls[0]["args"], {"query": "测试"})


if __name__ == "__main__":
    unittest.main()
