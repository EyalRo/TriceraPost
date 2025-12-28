import unittest

from app.nntp_client import NNTPClient


class DummyFile:
    def __init__(self, lines):
        self._lines = list(lines)

    def readline(self):
        if not self._lines:
            return b""
        return self._lines.pop(0)


class TestNNTPClient(unittest.TestCase):
    def test_read_multiline_unescapes_dots(self):
        client = NNTPClient("example.com", 119)
        client.file = DummyFile([b"line1\r\n", b"..dotline\r\n", b".\r\n"])
        self.assertEqual(["line1", ".dotline"], client._read_multiline())
