"""Identify the foreground application (used for exclusion rules).

Windows does not expose a simple "who owns the clipboard" API, so the best
available approximation is the process that owns the currently focused
window.  This is best-effort: protected processes may be unreadable, in
which case ``None`` is returned and the entry is captured normally.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
from typing import Optional

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def get_foreground_process() -> Optional[str]:
    """Return the executable name of the foreground process, if readable."""
    try:
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = wt.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return None

        handle = _kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value
        )
        if not handle:
            return None
        try:
            size = wt.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            ok = _kernel32.QueryFullProcessImageNameW(
                handle, 0, buffer, ctypes.byref(size)
            )
            if not ok:
                return None
            path = buffer.value
            return path.rsplit("\\", 1)[-1].lower() or None
        finally:
            _kernel32.CloseHandle(handle)
    except Exception:  # noqa: BLE001 - foreground lookup must never break capture
        return None
