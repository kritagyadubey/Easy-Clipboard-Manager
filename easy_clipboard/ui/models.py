"""Qt item models backing the history and snippet lists."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt

from ..models import ClipItem, Snippet
from . import format as fmt

ITEM_ROLE = Qt.ItemDataRole.UserRole + 1


class ClipItemModel(QAbstractListModel):
    """Flat list model over a snapshot of :class:`ClipItem` rows."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[ClipItem] = []

    # ------------------------------------------------------------------
    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802 - Qt API
        return 0 if parent.isValid() else len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None
        item = self._items[index.row()]
        if role == ITEM_ROLE:
            return item
        if role == Qt.ItemDataRole.DisplayRole:
            return item.preview_text
        if role == Qt.ItemDataRole.AccessibleTextRole:
            return (
                f"{item.content_type.label}, {item.char_count} characters, "
                f"copied {fmt.relative_time(item.last_copied_at)}"
            )
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    # ------------------------------------------------------------------
    def set_items(self, items: list[ClipItem]) -> None:
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()

    def items(self) -> list[ClipItem]:
        return list(self._items)

    def item_at(self, row: int) -> Optional[ClipItem]:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    def row_for_id(self, item_id: Optional[int]) -> int:
        if item_id is None:
            return -1
        for row, item in enumerate(self._items):
            if item.id == item_id:
                return row
        return -1

    def replace_item(self, item: ClipItem) -> None:
        row = self.row_for_id(item.id)
        if row >= 0:
            self._items[row] = item
            index = self.index(row, 0)
            self.dataChanged.emit(index, index)


class SnippetModel(QAbstractListModel):
    """List model over saved snippets."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._snippets: list[Snippet] = []

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802 - Qt API
        return 0 if parent.isValid() else len(self._snippets)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._snippets)):
            return None
        snippet = self._snippets[index.row()]
        if role == ITEM_ROLE:
            return snippet
        if role == Qt.ItemDataRole.DisplayRole:
            return snippet.title
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def set_snippets(self, snippets: list[Snippet]) -> None:
        self.beginResetModel()
        self._snippets = list(snippets)
        self.endResetModel()

    def snippets(self) -> list[Snippet]:
        return list(self._snippets)

    def snippet_at(self, row: int) -> Optional[Snippet]:
        if 0 <= row < len(self._snippets):
            return self._snippets[row]
        return None

    def row_for_id(self, snippet_id: Optional[int]) -> int:
        if snippet_id is None:
            return -1
        for row, snippet in enumerate(self._snippets):
            if snippet.id == snippet_id:
                return row
        return -1
