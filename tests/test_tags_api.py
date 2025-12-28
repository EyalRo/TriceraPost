import json
import os
import tempfile
import unittest

from app import db
from app.db import get_complete_db, get_nzb_db, init_complete_db, init_nzb_db
from gui.server import read_all_tags, read_nzbs_by_tag


class TestTagsApi(unittest.TestCase):
    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._old_nzb_path = db.NZB_DB_PATH
        self._old_complete_path = db.COMPLETE_DB_PATH
        temp_path = os.path.join(self._temp_dir.name, "tags.db")
        db.NZB_DB_PATH = temp_path
        db.COMPLETE_DB_PATH = temp_path

    def tearDown(self):
        db.NZB_DB_PATH = self._old_nzb_path
        db.COMPLETE_DB_PATH = self._old_complete_path
        self._temp_dir.cleanup()

    def test_read_all_tags_unions_sources(self):
        conn = get_nzb_db()
        init_nzb_db(conn)
        conn.execute(
            """
            INSERT INTO nzbs(key, name, source, group_name, poster, release_key,
                             nzb_source_subject, nzb_article, nzb_message_id,
                             bytes, path, payload, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "nzb-key",
                "Example",
                "generated",
                "alt.binaries.test",
                "poster",
                "rel-key",
                None,
                None,
                None,
                0,
                "",
                b"",
                json.dumps(["resolution:1080p", "format:h264"]),
            ),
        )
        conn.commit()
        conn.close()

        conn = get_complete_db()
        init_complete_db(conn)
        conn.execute(
            """
            INSERT INTO releases_complete(
                key, name, normalized_name, filename_guess, nzb_fetch_failed, nzb_source_subject,
                nzb_article, nzb_message_id, download_failed, groups, poster, bytes, size_human,
                first_seen, last_seen, parts_expected, parts_received, type,
                quality, source, codec, audio, languages, subtitles, tags
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "rel-key",
                "Example",
                "Example",
                "Example.mkv",
                0,
                None,
                None,
                None,
                0,
                json.dumps(["alt.binaries.test"]),
                "poster",
                0,
                "0 B",
                "now",
                "now",
                1,
                1,
                "tv",
                "1080p",
                "web-dl",
                "x264",
                "aac",
                json.dumps([]),
                0,
                json.dumps(["source:web-dl", "resolution:1080p"]),
            ),
        )
        conn.commit()
        conn.close()

        tags = read_all_tags()
        self.assertIn("resolution:1080p", tags)
        self.assertIn("format:h264", tags)
        self.assertIn("source:web-dl", tags)

    def test_read_nzbs_by_tag_filters(self):
        conn = get_nzb_db()
        init_nzb_db(conn)
        conn.execute(
            """
            INSERT INTO nzbs(key, name, source, group_name, poster, release_key,
                             nzb_source_subject, nzb_article, nzb_message_id,
                             bytes, path, payload, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "nzb-key-1",
                "Example 1",
                "generated",
                "alt.binaries.test",
                "poster",
                "rel-key",
                None,
                None,
                None,
                0,
                "",
                b"",
                json.dumps(["resolution:1080p"]),
            ),
        )
        conn.execute(
            """
            INSERT INTO nzbs(key, name, source, group_name, poster, release_key,
                             nzb_source_subject, nzb_article, nzb_message_id,
                             bytes, path, payload, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "nzb-key-2",
                "Example 2",
                "generated",
                "alt.binaries.test",
                "poster",
                "rel-key",
                None,
                None,
                None,
                0,
                "",
                b"",
                json.dumps(["resolution:720p"]),
            ),
        )
        conn.commit()
        conn.close()

        filtered = read_nzbs_by_tag("resolution:1080p")
        self.assertEqual(1, len(filtered))
        self.assertEqual("nzb-key-1", filtered[0]["key"])
