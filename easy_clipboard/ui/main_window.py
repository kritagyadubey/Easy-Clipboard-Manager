"""Main application window: sidebar, history, preview, snippets, toasts."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QByteArray, QUrl, Qt
from PySide6.QtGui import QCloseEvent, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QWidget,
)

from .. import APP_NAME
from ..clipboard import write_to_system_clipboard
from ..history import HistoryService
from ..logging_setup import get_logger
from ..models import ClipItem, Snippet
from ..paths import data_dir, default_export_dir
from ..portability import ImportError_, export_json, export_text, import_from_file
from ..settings import Settings, SettingsStore
from . import icons
from . import theme as theme_mod
from .format import count_label
from .history_view import HistoryView
from .preview_panel import PreviewPanel
from .sidebar import Sidebar
from .snippet_dialog import SnippetDialog
from .snippets_view import SnippetsView
from .widgets import Toast

log = get_logger("main-window")

# Sidebar section key -> (storage section, type filter, window title)
_SECTIONS = {
    "all": ("all", "", "All history"),
    "pinned": ("pinned", "", "Pinned"),
    "favorite": ("favorite", "", "Favorites"),
    "recent": ("recent", "", "Recent"),
    "links": ("type", "link", "Links"),
    "code": ("type", "code", "Code"),
    "text": ("type", "text,multiline", "Text"),
}


class MainWindow(QMainWindow):
    """The single application window."""

    def __init__(
        self,
        settings_store: SettingsStore,
        history: HistoryService,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._store = settings_store
        self._history = history
        self._current_section = "all"
        self._preview_item: Optional[ClipItem] = None
        self._last_deleted: Optional[ClipItem] = None
        self._settings_dialog = None
        self._applied = self._snapshot(settings_store.get())

        settings = self._store.get()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(940, 560)
        self.resize(1180, 720)

        central = QWidget(self)
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Sidebar --------------------------------------------------------
        self._sidebar = Sidebar(self)
        self._sidebar.section_selected.connect(self._on_section_selected)
        self._sidebar.settings_clicked.connect(self.open_settings)
        self._sidebar.monitoring_toggle_clicked.connect(self.toggle_monitoring)
        root.addWidget(self._sidebar)

        # Pages: history (inside a splitter with the preview) and snippets
        self._history_view = HistoryView(self)
        self._preview = PreviewPanel(self)
        self._splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(1)
        self._splitter.addWidget(self._history_view)
        self._splitter.addWidget(self._preview)
        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 2)

        self._snippets_view = SnippetsView(self)
        self._pages = QStackedWidget(self)
        self._pages.addWidget(self._splitter)
        self._pages.addWidget(self._snippets_view)
        root.addWidget(self._pages, 1)

        # Toast ----------------------------------------------------------
        self._toast = Toast(self)

        # History view wiring ---------------------------------------------
        self._history_view.search_changed.connect(self._on_history_query_changed)
        self._history_view.item_focused.connect(self._on_item_focused)
        self._history_view.item_activated.connect(self.copy_item)
        self._history_view.copy_requested.connect(self.copy_item)
        self._history_view.delete_requested.connect(self.delete_item)
        self._history_view.pin_requested.connect(self._on_pin_shortcut)
        self._history_view.clear_history_requested.connect(self.clear_history)
        self._history_view.export_requested.connect(lambda: self.export_data("all"))
        self._history_view.open_data_folder_requested.connect(self.open_data_folder)

        # Preview panel wiring ---------------------------------------------
        self._preview.copy_requested.connect(self._on_preview_copy)
        self._preview.pin_toggled.connect(self._on_pin_toggled)
        self._preview.favorite_toggled.connect(self._on_favorite_toggled)
        self._preview.save_snippet_requested.connect(self.save_snippet)
        self._preview.delete_requested.connect(self.delete_item)
        self._preview.open_link_requested.connect(self._open_link)
        self._preview.close_requested.connect(self._hide_preview)

        # Snippets view wiring ----------------------------------------------
        self._snippets_view.new_requested.connect(self.new_snippet)
        self._snippets_view.edit_requested.connect(self.edit_snippet)
        self._snippets_view.delete_requested.connect(self.delete_snippet)
        self._snippets_view.copy_requested.connect(self.copy_snippet)
        self._snippets_view.search_changed.connect(
            lambda _text: self.refresh_snippets(keep_selection=True)
        )

        # Shortcuts ----------------------------------------------------------
        self._install_shortcuts()

        # Apply persisted state ---------------------------------------------
        self._apply_theme()
        self._apply_density(settings.density)
        self._sidebar.set_monitoring(settings.monitoring_enabled)
        self._history_view.set_paused_banner(not settings.monitoring_enabled)
        if settings.last_section in _SECTIONS:
            self._current_section = settings.last_section
        self._sidebar.select(self._current_section)
        self.refresh_all()
        self._restore_geometry(settings.window_geometry)

    # ==================================================================
    # Refresh / query plumbing
    # ==================================================================
    @staticmethod
    def _snapshot(settings: Settings) -> tuple:
        return (
            settings.theme,
            settings.density,
            settings.monitoring_enabled,
            settings.max_items,
            settings.retention_days,
            settings.duplicate_handling,
            tuple(settings.excluded_apps),
        )

    def refresh_all(self) -> None:
        self.refresh_history(keep_selection=False)
        self.refresh_snippets(keep_selection=False)
        self.refresh_sidebar_counts()

    def refresh_history(self, keep_selection: bool = True) -> None:
        section, type_filter, title = _SECTIONS.get(
            self._current_section, _SECTIONS["all"]
        )
        search = self._history_view.search_text()
        sort = self._history_view.sort_key
        items = self._history.query(
            section=section,
            search=search,
            content_type=type_filter,
            sort=sort,
            limit=1000,
        )
        total = self._history.count(section, search, type_filter)
        self._history_view.set_section_title(title)
        self._history_view.set_result_count(len(items), total, bool(search))
        self._history_view.set_items(items, keep_selection=keep_selection)
        if keep_selection:
            selected = self._history_view.selected_id()
            if selected is not None:
                self._history_view.select_item(selected)

    def refresh_snippets(self, keep_selection: bool = True) -> None:
        self._snippets_view.set_snippets(
            self._history.snippets(self._snippets_view.search_text()),
            keep_selection=keep_selection,
        )

    def refresh_sidebar_counts(self) -> None:
        counts = {
            "all": self._history.count("all"),
            "pinned": self._history.count("pinned"),
            "favorite": self._history.count("favorite"),
            "recent": self._history.count("recent"),
            "links": self._history.count("type", "", "link"),
            "code": self._history.count("type", "", "code"),
            "text": self._history.count("type", "", "text,multiline"),
            "snippets": len(self._history.snippets()),
        }
        self._sidebar.set_counts(counts)
        self._sidebar.set_stats(
            self._history.stats(), self._history.settings.retention_days
        )

    # ==================================================================
    # Sections
    # ==================================================================
    def _on_section_selected(self, key: str) -> None:
        self._current_section = key
        if key == "snippets":
            self._pages.setCurrentWidget(self._snippets_view)
        else:
            self._pages.setCurrentIndex(0)
            self.refresh_history(keep_selection=False)
            self._history_view.scroll_to_top()
        try:
            self._store.update(last_section=key)
        except Exception:  # noqa: BLE001 - never block navigation on persistence
            log.exception("Could not persist last section")

    def show_section(self, key: str) -> None:
        self._sidebar.select(key)
        self._on_section_selected(key)

    def _on_history_query_changed(self, _text: str) -> None:
        self.refresh_history(keep_selection=False)

    # ==================================================================
    # Capture handling (called by the clipboard monitor)
    # ==================================================================
    def on_clipboard_captured(self, text: str, source_app: str) -> None:
        item = self._history.capture(text, source_app)
        if item is None:
            return
        self.refresh_sidebar_counts()
        if self._current_section != "snippets":
            search = self._history_view.search_text()
            if not search or search.lower() in text.lower():
                self.refresh_history(keep_selection=True)

    def on_monitor_error(self, message: str) -> None:
        self.show_toast(message, icon_name="alert", icon_color="#e5615a")

    # ==================================================================
    # Copy / pin / favorite / delete
    # ==================================================================
    def copy_item(self, item: Optional[ClipItem]) -> None:
        if item is None:
            return
        if not write_to_system_clipboard(item.content):
            self.show_toast(
                "The clipboard is busy — please try again.",
                icon_name="alert",
                icon_color="#e5615a",
            )
            return
        if item.id is not None:
            self._history.mark_copied(item.id)
        self.refresh_history(keep_selection=True)
        self.refresh_sidebar_counts()
        self.show_toast("Copied to clipboard", icon_name="copy")

    def _on_preview_copy(self, payload) -> None:
        if isinstance(payload, Snippet):
            self.copy_snippet(payload)
        else:
            self.copy_item(payload)

    def copy_snippet(self, snippet: Snippet) -> None:
        if not write_to_system_clipboard(snippet.content):
            self.show_toast(
                "The clipboard is busy — please try again.",
                icon_name="alert",
                icon_color="#e5615a",
            )
            return
        self.show_toast(f"Copied “{snippet.title}” to clipboard", icon_name="copy")

    def _on_pin_shortcut(self, item: ClipItem) -> None:
        self._on_pin_toggled(item, not item.is_pinned)

    def _on_pin_toggled(self, item: ClipItem, pinned: bool) -> None:
        if item.id is None:
            return
        self._history.set_pinned(item.id, pinned)
        item.is_pinned = pinned
        self.refresh_history(keep_selection=True)
        self.refresh_sidebar_counts()
        if self._preview_item is not None and self._preview_item.id == item.id:
            self._preview.set_item(item)
        self.show_toast("Pinned" if pinned else "Unpinned", icon_name="pin",
                        icon_color="#e0a63c")

    def _on_favorite_toggled(self, item: ClipItem, favorite: bool) -> None:
        if item.id is None:
            return
        self._history.set_favorite(item.id, favorite)
        item.is_favorite = favorite
        self.refresh_history(keep_selection=True)
        self.refresh_sidebar_counts()
        if self._preview_item is not None and self._preview_item.id == item.id:
            self._preview.set_item(item)
        self.show_toast(
            "Added to favorites" if favorite else "Removed from favorites",
            icon_name="star",
            icon_color="#ef7d9c",
        )

    def delete_item(self, item: Optional[ClipItem]) -> None:
        if item is None or item.id is None:
            return
        if item.is_protected:
            answer = QMessageBox.question(
                self,
                "Delete protected entry",
                "This entry is pinned or marked as a favorite.\n\n"
                "Delete it permanently?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._history.delete(item.id)
        self._last_deleted = item
        if self._preview_item is not None and self._preview_item.id == item.id:
            self._preview.clear()
            self._preview_item = None
        self.refresh_history(keep_selection=False)
        self.refresh_sidebar_counts()
        self.show_toast(
            "Entry deleted",
            icon_name="trash",
            icon_color="#e5615a",
            duration_ms=5000,
            action_label="Undo",
            action=self._undo_delete,
        )

    def _undo_delete(self) -> None:
        item = self._last_deleted
        self._last_deleted = None
        if item is None:
            return
        restored = self._history.db.add_item(
            ClipItem(
                content=item.content,
                content_type=item.content_type,
                created_at=item.created_at,
                last_copied_at=item.last_copied_at,
                is_pinned=item.is_pinned,
                is_favorite=item.is_favorite,
                source_app=item.source_app,
                copy_count=max(1, item.copy_count - 1),
            )
        )
        self.refresh_history(keep_selection=False)
        self.refresh_sidebar_counts()
        self._history_view.select_item(restored.id)
        self.show_toast("Entry restored", icon_name="check")

    def clear_history(self) -> None:
        protected = self._history.count("pinned") + self._history.count("favorite")
        note = ""
        if protected:
            note = (
                f"\n\n{count_label(protected)} that are pinned or favorite "
                "will be kept."
            )
        answer = QMessageBox.question(
            self,
            "Clear clipboard history",
            "Delete all ordinary clipboard history?" + note +
            "\n\nSaved snippets are not affected.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        removed = self._history.clear_history(keep_protected=True)
        self._preview.clear()
        self._preview_item = None
        self.refresh_all()
        self.show_toast(
            f"Cleared {count_label(removed)}",
            icon_name="trash",
            icon_color="#e5615a",
        )

    def clear_all_data(self) -> None:
        answer = QMessageBox.warning(
            self,
            "Delete all data",
            "This permanently deletes ALL clipboard history and saved snippets.\n\n"
            "This cannot be undone. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._history.clear_history(keep_protected=False)
        for snippet in self._history.snippets():
            if snippet.id is not None:
                self._history.delete_snippet(snippet.id)
        self._preview.clear()
        self._preview_item = None
        self.refresh_all()
        self.show_toast(
            "All clipboard data deleted", icon_name="shield", icon_color="#e5615a"
        )

    # ==================================================================
    # Snippets
    # ==================================================================
    def save_snippet(self, item: ClipItem) -> None:
        """Turn a clipboard entry into a named saved snippet."""
        dialog = SnippetDialog(initial_text=item.content, parent=self)
        dialog.snippet_saved.connect(self._create_snippet_from_dialog)
        dialog.exec()

    def new_snippet(self) -> None:
        dialog = SnippetDialog(parent=self)
        dialog.snippet_saved.connect(self._create_snippet_from_dialog)
        dialog.exec()

    def _create_snippet_from_dialog(self, data: dict) -> None:
        snippet = self._history.create_snippet(
            data["title"],
            data["content"],
            data.get("description", ""),
            data.get("tags", []),
        )
        self.refresh_snippets(keep_selection=False)
        self.refresh_sidebar_counts()
        self._snippets_view.select_snippet(snippet.id)
        self.show_toast(f"Snippet “{snippet.title}” saved", icon_name="bookmark")

    def edit_snippet(self, snippet: Snippet) -> None:
        dialog = SnippetDialog(snippet=snippet, parent=self)
        edited: dict = {}
        dialog.snippet_saved.connect(lambda data: edited.update(data))
        if dialog.exec() and edited:
            snippet.title = edited["title"]
            snippet.content = edited["content"]
            snippet.description = edited["description"]
            snippet.tags = edited["tags"]
            self._history.update_snippet(snippet)
            self.refresh_snippets(keep_selection=True)
            self.show_toast("Snippet updated", icon_name="check")

    def delete_snippet(self, snippet: Snippet) -> None:
        answer = QMessageBox.question(
            self,
            "Delete snippet",
            f"Delete the snippet “{snippet.title}” permanently?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if snippet.id is not None:
            self._history.delete_snippet(snippet.id)
        self.refresh_snippets(keep_selection=False)
        self.refresh_sidebar_counts()
        self.show_toast(
            "Snippet deleted", icon_name="trash", icon_color="#e5615a"
        )

    # ==================================================================
    # Preview
    # ==================================================================
    def _on_item_focused(self, item: Optional[ClipItem]) -> None:
        self._preview_item = item
        if item is None:
            self._preview.clear()
        else:
            self._preview.set_item(item)

    def _hide_preview(self) -> None:
        self._preview.hide()

    def _open_link(self, item: ClipItem) -> None:
        text = item.content.strip()
        if not text.startswith(("http://", "https://")):
            text = "https://" + text
        QDesktopServices.openUrl(QUrl(text))

    # ==================================================================
    # Import / export
    # ==================================================================
    def export_data(self, kind: str = "all") -> None:
        default_dir = default_export_dir()
        include_history = kind in ("all", "history")
        include_snippets = kind in ("all", "snippets")
        suggested = (
            "easy-clipboard-snippets.json" if kind == "snippets"
            else "easy-clipboard-export.json"
        )
        path, selected = QFileDialog.getSaveFileName(
            self,
            "Export clipboard data",
            str(default_dir / suggested),
            "JSON export (*.json);;Plain text (*.txt)",
        )
        if not path:
            return

        target = Path(path)
        try:
            items = self._history.db.all_items() if include_history else []
            snippets = self._history.snippets() if include_snippets else []
            if target.suffix.lower() == ".txt" or "Plain text" in (selected or ""):
                if not target.suffix:
                    target = target.with_suffix(".txt")
                total = export_text(items, target)
            else:
                if not target.suffix:
                    target = target.with_suffix(".json")
                total = export_json(items, snippets, target)
        except OSError as exc:
            QMessageBox.warning(
                self, "Export failed", f"Could not write the export file:\n{exc}"
            )
            return
        self.show_toast(
            f"Exported {count_label(total)} to {target.name}", icon_name="upload"
        )

    def import_data(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(
            self,
            "Import from file",
            str(default_export_dir()),
            "Supported files (*.json *.txt);;JSON (*.json);;Plain text (*.txt)",
        )
        if not path:
            return
        try:
            result = import_from_file(path, self._history.db)
        except ImportError_ as exc:
            QMessageBox.warning(self, "Import failed", str(exc))
            return
        except OSError as exc:
            QMessageBox.warning(self, "Import failed", f"Could not read file:\n{exc}")
            return
        self.refresh_all()
        self.show_toast(
            f"Import finished: {result.summary}",
            icon_name="download",
            duration_ms=5000,
        )

    def open_data_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_dir())))

    # ==================================================================
    # Monitoring / settings
    # ==================================================================
    def toggle_monitoring(self) -> None:
        settings = self._store.get()
        self._store.update(monitoring_enabled=not settings.monitoring_enabled)

    def apply_settings(self, settings: Settings) -> None:
        """React to persisted settings changes (invoked by the app)."""
        previous, self._applied = self._applied, self._snapshot(settings)
        if previous[0] != settings.theme or previous[1] != settings.density:
            self._apply_theme()
            self._apply_density(settings.density)
        if previous[2] != settings.monitoring_enabled:
            self._sidebar.set_monitoring(settings.monitoring_enabled)
            self._history_view.set_paused_banner(not settings.monitoring_enabled)
        if previous[3:] != (
            settings.max_items,
            settings.retention_days,
            settings.duplicate_handling,
            tuple(settings.excluded_apps),
        ):
            self._history.trim_history()
            self.refresh_sidebar_counts()
            self.refresh_history(keep_selection=True)

    def _apply_theme(self) -> None:
        app = QApplication.instance()
        settings = self._store.get()
        resolved = theme_mod.resolve_theme(settings.theme)
        if app is not None:
            app.theme_name = resolved
            pal = theme_mod.palette(resolved)
            app.setStyleSheet(theme_mod.build_stylesheet(pal, settings.density))
            app.setWindowIcon(theme_mod.render_logo(64, pal.accent))
            icons.clear_cache()
        self._sidebar.apply_theme()
        self._history_view.refresh_icons()
        self._preview.refresh_theme()
        self.update()

    def _apply_density(self, density: str) -> None:
        self._history_view.set_density(density)
        self._snippets_view.set_density(density)

    def open_settings(self) -> None:
        if self._settings_dialog is None:
            from .settings_dialog import SettingsDialog

            self._settings_dialog = SettingsDialog(self._store, self._history, self)
            self._settings_dialog.clear_history_requested.connect(self.clear_history)
            self._settings_dialog.clear_all_requested.connect(self.clear_all_data)
            self._settings_dialog.export_requested.connect(self.export_data)
            self._settings_dialog.import_requested.connect(self.import_data)
            self._settings_dialog.open_data_folder_requested.connect(
                self.open_data_folder
            )
        self._settings_dialog.show_storage_path(str(data_dir()))
        hotkey = getattr(QApplication.instance(), "global_hotkey", None)
        if hotkey is not None:
            self._settings_dialog.show_hotkey_status(
                hotkey.is_registered,
                hotkey.combo or self._store.get().global_hotkey,
            )
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    # ==================================================================
    # Global window behaviour
    # ==================================================================
    def _install_shortcuts(self) -> None:
        def add(key: str, slot) -> QShortcut:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(slot)
            return shortcut

        add("Ctrl+F", self._focus_search)
        add("Ctrl+L", self._focus_search)
        add("Ctrl+N", self.new_snippet)
        add("Ctrl+,", self.open_settings)

    def _focus_search(self) -> None:
        if self._pages.currentWidget() is self._snippets_view:
            self._snippets_view.focus_search()
        else:
            self._history_view.focus_search()

    def bring_to_front(self) -> None:
        """Show and focus the window (used by the tray and global hotkey)."""
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
        self._focus_search()

    # ==================================================================
    # Toast placement
    # ==================================================================
    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._position_toast()

    def _position_toast(self) -> None:
        if not self._toast.isVisible():
            return
        self._toast.adjustSize()
        width = self._toast.width()
        height = self._toast.height()
        x = (self.width() - width) // 2
        y = self.height() - height - 18
        self._toast.move(max(8, x), max(8, y))

    def show_toast(self, message: str, **kwargs) -> None:
        self._toast.show_message(message, **kwargs)
        self._toast.raise_()
        self._position_toast()

    # ==================================================================
    # Geometry persistence / close
    # ==================================================================
    def _restore_geometry(self, encoded: str) -> None:
        if not encoded:
            return
        try:
            data = QByteArray.fromBase64(encoded.encode("ascii"))
            if data and not self.restoreGeometry(data):
                log.debug("Stored window geometry could not be restored")
        except (ValueError, TypeError):
            log.debug("Stored window geometry is invalid")

    def _save_geometry(self) -> None:
        geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
        try:
            self._store.update(window_geometry=geometry)
        except Exception:  # noqa: BLE001 - never block closing on persistence
            log.exception("Could not save window geometry")

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        self._save_geometry()
        try:
            self._store.update(last_section=self._current_section)
        except Exception:  # noqa: BLE001
            log.exception("Could not persist last section")
        if self._store.get().minimize_to_tray:
            event.ignore()
            self.hide()
            log.info("Window hidden to system tray")
            return
        event.accept()
        QApplication.quit()
