"""Stream a ZIP of local files without spooling the archive to disk."""
from __future__ import annotations

import io
import os
import zipfile
from typing import Iterator, Sequence, Tuple

CHUNK = 1 << 20


class _Sink(io.RawIOBase):
    """Write-only, unseekable buffer: ZipFile falls back to data descriptors."""

    def __init__(self) -> None:
        self._chunks: list[bytes] = []
        self._pos = 0

    def writable(self) -> bool:
        return True

    def write(self, b) -> int:
        data = bytes(b)
        self._chunks.append(data)
        self._pos += len(data)
        return len(data)

    def tell(self) -> int:
        return self._pos

    def drain(self) -> bytes:
        data = b"".join(self._chunks)
        self._chunks.clear()
        return data


def stream_zip(files: Sequence[Tuple[str, str]]) -> Iterator[bytes]:
    """Yield a stored (uncompressed) ZIP of ``(path, arcname)`` pairs.

    MP4s are already compressed, so ZIP_STORED keeps CPU near zero.
    """
    sink = _Sink()
    zf = zipfile.ZipFile(sink, "w", zipfile.ZIP_STORED)
    try:
        for path, arcname in files:
            info = zipfile.ZipInfo.from_file(path, arcname)
            with open(path, "rb") as src, zf.open(info, "w", force_zip64=True) as dst:
                while True:
                    chunk = src.read(CHUNK)
                    if not chunk:
                        break
                    dst.write(chunk)
                    data = sink.drain()
                    if data:
                        yield data
    finally:
        zf.close()
    tail = sink.drain()
    if tail:
        yield tail


def safe_arcname(name: str) -> str:
    return os.path.basename(name)
