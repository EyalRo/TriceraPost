import unittest

from gui.http_assets import asset_info


class TestServerAssets(unittest.TestCase):
    def test_asset_info_known(self):
        self.assertEqual(
            ("style.css", "text/css; charset=utf-8"),
            asset_info("/assets/style.css"),
        )

    def test_asset_info_unknown(self):
        self.assertIsNone(asset_info("/assets/missing.css"))
