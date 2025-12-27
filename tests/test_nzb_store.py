import os
import tempfile
import unittest
from unittest import mock

from services import nzb_store


class NzbStoreTests(unittest.TestCase):
    def test_verify_message_ids_handles_connect_timeout(self):
        with mock.patch.object(nzb_store, "_connect_nntp", side_effect=TimeoutError("timed out")):
            ok, reason = nzb_store.verify_message_ids(["abc@news"])
        self.assertFalse(ok)
        self.assertIn("timed out", reason or "")

    def test_save_nzb_to_disk_handles_permission_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "nzbs.db")
            payload = b"test-nzb"
            with mock.patch.dict(os.environ, {"TRICERAPOST_SAVE_NZBS": "0"}):
                with mock.patch("services.db.NZB_DB_PATH", db_path):
                    key, _ = nzb_store.store_nzb_payload(
                        name="test",
                        payload=payload,
                        source="generated",
                    )
                    with mock.patch.object(nzb_store.os, "makedirs", side_effect=PermissionError("denied")):
                        saved = nzb_store.save_nzb_to_disk(key, directory=tmp)
        self.assertIsNone(saved)


if __name__ == "__main__":
    unittest.main()
