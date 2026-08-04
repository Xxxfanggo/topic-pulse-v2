import os
import unittest
from datetime import datetime

from topic_pulse_v2.llm_call import LLMClient, Message, MiniMaxLLMProvider


def require_minimax_api_key(test_case: unittest.TestCase) -> None:
    if not os.getenv("MINIMAX_API_KEY"):
        test_case.skipTest("Set MINIMAX_API_KEY before running real MiniMax tests.")


class LLMCallTests(unittest.TestCase):
    def test_missing_provider_raises_lookup_error(self):
        client = LLMClient()

        with self.assertRaises(LookupError):
            client.call([Message(role="user", content="hello")])

    def test_minimax_provider_converts_tool_message_with_call_id(self):
        messages = MiniMaxLLMProvider._to_langchain_messages(
            [
                Message(
                    role="assistant",
                    content="",
                    metadata={
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "name": "echo",
                                "args": {"value": "测试"},
                                "type": "tool_call",
                            }
                        ]
                    },
                ),
                Message(
                    role="tool",
                    name="echo",
                    tool_call_id="call-1",
                    content='{"echo": "测试"}',
                ),
            ]
        )

        self.assertEqual(messages[0].tool_calls[0]["id"], "call-1")
        self.assertEqual(messages[1].tool_call_id, "call-1")

    def test_minimax_provider_real_call(self):
        require_minimax_api_key(self)
        provider = MiniMaxLLMProvider()
        client = LLMClient({"minimax": provider}, default_provider="minimax")

        response = client.call(
            [
                Message(
                    role="system",
                    content=(
                        "You are a concise assistant. "
                        f"The current time is {datetime.now()}."
                    ),
                ),
                Message(role="user", content="Reply with the word pong only."),
            ],
            temperature=0,
        )

        self.assertTrue(response.content.strip())
        self.assertEqual(response.model, "MiniMax-M3")
        self.assertIn("response_metadata", response.metadata)


if __name__ == "__main__":
    unittest.main()
