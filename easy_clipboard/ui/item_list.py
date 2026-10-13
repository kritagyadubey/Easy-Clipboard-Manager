"""List view used for clipboard history and saved snippets."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QModelIndex, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QListView, QAbstractItemView


class CardListView(QListView):
    """A list view with hover tracking and keyboard affordances.

    Emits:
        enter_pressed     — Return / Enter on the current row
        delete_pressed    — Delete / Backspace on the current row
        pin_pressed       — Ctrl+P on the current row
        escape_pressed    — Escape (used by the host to clear selection)
        copy_pressed      — Ctrl+C on the current row
    """

    enter_pressed = Signal()
    delete_pressed = Signal()
    pin_pressed = Signal()
    escape_pressed = Signal()
    copy_pressed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hovered_row = -1
        self.density = "comfortable"

        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.viewport().installEventFilter(self)

        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setFrameShape(QListView.Shape.NoFrame)
        self.setViewportMargins(0, 0, 0, 0)
        self.setSpacing(0)
        self.setObjectName("ItemList")
        self.setAccessibleName("Clipboard entries")

    # ------------------------------------------------------------------
    def set_density(self, density: str) -> None:
        if density == self.density:
            return
        self.density = density
        # QListView caches the uniform row height, so a density change has to
        # invalidate that cache or rows keep their old height while the
        # delegate paints the new one (visible as overlapping text).
        self.setUniformItemSizes(False)
        self.doItemsLayout()
        self.setUniformItemSizes(True)
        self.doItemsLayout()
        self.updateGeometries()
        self.viewport().update()

    # ------------------------------------------------------------------
    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt API
        if obj is self.viewport():
            if event.type() == QEvent.Type.MouseMove:
                index = self.indexAt(event.position().toPoint())
                row = index.row() if index.isValid() else -1
                self._set_hovered(row)
            elif event.type() in (QEvent.Type.Leave, QEvent.Type.HoverLeave):
                self._set_hovered(-1)
        return super().eventFilter(obj, event)

    def _set_hovered(self, row: int) -> None:
        if row == self.hovered_row:
            return
        old, self.hovered_row = self.hovered_row, row
        for r in {old, row}:
            if r >= 0:
                index = self.model().index(r, 0) if self.model() else QModelIndex()
                if index.isValid():
                    self.viewport().update(self.visualRect(index))

    # ------------------------------------------------------------------
    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        modifiers = event.modifiers()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.currentIndex().isValid():
                self.enter_pressed.emit()
                event.accept()
                return
        elif key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self.currentIndex().isValid():
                self.delete_pressed.emit()
                event.accept()
                return
        elif key == Qt.Key.Key_Escape:
            self.escape_pressed.emit()
            event.accept()
            return
        elif key == Qt.Key.Key_C and modifiers & Qt.ControlModifier:
            if self.currentIndex().isValid():
                self.copy_pressed.emit()
                event.accept()
                return
        elif key == Qt.Key.Key_P and modifiers & Qt.ControlModifier:
            if self.currentIndex().isValid():
                self.pin_pressed.emit()
                event.accept()
                return
        super().keyPressEvent(event)

    def scroll_current_into_view(self) -> None:
        self.scrollTo(self.currentIndex(), QAbstractItemView.ScrollHint.EnsureVisible)
