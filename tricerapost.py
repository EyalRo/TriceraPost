#!/usr/bin/env python3
import ctypes
import os
import sys

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


def set_proc_name(name: str) -> None:
    try:
        libc = ctypes.CDLL("libc.so.6")
    except OSError:
        return
    try:
        libc.prctl(15, name.encode("utf-8"), 0, 0, 0)
    except Exception:
        return


def main() -> int:
    set_proc_name("tricerapost")
    import services.runner as runner
    return runner.main()


if __name__ == "__main__":
    raise SystemExit(main())
