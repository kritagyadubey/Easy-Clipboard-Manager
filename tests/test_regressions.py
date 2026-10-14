"""Regression tests for the 1.1.0 bug-fix pass.

Every test here pins down a defect found during the upgrade review and fixed
in the same release, so the fixes cannot silently regress.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
import uuid
from pathlib import Path

import pytest

from easy_clipboard.models import ClipItem
from easy_clipboard.settings import Settings, SettingsStore
from easy_clipboard.storage import Database, DatabaseError
from easy_clipboard.windows.hotkey import (
    GlobalHotkey,
    HotkeyError,
    format_hotkey,
    parse_hotkey,
)
from easy_clipboard.windows import single_instance


# ----------------------------------------------------------------------
# Helpers / fixtures (mirrors the composition root used by test_ui_smoke)
# ----------------------------------------------------------------------
def _wait(ms: int) -> None:
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


@pytest.fixture()
def window(qapp, settings_store, history, monkeypatch):
    from easy_clipboard.ui.main_window import MainWindow

    copied: list[str] = []
    monkeypatch.setattr(
        "easy_clipboard.ui.main_window.write_to_system_clipboard",
        lambda text: copied.append(text) or True,
    )
    win = MainWindow(settings_store, history)
    settings_store.add_listener(win.apply_settings)
    win._copied_log = copied  # type: ignore[attr-defined]
    yield win
    win.close()
    win.deleteLater()
    _wait(20)


def _seed(history, texts):
    items = []
    for text in texts:
        item = history.capture(text)
        assert item is not None
        items.append(item)
    return items


# ----------------------------------------------------------------------
# Settings: corrupt files and loose types must not crash the app
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "payload",
    ["[1, 2, 3]", '"just a string"', "42", "null", "true"],
)
def test_non_object_json_settings_recover(settings_path: Path, payload: str):
    """A valid-JSON-but-not-an-object settings file used to raise
    AttributeError (raw.items()) during startup."""
    settings_path.write_text(payload, encoding="utf-8")
    store = SettingsStore(settings_path)
    assert store.get() == Settings()
    assert settings_path.with_suffix(".json.corrupt").exists()
    json.loads(settings_path.read_text(encoding="utf-8"))  # fresh valid file


def test_string_booleans_and_stray_types_are_coerced(settings_path: Path):
    """bool("false") is True — hand-edited values must be parsed, not cast."""
    settings_path.write_text(
        json.dumps(
            {
                "minimize_to_tray": "false",
                "monitoring_enabled": "0",
                "launch_at_startup": "yes",
                "start_minimized": "off",
                "window_geometry": 12345,
                "last_section": 7,
            }
        ),
        encoding="utf-8",
    )
    s = SettingsStore(settings_path).get()
    assert s.minimize_to_tray is False
    assert s.monitoring_enabled is False
    assert s.launch_at_startup is True
    assert s.start_minimized is False
    assert s.window_geometry == ""  # _restore_geometry() calls .encode()
    assert s.last_section == "all"


def test_reset_restores_defaults_persists_and_notifies(settings_store):
    settings_store.update(
        theme="light",
        max_items=99,
        launch_at_startup=True,
        excluded_apps=["x.exe"],
    )
    seen: list[str] = []
    settings_store.add_listener(lambda s: seen.append(s.theme))

    result = settings_store.reset()

    assert result == Settings()
    assert settings_store.get() == Settings()
    assert seen == ["dark"]
    assert SettingsStore(settings_store.path).get() == Settings()


# ----------------------------------------------------------------------
# Storage: an unusable data folder is a DatabaseError, not a crash
# ----------------------------------------------------------------------
def test_database_open_oserror_becomes_database_error(tmp_path: Path):
    """mkdir() raises a real OSError (PermissionError, FileExistsError…)
    which used to escape _open() uncaught."""
    blocker = tmp_path / "not_a_directory"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(DatabaseError):
        Database(blocker / "history.db")


# ----------------------------------------------------------------------
# Hotkeys: Qt-style key names, display round-trip, clear errors
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "combo,keycode,display",
    [
        ("Ctrl+Del", 0x2E, "Ctrl+Del"),
        ("Ctrl+PgUp", 0x21, "Ctrl+PgUp"),
        ("Ctrl+PgDn", 0x22, "Ctrl+PgDown"),
        ("Ctrl+Ins", 0x2D, "Ctrl+Ins"),
        ("Ctrl+Esc", 0x1B, "Ctrl+Esc"),
        ("Ctrl+Enter", 0x0D, "Ctrl+Enter"),
        ("Ctrl+Backspace", 0x08, "Ctrl+Backspace"),
        ("Ctrl+Up", 0x26, "Ctrl+Up"),
    ],
)
def test_qt_style_key_aliases_parse_and_format(combo, keycode, display):
    _modifiers, key = parse_hotkey(combo)
    assert key == keycode
    assert format_hotkey(combo) == display
    # Formatting is idempotent: showing a shown combo changes nothing.
    assert format_hotkey(display) == display


def test_modifier_in_key_position_has_clear_error():
    with pytest.raises(HotkeyError, match="modifier"):
        parse_hotkey("Ctrl+Shift")
    with pytest.raises(HotkeyError, match="modifier"):
        parse_hotkey("Shift")
    with pytest.raises(HotkeyError, match="modifier"):
        parse_hotkey("Ctrl+Alt")


def test_failed_registration_remembers_requested_combo(qapp):
    """After a refused registration the requested combo must stick, or every
    later settings change would retry (and re-notify) the failure."""
    hotkey = GlobalHotkey()

    class RefusingUser32:
        def RegisterHotKey(self, *_args):  # noqa: N802
            return 0

        def UnregisterHotKey(self, *_args):  # noqa: N802
            return 1

    try:
        hotkey._user32 = RefusingUser32()
        assert hotkey.register("Ctrl+Shift+V") is False
        assert hotkey.is_registered is False
        assert hotkey.combo == "Ctrl+Shift+V"

        # An unparseable combo is rejected without clobbering the memory.
        assert hotkey.register("not a shortcut") is False
        assert hotkey.combo == "Ctrl+Shift+V"
    finally:
        hotkey.shutdown()


# ----------------------------------------------------------------------
# Single instance: the ERROR_ALREADY_EXISTS detection actually works
# ----------------------------------------------------------------------
def test_second_instance_is_rejected_and_can_notify(monkeypatch):
    suffix = uuid.uuid4().hex[:8]
    monkeypatch.setattr(single_instance, "_MUTEX_NAME", f"Local\\ECMTest_{suffix}")
    monkeypatch.setattr(single_instance, "_SHOW_EVENT", f"Local\\ECMTestShow_{suffix}")

    first = single_instance.SingleInstance()
    assert first.acquire() is True  # ctypes last-error handling works
    try:
        second = single_instance.SingleInstance()
        assert second.acquire() is False  # duplicate launch is refused
        assert second.notify_primary() is True  # and can ask us to show
        second.release()
    finally:
        first.release()


# ----------------------------------------------------------------------
# MainWindow: self-writes, toast sizing, close behaviour, data reset
# ----------------------------------------------------------------------
def test_copy_from_history_tells_monitor_to_ignore_our_write(
    window, history, qapp, monkeypatch
):
    class FakeMonitor:
        def __init__(self):
            self.ignored: list[str] = []

        def ignore_next(self, text: str) -> None:
            self.ignored.append(text)

    fake = FakeMonitor()
    monkeypatch.setattr(qapp, "clipboard_monitor", fake, raising=False)

    item = _seed(history, ["copy me"])[0]
    window.copy_item(window._history.get(item.id))
    assert window._copied_log == ["copy me"]
    assert fake.ignored == ["copy me"]

    snippet = history.create_snippet("title", "snippet body")
    window.copy_snippet(snippet)
    assert fake.ignored == ["copy me", "snippet body"]


def test_toast_truncates_long_messages_but_not_short_ones(window):
    window.show_toast("Copied to clipboard")
    assert window._toast._message.text() == "Copied to clipboard"

    window.show_toast("x" * 5000)
    text = window._toast._message.text()
    assert len(text) <= 160
    assert text.endswith("…")


def test_close_event_quits_without_a_tray_even_when_minimize_is_on(
    qapp, window, settings_store, monkeypatch
):
    from PySide6.QtGui import QCloseEvent

    settings_store.update(minimize_to_tray=True)
    quit_calls: list[int] = []
    monkeypatch.setattr(
        type(qapp), "quit", staticmethod(lambda *a: quit_calls.append(1))
    )

    # With a tray, close hides to the tray (historical behaviour).
    monkeypatch.setattr(qapp, "tray_available", True, raising=False)
    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted()
    assert quit_calls == []

    # Without a tray, hiding would make the app unreachable: close must quit.
    monkeypatch.setattr(qapp, "tray_available", False, raising=False)
    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted()
    assert quit_calls == [1]


def test_clear_all_data_resets_settings_and_startup_entry(
    window, settings_store, history, monkeypatch
):
    from PySide6.QtWidgets import QMessageBox
    from easy_clipboard.ui import main_window as main_window_mod

    _seed(history, ["secret"])
    history.create_snippet("keep?", "body")
    settings_store.update(
        theme="light",
        monitoring_enabled=False,
        launch_at_startup=True,
        max_items=200,
    )

    startup_calls: list[bool] = []
    monkeypatch.setattr(
        main_window_mod.autostart,
        "set_enabled",
        lambda enabled: startup_calls.append(enabled) or True,
    )
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )

    window.clear_all_data()

    # The dialog promises history, snippets AND settings are removed.
    assert window._history.count("all") == 0
    assert window._history.snippets() == []
    assert settings_store.get() == Settings()
    assert startup_calls == [False]


def test_import_applies_size_limits(window, settings_store, monkeypatch, tmp_path):
    from easy_clipboard.ui import main_window as main_window_mod
    from easy_clipboard.portability import export_json

    settings_store.update(max_items=25)  # the minimum allowed limit
    items = [ClipItem(content=f"imported entry {index}") for index in range(40)]
    export_path = tmp_path / "export.json"
    export_json(items, [], export_path)

    monkeypatch.setattr(
        main_window_mod.QFileDialog,
        "getOpenFileName",
        staticmethod(lambda *a, **k: (str(export_path), "JSON")),
    )
    window.import_data()

    assert window._history.count("all") <= 25
    assert window._history_view._count_label.text()  # view refreshed


# ----------------------------------------------------------------------
# Views: stale selection mirrors and honest counts
# ----------------------------------------------------------------------
def test_history_selection_is_dropped_when_not_kept(window, history):
    first, second = _seed(history, ["first", "second"])
    window.refresh_all()
    window._history_view.set_items([first, second])
    window._history_view.select_item(first.id)
    assert window._history_view.selected_id() == first.id

    # keep_selection=False (e.g. after a delete) must clear the mirror so a
    # removed id cannot linger and be reselected later.
    window._history_view.set_items([second], keep_selection=False)
    assert window._history_view.selected_id() is None


def test_result_count_reports_total_when_list_is_truncated(window):
    view = window._history_view
    view.set_result_count(1000, 1500, False)  # capped list, not searching
    assert "of 1,500" in view._count_label.text()

    view.set_result_count(5, 5, False)  # complete list: no "of"
    assert "of" not in view._count_label.text()

    view.set_result_count(3, 10, True)  # search narrowed the results
    assert "3 matches of 10" == view._count_label.text()


def test_snippets_count_reports_total_when_searching(window, history):
    history.create_snippet("one", "a")
    history.create_snippet("two", "b")
    window.refresh_all()
    window._snippets_view._search.setText("one")
    window.refresh_snippets(keep_selection=False)
    assert "1 snippet of 2" == window._snippets_view._count_label.text()


def test_preview_text_is_capped_for_huge_pastes():
    item = ClipItem(content="y" * 500_000)
    preview = item.preview_text
    assert len(preview) <= 1001
    assert preview.endswith("…")
    # Short entries keep their exact collapsed preview.
    assert ClipItem(content="a  b\tc").preview_text == "a b c"


# ----------------------------------------------------------------------
# Application glue: thread marshalling and the crash dialog
# ----------------------------------------------------------------------
def test_tray_controller_create_builds_a_working_icon(qapp, monkeypatch):
    """QSystemTrayIcon(APP_NAME, self) raised TypeError — a bare string is
    not a valid icon — which crashed the app on every real launch."""
    from PySide6.QtWidgets import QSystemTrayIcon
    from easy_clipboard.ui.tray import TrayController

    monkeypatch.setattr(
        QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True)
    )
    controller = TrayController()
    try:
        assert controller.create() is True
        assert controller.available is True
        assert controller._tray is not None
        assert controller._tray.toolTip() != ""
        assert controller._menu is not None
    finally:
        if controller._tray is not None:
            controller._tray.hide()
            controller._tray.deleteLater()
        if controller._menu is not None:
            controller._menu.deleteLater()
        _wait(20)


def test_show_bridge_marshals_requests_to_the_gui_thread(qapp):
    from PySide6.QtCore import QObject
    from easy_clipboard.app import _ShowBridge

    class Receiver(QObject):
        def __init__(self):
            super().__init__()
            self.calls: list[int] = []

        def on_requested(self) -> None:
            self.calls.append(threading.get_ident())

    bridge = _ShowBridge()
    receiver = Receiver()
    bridge.requested.connect(receiver.on_requested)

    # The single-instance listener lives in a plain Python thread; a
    # QTimer.singleShot posted from there never fires, but a signal does.
    worker = threading.Thread(target=bridge.requested.emit)
    worker.start()
    worker.join()
    _wait(50)

    assert receiver.calls == [threading.get_ident()]


def test_unhandled_exception_logs_and_shows_one_dialog(qapp, caplog, monkeypatch):
    import easy_clipboard.app as app_mod

    dialogs: list[tuple] = []
    monkeypatch.setattr(
        app_mod.QMessageBox,
        "critical",
        staticmethod(lambda *args, **kwargs: dialogs.append(args)),
    )
    original_hook = sys.excepthook
    sys.excepthook = lambda *args: None  # keep pytest's hook out of the test
    try:
        with caplog.at_level(logging.ERROR, logger="easy_clipboard"):
            app_mod._install_excepthook()
            error = RuntimeError("simulated failure")
            sys.excepthook(RuntimeError, error, error.__traceback__)
            sys.excepthook(RuntimeError, error, error.__traceback__)
    finally:
        sys.excepthook = original_hook

    assert len(dialogs) == 1  # friendly dialog shown exactly once
    assert "Unhandled exception" in caplog.text
    assert "simulated failure" in caplog.text
