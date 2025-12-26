import sqlite3
import tempfile
import unittest

from services import db


class DbMigrationTests(unittest.TestCase):
    def test_init_nzb_db_adds_payload_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/nzbs.db"
            conn = sqlite3.connect(path)
            conn.execute(
                """
                CREATE TABLE nzbs (
                    key TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    source TEXT NOT NULL,
                    group_name TEXT,
                    poster TEXT,
                    release_key TEXT,
                    nzb_source_subject TEXT,
                    nzb_article INTEGER,
                    nzb_message_id TEXT,
                    bytes INTEGER DEFAULT 0,
                    path TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE nzb_invalid (
                    key TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    source TEXT NOT NULL,
                    release_key TEXT,
                    reason TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()
            db.init_nzb_db(conn)
            cols = {row[1] for row in conn.execute("PRAGMA table_info(nzbs)").fetchall()}
            cols_invalid = {row[1] for row in conn.execute("PRAGMA table_info(nzb_invalid)").fetchall()}
            conn.close()

        self.assertIn("payload", cols)
        self.assertIn("payload", cols_invalid)


if __name__ == "__main__":
    unittest.main()
