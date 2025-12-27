import os
import sys
import tempfile
import unittest
from unittest import mock

class DummyNNTP:
    def __init__(self, *args, **kwargs):
        self.group_name = None

    def connect(self):
        return None

    def reader_mode(self):
        return None

    def auth(self, user, password):
        return None

    def group(self, group):
        self.group_name = group
        return 1, 1, 1, "y"

    def body(self, target):
        return ["<nzb></nzb>"]

    def article(self, target):
        return ["", "<nzb></nzb>"]

    def quit(self):
        return None


class DummyNNTPPipeline(DummyNNTP):
    def xover(self, start, end):
        return [
            (
                1,
                {
                    "subject": "Example [1/1] test.bin",
                    "from": "poster",
                    "date": "now",
                    "bytes": "123",
                    "message-id": "<msgid>",
                },
            )
        ]


class ServiceSmokeTests(unittest.TestCase):
    def test_aggregate_build_empty(self):
        from services import aggregate

        with mock.patch.object(aggregate, "get_ingest_db_readonly", return_value=None):
            aggregate.build_releases()

    def test_pipeline(self):
        from services import pipeline

        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["NNTP_HOST"] = "news.example.com"
            env["TRICERAPOST_DB_DIR"] = tmp
            env["TRICERAPOST_SETTINGS_PATH"] = os.path.join(tmp, "settings.json")
            argv = ["pipeline.py", "--groups", "alt.binaries.test", "--no-nzb", "--interval", "0"]
            with (
                mock.patch.dict(os.environ, env, clear=False),
                mock.patch.object(pipeline, "NNTPClient", DummyNNTPPipeline),
                mock.patch.object(pipeline, "build_releases"),
                mock.patch.object(pipeline, "filter_main"),
                mock.patch.object(sys, "argv", argv),
            ):
                code = pipeline.main()
                self.assertEqual(code, 0)
                pipeline.build_releases.assert_called_once()
                pipeline.filter_main.assert_called_once()


if __name__ == "__main__":
    unittest.main()
