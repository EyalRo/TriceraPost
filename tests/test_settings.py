import os
import tempfile
import unittest

from services import settings


class SettingsTests(unittest.TestCase):
    def test_save_and_load_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "settings.json")
            os.environ["TRICERAPOST_SETTINGS_PATH"] = path

            settings.save_settings({"NNTP_HOST": "news.example.com", "NNTP_SSL": True, "NNTP_PORT": 563})
            loaded = settings.load_settings()
            self.assertEqual(loaded.get("NNTP_HOST"), "news.example.com")
            self.assertTrue(loaded.get("NNTP_SSL"))
            self.assertEqual(loaded.get("NNTP_PORT"), 563)

            self.assertEqual(settings.get_setting("NNTP_HOST"), "news.example.com")
            self.assertTrue(settings.get_bool_setting("NNTP_SSL"))
            self.assertEqual(settings.get_int_setting("NNTP_PORT", 119), 563)

    def test_get_setting_falls_back_to_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["TRICERAPOST_SETTINGS_PATH"] = os.path.join(tmp, "settings.json")
            os.environ["NNTP_HOST"] = "env.example.com"
            self.assertEqual(settings.get_setting("NNTP_HOST"), "env.example.com")


if __name__ == "__main__":
    unittest.main()
