import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from topic_pulse_v2.information_search import HotNewsItem
from topic_pulse_v2.process.hotspot_agent import HotspotAgent, HotspotRunRequest
from topic_pulse_v2.tool_register import HOT_TOPIC_SEARCH_TOOL_NAME, ToolRegistry, hot_topic_search
from topic_pulse_v2.topics import SQLiteHotspotStore


class FakeHotNewsProvider:
    def __init__(self, items):
        self.items = items

    def fetch_hot_news(self):
        return list(self.items)


class HotTopicSearchToolTests(unittest.TestCase):
    def test_hot_topic_search_reads_local_ranking(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "topic_pulse.sqlite3"
            store = SQLiteHotspotStore(path=db_path)
            provider = FakeHotNewsProvider(
                [
                    HotNewsItem(
                        title="AI 芯片需求持续升温",
                        summary="多家厂商订单增长。",
                        source="weibo",
                        rank=1,
                        heat=9000,
                        category="科技",
                    ),
                    HotNewsItem(
                        title="新能源车销量创新高",
                        summary="新能源汽车市场继续增长。",
                        source="weibo",
                        rank=2,
                        heat=7800,
                        category="汽车",
                    ),
                ]
            )
            agent = HotspotAgent(provider=provider, store=store)
            agent.run(
                HotspotRunRequest(
                    run_date=date(2026, 8, 17),
                    captured_at=datetime(2026, 8, 17, 2, 0, tzinfo=timezone.utc),
                )
            )

            result = hot_topic_search(
                "AI 芯片",
                date="2026-08-17",
                db_path=str(db_path),
            )

            self.assertEqual(result["date"], "2026-08-17")
            self.assertEqual(result["count"], 1)
            self.assertIn("AI", result["items"][0]["title"])
            self.assertGreater(result["items"][0]["score"], 0)
            self.assertGreater(result["items"][0]["match_score"], 0)
            store.close()

    def test_hot_topic_search_returns_top_ranking_without_query(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "topic_pulse.sqlite3"
            store = SQLiteHotspotStore(path=db_path)
            provider = FakeHotNewsProvider(
                [
                    HotNewsItem(title="AI 芯片需求持续升温", source="weibo", rank=1, heat=9000),
                    HotNewsItem(title="新能源车销量创新高", source="weibo", rank=2, heat=7800),
                ]
            )
            HotspotAgent(provider=provider, store=store).run(
                HotspotRunRequest(
                    run_date=date(2026, 8, 17),
                    captured_at=datetime(2026, 8, 17, 2, 0, tzinfo=timezone.utc),
                )
            )

            result = hot_topic_search(date="2026-08-17", limit=1, db_path=str(db_path))

            self.assertEqual(result["count"], 1)
            self.assertEqual(result["total_count"], 2)
            self.assertEqual(result["items"][0]["rank"], 1)
            store.close()

    def test_tool_registry_auto_registers_hot_topic_search(self):
        registry = ToolRegistry()

        self.assertTrue(registry.has(HOT_TOPIC_SEARCH_TOOL_NAME))
        spec = registry.get(HOT_TOPIC_SEARCH_TOOL_NAME)
        self.assertEqual(spec.metadata["tool_display_name"], "本地热点排行查询")
        self.assertIn("query", spec.parameters["properties"])


if __name__ == "__main__":
    unittest.main()
