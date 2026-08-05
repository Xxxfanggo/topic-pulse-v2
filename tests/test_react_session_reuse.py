import unittest
from tempfile import TemporaryDirectory

from topic_pulse_v2.llm_call import LLMClient, LLMProvider, LLMRequest, LLMResponse
from topic_pulse_v2.process import ReActAgent, ReActConfig
from topic_pulse_v2.session import MarkdownSessionHistoryStore, SessionManager, SessionStatus
from topic_pulse_v2.tool_register import ToolRegistry


class FakeFinalAnswerProvider(LLMProvider):
    def call(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content='{"thought": "直接回答", "final_answer": "{\\"结果\\": \\"完成\\"}"}'
        )


class ReActSessionReuseTests(unittest.TestCase):
    def test_react_can_reuse_completed_session_for_next_turn(self):
        with TemporaryDirectory() as temp_dir:
            session_manager = SessionManager(
                history_store=MarkdownSessionHistoryStore(temp_dir),
            )
            agent = ReActAgent(
                llm_client=LLMClient(
                    {"fake": FakeFinalAnswerProvider()},
                    default_provider="fake",
                ),
                tool_registry=ToolRegistry(auto_register_local_tools=False),
                session_manager=session_manager,
                config=ReActConfig(trace_log_path=None),
            )

            first = agent.run(user_id="user-1", query="第一轮")
            second = agent.run(
                user_id="user-1",
                query="第二轮",
                session_id=first.session_id,
            )

            self.assertEqual(second.session_id, first.session_id)
            self.assertTrue(second.completed)
            self.assertEqual(
                session_manager.get(second.session_id).status,
                SessionStatus.COMPLETED,
            )

    def test_react_can_adopt_existing_history_session_id(self):
        with TemporaryDirectory() as temp_dir:
            session_manager = SessionManager(
                history_store=MarkdownSessionHistoryStore(temp_dir),
            )
            agent = ReActAgent(
                llm_client=LLMClient(
                    {"fake": FakeFinalAnswerProvider()},
                    default_provider="fake",
                ),
                tool_registry=ToolRegistry(auto_register_local_tools=False),
                session_manager=session_manager,
                config=ReActConfig(trace_log_path=None),
            )

            result = agent.run(
                user_id="user-1",
                query="继续这个会话",
                session_id="session-from-markdown",
            )

            self.assertEqual(result.session_id, "session-from-markdown")
            self.assertEqual(
                session_manager.get("session-from-markdown").status,
                SessionStatus.COMPLETED,
            )


if __name__ == "__main__":
    unittest.main()
