import unittest

from app.release_utils import build_tags


class TestReleaseTags(unittest.TestCase):
    def test_build_tags_extracts_common_fields(self):
        name = "Movie.Title.2024.2160p.WEB-DL.DV.HDR10+.HEVC.Atmos.TrueHD.mkv"
        tags = build_tags(name)
        self.assertIn("resolution:2160p", tags)
        self.assertIn("source:web-dl", tags)
        self.assertIn("hdr:dv", tags)
        self.assertIn("hdr:hdr10+", tags)
        self.assertIn("format:hevc", tags)
        self.assertIn("audio:atmos", tags)
        self.assertIn("audio:truehd", tags)
        self.assertIn("container:mkv", tags)

    def test_build_tags_uses_filename(self):
        name = "Show.Name"
        filename = "Show.Name.1080p.BluRay.x264.mkv"
        tags = build_tags(name, filename)
        self.assertIn("resolution:1080p", tags)
        self.assertIn("source:bluray", tags)
        self.assertIn("format:h264", tags)
