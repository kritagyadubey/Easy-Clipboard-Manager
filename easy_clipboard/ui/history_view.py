"""Central area: section header, search, filters and the history list."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..models import ClipItem
from . import format as fmt
from . import icons
from .delegates import ClipItemDelegate
from .item_list import CardListView
from .models import ClipItemModel
from .theme import palette
from .widgets import EmptyState, SearchField

SORT_LABELS = {
    "newest": "Newest first",
    "oldest": "Oldest first",
    "most_used": "Most used",
}


class HistoryView(QWidget):
    """Shows a filtered list of clipboard entries."""

    search_changed = Signal(str)
    item_focused = Signal(object)      # ClipItem | None
    item_activated = Signal(object)    # copy / open
    copy_requested = Signal(object)
    delete_requested = Signal(object)
    pin_requested = Signal(object)
    clear_history_requested = Signal()
    export_requested = Signal()
    open_data_folder_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._section_title = "All history"
        self._model = ClipItemModel(self)
        self._selected_id: Optional[int] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 12)
        root.setSpacing(12)

        # --------------------------------------------------------------
        # Header
        # --------------------------------------------------------------
        header = QHBoxLayout()
        header.setSpacing(10)
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        self._title_label = QLabel(self._section_title)
        self._title_label.setProperty("heading", True)
        self._count_label = QLabel("")
        self._count_label.setProperty("secondary", True)
        title_col.addWidget(self._title_label)
        title_col.addWidget(self._count_label)
        header.addLayout(title_col)
        header.addStretch(1)

        self._sort_button = QToolButton(self)
        self._sort_button.setObjectName("Ghost")
        self._sort_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._sort_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._sort_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sort_button.setFixedHeight(32)
        self._sort_button.setAccessibleName("Sort order")
        self._sort_menu = QMenu(self._sort_button)
        self._sort_actions: dict[str, object] = {}
        for key, label in SORT_LABELS.items():
            action = self._sort_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(key == "newest")
            action.triggered.connect(lambda _=False, k=key: self._on_sort_selected(k))
            self._sort_actions[key] = action
        self._sort_button.setMenu(self._sort_menu)
        self._sort_button.setText(SORT_LABELS["newest"] + "  ▾")
        header.addWidget(self._sort_button)

        self._more_button = QToolButton(self)
        self._more_button.setObjectName("Ghost")
        self._more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._more_button.setAccessibleName("More actions")
        self._more_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._more_menu = QMenu(self._more_button)
        self._more_menu.addAction(
            icons.icon("trash", palette("dark").danger, 15),
            "Clear history…",
            lambda: self.clear_history_requested.emit(),
        )
        self._more_menu.addAction(
            "Export entries…", lambda: self.export_requested.emit()
        )
        self._more_menu.addAction(
            "Open data folder", lambda: self.open_data_folder_requested.emit()
        )
        self._more_button.setMenu(self._more_menu)
        self._more_button.setIcon(icons.icon("menu", palette("dark").text_secondary, 16))
        self._more_button.setFixedSize(32, 32)
        header.addWidget(self._more_button)

        root.addLayout(header)

        # --------------------------------------------------------------
        # Paused banner
        # --------------------------------------------------------------
        self._paused_banner = QFrame(self)
        banner_layout = QHBoxLayout(self._paused_banner)
        banner_layout.setContentsMargins(12, 8, 12, 8)
        banner_icon = QLabel()
        banner_icon.setPixmap(icons.pixmap("pause", palette("dark").danger, 16))
        banner_layout.addWidget(banner_icon)
        banner_text = QLabel("Clipboard monitoring is paused — new copies are not being saved.")
        banner_text.setProperty("secondary", True)
        banner_layout.addWidget(banner_text)
        banner_layout.addStretch(1)
        self._paused_banner.hide()
        root.addWidget(self._paused_banner)

        # --------------------------------------------------------------
        # Search
        # --------------------------------------------------------------
        self._search = SearchField("Search your clipboard history…")
        self._search.setClearButtonEnabled(True)
        self._search.setFixedHeight(40)
        self._search.setAccessibleName("Search clipboard history")
        root.addWidget(self._search)

        # --------------------------------------------------------------
        # List + empty states
        # --------------------------------------------------------------
        self._list = CardListView(self)
        self._list.setModel(self._model)
        self._list.setItemDelegate(ClipItemDelegate(self._list))
        self._list.enter_pressed.connect(self._on_enter)
        self._list.copy_pressed.connect(self._on_copy_shortcut)
        self._list.delete_pressed.connect(self._on_delete_shortcut)
        self._list.pin_pressed.connect(self._on_pin_shortcut)
        self._list.escape_pressed.connect(self._on_escape)
        self._list.setSelectionModel(self._list.selectionModel())
        self._list.clicked.connect(lambda index: self._emit_focused(index.row()))
        self._list.selectionModel().currentChanged.connect(
            lambda current, _prev: self._emit_focused(current.row() if current.isValid() else -1)
        )
        self._list.doubleClicked.connect(lambda _index: self._on_enter())

        self._empty_search = EmptyState(
            "search",
            "No matching entries",
            "Try a different search term — search looks inside the full text of "
            "everything you have copied.",
        )
        self._empty_history = EmptyState(
            "layers",
            "Your clipboard history is empty",
            "Copy anything and it will show up here automatically, ready to be "
            "found again later.",
        )
        self._stack = QFrame(self)
        stack_layout = QVBoxLayout(self._stack)
        stack_layout.setContentsMargins(0, 0, 0, 0)
        stack_layout.addWidget(self._list)
        stack_layout.addWidget(self._empty_search)
        stack_layout.addWidget(self._empty_history)
        root.addWidget(self._stack, 1)
        self._list.raise_()

        # Debounced search ------------------------------------------------
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(140)
        self._search_timer.timeout.connect(
            lambda: self.search_changed.emit(self._search.text())
        )
        self._search.textChanged.connect(lambda _t: self._search_timer.start())

        self._show_empty("history")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_section_title(self, title: str) -> None:
        self._section_title = title
        self._title_label.setText(title)

    def set_result_count(self, shown: int, total: int, searching: bool) -> None:
        """Show how many entries are visible — and of how many in total.

        The "of total" part also matters when *not* searching: the list
        renders at most 1000 rows, so shown < total must be reported there
        too instead of implying the list is complete.
        """
        if shown == 0:
            self._count_label.setText("")
            return
        if searching:
            label = fmt.count_label(shown, "match", "matches")
        else:
            label = fmt.count_label(shown)
        if shown < total:
            label = f"{label} of {total:,}"
        self._count_label.setText(label)

    def set_items(self, items: list[ClipItem], *, keep_selection: bool = False) -> None:
        previous_id = self._selected_id if keep_selection else None
        self._model.set_items(items)
        if not items:
            self._selected_id = None
        elif previous_id is not None:
            row = self._model.row_for_id(previous_id)
            if row >= 0:
                self._list.setCurrentIndex(self._model.index(row, 0))
            else:
                self._selected_id = None
                self._list.clearSelection()
        else:
            # Nothing to restore: drop the mirror of the selection so a
            # deleted/filtered-away id cannot linger and be reselected later.
            self._selected_id = None
        self._update_empty_states()

    def set_sort(self, sort_key: str) -> None:
        self._sort_button.setText(SORT_LABELS.get(sort_key, sort_key) + "  ▾")
        for key, action in self._sort_actions.items():
            action.setChecked(key == sort_key)

    def current_item(self) -> Optional[ClipItem]:
        index = self._list.currentIndex()
        if not index.isValid():
            return None
        return self._model.item_at(index.row())

    def selected_id(self) -> Optional[int]:
        return self._selected_id

    def select_item(self, item_id: Optional[int]) -> None:
        row = self._model.row_for_id(item_id)
        if row >= 0:
            index = self._model.index(row, 0)
            self._list.setCurrentIndex(index)
            self._list.scroll_current_into_view()
            self._selected_id = item_id
        else:
            self._list.clearSelection()

    def search_text(self) -> str:
        return self._search.text()

    def focus_search(self) -> None:
        self._search.setFocus()
        self._search.selectAll()

    def clear_search(self) -> None:
        self._search.clear()

    def has_search(self) -> bool:
        return bool(self._search.text())

    def refresh_icons(self) -> None:
        pal = palette(self._theme_name())
        self._more_button.setIcon(icons.icon("menu", pal.text_secondary, 16))
        # Rebuild the "clear history" icon with the right colour.
        actions = self._more_menu.actions()
        if actions:
            actions[0].setIcon(icons.icon("trash", pal.danger, 15))
        self._list.viewport().update()

    def set_paused_banner(self, visible: bool) -> None:
        self._paused_banner.setVisible(visible)

    def set_density(self, density: str) -> None:
        self._list.set_density(density)

    def set_focus_list(self) -> None:
        self._list.setFocus()
        if not self._list.currentIndex().isValid() and self._model.rowCount() > 0:
            self._list.setCurrentIndex(self._model.index(0, 0))

    def scroll_to_top(self) -> None:
        self._list.scrollToTop()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _emit_focused(self, row: int) -> None:
        item = self._model.item_at(row)
        self._selected_id = item.id if item else None
        self.item_focused.emit(item)

    def _on_enter(self, *_args) -> None:
        item = self.current_item()
        if item is not None:
            self.item_activated.emit(item)

    def _on_copy_shortcut(self) -> None:
        item = self.current_item()
        if item is not None:
            self.copy_requested.emit(item)

    def _on_delete_shortcut(self) -> None:
        item = self.current_item()
        if item is not None:
            self.delete_requested.emit(item)

    def _on_pin_shortcut(self) -> None:
        item = self.current_item()
        if item is not None:
            self.pin_requested.emit(item)

    def _on_escape(self) -> None:
        if self.has_search():
            self.clear_search()
        else:
            self._list.clearSelection()
            self._selected_id = None
            self.item_focused.emit(None)

    def _on_sort_selected(self, key: str) -> None:
        self.set_sort(key)
        self.search_changed.emit(self._search.text())

    @property
    def sort_key(self) -> str:
        for key, action in self._sort_actions.items():
            if action.isChecked():
                return key
        return "newest"

    def _update_empty_states(self) -> None:
        count = self._model.rowCount()
        if count == 0:
            self._show_empty("search" if self.has_search() else "history")
        else:
            self._show_empty(None)

    def _show_empty(self, which: Optional[str]) -> None:
        self._list.setVisible(which is None)
        self._empty_search.setVisible(which == "search")
        self._empty_history.setVisible(which == "history")
        if which is None:
            self._list.raise_()

    @staticmethod
    def _theme_name() -> str:
        app = QApplication.instance()
        return getattr(app, "theme_name", "dark") if app else "dark"
