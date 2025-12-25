#!/usr/bin/env python3
import concurrent.futures
import os
import signal
import subprocess
import sys
import threading
import time

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def script_path(*parts: str) -> str:
    return os.path.join(ROOT_DIR, *parts)

BASE_WORKERS = [
    {
        "name": "tricerapost-ingest",
        "args": [script_path("services", "ingest_worker.py")],
        "role": "worker",
    },
    {
        "name": "tricerapost-nzb",
        "args": [script_path("services", "nzb_expander.py")],
        "role": "worker",
    },
    {
        "name": "tricerapost-writer",
        "args": [
            script_path("services", "writer_worker.py"),
            "--batch-size",
            os.environ.get("TRICERAPOST_WRITER_BATCH", "500"),
            "--flush-seconds",
            os.environ.get("TRICERAPOST_WRITER_FLUSH", "2"),
        ],
        "role": "worker",
    },
    {
        "name": "tricerapost-aggregate",
        "args": [script_path("services", "aggregate_writer.py")],
        "role": "worker",
    },
    {
        "name": "tricerapost-queue",
        "args": [
            script_path("services", "queue_monitor.py"),
            "--interval",
            os.environ.get("TRICERAPOST_QUEUE_INTERVAL", "5"),
        ],
        "role": "worker",
    },
]


def main() -> int:
    run_server = True
    run_scheduler = True
    procs = []
    lock = threading.Lock()

    def shutdown(signum=None, frame=None):
        with lock:
            running = [proc for proc in procs if proc.poll() is None]
        for proc in running:
            proc.terminate()
        time.sleep(0.5)
        with lock:
            running = [proc for proc in procs if proc.poll() is None]
        for proc in running:
            proc.kill()
        return 0

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    env = os.environ.copy()
    env["PYTHONPATH"] = ROOT_DIR

    def run_process(name: str, args: list[str], role: str) -> tuple[str, str, int]:
        proc = subprocess.Popen([name, *args], executable=sys.executable, env=env)
        with lock:
            procs.append(proc)
        code = proc.wait()
        return name, role, code

    tasks = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        for worker in BASE_WORKERS:
            tasks.append(executor.submit(run_process, worker["name"], worker["args"], worker["role"]))
        if run_server:
            tasks.append(executor.submit(run_process, "tricerapost-server", [script_path("server.py")], "server"))
        if run_scheduler:
            tasks.append(
                executor.submit(run_process, "tricerapost-scheduler", [script_path("services", "scheduler.py")], "scheduler")
            )

        try:
            for future in concurrent.futures.as_completed(tasks):
                name, role, code = future.result()
                if role == "scheduler":
                    continue
                shutdown()
                return code or 1
        except KeyboardInterrupt:
            shutdown()
            return 130
        finally:
            shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
