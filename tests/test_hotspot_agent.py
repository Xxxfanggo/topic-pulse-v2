import json
import tempfile
import unittest
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from topic_pulse_v2.information_search import HotNewsItem, create_hot_news_provider
from topic_pulse_v2.llm_call import LLMClient, MiniMaxLLMProvider
from topic_pulse_v2.process.hotspot_agent import (
    HotspotAgent,
    HotspotRunRequest,
    SQLiteHotspotStore,
)


class FakeHotNewsProvider:
    def __init__(self, items):
        self.items = items
        self.calls = 0



class HotspotAgentTests(unittest.TestCase):
    def test_empty_provider_skips_without_creating_ranking(self):
        llm_client = LLMClient(
            {"minimax": MiniMaxLLMProvider()},
            default_provider="minimax",
        )
        agent = HotspotAgent(llm_client=llm_client, provider=create_hot_news_provider(name="weibo"))

        result = agent.run(
            HotspotRunRequest(
                captured_at=datetime(2026, 8, 17, 1, 0, tzinfo=timezone.utc),
            )
        )
        print("-------------------------------------------")
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2, default=str))






if __name__ == "__main__":
    unittest.main()
