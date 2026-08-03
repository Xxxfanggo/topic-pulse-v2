import json
import unittest
from dataclasses import asdict

from topic_pulse_v2.llm_call import LLMClient, MiniMaxLLMProvider
from topic_pulse_v2.memory import InMemoryStore
from topic_pulse_v2.process import ReActAgent, ReActConfig
from topic_pulse_v2.session import SessionManager, SessionStatus
from topic_pulse_v2.tool_register import ToolRegistry


class ReActLoopTests(unittest.TestCase):
    def test_react_loop_returns_chinese_final_answer(self):
        llm_client = LLMClient(
            {"minimax": MiniMaxLLMProvider()},
            default_provider="minimax",
        )
        session_manager = SessionManager()
        memory = InMemoryStore()
        memory.save("user-1", "")

        result = ReActAgent(
            llm_client=llm_client,
            tool_registry=ToolRegistry(),
            memory_store=memory,
            session_manager=session_manager,
            config=ReActConfig(
                max_steps=5,
            ),
        ).run(user_id="user-1", query="李小璐出轨事件的内容总结")



        session = session_manager.get(result.session_id)

        print(json.dumps(asdict(result), ensure_ascii=False, indent=2, default=str))

        final_answer = result.steps[len(result.steps) - 1].final_answer

        print("==================================")
        print(final_answer)
        self.assertTrue(result.completed)
        self.assertEqual(session.status, SessionStatus.COMPLETED)
        self.assertIsNotNone(final_answer)



if __name__ == "__main__":
    unittest.main()
