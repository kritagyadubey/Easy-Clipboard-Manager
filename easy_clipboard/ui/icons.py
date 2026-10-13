"""Vector icon set.

Icons are drawn from SVG path data (24×24 grid, stroke-based, rounded caps)
and tinted at runtime, so a single definition works in every theme.  No emoji
are used anywhere in the interface.
"""

from __future__ import annotations

from typing import Dict

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import QByteArray

# Each entry: list of SVG elements (paths / shapes) drawn on a 24x24 grid.
_PATHS: Dict[str, str] = {
    "layers": """
        <polyline points="12 2 2 7 12 12 22 7 12 2"/>
        <polyline points="2 17 12 22 22 17"/>
        <polyline points="2 12 12 17 22 12"/>
    """,
    "clock": """
        <circle cx="12" cy="12" r="9"/>
        <polyline points="12 7 12 12 15.5 14"/>
    """,
    "pin": """
        <path d="M9.5 4h5"/>
        <path d="M10 4v6.8l-2.6 2.8a1.7 1.7 0 0 0 1.2 2.9h6.8a1.7 1.7 0 0 0 1.2-2.9L14 10.8V4"/>
        <line x1="12" y1="16.5" x2="12" y2="21"/>
    """,
    "pin-filled": """
        <path fill="currentColor" stroke="none" d="M9.5 3.2h5a.9.9 0 0 1 0 1.8h-.4v6.2l2.4 2.6a1.7 1.7 0 0 1-1.2 2.9H8.7a1.7 1.7 0 0 1-1.2-2.9l2.4-2.6V5h-.4a.9.9 0 0 1 0-1.8z"/>
        <line x1="12" y1="16.8" x2="12" y2="21"/>
    """,
    "star": """
        <polygon points="12 2.5 15.1 8.8 22 9.8 17 14.7 18.2 21.6 12 18.3 5.8 21.6 7 14.7 2 9.8 8.9 8.8"/>
    """,
    "star-filled": """
        <polygon fill="currentColor" stroke="none" points="12 2.5 15.1 8.8 22 9.8 17 14.7 18.2 21.6 12 18.3 5.8 21.6 7 14.7 2 9.8 8.9 8.8"/>
    """,
    "search": """
        <circle cx="11" cy="11" r="7.5"/>
        <line x1="21" y1="21" x2="16.5" y2="16.5"/>
    """,
    "copy": """
        <rect x="9" y="9" width="12.5" height="12.5" rx="2.5"/>
        <path d="M5.5 15H4.5A2 2 0 0 1 2.5 13V4.5a2 2 0 0 1 2-2H13a2 2 0 0 1 2 2v1"/>
    """,
    "trash": """
        <path d="M3.5 6h17"/>
        <path d="M19 6v13a2.5 2.5 0 0 1-2.5 2.5h-9A2.5 2.5 0 0 1 5 19V6"/>
        <path d="M9 6V4.5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2V6"/>
        <line x1="10" y1="11" x2="10" y2="17"/>
        <line x1="14" y1="11" x2="14" y2="17"/>
    """,
    "pause": """
        <rect x="6.5" y="4.5" width="3.6" height="15" rx="1.2"/>
        <rect x="13.9" y="4.5" width="3.6" height="15" rx="1.2"/>
    """,
    "play": """
        <polygon points="6.5 3.8 19.5 12 6.5 20.2"/>
    """,
    "settings": """
        <circle cx="12" cy="12" r="3.1"/>
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
    """,
    "link": """
        <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
        <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
    """,
    "code": """
        <polyline points="16.5 18 22 12 16.5 6"/>
        <polyline points="7.5 6 2 12 7.5 18"/>
    """,
    "braces": """
        <path d="M8 3H7a2 2 0 0 0-2 2v4a2 2 0 0 1-2 2 2 2 0 0 1 2 2v4a2 2 0 0 0 2 2h1"/>
        <path d="M16 3h1a2 2 0 0 1 2 2v4a2 2 0 0 0 2 2 2 2 0 0 0-2 2v4a2 2 0 0 1-2 2h-1"/>
    """,
    "hash": """
        <line x1="4.5" y1="9" x2="19.5" y2="9"/>
        <line x1="4.5" y1="15" x2="19.5" y2="15"/>
        <line x1="10" y1="3.5" x2="8" y2="20.5"/>
        <line x1="16" y1="3.5" x2="14" y2="20.5"/>
    """,
    "mail": """
        <rect x="2.5" y="5" width="19" height="14" rx="2.5"/>
        <polyline points="3 6.5 12 13 21 6.5"/>
    """,
    "file-text": """
        <path d="M14 2.5H6.5a2 2 0 0 0-2 2v15a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V8z"/>
        <polyline points="14 2.5 14 8 19.5 8"/>
        <line x1="8.5" y1="13" x2="15.5" y2="13"/>
        <line x1="8.5" y1="17" x2="15.5" y2="17"/>
        <line x1="8.5" y1="9" x2="11" y2="9"/>
    """,
    "bookmark": """
        <path d="M19 21l-7-5-7 5V5.5a2.5 2.5 0 0 1 2.5-2.5h9A2.5 2.5 0 0 1 19 5.5z"/>
    """,
    "x": """
        <line x1="18" y1="6" x2="6" y2="18"/>
        <line x1="6" y1="6" x2="18" y2="18"/>
    """,
    "chevron-down": """
        <polyline points="6 9.5 12 15.5 18 9.5"/>
    """,
    "chevron-right": """
        <polyline points="9.5 6 15.5 12 9.5 18"/>
    """,
    "plus": """
        <line x1="12" y1="5" x2="12" y2="19"/>
        <line x1="5" y1="12" x2="19" y2="12"/>
    """,
    "check": """
        <polyline points="20 6.5 9.5 17 4 11.5"/>
    """,
    "upload": """
        <path d="M21 15.5V19a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 19v-3.5"/>
        <polyline points="16.5 7.5 12 3 7.5 7.5"/>
        <line x1="12" y1="3" x2="12" y2="15.5"/>
    """,
    "download": """
        <path d="M21 15.5V19a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 19v-3.5"/>
        <polyline points="7.5 10.5 12 15 16.5 10.5"/>
        <line x1="12" y1="15" x2="12" y2="2.5"/>
    """,
    "folder": """
        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
    """,
    "edit": """
        <path d="M17.5 3.5a2.12 2.12 0 0 1 3 3L8 19l-4 1 1-4z"/>
    """,
    "external": """
        <path d="M18 13.5V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h5.5"/>
        <polyline points="14.5 3 21 3 21 9.5"/>
        <line x1="10" y1="14" x2="21" y2="3"/>
    """,
    "shield": """
        <path d="M12 22s8-3.5 8-10V5.5L12 2.5 4 5.5V12c0 6.5 8 10 8 10z"/>
        <polyline points="8.5 12 11 14.5 15.5 10"/>
    """,
    "keyboard": """
        <rect x="2" y="5.5" width="20" height="13" rx="2.5"/>
        <line x1="6" y1="9.5" x2="6.01" y2="9.5"/>
        <line x1="10" y1="9.5" x2="10.01" y2="9.5"/>
        <line x1="14" y1="9.5" x2="14.01" y2="9.5"/>
        <line x1="18" y1="9.5" x2="18.01" y2="9.5"/>
        <line x1="7" y1="14.5" x2="17" y2="14.5"/>
    """,
    "info": """
        <circle cx="12" cy="12" r="9"/>
        <line x1="12" y1="11" x2="12" y2="16.5"/>
        <line x1="12" y1="7.5" x2="12.01" y2="7.5"/>
    """,
    "moon": """
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
    """,
    "sun": """
        <circle cx="12" cy="12" r="4.2"/>
        <line x1="12" y1="1.8" x2="12" y2="4"/>
        <line x1="12" y1="20" x2="12" y2="22.2"/>
        <line x1="4.2" y1="4.2" x2="5.75" y2="5.75"/>
        <line x1="18.25" y1="18.25" x2="19.8" y2="19.8"/>
        <line x1="1.8" y1="12" x2="4" y2="12"/>
        <line x1="20" y1="12" x2="22.2" y2="12"/>
        <line x1="4.2" y1="19.8" x2="5.75" y2="18.25"/>
        <line x1="18.25" y1="5.75" x2="19.8" y2="4.2"/>
    """,
    "monitor": """
        <rect x="2.5" y="3.5" width="19" height="13" rx="2"/>
        <line x1="8.5" y1="21" x2="15.5" y2="21"/>
        <line x1="12" y1="16.5" x2="12" y2="21"/>
    """,
    "alert": """
        <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
        <line x1="12" y1="9.5" x2="12" y2="13.5"/>
        <line x1="12" y1="17.5" x2="12.01" y2="17.5"/>
    """,
    "archive": """
        <rect x="2.5" y="3.5" width="19" height="4.5" rx="1.5"/>
        <path d="M4.5 8v10.5a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V8"/>
        <line x1="10" y1="12.5" x2="14" y2="12.5"/>
    """,
    "menu": """
        <line x1="3.5" y1="7" x2="20.5" y2="7"/>
        <line x1="3.5" y1="12" x2="20.5" y2="12"/>
        <line x1="3.5" y1="17" x2="20.5" y2="17"/>
    """,
}

_SVG_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
    'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="{sw}" '
    'stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
)

_CACHE: Dict[tuple, QIcon] = {}


def available_icons() -> list[str]:
    return sorted(_PATHS)


def icon(name: str, color: str = "#9ba5b4", size: int = 18, stroke_width: float = 1.9) -> QIcon:
    """Return a tinted :class:`QIcon` for ``name`` (cached)."""
    key = (name, color, size, stroke_width)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    body = _PATHS.get(name, _PATHS["file-text"])
    svg = _SVG_TEMPLATE.format(
        size=size, color=color, sw=stroke_width, body=body
    )
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()

    result = QIcon(pixmap)
    _CACHE[key] = result
    return result


def pixmap(name: str, color: str = "#9ba5b4", size: int = 18, stroke_width: float = 1.9) -> QPixmap:
    """Same as :func:`icon` but returns the underlying pixmap."""
    return icon(name, color, size, stroke_width).pixmap(size, size)


def clear_cache() -> None:
    _CACHE.clear()
