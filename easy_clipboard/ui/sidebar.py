"""Left navigation sidebar."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .. import APP_NAME, TAGLINE
from ..models import StorageStats
from .theme import palette, render_logo
from .widgets import NavButton

# (key, label, icon, section caption)
_NAV_ITEMS = [
    ("all", "All history", "layers", "LIBRARY"),
    ("pinned", "Pinned", "pin", None),
    ("favorite", "Favorites", "star", None),
    ("recent", "Recent", "clock", None),
    ("links", "Links", "link", "TYPES"),
    ("code", "Code", "code", None),
    ("text", "Text", "file-text", None),
    ("snippets", "Saved snippets", "bookmark", None),
]


class Sidebar(QFrame):
    """Brand, navigation, monitoring control and storage summary."""

    section_selected = Signal(str)
    settings_clicked = Signal()
    monitoring_toggle_clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(240)
        self._buttons: dict[str, NavButton] = {}
        self._current = "all"

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 14, 12, 12)
        root.setSpacing(4)

        # --------------------------------------------------------------
        # Brand
        # --------------------------------------------------------------
        brand = QHBoxLayout()
        brand.setSpacing(10)
        self._logo_label = QLabel()
        self._logo_label.setFixedSize(34, 34)
        brand.addWidget(self._logo_label, 0, Qt.AlignmentFlag.AlignTop)
        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        name_label = QLabel(APP_NAME)
        name_label.setObjectName("BrandName")
        name_label.setWordWrap(True)
        tagline = QLabel(TAGLINE)
        tagline.setObjectName("BrandTagline")
        text_col.addWidget(name_label)
        text_col.addWidget(tagline)
        brand.addLayout(text_col)
        brand.addStretch(1)
        root.addLayout(brand)
        root.addSpacing(14)

        # --------------------------------------------------------------
        # Navigation
        # --------------------------------------------------------------
        for key, label, icon_name, caption in _NAV_ITEMS:
            if caption:
                caption_label = QLabel(caption)
                caption_label.setObjectName("SectionCaption")
                caption_label.setContentsMargins(10, 6, 0, 4)
                root.addWidget(caption_label)
            if key == "snippets":
                root.addSpacing(10)
            button = NavButton(key, label, icon_name)
            button.clicked.connect(lambda k=key: self._on_click(k))
            self._buttons[key] = button
            root.addWidget(button)

        root.addStretch(1)

        # --------------------------------------------------------------
        # Footer: storage summary + monitoring + settings
        # --------------------------------------------------------------
        self._stats_label = QLabel()
        self._stats_label.setObjectName("BrandTagline")
        self._stats_label.setContentsMargins(10, 0, 0, 6)
        root.addWidget(self._stats_label)

        self._monitor_button = NavButton("monitor", "Pause monitoring", "pause")
        self._monitor_button.clicked.connect(
            lambda: self.monitoring_toggle_clicked.emit()
        )
        root.addWidget(self._monitor_button)

        settings_button = NavButton("settings", "Settings", "settings")
        settings_button.clicked.connect(lambda: self.settings_clicked.emit())
        root.addWidget(settings_button)

        self.select("all")

    # ------------------------------------------------------------------
    def _refresh_logo(self) -> None:
        pal = palette(self._theme_name())
        self._logo_label.setPixmap(render_logo(34, pal.accent).scaled(
            34, 34, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        ))

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._refresh_logo()
        super().showEvent(event)

    def retranslate(self) -> None:
        self._refresh_logo()

    # ------------------------------------------------------------------
    def _on_click(self, key: str) -> None:
        self.select(key)
        self.section_selected.emit(key)

    def select(self, key: str) -> None:
        self._current = key
        for name, button in self._buttons.items():
            button.set_checked(name == key)

    def current_section(self) -> str:
        return self._current

    # ------------------------------------------------------------------
    def set_counts(self, counts: dict[str, int]) -> None:
        for key, button in self._buttons.items():
            button.set_count(counts.get(key))

    def set_monitoring(self, enabled: bool) -> None:
        if enabled:
            self._monitor_button.label = "Pause monitoring"
            self._monitor_button.icon_name = "pause"
            self._monitor_button.set_alert(False)
        else:
            self._monitor_button.label = "Monitoring paused"
            self._monitor_button.icon_name = "play"
            self._monitor_button.set_alert(True)
        self._monitor_button.update()

    def set_stats(self, stats: StorageStats, retention_days: int) -> None:
        parts = [f"{stats.item_count:,} entries", stats.size_label]
        if stats.snippet_count:
            parts.append(f"{stats.snippet_count:,} snippets")
        self._stats_label.setText("  ·  ".join(parts))
        self._stats_label.setToolTip(
            f"{stats.item_count:,} clipboard entries and "
            f"{stats.snippet_count:,} saved snippets stored locally.\n"
            f"Retention: "
            + (f"{retention_days} days" if retention_days else "keep everything")
        )

    # ------------------------------------------------------------------
    def apply_theme(self) -> None:
        self._refresh_logo()
        self.update()
        for button in self._buttons.values():
            button.update()

    @staticmethod
    def _theme_name() -> str:
        app = QApplication.instance()
        return getattr(app, "theme_name", "dark") if app else "dark"
