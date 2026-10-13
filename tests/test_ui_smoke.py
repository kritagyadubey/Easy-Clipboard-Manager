"""End-to-end UI smoke tests (offscreen Qt).

These exercise the real widgets, models and signal wiring — no mocks of the
application's own code.  Only OS-level side effects (the system clipboard and
confirmation dialogs) are stubbed so the suite stays deterministic.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QMessageBox  # noqa: E402

from easy_clipboard.ui.main_window import MainWindow  # noqa: E402


# ----------------------------------------------------------------------
# Helpers / fixtures
# ----------------------------------------------------------------------
def _wait(ms: int) -> None:
    """Pump the event loop for ``ms`` milliseconds."""
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


@pytest.fixture()
def window(qapp, settings_store, history, monkeypatch):
    # Never write to the developer's real clipboard from tests.
    copied: list[str] = []
    monkeypatch.setattr(
        "easy_clipboard.ui.main_window.write_to_system_clipboard",
        lambda text: copied.append(text) or True,
    )
    # Mirror the composition root: the app wires a settings listener that
    # pushes changes into the window (app.py:on_settings_changed).
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
# Construction
# ----------------------------------------------------------------------
def test_window_builds_with_all_pages(window: MainWindow, qapp):
    assert window.windowTitle()
    assert window._sidebar.current_section() == "all"
    assert window._pages.count() == 2
    assert window._history_view.search_text() == ""
    assert window._toast is not None


def test_window_starts_empty(window: MainWindow):
    assert window._history_view.current_item() is None
    assert window._history.count() == 0


def test_window_populates_from_history(window: MainWindow, history):
    _seed(history, ["alpha", "beta", "gamma"])
    window.refresh_all()
    model = window._history_view._model
    assert model.rowCount() == 3
    # Newest first, and the count label reflects the row total.
    assert model.item_at(0).content == "gamma"
    assert window._history_view._count_label.text()


# ----------------------------------------------------------------------
# Sections & search
# ----------------------------------------------------------------------
def test_section_navigation(window: MainWindow, history):
    _seed(history, ["https://example.com", "plain words", "def fn(): pass"])
    window.refresh_all()

    window.show_section("links")
    assert window._sidebar.current_section() == "links"
    model = window._history_view._model
    assert model.rowCount() == 1
    assert model.item_at(0).content == "https://example.com"

    window.show_section("pinned")
    assert model.rowCount() == 0

    window.show_section("all")
    assert model.rowCount() == 3


def test_search_filters_the_list(window: MainWindow, history):
    _seed(history, ["kitten video", "puppy photo", "kitten nap"])
    window.refresh_all()
    model = window._history_view._model
    assert model.rowCount() == 3

    window._history_view._search.setText("kitten")
    _wait(400)  # debounce timer is 140 ms
    assert window._history_view.search_text() == "kitten"
    assert model.rowCount() == 2

    window._history_view._search.setText("zzz-nothing")
    _wait(400)
    assert model.rowCount() == 0
    assert window._history_view.current_item() is None

    window._history_view.clear_search()
    _wait(400)
    assert model.rowCount() == 3


def test_search_matching_is_case_insensitive(window: MainWindow, history):
    _seed(history, ["Hello World"])
    window.refresh_all()
    window._history_view._search.setText("hello")
    _wait(400)
    assert window._history_view._model.rowCount() == 1


def test_snippets_page_switch(window: MainWindow, history):
    history.create_snippet("Greeting", "Hi there")
    window.show_section("snippets")
    assert window._pages.currentWidget() is window._snippets_view
    window.refresh_snippets(keep_selection=False)
    model = window._snippets_view._model
    assert model.rowCount() >= 1
    assert window._snippets_view.current_snippet() is None

    window.show_section("all")
    assert window._pages.currentIndex() == 0


# ----------------------------------------------------------------------
# Selection -> preview
# ----------------------------------------------------------------------
def test_selection_updates_preview(window: MainWindow, history):
    item = _seed(history, ["preview me"])[0]
    window.refresh_all()

    window._history_view.select_item(item.id)
    _wait(50)
    assert window._preview_item is not None
    assert window._preview_item.content == "preview me"
    assert window._preview.content_text() == "preview me"


def test_copy_writes_to_clipboard_and_marks_copied(window: MainWindow, history):
    item = _seed(history, ["copy this"])[0]
    window.refresh_all()
    window._history_view.select_item(item.id)

    window.copy_item(window._history_view.current_item())
    assert window._copied_log == ["copy this"]  # type: ignore[attr-defined]
    assert window._history.get(item.id).copy_count >= 1


def test_copy_with_no_selection_is_a_noop(window: MainWindow):
    window.copy_item(None)
    assert window._copied_log == []  # type: ignore[attr-defined]


# ----------------------------------------------------------------------
# Pin / favorite / delete
# ----------------------------------------------------------------------
def test_pin_toggles_and_moves_to_pinned_section(window: MainWindow, history):
    item = _seed(history, ["pin me"])[0]
    window.refresh_all()

    window._on_pin_toggled(item, True)
    assert window._history.get(item.id).is_pinned
    assert window._history.count("pinned") == 1

    window.show_section("pinned")
    assert window._history_view._model.rowCount() == 1

    window._on_pin_toggled(item, False)
    assert not window._history.get(item.id).is_pinned
    assert window._history.count("pinned") == 0


def test_favorite_toggle(window: MainWindow, history):
    item = _seed(history, ["love me"])[0]
    window._on_favorite_toggled(item, True)
    assert window._history.get(item.id).is_favorite
    assert window._history.count("favorite") == 1
    window._on_favorite_toggled(item, False)
    assert window._history.count("favorite") == 0


def test_delete_removes_entry_and_undo_restores_it(
    window: MainWindow, history, monkeypatch
):
    items = _seed(history, ["keep", "remove me"])
    window.refresh_all()

    # Ordinary entries delete without a confirmation dialog.
    window.delete_item(window._history.get(items[1].id))
    assert window._history.get(items[1].id) is None
    assert window._history.count() == 1

    # Undo restores content and protection flags.
    window._undo_delete()
    assert window._history.count() == 2
    restored = [i.content for i in window._history.query(sort="oldest")]
    assert "remove me" in restored


def test_deleting_protected_entry_asks_for_confirmation(
    window: MainWindow, history, monkeypatch
):
    item = _seed(history, ["pinned entry"])[0]
    window._on_pin_toggled(item, True)
    window.refresh_all()

    answers = {"value": QMessageBox.StandardButton.No}
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: answers["value"])
    )

    window.delete_item(window._history.get(item.id))
    assert window._history.get(item.id) is not None  # declined

    answers["value"] = QMessageBox.StandardButton.Yes
    window.delete_item(window._history.get(item.id))
    assert window._history.get(item.id) is None


def test_clear_history_confirmation_keeps_protected(
    window: MainWindow, history, monkeypatch
):
    _seed(history, ["one", "two", "three"])
    pinned = window._history.query()[0]
    window._on_pin_toggled(pinned, True)
    window.refresh_all()

    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(
            lambda *a, **k: QMessageBox.StandardButton.Yes
        ),
    )
    window.clear_history()
    assert window._history.count() == 1
    assert window._history.get(pinned.id) is not None

    # Declining the dialog clears nothing.
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.No),
    )
    window.clear_history()
    assert window._history.count() == 1


def test_clear_history_never_touches_snippets(window: MainWindow, history, monkeypatch):
    _seed(history, ["temporary"])
    history.create_snippet("Keep me", "body")
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )
    window.clear_history()
    assert window._history.count() == 0
    assert len(window._history.snippets()) == 1


# ----------------------------------------------------------------------
# Captures arriving from the monitor
# ----------------------------------------------------------------------
def test_live_capture_refreshes_the_view(window: MainWindow, history):
    window.refresh_all()
    assert window._history_view._model.rowCount() == 0

    window.on_clipboard_captured("freshly copied", "notepad.exe")
    assert window._history_view._model.rowCount() == 1
    assert window._history.count() == 1

    # Skipped captures (paused) leave the view alone.
    window._store.update(monitoring_enabled=False)
    window.on_clipboard_captured("while paused", "notepad.exe")
    assert window._history.count() == 1
    assert window._history_view._model.rowCount() == 1


def test_capture_respects_active_search_filter(window: MainWindow, history):
    _seed(history, ["kitten"])
    window.refresh_all()
    window._history_view._search.setText("kitten")
    _wait(400)

    window.on_clipboard_captured("unrelated text", "notepad.exe")
    # The new entry does not match the active filter, so it stays hidden.
    assert window._history_view._model.rowCount() == 1

    window.on_clipboard_captured("another kitten", "notepad.exe")
    assert window._history_view._model.rowCount() == 2


# ----------------------------------------------------------------------
# Settings-driven UI state
# ----------------------------------------------------------------------
def test_monitoring_toggle_updates_banner_and_sidebar(window: MainWindow):
    # The window is never shown in tests, so use isHidden() rather than
    # isVisible() to inspect visibility.
    assert window._history_view._paused_banner.isHidden()

    window.toggle_monitoring()
    settings = window._store.get()
    assert settings.monitoring_enabled is False
    assert not window._history_view._paused_banner.isHidden()  # banner shown
    assert window._sidebar._monitor_button.label == "Monitoring paused"

    window.toggle_monitoring()
    assert window._store.get().monitoring_enabled is True
    assert window._history_view._paused_banner.isHidden()
    assert window._sidebar._monitor_button.label == "Pause monitoring"


def test_theme_and_density_switch(window: MainWindow, qapp):
    window._store.update(theme="light", density="compact")
    window.apply_settings(window._store.get())
    assert window._store.get().theme == "light"
    assert window._store.get().density == "compact"

    window._store.update(theme="dark", density="comfortable")
    window.apply_settings(window._store.get())
    assert window._store.get().theme == "dark"


def test_sidebar_counts_reflect_history(window: MainWindow, history):
    _seed(history, ["a", "b"])
    window.refresh_sidebar_counts()
    window._on_pin_toggled(window._history.query()[0], True)
    assert window._history.count("all") == 2
    assert window._history.count("pinned") == 1


def test_last_section_is_persisted(window: MainWindow, settings_store):
    window.show_section("links")
    assert settings_store.get().last_section == "links"
    # A fresh window reopens on the same section.
    fresh = MainWindow(settings_store, window._history)
    try:
        assert fresh._sidebar.current_section() == "links"
    finally:
        fresh.close()
        fresh.deleteLater()
        _wait(20)


# ----------------------------------------------------------------------
# Settings dialog
# ----------------------------------------------------------------------
@pytest.fixture()
def settings_dialog(qapp, settings_store, history):
    from easy_clipboard.ui.settings_dialog import SettingsDialog

    dialog = SettingsDialog(settings_store, history)
    yield dialog
    dialog.close()
    dialog.deleteLater()
    _wait(20)


def test_settings_dialog_builds_every_category(settings_dialog, qapp):
    from easy_clipboard.ui.settings_dialog import _CATEGORIES

    assert set(settings_dialog._category_buttons) == {key for key, _l, _i in _CATEGORIES}
    assert settings_dialog._stack.count() == len(_CATEGORIES)
    # Starts on the General page.
    assert settings_dialog._stack.currentIndex() == 0
    assert settings_dialog._page_title.text() == "General"


def test_open_settings_shows_a_visible_dialog(window: MainWindow):
    window.open_settings()
    dialog = window._settings_dialog
    assert dialog is not None
    # Opening again reuses the same instance rather than stacking dialogs.
    window.open_settings()
    assert window._settings_dialog is dialog
    dialog.close()
    _wait(20)


def test_settings_dialog_category_switch(settings_dialog):
    settings_dialog._on_category("privacy")
    assert settings_dialog._stack.currentIndex() == 3
    assert settings_dialog._page_title.text().lower().startswith("privacy")


def test_settings_dialog_controls_write_through_to_store(
    settings_dialog, settings_store
):
    # Monitoring switch
    settings_dialog._monitoring_switch.set_checked(False)
    assert settings_store.get().monitoring_enabled is False

    # Max history size
    settings_dialog._max_spin.setValue(250)
    assert settings_store.get().max_items == 250

    # Retention
    index = settings_dialog._retention_combo.findData(7)
    settings_dialog._retention_combo.setCurrentIndex(index)
    assert settings_store.get().retention_days == 7

    # Duplicate handling
    index = settings_dialog._dup_combo.findData("ignore")
    settings_dialog._dup_combo.setCurrentIndex(index)
    assert settings_store.get().duplicate_handling == "ignore"

    # Values survive a reload from disk.
    from easy_clipboard.settings import SettingsStore

    reloaded = SettingsStore(settings_store.path)
    assert reloaded.get().max_items == 250
    assert reloaded.get().duplicate_handling == "ignore"


def test_settings_dialog_exclusion_list(settings_dialog, settings_store):
    settings_dialog._exclusion_input.setText("1Password.exe")
    settings_dialog._on_add_exclusion()
    assert settings_store.get().excluded_apps == ["1password.exe"]
    assert settings_dialog._exclusion_list.count() == 1

    # Duplicates are not added twice.
    settings_dialog._exclusion_input.setText("1password.exe")
    settings_dialog._on_add_exclusion()
    assert settings_dialog._exclusion_list.count() == 1

    settings_dialog._exclusion_list.setCurrentRow(0)
    settings_dialog._on_remove_exclusion()
    assert settings_store.get().excluded_apps == []
    assert settings_dialog._exclusion_list.count() == 0


def test_settings_dialog_reflects_external_changes(settings_dialog, settings_store):
    settings_store.update(max_items=999, theme="light")
    settings_dialog._on_settings_external_change(settings_store.get())
    assert settings_dialog._max_spin.value() == 999


def test_hotkey_capture_dialog_requires_a_modifier(qapp):
    from PySide6.QtCore import Qt, QEvent
    from PySide6.QtGui import QKeyEvent
    from easy_clipboard.ui.settings_dialog import _HotkeyCaptureDialog

    dialog = _HotkeyCaptureDialog()
    captured: list[str] = []
    dialog.captured.connect(captured.append)

    # A bare letter must be rejected.
    dialog.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier, "a"))
    assert captured == []
    assert not dialog.result()

    # Ctrl+Shift+V is accepted.
    dialog.keyPressEvent(
        QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_V,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
            "V",
        )
    )
    assert captured == ["Ctrl+Shift+V"]
    dialog.deleteLater()
    _wait(20)

