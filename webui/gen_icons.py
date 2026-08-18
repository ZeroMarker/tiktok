#!/usr/bin/env python3
"""Generate PWA icons for the Live Stream WebUI (pure stdlib, no Pillow needed).

Renders: rounded-square dark tile + green record dot (matches the dashboard UI),
with analytic anti-aliasing via signed distance functions.
Outputs are committed; rerun only when the visual identity changes.
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent

BG_TOP = (23, 33, 44)      # #17212c
BG_BOT = (11, 17, 24)      # #0b1118
GREEN = (54, 211, 153)     # #36d399
INNER = (5, 41, 29)        # #05291d


def clamp(v: float, a: float, b: float) -> float:
    return a if v < a else b if v > b else v


def lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[float, float, float]:
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def sd_round_rect(x: float, y: float, cx: float, cy: float, hw: float, hh: float, r: float) -> float:
    qx = abs(x - cx) - (hw - r)
    qy = abs(y - cy) - (hh - r)
    bx, by = max(qx, 0.0), max(qy, 0.0)
    return min(max(qx, qy), 0.0) + math.hypot(bx, by) - r


def sd_circle(x: float, y: float, cx: float, cy: float, r: float) -> float:
    return math.hypot(x - cx, y - cy) - r


def coverage(sd: float) -> float:
    return clamp(0.5 - sd, 0.0, 1.0)


def render(size: int, *, maskable: bool = False, path: Path) -> None:
    s = float(size)
    cx = cy = s / 2
    margin = 0.0 if maskable else s * 0.02
    corner = 0.0 if maskable else s * 0.22
    outer_r = s * 0.26 if maskable else s * 0.30
    inner_r = outer_r * 0.42
    inv = 1.0 / (size - 1)

    rows = []
    for y in range(size):
        row = bytearray()
        bg = lerp(BG_TOP, BG_BOT, y * inv)
        for x in range(size):
            px, py = x + 0.5, y + 0.5
            if maskable:
                a_bg = 1.0
            else:
                a_bg = coverage(sd_round_rect(px, py, cx, cy, s / 2 - margin, s / 2 - margin, corner))
            if a_bg <= 0:
                row += b"\x00\x00\x00\x00"
                continue
            a_dot = coverage(sd_circle(px, py, cx, cy, outer_r))
            a_in = coverage(sd_circle(px, py, cx, cy, inner_r))
            a_ring = max(0.0, a_dot - a_in)  # green ring between outer and inner edge

            r, g, b = bg
            if a_ring > 0:
                r += (GREEN[0] - r) * a_ring
                g += (GREEN[1] - g) * a_ring
                b += (GREEN[2] - b) * a_ring
            if a_in > 0:
                r += (INNER[0] - r) * a_in
                g += (INNER[1] - g) * a_in
                b += (INNER[2] - b) * a_in
            row += bytes((round(r), round(g), round(b), round(255 * a_bg)))
        rows.append(row)
    write_png(path, size, size, rows)


def write_png(path: Path, width: int, height: int, rows: list[bytearray]) -> None:
    raw = b"".join(b"\x00" + bytes(row) for row in rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))  # 8-bit RGBA
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)


def write_ico(path: Path, png_bytes: bytes) -> None:
    """ICO container embedding a PNG entry (supported by all modern browsers)."""
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", 32, 32, 0, 0, 1, 32, len(png_bytes), 22)
    path.write_bytes(header + entry + png_bytes)


def main() -> None:
    targets = [
        (32, False, OUT / "icon-32.png"),
        (180, False, OUT / "icon-180.png"),
        (192, False, OUT / "icon-192.png"),
        (512, False, OUT / "icon-512.png"),
        (512, True, OUT / "icon-maskable-512.png"),
    ]
    for size, maskable, path in targets:
        render(size, maskable=maskable, path=path)
        print(f"{path.name}: {size}x{size} {'maskable' if maskable else 'any'}")
    write_ico(OUT / "favicon.ico", (OUT / "icon-32.png").read_bytes())
    print("favicon.ico: 32x32 (PNG-in-ICO)")


if __name__ == "__main__":
    main()