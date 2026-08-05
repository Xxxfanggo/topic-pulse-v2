import json
import tempfile
import unittest

from topic_pulse_v2.llm_call import LLMClient, LLMProvider, LLMRequest, LLMResponse
from topic_pulse_v2.process import ReActAgent, ReActConfig
from topic_pulse_v2.session import MarkdownSessionHistoryStore, SessionManager
from topic_pulse_v2.tool_register import ToolRegistry


class CapturingHistoryProvider(LLMProvider):
    def __init__(self):
        self.requests: list[LLMRequest] = []

    def call(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(
            LLMRequest(
                messages=list(request.messages),
                model=request.model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                tools=list(request.tools),
                metadata=dict(request.metadata),
            )
        )
        index = len(self.requests)
        return LLMResponse(
            content=json.dumps(
                {
                    "thought": "直接回答",
                    "final_answer": json.dumps(
                        {"回答": f"第{index}次回答"},
                        ensure_ascii=False,
                    ),
                },
                ensure_ascii=False,
            )
        )


class ReActSessionHistoryTests(unittest.TestCase):
    def test_react_loads_history_by_session_id_on_next_turn(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            provider = CapturingHistoryProvider()
            session_manager = SessionManager(
                history_store=MarkdownSessionHistoryStore(temp_dir),
            )
            agent = ReActAgent(
                llm_client=LLMClient({"fake": provider}, default_provider="fake"),
                tool_registry=ToolRegistry(auto_register_local_tools=False),
                session_manager=session_manager,
                config=ReActConfig(trace_log_path=None),
            )

            first = agent.run(user_id="user-1", query="第一轮：帮我关注内存条价格")
            second = agent.run(
                user_id="user-1",
                query="第二轮：刚才那个话题怎么样了",
                session_id=first.session_id,
            )

            second_messages = provider.requests[1].messages
            history_messages = [
                message
                for message in second_messages
                if message.role in {"user", "assistant"}
            ]

            self.assertEqual(second.session_id, first.session_id)
            self.assertEqual(history_messages[0].content, "第一轮：帮我关注内存条价格")
            self.assertIn("第1次回答", history_messages[1].content)
            self.assertEqual(history_messages[-1].content, "第二轮：刚才那个话题怎么样了")


if __name__ == "__main__":
    unittest.main()
