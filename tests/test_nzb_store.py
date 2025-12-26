import importlib
import os
import tempfile
import unittest
from unittest import mock


class NzbStoreTests(unittest.TestCase):
    def test_verify_message_ids_handles_connect_timeout(self):
        from services import nzb_store

        with mock.patch.object(nzb_store, "_connect_nntp", side_effect=TimeoutError("timed out")):
            ok, reason = nzb_store.verify_message_ids(["abc@news"])
        self.assertFalse(ok)
        self.assertIn("timed out", reason or "")

    def test_store_payload_respects_auto_save_toggle(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["TRICERAPOST_DB_DIR"] = tmp
            os.environ["TRICERAPOST_NZB_DB"] = os.path.join(tmp, "nzbs.db")
            os.environ["TRICERAPOST_NZB_DIR"] = os.path.join(tmp, "nzbs")
            os.environ["TRICERAPOST_SAVE_NZBS"] = "0"

            from services import db, nzb_store
            importlib.reload(db)
            importlib.reload(nzb_store)

            key, path = nzb_store.store_nzb_payload(
                name="Example",
                payload=b"<nzb></nzb>",
                source="generated",
                group_name="alt.binaries.test",
                poster="poster",
            )
            self.assertEqual(path, "")
            self.assertFalse(os.path.exists(os.path.join(os.environ["TRICERAPOST_NZB_DIR"], f"{key[:8]}_Example.nzb")))

    def test_save_all_updates_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["TRICERAPOST_DB_DIR"] = tmp
            os.environ["TRICERAPOST_NZB_DB"] = os.path.join(tmp, "nzbs.db")
            os.environ["TRICERAPOST_NZB_DIR"] = os.path.join(tmp, "nzbs")
            os.environ["TRICERAPOST_SAVE_NZBS"] = "0"

            from services import db, nzb_store
            importlib.reload(db)
            importlib.reload(nzb_store)

            key, _ = nzb_store.store_nzb_payload(
                name="Example",
                payload=b"<nzb></nzb>",
                source="generated",
            )
            saved = nzb_store.save_all_nzbs_to_disk()
            self.assertEqual(saved, 1)

            conn = db.get_nzb_db_readonly()
            row = conn.execute("SELECT path FROM nzbs WHERE key = ?", (key,)).fetchone()
            conn.close()
            self.assertTrue(row["path"])
            self.assertTrue(os.path.exists(row["path"]))


if __name__ == "__main__":
    unittest.main()
