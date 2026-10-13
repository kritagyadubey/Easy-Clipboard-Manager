"""Clipboard monitoring.

Qt delivers ``QClipboard.dataChanged`` for every system clipboard update on
Windows, which makes event-driven capture possible without busy polling.  A
very low-frequency (2 s) sequence-number check is kept as a safety net for
the rare occasions where a change notification is missed; it costs a single
cheap Win32 call per tick.
"""

from __future__ import annotations

import ctypes
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QClipboard
from PySide6.QtWidgets import QApplication

from ..logging_setup import get_logger

log = get_logger("clipboard")

_user32 = ctypes.windll.user32

# Retry delay when the clipboard is locked by another process.
_RETRY_MS = 250


def write_to_system_clipboard(text: str) -> bool:
    """Put ``text`` on the system clipboard. Returns True on success."""
    app = QApplication.instance()
    if app is None:
        return False
    try:
        app.clipboard().setText(text, QClipboard.Clipboard)
        return True
    except Exception:  # noqa: BLE001 - clipboard can be locked by other apps
        log.warning("Failed to write to the clipboard")
        return False


class ClipboardMonitor(QObject):
    """Watches the system clipboard and emits captured text.

    Signals
    -------
    text_captured(text, source_app)
        A new clipboard value should be considered for storage.
    monitor_error(message)
        A user-facing problem (for example, repeated clipboard lock).
    """

    text_captured = Signal(str, str)
    monitor_error = Signal(str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._app = QApplication.instance()
        self._clipboard = self._app.clipboard() if self._app is not None else None
        self._running = False
        self._paused = False
        self._last_text: Optional[str] = None
        self._last_sequence = 0
        self._ignore_text: Optional[str] = None
        self._retry_count = 0
        self._capture_source = None  # callable -> Optional[str]

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(2000)
        self._poll_timer.timeout.connect(self._poll_sequence)

        self._retry_timer = QTimer(self)
        self._retry_timer.setSingleShot(True)
        self._retry_timer.timeout.connect(self._read_now)

        if self._clipboard is not None:
            self._clipboard.dataChanged.connect(self._on_data_changed)

    # ------------------------------------------------------------------
    def set_source_resolver(self, resolver) -> None:
        """``resolver()`` returns the foreground application name (or None)."""
        self._capture_source = resolver

    def start(self) -> None:
        if self._running or self._clipboard is None:
            return
        self._running = True
        self._last_sequence = _user32.GetClipboardSequenceNumber()
        self._poll_timer.start()
        log.info("Clipboard monitoring started")

    def stop(self) -> None:
        self._running = False
        self._poll_timer.stop()
        self._retry_timer.stop()
        log.info("Clipboard monitoring stopped")

    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        log.info("Clipboard monitoring %s", "paused" if paused else "resumed")

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    def ignore_next(self, text: str) -> None:
        """Suppress capture of a value this application just wrote."""
        self._ignore_text = text
        self._last_text = text
        self._last_sequence = _user32.GetClipboardSequenceNumber()

    # ------------------------------------------------------------------
    def _on_data_changed(self) -> None:
        if not self._running:
            return
        # Small debounce: applications sometimes set the clipboard twice in
        # quick succession (e.g. plain text + HTML formats).
        self._retry_timer.start(_RETRY_MS)

    def _poll_sequence(self) -> None:
        if not self._running:
            return
        sequence = _user32.GetClipboardSequenceNumber()
        if sequence != self._last_sequence:
            self._read_now()

    def _read_now(self) -> None:
        if not self._running or self._paused:
            self._last_sequence = _user32.GetClipboardSequenceNumber()
            return
        try:
            text = self._clipboard.text(QClipboard.Clipboard)
        except Exception:  # noqa: BLE001 - clipboard busy or unavailable
            self._retry_count += 1
            if self._retry_count == 5:
                self.monitor_error.emit(
                    "The clipboard is temporarily unavailable; capture will retry."
                )
            self._retry_timer.start(_RETRY_MS * 2)
            return

        self._retry_count = 0
        self._last_sequence = _user32.GetClipboardSequenceNumber()

        if text is None:
            return
        if text == self._last_text:
            return
        self._last_text = text
        if not text.strip():
            return
        if self._ignore_text is not None and text == self._ignore_text:
            self._ignore_text = None
            return

        source = ""
        if self._capture_source is not None:
            try:
                source = self._capture_source() or ""
            except Exception:  # noqa: BLE001
                source = ""
        self.text_captured.emit(text, source)
