import unittest

from gui.server import _asset_info


class TestServerAssets(unittest.TestCase):
    def test_asset_info_known(self):
        self.assertEqual(
            ("style.css", "text/css; charset=utf-8"),
            _asset_info("/assets/style.css"),
        )

    def test_asset_info_unknown(self):
        self.assertIsNone(_asset_info("/assets/missing.css"))
