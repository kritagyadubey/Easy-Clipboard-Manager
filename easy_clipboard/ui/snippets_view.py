"""Saved snippets page: list, search, preview and management actions."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..models import Snippet
from . import format as fmt
from .delegates import SnippetDelegate
from .item_list import CardListView
from .models import SnippetModel
from .preview_panel import PreviewPanel
from .widgets import EmptyState, SearchField


class SnippetsView(QWidget):
    """Everything related to saved snippets in one place."""

    new_requested = Signal()
    edit_requested = Signal(object)
    delete_requested = Signal(object)
    copy_requested = Signal(object)
    search_changed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._model = SnippetModel(self)
        self._selected_id: Optional[int] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 12)
        root.setSpacing(12)

        # Header ---------------------------------------------------------
        header = QHBoxLayout()
        header.setSpacing(10)
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Saved snippets")
        title.setProperty("heading", True)
        self._count_label = QLabel("")
        self._count_label.setProperty("secondary", True)
        title_col.addWidget(title)
        title_col.addWidget(self._count_label)
        header.addLayout(title_col)
        header.addStretch(1)
        self._new_button = QPushButton("New snippet")
        self._new_button.setObjectName("Primary")
        self._new_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._new_button.setToolTip("Create a new saved snippet (Ctrl+N)")
        self._new_button.clicked.connect(lambda: self.new_requested.emit())
        header.addWidget(self._new_button)
        root.addLayout(header)

        self._search = SearchField("Search snippets by title, tag or content…")
        self._search.setFixedHeight(40)
        root.addWidget(self._search)

        # Body: list + preview -------------------------------------------
        body = QHBoxLayout()
        body.setSpacing(0)

        self._list = CardListView(self)
        self._list.setModel(self._model)
        self._list.setItemDelegate(SnippetDelegate(self._list))
        self._list.enter_pressed.connect(self._on_copy)
        self._list.copy_pressed.connect(self._on_copy)
        self._list.delete_pressed.connect(self._on_delete_shortcut)
        self._list.escape_pressed.connect(self._on_escape)
        self._list.clicked.connect(lambda index: self._emit_focused(index.row()))
        self._list.selectionModel().currentChanged.connect(
            lambda current, _prev: self._emit_focused(
                current.row() if current.isValid() else -1
            )
        )
        self._list.doubleClicked.connect(lambda _index: self._on_copy())

        self._empty = EmptyState(
            "bookmark",
            "No saved snippets yet",
            "Turn any clipboard entry into a snippet to keep it forever — snippets "
            "are never removed by history cleanup.",
            action_label="Create your first snippet",
        )
        self._empty.action_clicked.connect(lambda: self.new_requested.emit())
        self._empty_search = EmptyState(
            "search",
            "No matching snippets",
            "No snippet matches this search. Try a different word or tag.",
        )

        list_column = QWidget(self)
        list_layout = QVBoxLayout(list_column)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(0)
        list_layout.addWidget(self._list)
        list_layout.addWidget(self._empty)
        list_layout.addWidget(self._empty_search)

        self._preview = PreviewPanel(self)
        self._preview.copy_requested.connect(lambda s: self.copy_requested.emit(s))
        self._preview.edit_snippet_requested.connect(lambda s: self.edit_requested.emit(s))
        self._preview.delete_requested.connect(lambda s: self.delete_requested.emit(s))
        self._preview.close_requested.connect(self._on_escape)

        divider = QWidget()
        divider.setFixedWidth(1)
        divider.setObjectName("PanelDivider")

        body.addWidget(list_column, 3)
        body.addWidget(divider)
        body.addWidget(self._preview, 2)
        root.addLayout(body, 1)

        # Debounced search -------------------------------------------------
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(140)
        self._search_timer.timeout.connect(
            lambda: self.search_changed.emit(self._search.text())
        )
        self._search.textChanged.connect(lambda _t: self._search_timer.start())

        self._update_empty_states()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_snippets(
        self,
        snippets: list[Snippet],
        *,
        keep_selection: bool = False,
        total: Optional[int] = None,
    ) -> None:
        """Replace the list contents.

        ``total`` is the number of snippets before filtering; when the
        visible list is shorter the count label says "of N" so the user
        knows the search narrowed the results.
        """
        previous = self._selected_id if keep_selection else None
        if not keep_selection:
            # Drop the mirror of the selection: the id may refer to an entry
            # that no longer exists (deleted or filtered away).
            self._selected_id = None
        self._model.set_snippets(snippets)
        if not snippets:
            self._count_label.setText("")
        else:
            label = fmt.count_label(len(snippets), "snippet", "snippets")
            if total is not None and len(snippets) < total:
                label = f"{label} of {total:,}"
            self._count_label.setText(label)
        if previous is not None:
            row = self._model.row_for_id(previous)
            if row >= 0:
                self._list.setCurrentIndex(self._model.index(row, 0))
            else:
                self._selected_id = None
                self._preview.clear()
        self._update_empty_states()

    def current_snippet(self) -> Optional[Snippet]:
        index = self._list.currentIndex()
        if not index.isValid():
            return None
        return self._model.snippet_at(index.row())

    def set_density(self, density: str) -> None:
        self._list.set_density(density)

    def search_text(self) -> str:
        return self._search.text()

    def focus_search(self) -> None:
        self._search.setFocus()
        self._search.selectAll()

    def focus_list(self) -> None:
        self._list.setFocus()
        if not self._list.currentIndex().isValid() and self._model.rowCount() > 0:
            self._list.setCurrentIndex(self._model.index(0, 0))

    def select_snippet(self, snippet_id: Optional[int]) -> None:
        row = self._model.row_for_id(snippet_id)
        if row >= 0:
            index = self._model.index(row, 0)
            self._list.setCurrentIndex(index)
            self._list.scroll_current_into_view()

    # ------------------------------------------------------------------
    def _emit_focused(self, row: int) -> None:
        snippet = self._model.snippet_at(row)
        self._selected_id = snippet.id if snippet else None
        if snippet is not None:
            self._preview.set_snippet(snippet)
        else:
            self._preview.clear()

    def _on_copy(self, *_args) -> None:
        snippet = self.current_snippet()
        if snippet is not None:
            self.copy_requested.emit(snippet)

    def _on_delete_shortcut(self) -> None:
        snippet = self.current_snippet()
        if snippet is not None:
            self.delete_requested.emit(snippet)

    def _on_escape(self) -> None:
        if self._search.text():
            self._search.clear()
        else:
            self._list.clearSelection()
            self._selected_id = None
            self._preview.clear()

    def _update_empty_states(self) -> None:
        has_items = self._model.rowCount() > 0
        searching = bool(self._search.text())
        self._list.setVisible(has_items)
        self._preview.setVisible(has_items)
        self._empty.setVisible(not has_items and not searching)
        self._empty_search.setVisible(not has_items and searching)
