import os
import sqlite3
import tempfile
import unittest
from unittest import mock


def _make_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


class FakeNNTPClient:
    def __init__(self, host, port, use_ssl=False):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.groups_called = []
        self.body_called = []
        self.article_called = []
        self.overview = []

    def connect(self):
        return None

    def reader_mode(self):
        return None

    def auth(self, user, password):
        return None

    def group(self, name):
        self.groups_called.append(name)
        # count, first, last, name
        return (3, 1, 3, name)

    def xover(self, start, end):
        return self.overview

    def body(self, target):
        self.body_called.append(target)
        raise RuntimeError("body failed")

    def article(self, target):
        self.article_called.append(target)
        return ["Header: value", "", "body"]

    def list(self):
        return []

    def quit(self):
        return None


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

    def test_is_binary_group(self):
        from app import pipeline

        self.assertTrue(pipeline._is_binary_group("alt.binaries.movies"))
        self.assertTrue(pipeline._is_binary_group("alt.bin"))
        self.assertTrue(pipeline._is_binary_group("foo-binaries.bar"))
        self.assertTrue(pipeline._is_binary_group("foo.binary.bar"))
        self.assertFalse(pipeline._is_binary_group("alt.text"))
        self.assertFalse(pipeline._is_binary_group("binoculars.news"))

    def test_extract_binary_groups(self):
        from app import pipeline

        groups = [
            {"group": "alt.binaries.movies"},
            {"group": "alt.text"},
            {"group": "alt.bin"},
            {"group": "alt.bin"},
            {"group": ""},
            {},
        ]
        self.assertEqual(pipeline._extract_binary_groups(groups), ["alt.bin", "alt.binaries.movies"])

    def test_load_groups_json_missing_or_invalid(self):
        from app import pipeline

        missing = os.path.join(self.tmpdir.name, "missing.json")
        self.assertEqual(pipeline._load_groups_json(missing), [])

        bad = os.path.join(self.tmpdir.name, "bad.json")
        with open(bad, "w", encoding="utf-8") as handle:
            handle.write("{bad")
        self.assertEqual(pipeline._load_groups_json(bad), [])

        mixed = os.path.join(self.tmpdir.name, "mixed.json")
        with open(mixed, "w", encoding="utf-8") as handle:
            handle.write('[{"group": "alt.binaries.movies"}, 5, "x"]')
        self.assertEqual(pipeline._load_groups_json(mixed), [{"group": "alt.binaries.movies"}])

        not_list = os.path.join(self.tmpdir.name, "not_list.json")
        with open(not_list, "w", encoding="utf-8") as handle:
            handle.write('{"group": "alt.binaries.movies"}')
        self.assertEqual(pipeline._load_groups_json(not_list), [])

    def test_write_groups_json_ignores_os_errors(self):
        from app import pipeline

        with mock.patch("builtins.open", side_effect=OSError("nope")):
            pipeline._write_groups_json("/nope/groups.json", [{"group": "alt.binaries.movies"}])

    def test_fetch_nzb_body_fallback(self):
        from app import pipeline

        client = FakeNNTPClient("example", 119)
        with mock.patch("app.pipeline.strip_article_headers", return_value=["body"]) as strip_headers:
            body = pipeline._fetch_nzb_body(client, "alt.binaries.test", "123")

        self.assertEqual(body, ["body"])
        self.assertEqual(client.groups_called, ["alt.binaries.test", "alt.binaries.test"])
        self.assertEqual(client.body_called, ["123"])
        self.assertEqual(client.article_called, ["123"])
        strip_headers.assert_called_once()

    def test_ingest_nzb_target_records_failure(self):
        from app import pipeline

        ingest_conn = _make_db(os.path.join(self.tmpdir.name, "ingest.db"))
        from app import db as app_db

        app_db.init_ingest_db(ingest_conn)
        self.addCleanup(ingest_conn.close)
        with mock.patch("app.pipeline._fetch_nzb_body", return_value=None), mock.patch(
            "app.pipeline.append_record"
        ) as append_record:
            pipeline._ingest_nzb_target(
                client=FakeNNTPClient("example", 119),
                ingest_conn=ingest_conn,
                group="alt.binaries.test",
                article=10,
                subject="test.nzb",
                poster="poster",
                date="date",
                message_id="<id>",
                verify_nzb=True,
            )

        self.assertTrue(append_record.called)
        record = append_record.call_args[0][1]
        self.assertEqual(record["type"], "nzb_failed")

    def test_ingest_nzb_target_stores_payload_and_records(self):
        from app import pipeline

        ingest_conn = _make_db(os.path.join(self.tmpdir.name, "ingest.db"))
        from app import db as app_db

        app_db.init_ingest_db(ingest_conn)
        self.addCleanup(ingest_conn.close)
        nzb_file = {
            "groups": ["alt.binaries.test"],
            "subject": "file",
            "poster": "poster2",
            "bytes": "12",
            "segments": "2",
        }

        with mock.patch("app.pipeline._fetch_nzb_body", return_value=["<nzb></nzb>"]), mock.patch(
            "app.pipeline.parse_nzb",
            return_value=[nzb_file],
        ), mock.patch(
            "app.pipeline.build_nzb_payload",
            return_value=b"payload",
        ), mock.patch(
            "app.pipeline.parse_nzb_segments",
            return_value=[{"message_id": "<seg>"}],
        ), mock.patch(
            "app.pipeline.verify_message_ids",
            return_value=(True, None),
        ), mock.patch(
            "app.pipeline.store_nzb_payload"
        ) as store_payload, mock.patch(
            "app.pipeline.store_nzb_invalid"
        ) as store_invalid, mock.patch(
            "app.pipeline.append_record"
        ) as append_record:
            pipeline._ingest_nzb_target(
                client=FakeNNTPClient("example", 119),
                ingest_conn=ingest_conn,
                group="alt.binaries.test",
                article=10,
                subject="test.nzb",
                poster="poster",
                date="date",
                message_id="<id>",
                verify_nzb=True,
            )

        self.assertTrue(store_payload.called)
        self.assertFalse(store_invalid.called)
        self.assertTrue(append_record.called)
        record = append_record.call_args[0][1]
        self.assertEqual(record["type"], "nzb_file")
        self.assertEqual(record["payload"]["segments"], 2)

    def test_ingest_nzb_target_marks_invalid(self):
        from app import pipeline

        ingest_conn = _make_db(os.path.join(self.tmpdir.name, "ingest.db"))
        from app import db as app_db

        app_db.init_ingest_db(ingest_conn)
        self.addCleanup(ingest_conn.close)
        with mock.patch("app.pipeline._fetch_nzb_body", return_value=["<nzb></nzb>"]), mock.patch(
            "app.pipeline.parse_nzb",
            return_value=[],
        ), mock.patch(
            "app.pipeline.build_nzb_payload",
            return_value=b"payload",
        ), mock.patch(
            "app.pipeline.parse_nzb_segments",
            return_value=[{"message_id": "<seg>"}],
        ), mock.patch(
            "app.pipeline.verify_message_ids",
            return_value=(False, "bad"),
        ), mock.patch(
            "app.pipeline.store_nzb_payload"
        ) as store_payload, mock.patch(
            "app.pipeline.store_nzb_invalid"
        ) as store_invalid:
            pipeline._ingest_nzb_target(
                client=FakeNNTPClient("example", 119),
                ingest_conn=ingest_conn,
                group="alt.binaries.test",
                article=10,
                subject="test.nzb",
                poster="poster",
                date="date",
                message_id="<id>",
                verify_nzb=True,
            )

        self.assertFalse(store_payload.called)
        self.assertTrue(store_invalid.called)

    def test_run_pipeline_once_requires_host(self):
        from app import pipeline

        with mock.patch("app.pipeline.get_setting", return_value=None):
            code = pipeline.run_pipeline_once(groups=["alt.binaries.test"])
        self.assertEqual(code, 1)

    def test_run_pipeline_once_basic_flow(self):
        from app import pipeline
        from app import db as app_db

        state_path = os.path.join(self.tmpdir.name, "state.db")
        ingest_path = os.path.join(self.tmpdir.name, "ingest.db")

        def _state_conn():
            return _make_db(state_path)

        def _ingest_conn():
            return _make_db(ingest_path)

        fake = FakeNNTPClient("example", 119)
        fake.overview = [
            (1, ("subject", "poster", "date", "<id>", "", "12")),
            (2, ("subject2", "poster2", "date2", "<id2>", "", "34")),
        ]

        def _fake_setting(key, default=None):
            if key == "NNTP_HOST":
                return "example"
            if key == "NNTP_USER":
                return "user"
            if key == "NNTP_PASS":
                return "pass"
            return default

        def _fake_int_setting(key, default):
            if key == "NNTP_PORT":
                return 119
            if key == "NNTP_LOOKBACK":
                return 2000
            return default

        with mock.patch("app.pipeline.NNTPClient", return_value=fake), mock.patch(
            "app.pipeline.get_setting", side_effect=_fake_setting
        ), mock.patch(
            "app.pipeline.get_int_setting", side_effect=_fake_int_setting
        ), mock.patch(
            "app.pipeline.get_bool_setting", return_value=False
        ), mock.patch(
            "app.pipeline.get_state_db", side_effect=_state_conn
        ), mock.patch(
            "app.pipeline.get_ingest_db", side_effect=_ingest_conn
        ), mock.patch(
            "app.pipeline.init_state_db", side_effect=app_db.init_state_db
        ), mock.patch(
            "app.pipeline.init_ingest_db", side_effect=app_db.init_ingest_db
        ), mock.patch(
            "app.pipeline.build_releases"
        ) as build_releases, mock.patch(
            "app.pipeline.filter_main"
        ) as filter_main:
            code = pipeline.run_pipeline_once(
                groups=["alt.binaries.test"],
                parse_nzb_bodies=False,
                verify_nzb=False,
                progress_seconds=999,
            )

        self.assertEqual(code, 0)
        self.assertTrue(build_releases.called)
        self.assertTrue(filter_main.called)
        check_conn = _make_db(ingest_path)
        try:
            rows = check_conn.execute("SELECT * FROM ingest").fetchall()
        finally:
            check_conn.close()
        self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main()
