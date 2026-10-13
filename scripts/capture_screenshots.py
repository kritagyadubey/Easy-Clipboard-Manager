#!/usr/bin/env python3
"""Capture real screenshots of the running application for the README.

The demo runs against an isolated temporary data directory and seeds clearly
fictional sample content, so no real clipboard data and no user settings are
ever touched.

Usage:  python scripts/capture_screenshots.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

import easy_clipboard.paths as paths  # noqa: E402
import easy_clipboard.ui.theme as theme  # noqa: E402

OUT_DIR = ROOT / "docs" / "screenshots"

SAMPLE_ITEMS = [
    ("https://github.com/kritagyadubey/Easy-Clipboard-Manager", "chrome.exe"),
    ("git rebase -i HEAD~3 --exec 'npm test'", "Windows Terminal"),
    (
        "def normalize(text: str) -> str:\n"
        '    """Collapse whitespace and trim."""\n'
        '    return " ".join(text.split())',
        "Code.exe",
    ),
    (
        '{"repo": "Easy-Clipboard-Manager", "language": "Python", "stars": 0}',
        "Code.exe",
    ),
    (
        "Hi Priya,\n\nThanks for the review notes — I've pushed the fixes for the "
        "search ranking issue and added tests for the retention rules.\n\n"
        "Best regards,\nKrita",
        "outlook.exe",
    ),
    ("kritagyadubey07@gmail.com", "chrome.exe"),
    ("SELECT id, content FROM items ORDER BY last_copied_at DESC LIMIT 50;", "DBeaver.exe"),
    ("The quick brown fox jumps over the lazy dog.", "notepad.exe"),
    ("192.168.1.104", "cmd.exe"),
    (
        "Meeting notes — 12 Oct\n- Ship clipboard history this week\n"
        "- Add retention settings\n- Write README screenshots",
        "notepad.exe",
    ),
]


def seed(service, database) -> None:
    for offset, (text, source) in enumerate(SAMPLE_ITEMS):
        item = service.capture(text, source)
        if item is None:
            continue
        # Stagger timestamps so relative times look natural.
        database.set_item_timestamps(
            item.id, time.time() - offset * 137, time.time() - offset * 137
        )
    first = service.query(limit=10)
    if len(first) >= 2:
        service.set_favorite(first[1].id, True)
    if len(first) >= 3:
        service.set_pinned(first[2].id, True)
    if len(first) >= 4:
        service.set_favorite(first[4].id, True)

    service.create_snippet(
        "Git cleanup",
        "git fetch --prune\ngit rebase origin/main\ngit push --force-with-lease",
        "Safe cleanup for a feature branch",
        ["git", "command"],
    )
    service.create_snippet(
        "Email greeting",
        "Hi there,\n\nThanks for reaching out! I'll get back to you within 24 hours.",
        "Standard reply template",
        ["email", "template"],
    )
    service.create_snippet(
        "Python venv",
        "python -m venv .venv\n.venv\\Scripts\\activate\npip install -r requirements.txt",
        "",
        ["python", "setup"],
    )


def grab(widget, name: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pixmap = widget.grab()
    target = OUT_DIR / name
    pixmap.save(str(target))
    print("saved", target)


def settle(app, ms: int = 200) -> None:
    """Run the event loop long enough for debounce timers to fire."""
    deadline = time.time() + ms / 1000.0
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix="easy-clipboard-demo-"))

    # Point the app at the sandbox before Qt objects are created.
    paths.data_dir = lambda: temp  # type: ignore[assignment]

    app = QApplication(sys.argv[:1])
    app.theme_name = "dark"
    pal = theme.palette("dark")
    app.setStyleSheet(theme.build_stylesheet(pal, "comfortable"))
    app.setWindowIcon(theme.render_logo(64, pal.accent))

    from easy_clipboard.history import HistoryService
    from easy_clipboard.settings import SettingsStore
    from easy_clipboard.storage import Database
    from easy_clipboard.ui.main_window import MainWindow

    store = SettingsStore(temp / "settings.json")
    database = Database(temp / "history.db")
    service = HistoryService(database, store)
    seed(service, database)

    window = MainWindow(store, service)
    window.resize(1280, 800)
    window.show()
    app.processEvents()

    window.refresh_all()
    app.processEvents()

    # 1. Main window with a selection ------------------------------------
    window._history_view._list.setCurrentIndex(
        window._history_view._model.index(0, 0)
    )
    window._history_view._emit_focused(0)
    settle(app, 300)
    grab(window, "main-dark.png")

    # 2. Search results ----------------------------------------------------
    window._history_view._search.setText("git")
    settle(app, 350)  # the search box debounces for 140 ms
    grab(window, "search-dark.png")
    window._history_view._search.setText("")
    settle(app, 350)

    # 3. Snippets page ------------------------------------------------------
    window.show_section("snippets")
    window._snippets_view._list.setCurrentIndex(
        window._snippets_view._model.index(0, 0)
    )
    window._snippets_view._emit_focused(0)
    settle(app, 300)
    grab(window, "snippets-dark.png")

    # 4. Settings dialog -----------------------------------------------------
    window.show_section("all")
    window.open_settings()
    settle(app, 300)
    dialog = window._settings_dialog
    if dialog is not None:
        grab(dialog, "settings-dark.png")
        dialog._select_category("privacy")
        # The demo runs from a throwaway temp folder; show where a real
        # install keeps its data instead of the random demo path.
        dialog.show_storage_path(
            str(Path.home() / "AppData" / "Local" / "EasyClipboardManager")
        )
        settle(app, 300)
        grab(dialog, "settings-privacy-dark.png")
        dialog.reject()

    # 5. Light theme ----------------------------------------------------------
    store.update(theme="light")
    window.apply_settings(store.get())
    window._history_view._list.setCurrentIndex(
        window._history_view._model.index(0, 0)
    )
    window._history_view._emit_focused(0)
    settle(app, 400)
    grab(window, "main-light.png")

    # 6. Compact density in dark ---------------------------------------------
    store.update(theme="dark", density="compact")
    window.apply_settings(store.get())
    settle(app, 400)
    window._history_view._list.setCurrentIndex(
        window._history_view._model.index(0, 0)
    )
    window._history_view._emit_focused(0)
    settle(app, 200)
    grab(window, "main-compact-dark.png")

    window.close()
    shutil.rmtree(temp, ignore_errors=True)
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
