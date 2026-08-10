import tempfile
import unittest
from pathlib import Path

from topic_pulse_v2.tool_register import (
    TOPIC_MARKDOWN_READ_DETAIL_TOOL_NAME,
    TOPIC_MARKDOWN_READ_SUMMARY_TOOL_NAME,
    ToolRegistry,
    topic_markdown_read_detail,
    topic_markdown_read_summary,
    topic_markdown_store,
)


class TopicMarkdownReadToolsTests(unittest.TestCase):
    def test_read_summary_detail_and_update_existing_topic(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            created = topic_markdown_store(
                "互联网大厂因 AI 裁员",
                latest_content={
                    "summary": "互联网大厂因 AI 提效进行组织调整，话题仍在发酵。",
                    "web_results": [
                        {
                            "publish_time": "2026-08-01T09:00:00+08:00",
                            "title": "互联网公司调整 AI 相关岗位",
                            "summary": "多家公司重新配置研发和运营岗位。",
                            "site_name": "示例新闻",
                            "url": "https://example.com/ai-job-1",
                        }
                    ],
                },
                keywords=["AI 裁员", "互联网大厂"],
                root_dir=temp_dir,
                created_at="2026-08-01",
            )

            summary_result = topic_markdown_read_summary("AI 裁员", root_dir=temp_dir)
            self.assertEqual(summary_result["count"], 1)
            self.assertEqual(summary_result["topics"][0]["topic_name"], "互联网大厂因 AI 裁员")
            self.assertIn("互联网大厂", summary_result["topics"][0]["keywords"])

            fuzzy_summary_result = topic_markdown_read_summary(
                "查一下互联网大厂最近因 AI 优化岗位的走势",
                root_dir=temp_dir,
            )
            self.assertEqual(fuzzy_summary_result["count"], 1)
            self.assertEqual(fuzzy_summary_result["topics"][0]["topic_name"], "互联网大厂因 AI 裁员")
            self.assertGreater(fuzzy_summary_result["topics"][0]["match_score"], 0)

            detail_result = topic_markdown_read_detail(path=created["path"], root_dir=temp_dir)
            self.assertEqual(detail_result["topic_name"], "互联网大厂因 AI 裁员")
            self.assertEqual(detail_result["timeline_count"], 1)
            self.assertIn("互联网公司调整 AI 相关岗位", detail_result["content"])

            updated = topic_markdown_store(
                "互联网大厂因 AI 裁员",
                operation="update",
                summary="AI 提效引发的组织调整仍在继续，新增岗位优化案例。",
                keywords=["AI 裁员", "组织调整"],
                current_status="持续跟踪中",
                timeline_items=[
                    {
                        "date": "2026-08-03",
                        "title": "某互联网大厂继续优化非核心岗位",
                        "summary": "公司称调整与 AI 工具普及后的效率提升有关。",
                        "source": "豆包来源站点",
                        "url": "https://example.com/ai-job-2",
                    }
                ],
                root_dir=temp_dir,
            )

            content = Path(updated["path"]).read_text(encoding="utf-8")
            timeline_content = content.split("## 时间线", 1)[1]

            self.assertFalse(updated["created"])
            self.assertEqual(updated["operation"], "update")
            self.assertEqual(updated["appended_count"], 1)
            self.assertIn("AI 提效引发的组织调整仍在继续", content)
            self.assertIn("- 当前状态：持续跟踪中", content)
            self.assertIn("- 关键词：AI 裁员、组织调整", content)
            self.assertIn("- 来源：豆包来源站点", content)
            self.assertIn("- 链接：https://example.com/ai-job-2", content)
            self.assertLess(
                timeline_content.index("某互联网大厂继续优化非核心岗位"),
                timeline_content.index("互联网公司调整 AI 相关岗位"),
            )

            registry = ToolRegistry()
            self.assertTrue(registry.has(TOPIC_MARKDOWN_READ_SUMMARY_TOOL_NAME))
            self.assertTrue(registry.has(TOPIC_MARKDOWN_READ_DETAIL_TOOL_NAME))


if __name__ == "__main__":
    unittest.main()
