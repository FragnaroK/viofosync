"""Clip ZIP streaming and places search."""
from __future__ import annotations

import io
import zipfile

from web.services.zipstream import stream_zip


def test_stream_zip_roundtrip(tmp_path):
    a = tmp_path / "a.MP4"
    b = tmp_path / "b.MP4"
    a.write_bytes(b"A" * 3_000_000)
    b.write_bytes(b"hello")

    data = b"".join(stream_zip([(str(a), "a.MP4"), (str(b), "b.MP4")]))

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        assert zf.namelist() == ["a.MP4", "b.MP4"]
        assert zf.read("a.MP4") == b"A" * 3_000_000
        assert zf.read("b.MP4") == b"hello"
        assert zf.testzip() is None


def test_stream_zip_yields_incrementally(tmp_path):
    big = tmp_path / "big.MP4"
    big.write_bytes(b"x" * (3 << 20))
    chunks = list(stream_zip([(str(big), "big.MP4")]))
    assert len(chunks) > 2
