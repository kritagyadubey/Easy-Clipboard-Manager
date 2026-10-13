"""Filesystem locations used by the application.

All user data lives in a single per-user folder under ``%LOCALAPPDATA%``
so that privacy documentation, backups and uninstallation stay simple.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "EasyClipboardManager"

DB_FILENAME = "history.db"
SETTINGS_FILENAME = "settings.json"
LOG_FILENAME = "app.log"


def is_frozen() -> bool:
    """Return True when running from a packaged executable."""
    return bool(getattr(sys, "frozen", False))


def data_dir() -> Path:
    """Return the per-user data directory, creating it if needed."""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    path = Path(base) / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / DB_FILENAME


def settings_path() -> Path:
    return data_dir() / SETTINGS_FILENAME


def log_path() -> Path:
    return data_dir() / LOG_FILENAME


def default_export_dir() -> Path:
    docs = Path.home() / "Documents"
    return docs if docs.exists() else data_dir()


def executable_path() -> str:
    """Path used for Start-with-Windows registration."""
    if is_frozen():
        return sys.executable
    return sys.executable
