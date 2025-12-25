import json
import os
import tempfile
import threading
import time
import unittest
from urllib import request


class ApiSqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        os.environ["TRICERAPOST_DB_DIR"] = cls.tmpdir.name
        os.environ["TRICERAPOST_STATE_DB"] = os.path.join(cls.tmpdir.name, "state.db")
        os.environ["TRICERAPOST_INGEST_DB"] = os.path.join(cls.tmpdir.name, "ingest.db")
        os.environ["TRICERAPOST_RELEASES_DB"] = os.path.join(cls.tmpdir.name, "releases.db")
        os.environ["TRICERAPOST_COMPLETE_DB"] = os.path.join(cls.tmpdir.name, "complete.db")
        os.environ["TRICERAPOST_NZB_DB"] = os.path.join(cls.tmpdir.name, "nzbs.db")
        from services.db import (
            get_complete_db,
            get_nzb_db,
            get_releases_db,
            init_complete_db,
            init_nzb_db,
            init_releases_db,
        )

        conn = get_releases_db()
        init_releases_db(conn)
        conn.execute("DELETE FROM releases")
        conn.execute(
            """
            INSERT INTO releases(
                key, name, normalized_name, filename_hint, poster, group_name, source,
                message_id, nzb_source_subject, nzb_article, nzb_message_id, nzb_fetch_failed,
                first_seen, last_seen, bytes, size_human, parts_received, parts_expected,
                part_numbers, part_total, articles, subjects
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "alt.binaries.tv.hbo|poster|Example",
                "Example",
                "Example",
                "Example.mkv",
                "poster",
                "alt.binaries.tv.hbo",
                "header",
                "<msgid>",
                None,
                None,
                None,
                0,
                "2025-01-01",
                "2025-01-02",
                1024,
                "1.0 KB",
                2,
                2,
                json.dumps([1, 2]),
                2,
                2,
                json.dumps(["Example.part01", "Example.part02"]),
            ),
        )
        conn.commit()
        conn.close()

        conn = get_nzb_db()
        init_nzb_db(conn)
        conn.execute("DELETE FROM nzbs")
        conn.execute("DELETE FROM nzb_invalid")
        conn.execute(
            """
            INSERT INTO nzbs(key, name, source, group_name, poster, release_key, bytes, path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("nzb-key", "Example.nzb", "generated", "alt.binaries.tv.hbo", "poster", "Example|poster", 123, "/tmp/example.nzb"),
        )
        conn.execute(
            """
            INSERT INTO nzb_invalid(key, name, source, release_key, reason)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("bad-key", "Bad.nzb", "found", None, "missing"),
        )
        conn.commit()
        conn.close()

        conn = get_complete_db()
        init_complete_db(conn)
        conn.execute("DELETE FROM releases_complete")
        conn.execute(
            """
            INSERT INTO releases_complete(
                key, name, filename_guess, nzb_fetch_failed, nzb_source_subject,
                groups, poster, bytes, size_human, first_seen, last_seen,
                parts_expected, parts_received, type, quality, source, codec,
                audio, languages, subtitles
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Example|poster",
                "Example",
                "Example.mkv",
                0,
                None,
                json.dumps(["alt.binaries.tv.hbo"]),
                "poster",
                1024,
                "1.0 KB",
                "2025-01-01",
                "2025-01-02",
                2,
                2,
                "tv",
                "720p",
                "hdtv",
                "x264",
                "aac",
                json.dumps(["eng"]),
                0,
            ),
        )
        conn.commit()
        conn.close()

        import server

        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=2)
        cls.tmpdir.cleanup()

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def fetch_json(self, path, method="GET", payload=None):
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = request.Request(self.url(path), data=data, headers=headers, method=method)
        with request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def test_get_groups(self):
        data = self.fetch_json("/api/groups")
        self.assertIsInstance(data, list)
        if data:
            self.assertIn("group", data[0])

    def test_get_releases_raw(self):
        data = self.fetch_json("/api/releases/raw")
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["group"], "alt.binaries.tv.hbo")
        self.assertEqual(data[0]["parts_expected"], 2)

    def test_get_releases_complete(self):
        data = self.fetch_json("/api/releases")
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["type"], "tv")
        self.assertEqual(data[0]["languages"], ["eng"])
        self.assertTrue(data[0]["nzb_created"])

    def test_get_nzbs(self):
        data = self.fetch_json("/api/nzbs")
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["source"], "generated")


if __name__ == "__main__":
    unittest.main()
