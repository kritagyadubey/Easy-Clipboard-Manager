"""Guarantee that only one CopyVault instance runs at a time.

A named Windows mutex advertises the running instance; a companion named
event lets a second launch ask the first one to show its window.
"""

from __future__ import annotations

import ctypes
import threading
from typing import Callable, Optional

from ..logging_setup import get_logger

log = get_logger("single_instance")

_ERROR_ALREADY_EXISTS = 183

_MUTEX_NAME = "Local\\EasyClipboardManager_SingleInstance"
_SHOW_EVENT = "Local\\EasyClipboardManager_ShowWindow"

_kernel32 = ctypes.windll.kernel32


class SingleInstance:
    """Context manager owning the instance mutex and show-event listener."""

    def __init__(self) -> None:
        self._mutex: Optional[int] = None
        self._show_event: Optional[int] = None
        self._listener_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.is_primary = False

    # ------------------------------------------------------------------
    def acquire(self) -> bool:
        """Return True when this process is the primary instance."""
        self._mutex = int(_kernel32.CreateMutexW(None, False, _MUTEX_NAME))
        already = ctypes.get_last_error() == _ERROR_ALREADY_EXISTS
        if self._mutex and not already:
            self.is_primary = True
            self._show_event = int(_kernel32.CreateEventW(None, False, False, _SHOW_EVENT))
            self._start_listener()
        elif self._mutex:
            # Another instance is running: ask it to come to the foreground.
            self.notify_primary()
        return self.is_primary

    def notify_primary(self) -> None:
        handle = int(_kernel32.OpenEventW(0x0002, False, _SHOW_EVENT))  # EVENT_MODIFY_STATE
        if handle:
            try:
                _kernel32.SetEvent(handle)
            finally:
                _kernel32.CloseHandle(handle)

    def _start_listener(self) -> None:
        def loop() -> None:
            while not self._stop.is_set():
                if self._show_event:
                    result = _kernel32.WaitForSingleObject(self._show_event, 250)
                    if result == 0:  # WAIT_OBJECT_0
                        try:
                            self.on_show_requested()
                        except Exception:  # noqa: BLE001
                            log.exception("Show-request handler failed")

        self._listener_thread = threading.Thread(target=loop, daemon=True, name="show-event")
        self._listener_thread.start()

    def set_show_handler(self, callback: Callable[[], None]) -> None:
        self.on_show_requested = callback

    def on_show_requested(self) -> None:  # replaced by set_show_handler
        pass

    # ------------------------------------------------------------------
    def release(self) -> None:
        self._stop.set()
        if self._listener_thread and self._listener_thread.is_alive():
            self._listener_thread.join(timeout=1.0)
        for handle in (self._show_event, self._mutex):
            if handle:
                _kernel32.CloseHandle(handle)
        self._show_event = None
        self._mutex = None
