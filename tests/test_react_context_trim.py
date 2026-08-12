import unittest

from topic_pulse_v2.context_trim import ReActContextBudget, ReActContextManager
from topic_pulse_v2.session import SessionMessage


class ReActContextManagerTests(unittest.TestCase):
    def test_trims_text_to_budget(self):
        manager = ReActContextManager()

        trimmed = manager.trim_text_to_token_budget("x" * 100, 5)

        self.assertIn("[content trimmed to fit budget]", trimmed)
        self.assertLess(len(trimmed), 80)

    def test_restores_complete_tool_block_with_empty_assistant_content(self):
        manager = ReActContextManager()

        messages = manager.session_history_messages(
            [
                SessionMessage(
                    role="assistant",
                    content="",
                    metadata={
                        "type": "tool_call",
                        "visibility": "internal",
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "name": "lookup_topic",
                                "args": {},
                                "type": "tool_call",
                            }
                        ],
                    },
                ),
                SessionMessage(
                    role="tool",
                    content="result",
                    metadata={
                        "type": "tool_result",
                        "visibility": "internal",
                        "name": "lookup_topic",
                        "tool_call_id": "call-1",
                    },
                ),
            ]
        )

        self.assertEqual([message.role for message in messages], ["assistant", "tool"])
        self.assertEqual(messages[1].tool_call_id, "call-1")

    def test_drops_incomplete_tool_block(self):
        manager = ReActContextManager()

        messages = manager.session_history_messages(
            [
                SessionMessage(
                    role="assistant",
                    content="",
                    metadata={
                        "type": "tool_call",
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "name": "lookup_topic",
                                "args": {},
                                "type": "tool_call",
                            }
                        ],
                    },
                ),
            ]
        )

        self.assertEqual(messages, [])

    def test_keeps_recent_turns_when_history_exceeds_budget(self):
        manager = ReActContextManager(
            ReActContextBudget(
                session_history_token_budget=1,
                session_history_recent_turns_on_over_budget=2,
            )
        )
        history = []
        for index in range(1, 5):
            history.append(SessionMessage(role="user", content=f"user {index} " + ("x" * 40)))
            history.append(SessionMessage(role="assistant", content=f"answer {index} " + ("y" * 40)))

        messages = manager.session_history_messages(history)
        contents = [message.content for message in messages]

        self.assertFalse(any("user 1" in content for content in contents))
        self.assertFalse(any("answer 2" in content for content in contents))
        self.assertTrue(any("user 3" in content for content in contents))
        self.assertTrue(any("answer 4" in content for content in contents))

    def test_current_query_is_kept_outside_recent_turn_budget(self):
        manager = ReActContextManager(
            ReActContextBudget(
                session_history_token_budget=1,
                session_history_recent_turns_on_over_budget=1,
            )
        )
        history = [
            SessionMessage(role="user", content="old user " + ("x" * 40)),
            SessionMessage(role="assistant", content="old answer " + ("y" * 40)),
            SessionMessage(role="user", content="current query"),
        ]

        messages = manager.session_history_messages(history, current_query="current query")

        self.assertEqual([message.content for message in messages], [
            "old user " + ("x" * 40),
            "old answer " + ("y" * 40),
            "current query",
        ])


if __name__ == "__main__":
    unittest.main()
