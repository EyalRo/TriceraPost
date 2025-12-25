import unittest
from unittest import mock

from services import nzb_store


class NzbStoreTests(unittest.TestCase):
    def test_verify_message_ids_handles_connect_timeout(self):
        with mock.patch.object(nzb_store, "_connect_nntp", side_effect=TimeoutError("timed out")):
            ok, reason = nzb_store.verify_message_ids(["abc@news"])
        self.assertFalse(ok)
        self.assertIn("timed out", reason or "")


if __name__ == "__main__":
    unittest.main()
