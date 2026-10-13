"""Right-hand preview panel showing the selected clipboard entry in full."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..models import ClipItem
from . import format as fmt
from . import icons
from .theme import TYPE_ICONS, base_font, mono_font, palette


class PreviewPanel(QFrame):
    """Full-text preview plus the actions available for the selected entry."""

    copy_requested = Signal(object)
    pin_toggled = Signal(object, bool)
    favorite_toggled = Signal(object, bool)
    save_snippet_requested = Signal(object)
    edit_snippet_requested = Signal(object)
    delete_requested = Signal(object)
    open_link_requested = Signal(object)
    close_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("PreviewPanel")
        self.setMinimumWidth(300)
        self._item: Optional[ClipItem] = None
        self._snippet = None
        self._mode = "item"

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 14)
        root.setSpacing(10)

        # Header ---------------------------------------------------------
        header = QHBoxLayout()
        header.setSpacing(8)
        self._type_icon = QLabel()
        self._type_icon.setFixedSize(22, 22)
        header.addWidget(self._type_icon)

        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        self._title = QLabel("No selection")
        self._title.setProperty("title", True)
        self._meta = QLabel("Select an entry to preview it")
        self._meta.setProperty("muted", True)
        title_col.addWidget(self._title)
        title_col.addWidget(self._meta)
        header.addLayout(title_col, 1)

        self._close_button = QPushButton()
        self._close_button.setObjectName("IconBtn")
        self._close_button.setFixedSize(28, 28)
        self._close_button.setAccessibleName("Hide preview")
        self._close_button.setToolTip("Hide preview (Esc)")
        self._close_button.clicked.connect(lambda: self.close_requested.emit())
        header.addWidget(self._close_button)
        root.addLayout(header)

        # Tags (snippets only) ------------------------------------------
        self._tags_label = QLabel()
        self._tags_label.setProperty("secondary", True)
        self._tags_label.hide()
        root.addWidget(self._tags_label)

        # Body -----------------------------------------------------------
        self._body = QPlainTextEdit()
        self._body.setObjectName("Field")
        self._body.setReadOnly(True)
        self._body.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self._body.setPlaceholderText("Nothing selected")
        self._body.setTabChangesFocus(True)
        self._body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._body.setMinimumHeight(120)
        root.addWidget(self._body, 1)

        self._detail_label = QLabel("")
        self._detail_label.setProperty("muted", True)
        root.addWidget(self._detail_label)

        # Actions --------------------------------------------------------
        actions = QHBoxLayout()
        actions.setSpacing(6)
        self._copy_button = QPushButton("Copy")
        self._copy_button.setObjectName("Primary")
        self._copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_button.clicked.connect(self._on_copy)
        actions.addWidget(self._copy_button, 1)

        self._open_button = QPushButton("Open")
        self._open_button.clicked.connect(self._on_open_link)
        self._open_button.hide()
        actions.addWidget(self._open_button)
        root.addLayout(actions)

        secondary = QHBoxLayout()
        secondary.setSpacing(6)
        self._pin_button = QPushButton()
        self._pin_button.setObjectName("IconBtn")
        self._pin_button.setCheckable(True)
        self._pin_button.setFixedSize(34, 34)
        self._pin_button.setToolTip("Pin this entry (Ctrl+P)")
        self._pin_button.setAccessibleName("Pin entry")
        self._pin_button.clicked.connect(self._on_pin)
        secondary.addWidget(self._pin_button)

        self._favorite_button = QPushButton()
        self._favorite_button.setObjectName("IconBtn")
        self._favorite_button.setCheckable(True)
        self._favorite_button.setFixedSize(34, 34)
        self._favorite_button.setToolTip("Mark as favorite")
        self._favorite_button.setAccessibleName("Favorite entry")
        self._favorite_button.clicked.connect(self._on_favorite)
        secondary.addWidget(self._favorite_button)

        self._snippet_button = QPushButton("Save as snippet")
        self._snippet_button.setObjectName("Ghost")
        self._snippet_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._snippet_button.setToolTip("Keep this text permanently in Saved snippets")
        self._snippet_button.clicked.connect(self._on_save_snippet)
        secondary.addWidget(self._snippet_button, 1)

        self._edit_button = QPushButton("Edit")
        self._edit_button.setObjectName("Ghost")
        self._edit_button.hide()
        self._edit_button.clicked.connect(self._on_edit)
        secondary.addWidget(self._edit_button)

        self._delete_button = QPushButton()
        self._delete_button.setObjectName("IconBtn")
        self._delete_button.setFixedSize(34, 34)
        self._delete_button.setToolTip("Delete this entry")
        self._delete_button.setAccessibleName("Delete entry")
        self._delete_button.clicked.connect(self._on_delete)
        secondary.addWidget(self._delete_button)
        root.addLayout(secondary)

        self.clear()
        self._refresh_icons()

    # ------------------------------------------------------------------
    def _refresh_icons(self) -> None:
        pal = palette(self._theme_name())
        self._close_button.setIcon(icons.icon("x", pal.text_muted, 14))
        self._pin_button.setIcon(
            icons.icon(
                "pin-filled" if self._pin_button.isChecked() else "pin",
                pal.pin if self._pin_button.isChecked() else pal.text_secondary,
                16,
            )
        )
        self._favorite_button.setIcon(
            icons.icon(
                "star-filled" if self._favorite_button.isChecked() else "star",
                pal.favorite if self._favorite_button.isChecked() else pal.text_secondary,
                16,
            )
        )
        self._delete_button.setIcon(icons.icon("trash", pal.danger, 16))

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._refresh_icons()
        super().showEvent(event)

    # ------------------------------------------------------------------
    def set_item(self, item: Optional[ClipItem]) -> None:
        """Show a clipboard entry (or clear the panel when None)."""
        self._mode = "item"
        self._item = item
        self._snippet = None
        if item is None:
            self.clear()
            return
        pal = palette(self._theme_name())
        icon_name = TYPE_ICONS.get(item.content_type.value, "file-text")
        self._type_icon.setPixmap(
            icons.pixmap(icon_name, pal.type_color(item.content_type.value), 20)
        )
        self._title.setText(item.content_type.label)
        self._meta.setText(fmt.full_time(item.last_copied_at))

        self._body.setFont(
            mono_font(13)
            if item.content_type.value in ("code", "json")
            else base_font(13)
        )
        self._body.setPlainText(item.content)
        self._body.setReadOnly(True)

        details = [f"{item.char_count:,} characters", f"{item.line_count:,} line(s)"]
        if item.source_app:
            details.append(f"from {item.source_app}")
        if item.copy_count > 1:
            details.append(f"copied {item.copy_count} times")
        self._detail_label.setText("  ·  ".join(details))

        self._pin_button.setChecked(item.is_pinned)
        self._favorite_button.setChecked(item.is_favorite)
        self._pin_button.show()
        self._favorite_button.show()
        self._snippet_button.setText("Save as snippet")
        self._snippet_button.show()
        self._edit_button.hide()
        self._tags_label.hide()
        from ..classifier import is_probably_link

        is_link = is_probably_link(item.content)
        self._open_button.setVisible(is_link)
        self._copy_button.setText("Copy")
        self._refresh_icons()

    def set_snippet(self, snippet) -> None:
        """Show a saved snippet inside the same panel."""
        self._mode = "snippet"
        self._snippet = snippet
        self._item = None
        pal = palette(self._theme_name())
        self._type_icon.setPixmap(icons.pixmap("bookmark", pal.accent, 20))
        self._title.setText(snippet.title or "Snippet")
        self._meta.setText(f"Updated {fmt.relative_time(snippet.updated_at)}")
        self._body.setFont(base_font(13))
        self._body.setPlainText(snippet.content)
        if snippet.tags:
            self._tags_label.setText("  ".join(f"#{tag}" for tag in snippet.tags))
            self._tags_label.show()
        else:
            self._tags_label.hide()
        details = [f"{len(snippet.content):,} characters"]
        if snippet.description:
            details.append(snippet.description)
        self._detail_label.setText("  ·  ".join(details))
        self._pin_button.hide()
        self._favorite_button.hide()
        self._snippet_button.hide()
        self._edit_button.show()
        self._open_button.hide()
        self._copy_button.setText("Copy")
        self._refresh_icons()

    def clear(self) -> None:
        self._item = None
        self._snippet = None
        self._title.setText("No selection")
        self._meta.setText("Select an entry to preview it")
        self._body.clear()
        self._body.setPlaceholderText("Select an entry from the list to see its full content here.")
        self._detail_label.setText("")
        self._tags_label.hide()
        self._pin_button.hide()
        self._favorite_button.hide()
        self._snippet_button.hide()
        self._edit_button.hide()
        self._open_button.hide()
        self._pin_button.setChecked(False)
        self._favorite_button.setChecked(False)
        self._type_icon.clear()

    # ------------------------------------------------------------------
    def content_text(self) -> str:
        return self._body.toPlainText()

    def refresh_theme(self) -> None:
        self._refresh_icons()

    # ------------------------------------------------------------------
    def _on_copy(self) -> None:
        if self._mode == "snippet" and self._snippet is not None:
            self.copy_requested.emit(self._snippet)
        elif self._item is not None:
            self.copy_requested.emit(self._item)

    def _on_open_link(self) -> None:
        if self._item is not None:
            self.open_link_requested.emit(self._item)

    def _on_pin(self) -> None:
        if self._item is not None:
            self.pin_toggled.emit(self._item, self._pin_button.isChecked())
        self._refresh_icons()

    def _on_favorite(self) -> None:
        if self._item is not None:
            self.favorite_toggled.emit(self._item, self._favorite_button.isChecked())
        self._refresh_icons()

    def _on_save_snippet(self) -> None:
        if self._item is not None:
            self.save_snippet_requested.emit(self._item)

    def _on_edit(self) -> None:
        if self._snippet is not None:
            self.edit_snippet_requested.emit(self._snippet)

    def _on_delete(self) -> None:
        if self._mode == "snippet" and self._snippet is not None:
            self.delete_requested.emit(self._snippet)
        elif self._item is not None:
            self.delete_requested.emit(self._item)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    @staticmethod
    def _theme_name() -> str:
        app = QApplication.instance()
        return getattr(app, "theme_name", "dark") if app else "dark"
