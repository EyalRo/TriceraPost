import os
import struct
from typing import Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_WASM_PATH = os.path.join(
    BASE_DIR,
    "parsers",
    "overview",
    "wasm",
    "pipeline.wasm",
)

_ENTRY_SIZE = 8
_FLAG_NZB = 1


class WasmPipeline:
    def __init__(self, wasm_path: str) -> None:
        from wasmtime import Engine, Instance, Module, Store

        self._engine = Engine()
        self._store = Store(self._engine)
        module = Module.from_file(self._engine, wasm_path)
        self._instance = Instance(self._store, module, [])
        exports = self._instance.exports(self._store)
        self._memory = exports["memory"]
        self._alloc = exports["alloc"]
        self._dealloc = exports["dealloc"]
        self._parse_overviews = exports["parse_overviews"]

    def _write(self, ptr: int, data: bytes) -> None:
        self._memory.write(self._store, data, ptr)

    def _read(self, ptr: int, size: int) -> bytes:
        return self._memory.read(self._store, ptr, ptr + size)

    def parse_overviews(self, overview_list: list[tuple[int, dict]]) -> Optional[list[tuple[int, bool]]]:
        if not overview_list:
            return []

        buf = bytearray()
        buf.extend(struct.pack("<I", len(overview_list)))
        for _, overview in overview_list:
            subject = (overview.get("subject") or "").encode("utf-8", errors="ignore")
            poster = (overview.get("from") or "").encode("utf-8", errors="ignore")
            date_raw = (overview.get("date") or "").encode("utf-8", errors="ignore")
            size_raw = (overview.get("bytes") or "0").encode("utf-8", errors="ignore")
            message_id = (overview.get("message-id") or "").encode("utf-8", errors="ignore")
            for field in (subject, poster, date_raw, size_raw, message_id):
                buf.extend(struct.pack("<I", len(field)))
                buf.extend(field)

        in_size = len(buf)
        out_size = len(overview_list) * _ENTRY_SIZE
        in_ptr = self._alloc(self._store, in_size)
        out_ptr = self._alloc(self._store, out_size)
        if not in_ptr or not out_ptr:
            if in_ptr:
                self._dealloc(self._store, in_ptr, in_size)
            if out_ptr:
                self._dealloc(self._store, out_ptr, out_size)
            return None

        try:
            self._write(in_ptr, bytes(buf))
            status = self._parse_overviews(self._store, in_ptr, in_size, out_ptr, out_size)
            if status != 0:
                return None
            raw = self._read(out_ptr, out_size)
        finally:
            self._dealloc(self._store, in_ptr, in_size)
            self._dealloc(self._store, out_ptr, out_size)

        results = []
        for offset in range(0, len(raw), _ENTRY_SIZE):
            size, flags = struct.unpack_from("<II", raw, offset)
            results.append((int(size), bool(flags & _FLAG_NZB)))
        return results


def get_wasm_pipeline() -> Optional[WasmPipeline]:
    if os.environ.get("TRICERAPOST_DISABLE_WASM"):
        return None

    wasm_path = os.environ.get("TRICERAPOST_PIPELINE_WASM", DEFAULT_WASM_PATH)
    if not os.path.exists(wasm_path):
        return None

    try:
        return WasmPipeline(wasm_path)
    except Exception:
        return None
