"""Shared pytest fixtures.

GUI tests run on Qt's offscreen platform so the suite works on headless
machines and CI runners as well as on a normal Windows desktop.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture()
def settings_path(data_dir: Path) -> Path:
    return data_dir / "settings.json"


@pytest.fixture()
def settings_store(settings_path: Path):
    from easy_clipboard.settings import SettingsStore

    return SettingsStore(settings_path)


@pytest.fixture()
def database(data_dir: Path):
    from easy_clipboard.storage import Database

    db = Database(data_dir / "history.db")
    yield db
    db.close()


@pytest.fixture()
def history(database, settings_store):
    from easy_clipboard.history import HistoryService

    return HistoryService(database, settings_store)


@pytest.fixture(scope="session")
def qapp():
    """Session-wide QApplication for UI tests."""
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    app.theme_name = "dark"
    yield app
