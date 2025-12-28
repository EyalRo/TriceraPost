import unittest

from app.nzb_utils import build_nzb_xml, parse_nzb_segments


class TestNzbUtils(unittest.TestCase):
    def test_parse_nzb_segments_strips_brackets(self):
        payload = (
            b'<?xml version="1.0"?>'
            b"<nzb><file><segments>"
            b'<segment bytes="123" number="1"> &lt;abc@xyz&gt; </segment>'
            b"</segments></file></nzb>"
        )
        segments = parse_nzb_segments(payload)
        self.assertEqual(1, len(segments))
        self.assertEqual("abc@xyz", segments[0]["message_id"])

    def test_build_nzb_xml_strips_brackets(self):
        payload = build_nzb_xml(
            name="test",
            poster=None,
            groups=["alt.binaries.test"],
            segments=[{"message_id": "<abc@xyz>", "bytes": 123, "number": 1}],
        )
        segments = parse_nzb_segments(payload)
        self.assertEqual(1, len(segments))
        self.assertEqual("abc@xyz", segments[0]["message_id"])
