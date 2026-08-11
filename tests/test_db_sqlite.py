import tempfile
import unittest
from pathlib import Path

from topic_pulse_v2.db import SQLiteDatabase


class SQLiteDatabaseTests(unittest.TestCase):
    def test_execute_and_fetch_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = SQLiteDatabase(Path(temp_dir) / "topic_pulse.sqlite3")
            try:
                database.initialize()
                database.execute("CREATE TABLE items (id TEXT PRIMARY KEY, name TEXT NOT NULL)")
                database.execute(
                    "INSERT INTO items (id, name) VALUES (?, ?)",
                    ("item-1", "first"),
                )

                row = database.fetch_one("SELECT * FROM items WHERE id = ?", ("item-1",))

                self.assertEqual(row, {"id": "item-1", "name": "first"})
            finally:
                database.close()

    def test_transaction_rolls_back_on_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = SQLiteDatabase(Path(temp_dir) / "topic_pulse.sqlite3")
            try:
                database.initialize()
                database.execute("CREATE TABLE items (id TEXT PRIMARY KEY)")

                with self.assertRaises(RuntimeError):
                    with database.transaction():
                        database.execute("INSERT INTO items (id) VALUES (?)", ("item-1",))
                        raise RuntimeError("stop")

                self.assertEqual(database.fetch_all("SELECT * FROM items"), [])
            finally:
                database.close()


if __name__ == "__main__":
    unittest.main()
