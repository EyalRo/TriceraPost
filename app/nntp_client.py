#!/usr/bin/env python3.13
from __future__ import annotations
import socket
import ssl

type NNTPGroup = dict[str, str]
type NNTPOverview = dict[str, str]
type NNTPOverviewEntry = tuple[int, NNTPOverview]


class NNTPError(Exception):
    pass


class NNTPClient:
    def __init__(self, host: str, port: int, use_ssl: bool = False):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.sock = None
        self.file = None

    def connect(self) -> str:
        self.sock = socket.create_connection((self.host, self.port), timeout=30)
        if self.use_ssl:
            context = ssl.create_default_context()
            self.sock = context.wrap_socket(self.sock, server_hostname=self.host)
        self.file = self.sock.makefile("rwb", buffering=0)
        return self._read_status()

    def close(self) -> None:
        if self.file:
            self.file.close()
        if self.sock:
            self.sock.close()

    def _readline(self) -> str:
        if not self.file:
            raise NNTPError("Not connected")
        line = self.file.readline()
        if not line:
            raise NNTPError("Connection closed")
        return line.decode("utf-8", errors="replace").rstrip("\r\n")

    def _write(self, line: str) -> None:
        if not self.file:
            raise NNTPError("Not connected")
        payload = f"{line}\r\n".encode("utf-8")
        self.file.write(payload)

    def _read_status(self) -> str:
        line = self._readline()
        if len(line) < 3 or not line[:3].isdigit():
            raise NNTPError(f"Invalid response: {line}")
        return line

    def _expect(self, ok_prefixes: tuple[str, ...]) -> str:
        line = self._read_status()
        if not line.startswith(ok_prefixes):
            raise NNTPError(line)
        return line

    def command(self, line: str, ok_prefixes: tuple[str, ...] = ("2", "3")) -> str:
        self._write(line)
        return self._expect(ok_prefixes)

    def _read_multiline(self) -> list[str]:
        lines = []
        while True:
            line = self._readline()
            if line == ".":
                break
            if line.startswith(".."):
                line = line[1:]
            lines.append(line)
        return lines

    def reader_mode(self) -> None:
        try:
            self.command("MODE READER")
        except NNTPError:
            pass

    def auth(self, user: str, password: str) -> None:
        if not user:
            return
        self.command(f"AUTHINFO USER {user}", ok_prefixes=("2", "3"))
        if password:
            self.command(f"AUTHINFO PASS {password}", ok_prefixes=("2",))

    def list(self) -> list[NNTPGroup]:
        self.command("LIST", ok_prefixes=("2",))
        lines = self._read_multiline()
        groups = []
        for line in lines:
            parts = line.split()
            name = parts[0] if len(parts) > 0 else ""
            high = parts[1] if len(parts) > 1 else ""
            low = parts[2] if len(parts) > 2 else ""
            flags = parts[3] if len(parts) > 3 else ""
            groups.append(
                {
                    "group": name,
                    "high": high,
                    "low": low,
                    "flags": flags,
                    "raw": line,
                }
            )
        return groups

    def group(self, group: str) -> tuple[int, int, int, str]:
        line = self.command(f"GROUP {group}", ok_prefixes=("2",))
        # 211 count first last group
        parts = line.split()
        count = int(parts[1]) if len(parts) > 1 else 0
        first = int(parts[2]) if len(parts) > 2 else 0
        last = int(parts[3]) if len(parts) > 3 else 0
        name = parts[4] if len(parts) > 4 else group
        return count, first, last, name

    def xover(self, start: int, end: int) -> list[NNTPOverviewEntry]:
        self.command(f"XOVER {start}-{end}", ok_prefixes=("2",))
        lines = self._read_multiline()
        results = []
        for line in lines:
            parts = line.split("\t")
            art_num = int(parts[0]) if parts and parts[0].isdigit() else 0
            overview = {
                "subject": parts[1] if len(parts) > 1 else "",
                "from": parts[2] if len(parts) > 2 else "",
                "date": parts[3] if len(parts) > 3 else "",
                "message-id": parts[4] if len(parts) > 4 else "",
                "references": parts[5] if len(parts) > 5 else "",
                "bytes": parts[6] if len(parts) > 6 else "0",
                "lines": parts[7] if len(parts) > 7 else "",
                "xref": parts[8] if len(parts) > 8 else "",
                "raw": line,
            }
            results.append((art_num, overview))
        return results

    def body(self, article) -> list[str]:
        self.command(f"BODY {article}", ok_prefixes=("2",))
        return self._read_multiline()

    def article(self, article) -> list[str]:
        self.command(f"ARTICLE {article}", ok_prefixes=("2",))
        return self._read_multiline()

    def stat(self, article) -> str:
        return self.command(f"STAT {article}", ok_prefixes=("2",))

    def quit(self) -> None:
        try:
            self.command("QUIT", ok_prefixes=("2",))
        finally:
            self.close()
