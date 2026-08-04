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

        self.assertIn("用户明确表达想要长期关注", prompt)
        self.assertIn("命中了 data/topics 下已经存储的 Markdown 关注话题", prompt)
        self.assertIn("没有返回相关候选，并且用户也没有明确关注", prompt)
        self.assertIn("不要调用 topic_markdown_store", prompt)


if __name__ == "__main__":
    unittest.main()
