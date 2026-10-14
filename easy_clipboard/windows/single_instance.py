"""Guarantee that only one Easy Clipboard Manager instance runs at a time.

A named Windows mutex advertises the running instance; a companion named
event lets a second launch ask the first one to show its window.

Note on ``use_last_error``: ``ctypes.windll`` does **not** keep a private
copy of the thread's ``GetLastError`` value, so ``ctypes.get_last_error()``
always returns 0 after a call made through it.  Detecting
``ERROR_ALREADY_EXISTS`` (which is how "another instance is running" is
detected) therefore requires a DLL loaded with ``use_last_error=True``.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import threading
import time
from typing import Callable, Optional

from ..logging_setup import get_logger

log = get_logger("single_instance")

_ERROR_ALREADY_EXISTS = 183

_MUTEX_NAME = "Local\\EasyClipboardManager_SingleInstance"
_SHOW_EVENT = "Local\\EasyClipboardManager_ShowWindow"

# use_last_error=True is essential here - see the module docstring.
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateMutexW.restype = wt.HANDLE
_kernel32.CreateEventW.restype = wt.HANDLE
_kernel32.OpenEventW.restype = wt.HANDLE
_kernel32.WaitForSingleObject.restype = wt.DWORD
_kernel32.CreateMutexW.argtypes = (wt.LPVOID, wt.BOOL, wt.LPCWSTR)
_kernel32.CreateEventW.argtypes = (wt.LPVOID, wt.BOOL, wt.BOOL, wt.LPCWSTR)
_kernel32.OpenEventW.argtypes = (wt.DWORD, wt.BOOL, wt.LPCWSTR)
_kernel32.SetEvent.argtypes = (wt.HANDLE,)
_kernel32.CloseHandle.argtypes = (wt.HANDLE,)
_kernel32.WaitForSingleObject.argtypes = (wt.HANDLE, wt.DWORD)

# How long a second launch keeps looking for the primary's show-event
# (the primary may still be starting up when the mutex is first seen).
_NOTIFY_TIMEOUT_S = 2.0
_NOTIFY_POLL_S = 0.05


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
        handle = _kernel32.CreateMutexW(None, False, _MUTEX_NAME)
        # NOTE: ctypes.get_last_error() must be read immediately after the
        # call above; it is what tells us the mutex already existed.
        already = ctypes.get_last_error() == _ERROR_ALREADY_EXISTS
        self._mutex = int(handle) if handle else None
        if self._mutex is None:
            log.error("Could not create the single-instance mutex; refusing to run")
            return self.is_primary
        if not already:
            self.is_primary = True
            event = _kernel32.CreateEventW(None, False, False, _SHOW_EVENT)
            self._show_event = int(event) if event else None
            if self._show_event is None:
                log.error("Could not create the show-window event")
            self._start_listener()
        else:
            # Another instance is running: ask it to come to the foreground.
            self.notify_primary()
        return self.is_primary

    def notify_primary(self) -> bool:
        """Signal the primary instance to show its window.

        Retries briefly because a freshly started primary may not have
        created its show-event yet.  Returns True when the signal was sent.
        """
        deadline = time.monotonic() + _NOTIFY_TIMEOUT_S
        while True:
            # EVENT_MODIFY_STATE (0x0002) is required for SetEvent.
            handle = _kernel32.OpenEventW(0x0002, False, _SHOW_EVENT)
            if handle:
                try:
                    _kernel32.SetEvent(handle)
                    return True
                finally:
                    _kernel32.CloseHandle(handle)
            if time.monotonic() >= deadline:
                log.warning("Primary instance's show-event is not available")
                return False
            time.sleep(_NOTIFY_POLL_S)

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
                else:
                    # No event to wait on: never busy-spin.
                    time.sleep(0.25)

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
