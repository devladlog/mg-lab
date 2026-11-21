"""Write the two icons every app package needs, without any imaging library.

Learn (App package for Microsoft 365): color.png 192x192; outline.png 32x32 with a transparent background."""
from __future__ import annotations

import struct
import zlib


def _png(width: int, height: int, pixel) -> bytes:
    raw = b"".join(b"\x00" + b"".join(bytes(pixel(x, y)) for x in range(width)) for y in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def color_icon() -> bytes:
    """192x192: solid dark blue square with a white 'V' made of two thick strokes (safe area 120x120)."""
    def px(x, y):
        cx = x - 96
        top, bottom = 36, 156
        if top <= y <= bottom:
            half = (bottom - y) * 0.5 + 6   # the V narrows towards the bottom
            inner = (bottom - y) * 0.5 - 8
            if inner < abs(cx) <= half + 14 and abs(cx) >= max(inner, 0):
                return (255, 255, 255, 255)
        return (0x1F, 0x4E, 0x79, 255)
    return _png(192, 192, px)


def outline_icon() -> bytes:
    """32x32: transparent background, white 'V' outline (Learn: outline icon is white on transparent)."""
    def px(x, y):
        cx = x - 16
        if 6 <= y <= 26 and abs(cx) <= (26 - y) * 0.5 + 2 and abs(cx) >= (26 - y) * 0.5 - 1:
            return (255, 255, 255, 255)
        return (0, 0, 0, 0)
    return _png(32, 32, px)


def png_size(data: bytes) -> tuple[int, int]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    return struct.unpack(">II", data[16:24])
