import unittest

from topic_pulse_v2.memory import InMemoryStore


class MemoryTests(unittest.TestCase):
    def test_save_and_search_memory_by_user_id(self):
        store = InMemoryStore()

        record = store.save(
            "user-1",
            "The user prefers concise answers.",
            metadata={"source": "test"},
        )
        store.save("user-2", "Another user prefers detailed answers.")

        results = store.search("user-1", "concise")
        self.assertEqual([item.id for item in results], [record.id])
        self.assertEqual(results[0].user_id, "user-1")
        self.assertEqual(results[0].metadata, {"source": "test"})

    def test_search_without_query_returns_user_memories_only(self):
        store = InMemoryStore()
        first = store.save("user-1", "first memory")
        second = store.save("user-1", "second memory")
        store.save("user-2", "third memory")

        results = store.search("user-1")

        self.assertEqual([item.id for item in results], [second.id, first.id])

    def test_empty_user_id_is_rejected(self):
        store = InMemoryStore()

        with self.assertRaises(ValueError):
            store.save("", "memory")

        with self.assertRaises(ValueError):
            store.search("")


if __name__ == "__main__":
    unittest.main()
