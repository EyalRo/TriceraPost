import json
import os
import tempfile
import threading
import time
import unittest
from urllib import error, request


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
        os.environ["TRICERAPOST_SETTINGS_PATH"] = os.path.join(cls.tmpdir.name, "settings.json")
        from services.db import (
            get_complete_db,
            get_nzb_db,
            get_ingest_db,
            get_state_db,
            get_releases_db,
            init_complete_db,
            init_ingest_db,
            init_nzb_db,
            init_releases_db,
            init_state_db,
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
            INSERT INTO nzbs(key, name, source, group_name, poster, release_key, bytes, path, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "nzb-key",
                "Example.nzb",
                "generated",
                "alt.binaries.tv.hbo",
                "poster",
                "Example|poster",
                123,
                "",
                b"<nzb></nzb>",
            ),
        )
        conn.execute(
            """
            INSERT INTO nzb_invalid(key, name, source, release_key, reason, payload)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("bad-key", "Bad.nzb", "found", None, "missing", None),
        )
        conn.commit()
        conn.close()

        conn = get_state_db()
        init_state_db(conn)
        conn.execute("DELETE FROM state")
        conn.execute("INSERT INTO state(group_name, last_article) VALUES (?, ?)", ("alt.binaries.tv.hbo", 123))
        conn.commit()
        conn.close()

        conn = get_ingest_db()
        init_ingest_db(conn)
        conn.execute("DELETE FROM ingest")
        conn.execute(
            """
            INSERT INTO ingest(group_name, type, article, subject, poster, date, bytes, message_id, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("alt.binaries.tv.hbo", "header", 1, "Example", "poster", "now", 123, "<msgid>", None),
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

    def fetch_json_with_status(self, path, method="GET", payload=None):
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = request.Request(self.url(path), data=data, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                payload = {"raw": body}
            return exc.code, payload

    def fetch_bytes(self, path):
        req = request.Request(self.url(path), method="GET")
        with request.urlopen(req, timeout=5) as resp:
            return resp.read()

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

    def test_get_status(self):
        data = self.fetch_json("/api/status")
        self.assertEqual(data["groups_scanned"], 1)
        self.assertEqual(data["posts_scanned"], 1)
        self.assertEqual(data["sets_found"], 1)
        self.assertEqual(data["sets_rejected"], 1)
        self.assertEqual(data["nzbs_found"], 0)
        self.assertEqual(data["nzbs_generated"], 1)

    def test_get_nzb_payload(self):
        payload = self.fetch_bytes("/api/nzb/file?key=nzb-key")
        self.assertEqual(payload, b"<nzb></nzb>")

    def test_settings_roundtrip(self):
        data = self.fetch_json("/api/settings")
        self.assertIn("NNTP_PASS_SET", data)
        self.assertFalse(data["NNTP_PASS_SET"])

        payload = {
            "NNTP_HOST": "news.example.com",
            "NNTP_PORT": 563,
            "NNTP_SSL": True,
            "NNTP_USER": "demo",
            "NNTP_PASS": "secret",
            "NNTP_LOOKBACK": 999,
            "NNTP_GROUPS": "alt.binaries.test",
        }
        data = self.fetch_json("/api/settings", method="POST", payload=payload)
        self.assertTrue(data["ok"])
        self.assertEqual(data["settings"]["NNTP_HOST"], "news.example.com")
        self.assertEqual(data["settings"]["NNTP_PORT"], 563)
        self.assertTrue(data["settings"]["NNTP_SSL"])
        self.assertEqual(data["settings"]["NNTP_USER"], "demo")
        self.assertEqual(data["settings"]["NNTP_LOOKBACK"], 999)
        self.assertEqual(data["settings"]["NNTP_GROUPS"], "alt.binaries.test")
        self.assertTrue(data["settings"]["NNTP_PASS_SET"])

        data = self.fetch_json("/api/settings", method="POST", payload={"clear_password": True})
        self.assertTrue(data["ok"])
        self.assertFalse(data["settings"]["NNTP_PASS_SET"])

    def test_z_admin_clear_db_requires_confirm(self):
        status, data = self.fetch_json_with_status("/api/admin/clear_db", method="POST", payload={})
        self.assertEqual(status, 400)
        self.assertFalse(data["ok"])

    def test_zz_admin_clear_db(self):
        status, data = self.fetch_json_with_status("/api/admin/clear_db", method="POST", payload={"confirm": True})
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertGreaterEqual(len(data["removed"]), 1)


if __name__ == "__main__":
    unittest.main()
