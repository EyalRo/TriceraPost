import os
import tempfile
import unittest

from gui.settings_api import apply_settings_payload, build_settings_payload


class TestSettingsApi(unittest.TestCase):
    def setUp(self):
        self._old_path = os.environ.get("TRICERAPOST_SETTINGS_PATH")
        self._temp_dir = tempfile.TemporaryDirectory()
        os.environ["TRICERAPOST_SETTINGS_PATH"] = os.path.join(
            self._temp_dir.name, "settings.json"
        )

    def tearDown(self):
        if self._old_path is None:
            os.environ.pop("TRICERAPOST_SETTINGS_PATH", None)
        else:
            os.environ["TRICERAPOST_SETTINGS_PATH"] = self._old_path
        self._temp_dir.cleanup()

    def test_apply_settings_payload_persists(self):
        payload = {
            "NNTP_HOST": "news.example.com",
            "NNTP_PORT": "563",
            "NNTP_SSL": True,
            "NNTP_USER": "user",
            "NNTP_GROUPS": "alt.binaries.test",
            "NNTP_LOOKBACK": "1234",
            "TRICERAPOST_SCHEDULER_INTERVAL": "300",
            "TRICERAPOST_SAVE_NZBS": False,
            "TRICERAPOST_NZB_DIR": "/tmp/nzbs",
            "TRICERAPOST_DOWNLOAD_STATION_ENABLED": False,
        }
        result = apply_settings_payload(payload)
        self.assertEqual("news.example.com", result["NNTP_HOST"])
        self.assertEqual(563, result["NNTP_PORT"])
        self.assertTrue(result["NNTP_SSL"])
        self.assertEqual("user", result["NNTP_USER"])
        self.assertEqual("alt.binaries.test", result["NNTP_GROUPS"])
        self.assertEqual(1234, result["NNTP_LOOKBACK"])
        self.assertEqual(300, result["TRICERAPOST_SCHEDULER_INTERVAL"])
        self.assertFalse(result["TRICERAPOST_SAVE_NZBS"])
        self.assertEqual("/tmp/nzbs", result["TRICERAPOST_NZB_DIR"])
        self.assertFalse(result["TRICERAPOST_DOWNLOAD_STATION_ENABLED"])

        refreshed = build_settings_payload()
        self.assertEqual("news.example.com", refreshed["NNTP_HOST"])
        self.assertEqual(563, refreshed["NNTP_PORT"])
