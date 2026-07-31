import json
import os
import unittest

from topic_pulse_v2.information_search import DoubaoSearchClient, DoubaoSearchConfig


class DoubaoSearchTests(unittest.TestCase):
    def test_web_search_returns_weather_results(self):
        if not os.getenv("DOUBAO_SEARCH_API_KEY"):
            self.skipTest("Set DOUBAO_SEARCH_API_KEY before running Doubao search tests.")

        query = "今天成都天气怎么样"
        client = DoubaoSearchClient(DoubaoSearchConfig(timeout=30))

        response = client.web_search(query)
        print(json.dumps(response.raw, ensure_ascii=False, indent=2))

        self.assertEqual(response.query, query)
        self.assertEqual(response.search_type, "web")
        self.assertGreater(response.result_count, 0)
        self.assertTrue(response.request_id)
        self.assertTrue(response.web_results)
        self.assertTrue(response.web_results[0].title)


if __name__ == "__main__":
    unittest.main()
