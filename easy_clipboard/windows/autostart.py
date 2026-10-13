"""Start-with-Windows support via the per-user Run registry key.

No administrator rights are required: the key lives under the current user's
hive and only affects that account.
"""

from __future__ import annotations

import sys

from ..logging_setup import get_logger

log = get_logger("autostart")

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "EasyClipboardManager"

try:
    import winreg
except ImportError:  # pragma: no cover - non-Windows fallback
    winreg = None  # type: ignore[assignment]


def _command() -> str:
    """Best command line for launching the app in the background."""
    if getattr(sys, "frozen", False):
        # Packaged executable: start minimised in the tray.
        return f'"{sys.executable}" --background'
    return f'"{sys.executable}" -m easy_clipboard --background'


def is_available() -> bool:
    return winreg is not None


def is_enabled() -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _VALUE_NAME)
        return True
    except OSError:
        return False


def set_enabled(enabled: bool) -> bool:
    """Enable or disable launch-at-startup. Returns True on success."""
    if winreg is None:
        return False
    try:
        if enabled:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, _command())
            log.info("Launch at startup enabled")
        else:
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
                ) as key:
                    winreg.DeleteValue(key, _VALUE_NAME)
            except FileNotFoundError:
                pass
            log.info("Launch at startup disabled")
        return True
    except OSError as exc:
        log.warning("Could not update startup registration (%s)", type(exc).__name__)
        return False
