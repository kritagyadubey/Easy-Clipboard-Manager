"""Persistent user preferences.

Settings are stored as JSON in the per-user data folder.  Every preference
declared here is wired to real application behaviour — there are no
decorative switches.
"""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .logging_setup import get_logger

log = get_logger("settings")

THEMES = ("dark", "light", "system")
DENSITIES = ("comfortable", "compact")
DUPLICATE_MODES = ("refresh", "ignore")

DEFAULT_HOTKEY = "Ctrl+Shift+V"
MAX_HISTORY_LIMIT = 10_000
MIN_HISTORY_LIMIT = 25
MAX_RETENTION_DAYS = 3650  # effectively "forever" for practical purposes


def _as_bool(value: Any, default: bool) -> bool:
    """Coerce loosely-typed JSON values to a real bool.

    ``bool("false")`` is ``True`` in Python, so plain ``bool()`` would turn a
    hand-edited "false" in the settings file into an enabled preference.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        token = value.strip().lower()
        if token in ("1", "true", "yes", "on"):
            return True
        if token in ("0", "false", "no", "off", ""):
            return False
    return default


@dataclass
class Settings:
    # General -----------------------------------------------------------------
    launch_at_startup: bool = False
    minimize_to_tray: bool = True
    start_minimized: bool = False
    global_hotkey: str = DEFAULT_HOTKEY

    # Appearance --------------------------------------------------------------
    theme: str = "dark"                 # dark | light | system
    density: str = "comfortable"        # comfortable | compact

    # Clipboard history -------------------------------------------------------
    monitoring_enabled: bool = True
    max_items: int = 500                # ordinary (unprotected) history size
    retention_days: int = 30            # 0 keeps entries indefinitely
    duplicate_handling: str = "refresh"  # refresh | ignore
    excluded_apps: list[str] = field(default_factory=list)

    # Internal ----------------------------------------------------------------
    window_geometry: str = ""           # base64 of QMainWindow.saveGeometry()
    last_section: str = "all"

    def normalised(self) -> "Settings":
        """Return a copy with every value coerced to a valid range."""
        s = deepcopy(self)
        s.launch_at_startup = _as_bool(s.launch_at_startup, False)
        s.minimize_to_tray = _as_bool(s.minimize_to_tray, True)
        s.start_minimized = _as_bool(s.start_minimized, False)
        s.monitoring_enabled = _as_bool(s.monitoring_enabled, True)
        if s.theme not in THEMES:
            s.theme = "dark"
        if s.density not in DENSITIES:
            s.density = "comfortable"
        if s.duplicate_handling not in DUPLICATE_MODES:
            s.duplicate_handling = "refresh"
        if not isinstance(s.window_geometry, str):
            # _restore_geometry calls .encode() on this; a stray int would crash.
            s.window_geometry = ""
        if not isinstance(s.last_section, str):
            s.last_section = "all"
        try:
            s.max_items = int(s.max_items)
        except (TypeError, ValueError):
            s.max_items = 500
        s.max_items = max(MIN_HISTORY_LIMIT, min(MAX_HISTORY_LIMIT, s.max_items))
        try:
            s.retention_days = int(s.retention_days)
        except (TypeError, ValueError):
            s.retention_days = 30
        s.retention_days = max(0, min(MAX_RETENTION_DAYS, s.retention_days))
        raw_apps = s.excluded_apps
        if not isinstance(raw_apps, (list, tuple)):
            raw_apps = []
        s.excluded_apps = [
            str(app).strip().lower()
            for app in raw_apps
            if str(app).strip()
        ]
        if not isinstance(s.global_hotkey, str) or not s.global_hotkey.strip():
            s.global_hotkey = DEFAULT_HOTKEY
        return s


class SettingsStore:
    """Loads, validates and persists :class:`Settings`."""

    def __init__(self, path: Path):
        self._path = Path(path)
        self._lock = threading.RLock()
        self._settings = Settings()
        self._listeners: list[Any] = []
        self.load()

    # ------------------------------------------------------------------
    @property
    def path(self) -> Path:
        return self._path

    def get(self) -> Settings:
        with self._lock:
            return deepcopy(self._settings)

    def update(self, **changes: Any) -> Settings:
        """Apply the given changes, persist them and notify listeners."""
        with self._lock:
            for key, value in changes.items():
                if not hasattr(self._settings, key):
                    raise KeyError(f"Unknown setting: {key}")
                setattr(self._settings, key, value)
            self._settings = self._settings.normalised()
            snapshot = deepcopy(self._settings)
        self.save()
        self._notify(snapshot)
        return snapshot

    def add_listener(self, callback) -> None:
        """``callback(new_settings)`` runs after every persisted change."""
        self._listeners.append(callback)

    def reset(self) -> Settings:
        """Restore every preference to its default and notify listeners.

        Used by "Delete all data" — the dialog promises that settings are
        removed too, not just history and snippets.
        """
        with self._lock:
            self._settings = Settings().normalised()
            snapshot = deepcopy(self._settings)
        self.save()
        self._notify(snapshot)
        return snapshot

    def _notify(self, settings: Settings) -> None:
        for callback in list(self._listeners):
            try:
                callback(settings)
            except Exception:  # noqa: BLE001 - listeners must not break settings
                log.exception("Settings listener failed")

    # ------------------------------------------------------------------
    def load(self) -> None:
        with self._lock:
            if not self._path.exists():
                self._settings = Settings().normalised()
                return
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    # e.g. "null", a JSON array or a bare number: valid JSON,
                    # but not a settings object (raw.items() would raise).
                    raise TypeError(f"settings root is {type(raw).__name__}, not an object")
                known = {f for f in Settings.__dataclass_fields__}
                data = {k: v for k, v in raw.items() if k in known}
                self._settings = Settings(**data).normalised()
            except (ValueError, TypeError, OSError) as exc:
                log.warning("Settings file unreadable (%s); using defaults", type(exc).__name__)
                self._settings = Settings().normalised()
                self._quarantine_corrupt_file()
                self.save()

    def save(self) -> None:
        with self._lock:
            payload = asdict(self._settings.normalised())
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self._path.with_suffix(".json.tmp")
                tmp.write_text(
                    json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                tmp.replace(self._path)
            except OSError as exc:
                log.warning("Could not persist settings (%s)", type(exc).__name__)

    def _quarantine_corrupt_file(self) -> None:
        try:
            backup = self._path.with_suffix(".json.corrupt")
            if backup.exists():
                backup.unlink()
            self._path.replace(backup)
            log.info("Corrupt settings file moved aside for inspection")
        except OSError:
            pass
