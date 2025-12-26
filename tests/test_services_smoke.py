import json
import os
import sys
import tempfile
import unittest
from unittest import mock


class StopLoop(Exception):
    pass


class DummyProc:
    _pid = 1000

    def __init__(self):
        self.pid = DummyProc._pid
        DummyProc._pid += 1

    def poll(self):
        return 0

    def wait(self):
        return 0

    def terminate(self):
        return None

    def kill(self):
        return None


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


class ServiceSmokeTests(unittest.TestCase):
    def test_ingest_worker(self):
        from services import ingest_worker

        event = {"id": 1, "type": "scan_requested", "payload": {"groups": ["alt.binaries.test"]}}
        with (
            mock.patch.object(ingest_worker, "iter_events", side_effect=[iter([event]), iter([])]),
            mock.patch.object(ingest_worker, "ingest_groups"),
            mock.patch.object(ingest_worker, "publish_event"),
            mock.patch.object(ingest_worker, "get_last_event_id", return_value=0),
            mock.patch.object(ingest_worker, "set_last_event_id"),
            mock.patch.object(ingest_worker.time, "sleep", side_effect=StopLoop),
            mock.patch.object(sys, "argv", ["ingest_worker.py"]),
        ):
            with self.assertRaises(StopLoop):
                ingest_worker.main()
            ingest_worker.ingest_groups.assert_called_once()

    def test_nzb_expander(self):
        from services import nzb_expander

        event = {
            "id": 1,
            "type": "nzb_seen",
            "payload": {
                "group": "alt.binaries.test",
                "article": 1,
                "message_id": "<msgid>",
                "subject": "test.nzb",
                "poster": "poster",
                "date": "now",
            },
        }
        env = os.environ.copy()
        env["NNTP_HOST"] = "news.example.com"
        with (
            mock.patch.dict(os.environ, env, clear=False),
            mock.patch.object(nzb_expander, "NNTPClient", DummyNNTP),
            mock.patch.object(nzb_expander, "iter_events", side_effect=[iter([event]), iter([])]),
            mock.patch.object(nzb_expander, "publish_event"),
            mock.patch.object(nzb_expander, "store_nzb_payload"),
            mock.patch.object(nzb_expander, "verify_message_ids", return_value=(True, None)),
            mock.patch.object(nzb_expander, "get_last_event_id", return_value=0),
            mock.patch.object(nzb_expander, "set_last_event_id"),
            mock.patch.object(nzb_expander.time, "sleep", side_effect=StopLoop),
            mock.patch.object(sys, "argv", ["nzb_expander.py"]),
        ):
            with self.assertRaises(StopLoop):
                nzb_expander.main()
            nzb_expander.store_nzb_payload.assert_called_once()

    def test_aggregate_writer(self):
        from services import aggregate_writer

        event = {"id": 1, "type": "scan_finished", "payload": {}}
        env = os.environ.copy()
        env["TRICERAPOST_AGGREGATE_DEBOUNCE"] = "0"
        env["TRICERAPOST_AGGREGATE_INTERVAL"] = "0"
        with (
            mock.patch.dict(os.environ, env, clear=False),
            mock.patch.object(aggregate_writer, "iter_events", side_effect=[iter([event]), iter([])]),
            mock.patch.object(aggregate_writer, "build_releases"),
            mock.patch.object(aggregate_writer, "filter_main"),
            mock.patch.object(aggregate_writer, "get_last_event_id", return_value=0),
            mock.patch.object(aggregate_writer, "set_last_event_id"),
            mock.patch.object(aggregate_writer.time, "sleep", side_effect=StopLoop),
            mock.patch.object(sys, "argv", ["aggregate_writer.py"]),
        ):
            with self.assertRaises(StopLoop):
                aggregate_writer.main()
            aggregate_writer.build_releases.assert_called_once()
            aggregate_writer.filter_main.assert_called_once()

    def test_aggregate_worker(self):
        from services import aggregate_worker

        event = {"id": 1, "type": "scan_finished", "payload": {}}
        with (
            mock.patch.object(aggregate_worker, "iter_events", side_effect=[iter([event]), iter([])]),
            mock.patch.object(aggregate_worker, "publish_event"),
            mock.patch.object(aggregate_worker, "get_last_event_id", return_value=0),
            mock.patch.object(aggregate_worker, "set_last_event_id"),
            mock.patch.object(aggregate_worker.time, "sleep", side_effect=StopLoop),
            mock.patch.object(sys, "argv", ["aggregate_worker.py", "--debounce", "0", "--poll", "0"]),
        ):
            with self.assertRaises(StopLoop):
                aggregate_worker.main()
            aggregate_worker.publish_event.assert_called_with("aggregate_requested", {})

    def test_writer_worker(self):
        from services import writer_worker

        event = {"id": 1, "type": "header_ingested", "payload": {"group": "g", "type": "header"}}
        argv = ["writer_worker.py", "--batch-size", "1", "--flush-seconds", "999", "--poll", "0"]
        with (
            mock.patch.object(writer_worker, "iter_events", side_effect=[iter([event]), iter([])]),
            mock.patch.object(writer_worker, "flush_ingest"),
            mock.patch.object(writer_worker, "get_last_event_id", return_value=0),
            mock.patch.object(writer_worker, "set_last_event_id"),
            mock.patch.object(writer_worker.time, "sleep", side_effect=StopLoop),
            mock.patch.object(sys, "argv", argv),
        ):
            with self.assertRaises(StopLoop):
                writer_worker.main()
            writer_worker.flush_ingest.assert_called_once()

    def test_scheduler(self):
        from services import scheduler

        with tempfile.TemporaryDirectory() as tmp:
            groups_path = os.path.join(tmp, "groups.json")
            with open(groups_path, "w", encoding="utf-8") as handle:
                json.dump([{"group": "alt.binaries.test"}, {"group": "alt.misc"}], handle)
            env = os.environ.copy()
            env.pop("NNTP_GROUPS", None)
            env["TRICERAPOST_SETTINGS_PATH"] = os.path.join(tmp, "settings.json")
            with (
                mock.patch.dict(os.environ, env, clear=False),
                mock.patch.object(scheduler, "GROUPS_PATH", groups_path),
                mock.patch.object(scheduler, "publish_event"),
                mock.patch.object(sys, "argv", ["scheduler.py"]),
            ):
                code = scheduler.main()
                self.assertEqual(code, 0)
                scheduler.publish_event.assert_called_once()

    def test_orchestrator(self):
        from services import orchestrator

        with (
            mock.patch.object(orchestrator, "load_groups", return_value=["alt.binaries.test"]),
            mock.patch.object(orchestrator, "publish_event"),
            mock.patch.object(sys, "argv", ["orchestrator.py"]),
        ):
            code = orchestrator.main()
            self.assertEqual(code, 0)
            orchestrator.publish_event.assert_called_once()

    def test_runner(self):
        from services import runner

        with mock.patch.object(runner.subprocess, "Popen", side_effect=lambda *args, **kwargs: DummyProc()) as popen:
            code = runner.main()
            self.assertEqual(code, 1)
            self.assertTrue(popen.called)
            first_cmd = popen.call_args[0][0]
            self.assertTrue(first_cmd[0].startswith("tricerapost-"))

    def test_queue_monitor(self):
        from services import queue_monitor

        with (
            mock.patch.object(queue_monitor, "get_queue_stats", return_value=(0, 0, 0)),
            mock.patch.object(queue_monitor.time, "sleep", side_effect=StopLoop),
            mock.patch.object(sys, "argv", ["queue_monitor.py"]),
        ):
            with self.assertRaises(StopLoop):
                queue_monitor.main()

    def test_aggregate_build_empty(self):
        from services import aggregate

        with mock.patch.object(aggregate, "get_ingest_db_readonly", return_value=None):
            aggregate.build_releases()


if __name__ == "__main__":
    unittest.main()
