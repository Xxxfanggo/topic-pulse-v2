import json
import unittest
from dataclasses import asdict

from topic_pulse_v2.information_search import (
    DEFAULT_WEIBO_HOT_COOKIE,
    EmptyHotNewsProvider,
    WeiboHotNewsProvider,
    create_hot_news_provider,
)


class FakeResponse:
    def __init__(self, text, *, content=None, encoding=None, apparent_encoding=None, headers=None):
        self.text = text
        self.content = content
        self.encoding = encoding
        self.apparent_encoding = apparent_encoding
        self.headers = headers or {}

    def raise_for_status(self):
        return None


class WeiboHotNewsProviderTests(unittest.TestCase):

    def test_fetch_hot_news_returns(self):
        provider = WeiboHotNewsProvider()

        items = provider.fetch_hot_news()
        print("-------------------------------------------")
        print(json.dumps([asdict(item) for item in items], ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    unittest.main()
