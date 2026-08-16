import json
import unittest

from topic_pulse_v2.tool_register import (
    DOUBAO_SEARCH_TOOL_NAME,
    HOT_TOPIC_SEARCH_TOOL_NAME,
    TOPIC_MARKDOWN_STORE_TOOL_NAME,
    ToolRegistry,
)


class ToolRegisterTests(unittest.TestCase):
    def test_register_and_get_tool(self):
        registry = ToolRegistry()

        registered_tools = [tool.to_dict() for tool in registry.list()]

        print(json.dumps(registered_tools, ensure_ascii=False, indent=2))

        print("-------------------------------------------")

        print(json.dumps(registry.as_llm_tools(), ensure_ascii=False, indent=2))


        self.assertTrue(registry.has(DOUBAO_SEARCH_TOOL_NAME))
        spec = registry.get(DOUBAO_SEARCH_TOOL_NAME)
        self.assertEqual(spec.metadata["tool_display_name"], "豆包搜索")
        self.assertIn("query", spec.parameters["required"])
        self.assertTrue(registry.has(TOPIC_MARKDOWN_STORE_TOOL_NAME))
        self.assertTrue(registry.has(HOT_TOPIC_SEARCH_TOOL_NAME))

if __name__ == "__main__":
    unittest.main()
