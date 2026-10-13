"""Create / edit dialog for saved snippets."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..models import Snippet
from .theme import palette


class SnippetDialog(QDialog):
    """Collects a title, optional metadata and the snippet text."""

    snippet_saved = Signal(object)  # Snippet-shaped dict

    def __init__(
        self,
        snippet: Optional[Snippet] = None,
        initial_text: str = "",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._existing = snippet
        self.setWindowTitle("Edit snippet" if snippet else "New snippet")
        self.setMinimumSize(560, 480)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(14)

        heading = QLabel("Edit snippet" if snippet else "Save a snippet")
        heading.setProperty("heading", True)
        root.addWidget(heading)

        hint = QLabel(
            "Snippets are stored separately from clipboard history and are never "
            "removed by retention rules."
        )
        hint.setProperty("secondary", True)
        hint.setWordWrap(True)
        root.addWidget(hint)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        self._title = QLineEdit()
        self._title.setObjectName("Field")
        self._title.setPlaceholderText("e.g. Deploy command, Email greeting…")
        self._title.setAccessibleName("Snippet title")
        form.addRow(QLabel("Title"), self._title)

        self._tags = QLineEdit()
        self._tags.setObjectName("Field")
        self._tags.setPlaceholderText("code, command, template (comma separated)")
        self._tags.setAccessibleName("Snippet tags")
        form.addRow(QLabel("Tags"), self._tags)

        self._description = QLineEdit()
        self._description.setObjectName("Field")
        self._description.setPlaceholderText("Optional note about when to use this snippet")
        self._description.setAccessibleName("Snippet description")
        form.addRow(QLabel("Description"), self._description)
        root.addLayout(form)

        content_label = QLabel("Content")
        root.addWidget(content_label)
        self._content = QPlainTextEdit()
        self._content.setObjectName("Field")
        self._content.setPlaceholderText("Paste or type the text you want to keep…")
        self._content.setAccessibleName("Snippet content")
        self._content.setMinimumHeight(160)
        self._content.setTabChangesFocus(True)
        root.addWidget(self._content, 1)

        self._error = QLabel("")
        self._error.setProperty("muted", True)
        self._error.setStyleSheet(f"color: {palette('dark').danger};")
        root.addWidget(self._error)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        self._save = QPushButton("Save snippet")
        self._save.setObjectName("Primary")
        self._save.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save.clicked.connect(self._on_save)
        buttons.addWidget(cancel)
        buttons.addWidget(self._save)
        root.addLayout(buttons)

        if snippet is not None:
            self._title.setText(snippet.title)
            self._tags.setText(", ".join(snippet.tags))
            self._description.setText(snippet.description)
            self._content.setPlainText(snippet.content)
        elif initial_text:
            self._content.setPlainText(initial_text)

        self._title.setFocus()

    # ------------------------------------------------------------------
    def _on_save(self) -> None:
        content = self._content.toPlainText()
        title = self._title.text().strip()
        if not content.strip():
            self._error.setText("Snippet content cannot be empty.")
            self._content.setFocus()
            return
        if not title:
            first_line = content.strip().splitlines()[0][:60]
            title = first_line + ("…" if len(content.strip().splitlines()[0]) > 60 else "")
        tags = [t.strip().lstrip("#") for t in self._tags.text().split(",") if t.strip()]
        self.snippet_saved.emit(
            {
                "title": title,
                "content": content,
                "description": self._description.text().strip(),
                "tags": tags[:12],
            }
        )
        self.accept()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        super().closeEvent(event)
