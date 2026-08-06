import unittest

from topic_pulse_v2.llm_call import LLMClient
from topic_pulse_v2.process import ReActAgent
from topic_pulse_v2.tool_register import ToolRegistry


class ReActTopicMemorySelectionTests(unittest.TestCase):
    def test_all_topic_markdown_tools_are_exposed_for_local_topic_matching(self):
        agent = ReActAgent(
            llm_client=LLMClient(),
            tool_registry=ToolRegistry(),
        )

        tools = agent._tool_registry.as_llm_tools()
        tool_names = [tool["function"]["name"] for tool in tools]

        self.assertIn("doubao_search", tool_names)
        self.assertIn("topic_markdown_store", tool_names)
        self.assertIn("topic_markdown_read_summary", tool_names)
        self.assertIn("topic_markdown_read_detail", tool_names)

    def test_prompt_requires_local_match_or_explicit_follow_intent_before_store(self):
        prompt = ReActAgent(
            llm_client=LLMClient(),
            tool_registry=ToolRegistry(),
        )._config.system_prompt

        self.assertIn("# 长期关注话题决策流程", prompt)
        self.assertIn("如果用户明确表达“帮我关注”“持续关注”“长期跟踪”", prompt)
        self.assertIn("必须先调用 topic_markdown_read_summary", prompt)
        self.assertIn("禁止调用 topic_markdown_store", prompt)
        self.assertIn("# 关键工具参数要求", prompt)
        self.assertIn("doubao_search 时，arguments 必须包含 query", prompt)
        self.assertIn("title 和 url 两个英文 key", prompt)
        self.assertIn("禁止使用中文 key", prompt)


if __name__ == "__main__":
    unittest.main()
