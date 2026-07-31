import unittest

from topic_pulse_v2.tool_call import ToolCallRequest, ToolExecutor
from topic_pulse_v2.tool_register import ToolRegistry


async def async_double(value):
    return value * 2


class ToolCallTests(unittest.IsolatedAsyncioTestCase):
    def test_call_sync_tool_successfully(self):
        registry = ToolRegistry()
        registry.register("add", lambda a, b: a + b)
        executor = ToolExecutor(registry)

        result = executor.call("add", {"a": 2, "b": 3})

        self.assertTrue(result.success)
        self.assertEqual(result.result, 5)
        self.assertIsNone(result.error)

    def test_call_returns_error_for_bad_arguments(self):
        registry = ToolRegistry()
        registry.register("add", lambda a, b: a + b)
        executor = ToolExecutor(registry)

        result = executor.call("add", {"a": 2})

        self.assertFalse(result.success)
        self.assertIn("TypeError", result.error)

    async def test_async_call_supports_async_tool(self):
        registry = ToolRegistry()
        registry.register("async_double", async_double)
        executor = ToolExecutor(registry)

        result = await executor.async_call("async_double", {"value": 4})

        self.assertTrue(result.success)
        self.assertEqual(result.result, 8)

    def test_batch_call_preserves_order(self):
        registry = ToolRegistry()
        registry.register("echo", lambda value: value)
        executor = ToolExecutor(registry)

        results = executor.batch_call(
            [
                ToolCallRequest(name="echo", arguments={"value": "a"}),
                ToolCallRequest(name="echo", arguments={"value": "b"}),
            ]
        )

        self.assertEqual([result.result for result in results], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
