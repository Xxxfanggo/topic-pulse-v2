import json
import tempfile
import unittest

from topic_pulse_v2.llm_call import LLMClient, LLMProvider, LLMRequest, LLMResponse
from topic_pulse_v2.process import ReActAgent, ReActConfig
from topic_pulse_v2.session import MarkdownSessionHistoryStore, SessionManager, SessionStatus
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


class FailingProvider(LLMProvider):
    def call(self, request: LLMRequest) -> LLMResponse:
        raise RuntimeError("model unavailable")


class ToolThenAnswerProvider(LLMProvider):
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
        if len(self.requests) == 1:
            return LLMResponse(
                content=json.dumps(
                    {
                        "thought": "需要查工具",
                        "action": "lookup_topic",
                        "arguments": {"query": "内存条价格"},
                    },
                    ensure_ascii=False,
                )
            )
        return LLMResponse(
            content=json.dumps(
                {
                    "thought": "基于已有观察回答",
                    "final_answer": json.dumps({"回答": "完成"}, ensure_ascii=False),
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

    def test_react_persists_tool_results_and_loads_them_next_turn(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            provider = ToolThenAnswerProvider()
            session_manager = SessionManager(
                history_store=MarkdownSessionHistoryStore(temp_dir),
            )
            registry = ToolRegistry(auto_register_local_tools=False)
            registry.register("lookup_topic", lambda query: {"topic": query, "status": "上涨"})
            agent = ReActAgent(
                llm_client=LLMClient({"fake": provider}, default_provider="fake"),
                tool_registry=registry,
                session_manager=session_manager,
                config=ReActConfig(max_steps=2, trace_log_path=None),
            )

            first = agent.run(user_id="user-1", query="第一轮：查内存条价格")
            agent.run(
                user_id="user-1",
                query="第二轮：接着刚才的观察继续",
                session_id=first.session_id,
            )

            history = session_manager.get_history(first.session_id)
            tool_history = [message for message in history if message.role == "tool"]
            second_turn_messages = provider.requests[2].messages
            restored_tool_messages = [
                message for message in second_turn_messages if message.role == "tool"
            ]
            restored_tool_call_assistants = [
                message
                for message in second_turn_messages
                if message.role == "assistant" and message.metadata.get("type") == "tool_call"
            ]

            self.assertEqual(len(tool_history), 1)
            self.assertEqual(tool_history[0].metadata["visibility"], "internal")
            self.assertEqual(tool_history[0].metadata["name"], "lookup_topic")
            self.assertTrue(restored_tool_messages)
            self.assertEqual(restored_tool_messages[0].name, "lookup_topic")
            self.assertEqual(
                restored_tool_messages[0].tool_call_id,
                tool_history[0].metadata["tool_call_id"],
            )
            self.assertTrue(restored_tool_call_assistants)
            self.assertTrue(restored_tool_call_assistants[0].metadata.get("tool_calls"))

    def test_react_history_limit_does_not_restore_orphan_tool_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            provider = CapturingHistoryProvider()
            session_manager = SessionManager(
                history_store=MarkdownSessionHistoryStore(temp_dir),
            )
            session = session_manager.create()
            session_manager.append_history(
                session.id,
                "assistant",
                '{"thought":"call tool","action":"lookup_topic","arguments":{}}',
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
            )
            session_manager.append_history(
                session.id,
                "tool",
                '{"tool":"lookup_topic","success":true,"result":{"status":"ok"}}',
                metadata={
                    "type": "tool_result",
                    "visibility": "internal",
                    "name": "lookup_topic",
                    "tool_call_id": "call-1",
                },
            )
            session_manager.append_history(
                session.id,
                "assistant",
                '{"summary":"上一轮回答"}',
                metadata={"type": "final_answer", "completed": True},
            )
            agent = ReActAgent(
                llm_client=LLMClient({"fake": provider}, default_provider="fake"),
                tool_registry=ToolRegistry(auto_register_local_tools=False),
                session_manager=session_manager,
                config=ReActConfig(session_history_limit=2, trace_log_path=None),
            )

            agent.run(user_id="user-1", query="继续", session_id=session.id)

            restored_messages = provider.requests[0].messages
            self.assertFalse([message for message in restored_messages if message.role == "tool"])
            self.assertFalse(
                [
                    message
                    for message in restored_messages
                    if message.role == "assistant" and message.metadata.get("type") == "tool_call"
                ]
            )

    def test_react_restores_empty_assistant_tool_call_with_tool_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            provider = CapturingHistoryProvider()
            session_manager = SessionManager(
                history_store=MarkdownSessionHistoryStore(temp_dir),
            )
            session = session_manager.create()
            session_manager.append_history(
                session.id,
                "assistant",
                "",
                metadata={
                    "type": "tool_call",
                    "visibility": "internal",
                    "tool_calls": [
                        {
                            "id": "call-empty",
                            "name": "lookup_topic",
                            "args": {"query": "内存条"},
                            "type": "tool_call",
                        }
                    ],
                },
            )
            session_manager.append_history(
                session.id,
                "tool",
                '{"tool":"lookup_topic","success":true,"result":{"status":"ok"}}',
                metadata={
                    "type": "tool_result",
                    "visibility": "internal",
                    "name": "lookup_topic",
                    "tool_call_id": "call-empty",
                },
            )
            agent = ReActAgent(
                llm_client=LLMClient({"fake": provider}, default_provider="fake"),
                tool_registry=ToolRegistry(auto_register_local_tools=False),
                session_manager=session_manager,
                config=ReActConfig(trace_log_path=None),
            )

            agent.run(user_id="user-1", query="继续", session_id=session.id)

            restored_messages = provider.requests[0].messages
            restored_tool_call_assistants = [
                message
                for message in restored_messages
                if message.role == "assistant" and message.metadata.get("type") == "tool_call"
            ]
            restored_tool_messages = [
                message for message in restored_messages if message.role == "tool"
            ]
            self.assertEqual(len(restored_tool_call_assistants), 1)
            self.assertEqual(len(restored_tool_messages), 1)
            self.assertEqual(restored_tool_messages[0].tool_call_id, "call-empty")

    def test_react_persists_user_input_before_llm_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_manager = SessionManager(
                history_store=MarkdownSessionHistoryStore(temp_dir),
            )
            agent = ReActAgent(
                llm_client=LLMClient({"fake": FailingProvider()}, default_provider="fake"),
                tool_registry=ToolRegistry(auto_register_local_tools=False),
                session_manager=session_manager,
                config=ReActConfig(trace_log_path=None),
            )

            with self.assertRaises(RuntimeError):
                agent.run(user_id="user-1", query="这轮会失败但要保留")

            sessions = session_manager.list()
            self.assertEqual(len(sessions), 1)
            self.assertEqual(sessions[0].status, SessionStatus.FAILED)

            history = session_manager.get_history(sessions[0].id)
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0].role, "user")
            self.assertEqual(history[0].content, "这轮会失败但要保留")

    def test_scheduler_turn_marks_session_history_hidden(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_manager = SessionManager(
                history_store=MarkdownSessionHistoryStore(temp_dir),
            )
            agent = ReActAgent(
                llm_client=LLMClient({"fake": CapturingHistoryProvider()}, default_provider="fake"),
                tool_registry=ToolRegistry(auto_register_local_tools=False),
                session_manager=session_manager,
                config=ReActConfig(trace_log_path=None),
            )

            result = agent.run(
                user_id="scheduler",
                query="刷新话题",
                metadata={"source": "scheduler", "task": "refresh_topic"},
            )

            history = session_manager.get_history(result.session_id)
            self.assertEqual(history[0].metadata["source"], "scheduler")
            self.assertEqual(history[0].metadata["task"], "refresh_topic")
            self.assertEqual(history[0].metadata["visibility"], "hidden")


if __name__ == "__main__":
    unittest.main()
