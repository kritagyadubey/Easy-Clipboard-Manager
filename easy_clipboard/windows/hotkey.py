"""Global keyboard shortcut via the Win32 ``RegisterHotKey`` API.

The shortcut is registered against a hidden Qt window so that ``WM_HOTKEY``
arrives through Qt's native event filter.  No administrator rights are
needed.  If the combination is already taken by another application the
registration fails cleanly and the caller can tell the user.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
from typing import Optional

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication, QWidget

from ..logging_setup import get_logger

log = get_logger("hotkey")

WM_HOTKEY = 0x0312
_HOTKEY_ID = 0xE0C1

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

_VK_KEYS = {
    "A": 0x41, "B": 0x42, "C": 0x43, "D": 0x44, "E": 0x45, "F": 0x46,
    "G": 0x47, "H": 0x48, "I": 0x49, "J": 0x4A, "K": 0x4B, "L": 0x4C,
    "M": 0x4D, "N": 0x4E, "O": 0x4F, "P": 0x50, "Q": 0x51, "R": 0x52,
    "S": 0x53, "T": 0x54, "U": 0x55, "V": 0x56, "W": 0x57, "X": 0x58,
    "Y": 0x59, "Z": 0x5A,
    **{str(i): 0x30 + i for i in range(10)},
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73, "F5": 0x74, "F6": 0x75,
    "F7": 0x76, "F8": 0x77, "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
    "SPACE": 0x20, "TAB": 0x09, "INSERT": 0x2D, "DELETE": 0x2E,
    "HOME": 0x24, "END": 0x23, "PRIOR": 0x21, "NEXT": 0x22,
}

_MODIFIER_TOKENS = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
    "super": MOD_WIN,
}


class HotkeyError(ValueError):
    """Raised for shortcut strings Windows cannot register."""


def parse_hotkey(text: str) -> tuple[int, int]:
    """Parse ``"Ctrl+Shift+V"`` into ``(modifiers, virtual key)``."""
    parts = [p.strip() for p in text.replace("-", "+").split("+") if p.strip()]
    if not parts:
        raise HotkeyError("Empty shortcut")
    modifiers = MOD_NOREPEAT
    key: Optional[int] = None
    for index, part in enumerate(parts):
        upper = part.upper()
        if index < len(parts) - 1:
            token = _MODIFIER_TOKENS.get(part.lower())
            if token is None:
                raise HotkeyError(f"Unknown modifier: {part}")
            modifiers |= token
        else:
            key = _VK_KEYS.get(upper)
            if key is None:
                raise HotkeyError(f"Unsupported key: {part}")
    if key is None:
        raise HotkeyError("No key specified")
    if modifiers == MOD_NOREPEAT:
        # A bare key would hijack normal typing system-wide.
        raise HotkeyError("Shortcut must include at least one modifier")
    return modifiers, key


def format_hotkey(combo: str) -> str:
    """Normalise a shortcut string for display (``ctrl+shift+v`` -> ``Ctrl+Shift+V``)."""
    try:
        modifiers, key = parse_hotkey(combo)
    except HotkeyError:
        return combo
    names = []
    if modifiers & MOD_CONTROL:
        names.append("Ctrl")
    if modifiers & MOD_ALT:
        names.append("Alt")
    if modifiers & MOD_SHIFT:
        names.append("Shift")
    if modifiers & MOD_WIN:
        names.append("Win")
    key_name = next((k.title() for k, v in _VK_KEYS.items() if v == key), str(key))
    names.append(key_name)
    return "+".join(names)


class GlobalHotkey(QObject):
    """Registers a system-wide shortcut and emits ``activated``."""

    activated = Signal()

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._user32 = ctypes.windll.user32
        self._host = QWidget(None)
        self._host.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self._host.winId()  # force native window creation
        self._registered = False
        self._combo = ""
        self._filter = _HotkeyFilter(self)
        app = QApplication.instance()
        if app is not None:
            app.installNativeEventFilter(self._filter)

    # ------------------------------------------------------------------
    @property
    def is_registered(self) -> bool:
        return self._registered

    @property
    def combo(self) -> str:
        return self._combo

    def register(self, combo: str) -> bool:
        """(Re-)register ``combo``. Returns False when Windows refuses."""
        self.unregister()
        try:
            modifiers, key = parse_hotkey(combo)
        except HotkeyError as exc:
            log.warning("Invalid shortcut %r (%s)", combo, exc)
            return False
        ok = bool(
            self._user32.RegisterHotKey(
                int(self._host.winId()), _HOTKEY_ID, modifiers, key
            )
        )
        self._registered = ok
        self._combo = combo if ok else ""
        if ok:
            log.info("Global shortcut registered: %s", format_hotkey(combo))
        else:
            log.warning("Global shortcut unavailable (already in use): %s", combo)
        return ok

    def unregister(self) -> None:
        if self._registered:
            self._user32.UnregisterHotKey(int(self._host.winId()), _HOTKEY_ID)
            self._registered = False

    def _handle_native(self, message) -> bool:
        if not self._registered:
            return False
        try:
            msg = wt.MSG.from_address(int(message))
        except (TypeError, ValueError):
            return False
        if msg.message == WM_HOTKEY and msg.wParam == _HOTKEY_ID:
            self.activated.emit()
            return True
        return False

    def shutdown(self) -> None:
        self.unregister()
        app = QApplication.instance()
        if app is not None:
            app.removeNativeEventFilter(self._filter)
        self._host.deleteLater()


class _HotkeyFilter(QObject):
    """Bridges native ``WM_HOTKEY`` messages to :class:`GlobalHotkey`."""

    def __init__(self, hotkey: GlobalHotkey):
        super().__init__()
        self._hotkey = hotkey

    def nativeEventFilter(self, event_type, message):  # noqa: N802 - Qt API name
        try:
            handled = self._hotkey._handle_native(message)
        except Exception:  # noqa: BLE001 - never let the filter raise
            return False, 0
        return (True, 0) if handled else (False, 0)
