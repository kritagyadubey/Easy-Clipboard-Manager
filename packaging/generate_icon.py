"""Generate packaging/app.ico from the programmatic app logo.

Run from the repository root:

    python packaging/generate_icon.py

The .ico is derived from ``theme.render_logo()`` so the executable icon is
always the same mark the application draws in its own UI — there is no
separate design asset that can drift out of sync.  Multi-size (16–256 px)
PNG-compressed entries, which Windows Vista and later understand.
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SIZES = (16, 24, 32, 48, 64, 128, 256)
OUTPUT = Path(__file__).resolve().parent / "app.ico"


def _png_bytes(size: int) -> bytes:
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtWidgets import QApplication

    from easy_clipboard.ui.theme import render_logo

    QApplication.instance() or QApplication([])
    pixmap = render_logo(size)
    buffer = QBuffer()
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        raise RuntimeError("could not open an in-memory buffer for PNG output")
    if not pixmap.save(buffer, "PNG"):
        raise RuntimeError(f"could not encode the {size}px logo as PNG")
    return bytes(buffer.data())


def build_ico() -> bytes:
    images = [_png_bytes(size) for size in SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))  # reserved, type=icon, count
    entries = b""
    offset = 6 + 16 * len(images)
    for size, data in zip(SIZES, images):
        dimension = 0 if size >= 256 else size  # 0 means 256 in an ICONDIRENTRY
        entries += struct.pack(
            "<BBBBHHII",
            dimension,
            dimension,
            0,  # palette colours
            0,  # reserved
            1,  # colour planes
            32,  # bits per pixel
            len(data),
            offset,
        )
        offset += len(data)
    return header + entries + b"".join(images)


def main() -> None:
    OUTPUT.write_bytes(build_ico())
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
