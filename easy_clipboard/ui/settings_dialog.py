"""Settings dialog: General, Appearance, History, Privacy & data, About.

Every control here is wired to real behaviour.  Changes are applied and
persisted immediately; the dialog only needs a Close button.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QKeySequence, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..history import HistoryService
from ..logging_setup import get_logger
from ..settings import (
    DEFAULT_HOTKEY,
    DUPLICATE_MODES,
    Settings,
    SettingsStore,
)
from ..windows import autostart
from ..windows.hotkey import format_hotkey
from . import icons
from .theme import base_font, palette, render_logo
from .widgets import Card, Switch

log = get_logger("settings-ui")

_CATEGORIES = [
    ("general", "General", "settings"),
    ("appearance", "Appearance", "moon"),
    ("history", "Clipboard history", "layers"),
    ("privacy", "Privacy & data", "shield"),
    ("about", "About", "info"),
]

_RETENTION_OPTIONS = [
    (0, "Keep everything"),
    (1, "1 day"),
    (7, "7 days"),
    (14, "14 days"),
    (30, "30 days"),
    (90, "90 days"),
    (365, "1 year"),
]


# ----------------------------------------------------------------------
# Small building blocks
# ----------------------------------------------------------------------
class FormRow(QFrame):
    """A label/description on the left, a control on the right."""

    def __init__(self, title: str, description: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("FormRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(16)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("FormLabel")
        text_col.addWidget(title_label)
        if description:
            desc = QLabel(description)
            desc.setObjectName("FormHint")
            desc.setWordWrap(True)
            text_col.addWidget(desc)
        layout.addLayout(text_col, 1)
        self._control_slot = QHBoxLayout()
        self._control_slot.setSpacing(8)
        layout.addLayout(self._control_slot)

    def add_control(self, widget: QWidget) -> None:
        self._control_slot.addWidget(widget)
        self._control_slot.addStretch(0)

    def add_right_widget(self, widget: QWidget) -> None:
        """Attach a read-only informational widget to the right side."""
        self._control_slot.addWidget(widget, 1)


class CategoryButton(QWidget):
    """Left-rail category entry in the settings dialog."""

    def __init__(self, key: str, label: str, icon_name: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.label = label
        self.icon_name = icon_name
        self._checked = False
        self._hover = False
        self.setFixedHeight(38)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(label)

    def set_checked(self, checked: bool) -> None:
        self._checked = checked
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            handler = getattr(self, "_handler", None)
            if handler:
                handler(self.key)
        super().mouseReleaseEvent(event)

    def set_handler(self, handler) -> None:
        self._handler = handler

    def paintEvent(self, event) -> None:  # noqa: N802
        pal = palette(_theme_name())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(6, 4, -6, -4)
        if self._checked:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(pal.accent_soft))
            painter.drawRoundedRect(rect, 8, 8)
            text_color, icon_color = pal.accent, pal.accent
        elif self._hover:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(pal.surface_hover))
            painter.drawRoundedRect(rect, 8, 8)
            text_color, icon_color = pal.text, pal.text_secondary
        else:
            text_color, icon_color = pal.text_secondary, pal.text_muted

        painter.drawPixmap(
            rect.left() + 10, (self.height() - 16) // 2,
            icons.pixmap(self.icon_name, icon_color, 16),
        )
        painter.setPen(QColor(text_color))
        painter.setFont(base_font(13))
        painter.drawText(
            rect.left() + 36, (self.height() + 13) // 2 - 1, self.label
        )
        painter.end()


def _theme_name() -> str:
    app = QApplication.instance()
    return getattr(app, "theme_name", "dark") if app else "dark"


class SegmentedControl(QWidget):
    """Three-way (or n-way) segmented choice, used for theme and density."""

    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], current: str, parent=None):
        super().__init__(parent)
        self._options = options
        self._current = current
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self._buttons: dict[str, QPushButton] = {}
        for key, label in options:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setAccessibleName(label)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, k=key: self.set_value(k))
            self._buttons[key] = button
            layout.addWidget(button)
        self._sync_style()

    def set_value(self, key: str) -> None:
        if key == self._current:
            return
        self._current = key
        self._sync_style()
        self.changed.emit(key)

    def _sync_style(self) -> None:
        pal = palette(_theme_name())
        for key, button in self._buttons.items():
            active = key == self._current
            button.setCheckable(True)
            button.setChecked(active)
            if active:
                button.setStyleSheet(
                    f"QPushButton {{ background: {pal.accent_soft};"
                    f" color: {pal.accent}; border: 1px solid {pal.accent};"
                    " font-weight: 600; }}"
                )
            else:
                button.setStyleSheet(
                    f"QPushButton {{ background: {pal.surface};"
                    f" color: {pal.text_secondary}; border: 1px solid {pal.border}; }}"
                )


# ----------------------------------------------------------------------
# Dialog
# ----------------------------------------------------------------------
class SettingsDialog(QDialog):
    """All application preferences."""

    clear_history_requested = Signal()
    clear_all_requested = Signal()
    export_requested = Signal(str)   # "history" | "snippets" | "all"
    import_requested = Signal()
    open_data_folder_requested = Signal()
    hotkey_conflict = Signal(str)

    def __init__(
        self,
        settings_store: SettingsStore,
        history: HistoryService,
        parent=None,
    ):
        super().__init__(parent)
        self._store = settings_store
        self._history = history
        self.setWindowTitle("Settings — Easy Clipboard Manager")
        self.setMinimumSize(860, 600)
        self.setModal(True)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Left rail ------------------------------------------------------
        rail = QFrame(self)
        rail.setFixedWidth(210)
        rail.setStyleSheet(f"background: {palette(_theme_name()).bg_alt};")
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(14, 20, 14, 16)
        rail_layout.setSpacing(2)
        rail_title = QLabel("Settings")
        rail_title.setProperty("title", True)
        rail_title.setContentsMargins(10, 0, 0, 8)
        rail_layout.addWidget(rail_title)

        self._category_buttons: dict[str, CategoryButton] = {}
        for key, label, icon_name in _CATEGORIES:
            button = CategoryButton(key, label, icon_name)
            button.set_handler(self._on_category)
            self._category_buttons[key] = button
            rail_layout.addWidget(button)
        rail_layout.addStretch(1)
        root.addWidget(rail)

        # Right side ----------------------------------------------------
        right = QWidget(self)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(24, 20, 24, 16)
        right_layout.setSpacing(10)

        self._page_title = QLabel("General")
        self._page_title.setProperty("heading", True)
        right_layout.addWidget(self._page_title)

        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._build_general_page())
        self._stack.addWidget(self._build_appearance_page())
        self._stack.addWidget(self._build_history_page())
        self._stack.addWidget(self._build_privacy_page())
        self._stack.addWidget(self._build_about_page())
        right_layout.addWidget(self._stack, 1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        close = QPushButton("Close")
        close.setObjectName("Primary")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.accept)
        footer.addWidget(close)
        right_layout.addLayout(footer)
        root.addWidget(right, 1)

        self._select_category("general")
        self._store.add_listener(self._on_settings_external_change)

    # ------------------------------------------------------------------
    # Page builders
    # ------------------------------------------------------------------
    def _page(self) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 8, 8, 8)
        layout.setSpacing(8)
        scroll.setWidget(container)
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(scroll)
        return page, layout

    def _build_general_page(self) -> QWidget:
        page, layout = self._page()
        settings = self._store.get()

        self._startup_switch = Switch(settings.launch_at_startup)
        self._startup_switch.setAccessibleName("Launch at Windows startup")
        self._startup_switch.toggled.connect(self._on_startup_toggled)
        layout.addWidget(
            self._row(
                "Launch at Windows startup",
                "Start Easy Clipboard Manager automatically when you sign in to Windows.",
                self._startup_switch,
            )
        )

        self._tray_switch = Switch(settings.minimize_to_tray)
        self._tray_switch.setAccessibleName("Minimize to tray on close")
        self._tray_switch.toggled.connect(
            lambda checked: self._store.update(minimize_to_tray=checked)
        )
        layout.addWidget(
            self._row(
                "Close button minimizes to tray",
                "Keep clipboard monitoring running when you close the window. "
                "Use Exit in the tray menu to quit completely.",
                self._tray_switch,
            )
        )

        self._start_minimized_switch = Switch(settings.start_minimized)
        self._start_minimized_switch.setAccessibleName("Start minimized")
        self._start_minimized_switch.toggled.connect(
            lambda checked: self._store.update(start_minimized=checked)
        )
        layout.addWidget(
            self._row(
                "Start minimized",
                "Launch directly into the system tray instead of opening the window.",
                self._start_minimized_switch,
            )
        )

        # Global shortcut -------------------------------------------------
        shortcut_row = FormRow(
            "Global shortcut",
            "Bring Easy Clipboard Manager to the foreground from any application. "
            "Click Record, then press the new combination.",
        )
        self._hotkey_field = QLineEdit(format_hotkey(settings.global_hotkey))
        self._hotkey_field.setObjectName("Field")
        self._hotkey_field.setReadOnly(True)
        self._hotkey_field.setFixedWidth(160)
        self._hotkey_field.setAccessibleName("Global shortcut")
        self._record_button = QPushButton("Record")
        self._record_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._record_button.clicked.connect(self._on_record_hotkey)
        self._reset_hotkey_button = QPushButton("Reset")
        self._reset_hotkey_button.setObjectName("Ghost")
        self._reset_hotkey_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reset_hotkey_button.clicked.connect(
            lambda: self._apply_hotkey(DEFAULT_HOTKEY)
        )
        shortcut_row.add_control(self._hotkey_field)
        shortcut_row.add_control(self._record_button)
        shortcut_row.add_control(self._reset_hotkey_button)
        layout.addWidget(shortcut_row)

        self._hotkey_status = QLabel("")
        self._hotkey_status.setObjectName("FormHint")
        self._hotkey_status.setContentsMargins(14, 0, 0, 4)
        layout.addWidget(self._hotkey_status)
        return page

    def _build_appearance_page(self) -> QWidget:
        page, layout = self._page()
        settings = self._store.get()

        theme_row = FormRow(
            "Theme",
            "Match Windows, or pick dark or light explicitly.",
        )
        self._theme_control = SegmentedControl(
            [("dark", "Dark"), ("light", "Light"), ("system", "System")],
            settings.theme,
        )
        self._theme_control.changed.connect(
            lambda value: self._store.update(theme=value)
        )
        theme_row.add_control(self._theme_control)
        layout.addWidget(theme_row)

        density_row = FormRow(
            "Density",
            "Compact fits more entries on screen; comfortable is easier to scan.",
        )
        self._density_control = SegmentedControl(
            [("comfortable", "Comfortable"), ("compact", "Compact")],
            settings.density,
        )
        self._density_control.changed.connect(
            lambda value: self._store.update(density=value)
        )
        density_row.add_control(self._density_control)
        layout.addWidget(density_row)
        layout.addStretch(1)
        return page

    def _build_history_page(self) -> QWidget:
        page, layout = self._page()
        settings = self._store.get()

        self._monitoring_switch = Switch(settings.monitoring_enabled)
        self._monitoring_switch.setAccessibleName("Clipboard monitoring")
        self._monitoring_switch.toggled.connect(
            lambda checked: self._store.update(monitoring_enabled=checked)
        )
        layout.addWidget(
            self._row(
                "Capture clipboard changes",
                "When off, nothing new is recorded. Existing history is untouched.",
                self._monitoring_switch,
            )
        )

        max_row = FormRow(
            "Maximum history size",
            "Older unprotected entries are removed once this limit is exceeded.",
        )
        self._max_spin = QSpinBox()
        self._max_spin.setObjectName("Field")
        self._max_spin.setRange(25, 10000)
        self._max_spin.setSingleStep(25)
        self._max_spin.setValue(settings.max_items)
        self._max_spin.setSuffix(" entries")
        self._max_spin.setAccessibleName("Maximum history size")
        self._max_spin.valueChanged.connect(
            lambda value: self._store.update(max_items=value)
        )
        max_row.add_control(self._max_spin)
        layout.addWidget(max_row)

        retention_row = FormRow(
            "Retention period",
            "Entries older than this are deleted automatically. Pinned and "
            "favorite entries are always kept.",
        )
        self._retention_combo = QComboBox()
        self._retention_combo.setObjectName("Field")
        self._retention_combo.setAccessibleName("Retention period")
        for days, label in _RETENTION_OPTIONS:
            self._retention_combo.addItem(label, days)
        index = next(
            (i for i, (d, _l) in enumerate(_RETENTION_OPTIONS) if d == settings.retention_days),
            0,
        )
        self._retention_combo.setCurrentIndex(index)
        self._retention_combo.currentIndexChanged.connect(
            lambda i: self._store.update(
                retention_days=self._retention_combo.itemData(i)
            )
        )
        retention_row.add_control(self._retention_combo)
        layout.addWidget(retention_row)

        dup_row = FormRow(
            "Duplicate handling",
            "What happens when you copy text that is already in your history.",
        )
        self._dup_combo = QComboBox()
        self._dup_combo.setObjectName("Field")
        self._dup_combo.setAccessibleName("Duplicate handling")
        self._dup_combo.addItem("Move to top and refresh time", "refresh")
        self._dup_combo.addItem("Ignore duplicate copies", "ignore")
        self._dup_combo.setCurrentIndex(0 if settings.duplicate_handling == "refresh" else 1)
        self._dup_combo.currentIndexChanged.connect(
            lambda i: self._store.update(
                duplicate_handling=self._dup_combo.itemData(i) or DUPLICATE_MODES[0]
            )
        )
        dup_row.add_control(self._dup_combo)
        layout.addWidget(dup_row)

        # Excluded applications -------------------------------------------
        exclusion_card = Card()
        exclusion_layout = QVBoxLayout(exclusion_card)
        exclusion_layout.setContentsMargins(16, 14, 16, 14)
        exclusion_layout.setSpacing(8)
        title = QLabel("Excluded applications")
        title.setProperty("title", True)
        exclusion_layout.addWidget(title)
        hint = QLabel(
            "Copies made while one of these applications is focused are not saved. "
            "Enter the executable name, e.g. 1password.exe.\n"
            "Honest limitation: Windows does not reliably report which application "
            "owns the clipboard, so this is a best-effort guard — it cannot detect "
            "every sensitive field."
        )
        hint.setObjectName("FormHint")
        hint.setWordWrap(True)
        exclusion_layout.addWidget(hint)

        self._exclusion_list = QListWidget()
        self._exclusion_list.setObjectName("Field")
        self._exclusion_list.setFixedHeight(110)
        self._exclusion_list.setAccessibleName("Excluded applications")
        for app_name in settings.excluded_apps:
            self._exclusion_list.addItem(QListWidgetItem(app_name))
        exclusion_layout.addWidget(self._exclusion_list)

        add_row = QHBoxLayout()
        add_row.setSpacing(8)
        self._exclusion_input = QLineEdit()
        self._exclusion_input.setObjectName("Field")
        self._exclusion_input.setPlaceholderText("application.exe")
        self._exclusion_input.setAccessibleName("Application to exclude")
        self._exclusion_input.returnPressed.connect(self._on_add_exclusion)
        add_row.addWidget(self._exclusion_input, 1)
        add_button = QPushButton("Add")
        add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        add_button.clicked.connect(self._on_add_exclusion)
        add_row.addWidget(add_button)
        remove_button = QPushButton("Remove")
        remove_button.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_button.clicked.connect(self._on_remove_exclusion)
        add_row.addWidget(remove_button)
        exclusion_layout.addLayout(add_row)
        layout.addWidget(exclusion_card)
        layout.addStretch(1)
        return page

    def _build_privacy_page(self) -> QWidget:
        page, layout = self._page()

        intro = QLabel(
            "Everything Easy Clipboard Manager stores stays on this computer. There is no "
            "account, cloud sync, analytics or network access — clipboard text "
            "is never uploaded or written to logs."
        )
        intro.setProperty("secondary", True)
        intro.setWordWrap(True)
        layout.addWidget(intro)

        layout.addWidget(
            self._row(
                "Open data folder",
                "Show the local folder containing your database and settings.",
                self._button("Open folder", self.open_data_folder_requested.emit),
            )
        )
        self._storage_path_label = QLabel("")
        self._storage_path_label.setObjectName("FormHint")
        self._storage_path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._storage_path_label.setContentsMargins(14, 0, 0, 4)
        layout.addWidget(self._storage_path_label)

        layout.addWidget(
            self._row(
                "Export clipboard history",
                "Save your history as JSON (with pins and favorites) or plain text.",
                self._button(
                    "Export history…",
                    lambda: self.export_requested.emit("history"),
                ),
            )
        )
        layout.addWidget(
            self._row(
                "Export saved snippets",
                "Back up every snippet with its title, tags and description.",
                self._button(
                    "Export snippets…",
                    lambda: self.export_requested.emit("snippets"),
                ),
            )
        )
        layout.addWidget(
            self._row(
                "Import from file",
                "Import a previous export. Existing entries are never overwritten; "
                "duplicates are skipped.",
                self._button("Import…", self.import_requested.emit),
            )
        )

        danger_card = Card()
        danger_layout = QVBoxLayout(danger_card)
        danger_layout.setContentsMargins(16, 14, 16, 14)
        danger_layout.setSpacing(8)
        danger_title = QLabel("Danger zone")
        danger_title.setProperty("title", True)
        danger_layout.addWidget(danger_title)

        clear_row = QHBoxLayout()
        clear_row.setSpacing(8)
        clear_button = QPushButton("Clear clipboard history")
        clear_button.setObjectName("Danger")
        clear_button.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_button.clicked.connect(self.clear_history_requested.emit)
        clear_row.addWidget(clear_button)
        clear_hint = QLabel("Keeps pinned entries, favorites and snippets.")
        clear_hint.setObjectName("FormHint")
        clear_row.addWidget(clear_hint, 1)
        danger_layout.addLayout(clear_row)

        delete_row = QHBoxLayout()
        delete_row.setSpacing(8)
        delete_all_button = QPushButton("Delete all data")
        delete_all_button.setObjectName("DangerSolid")
        delete_all_button.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_all_button.clicked.connect(self.clear_all_requested.emit)
        delete_row.addWidget(delete_all_button)
        delete_hint = QLabel("Removes history, snippets and settings permanently.")
        delete_hint.setObjectName("FormHint")
        delete_row.addWidget(delete_hint, 1)
        danger_layout.addLayout(delete_row)
        layout.addWidget(danger_card)
        layout.addStretch(1)
        return page

    def _build_about_page(self) -> QWidget:
        page, layout = self._page()
        pal = palette(_theme_name())

        header = QHBoxLayout()
        header.setSpacing(16)
        logo = QLabel()
        logo.setPixmap(render_logo(64, pal.accent))
        logo.setFixedSize(64, 64)
        header.addWidget(logo)
        col = QVBoxLayout()
        col.setSpacing(2)
        name = QLabel("Easy Clipboard Manager")
        name.setProperty("heading", True)
        version = QLabel(f"Version {__version__}")
        version.setProperty("secondary", True)
        col.addWidget(name)
        col.addWidget(version)
        header.addLayout(col, 1)
        layout.addLayout(header)

        description = QLabel(
            "A lightweight, privacy-first clipboard history manager for Windows. "
            "Everything you copy is captured locally, indexed for instant search, "
            "and stays under your control: pin what matters, save snippets, and "
            "clear anything with one click."
        )
        description.setWordWrap(True)
        description.setProperty("secondary", True)
        layout.addWidget(description)

        facts = [
            ("Storage", "Local SQLite database in your user profile — no cloud, no account."),
            ("Network", "Easy Clipboard Manager makes no network requests of any kind."),
            ("Logging", "Diagnostic logs record events only; clipboard text is never logged."),
            ("License", "MIT License."),
            ("Credits", "Built with Python and Qt for Windows (PySide6)."),
        ]
        for label, value in facts:
            layout.addWidget(FormRow(label, value))

        links = QHBoxLayout()
        links.setSpacing(8)
        links.addWidget(
            self._button(
                "Open project repository",
                lambda: self._open_url(
                    "https://github.com/kritagyadubey/Easy-Clipboard-Manager"
                ),
            )
        )
        links.addWidget(
            self._button(
                "Open documentation",
                lambda: self._open_url(
                    "https://github.com/kritagyadubey/Easy-Clipboard-Manager#readme"
                ),
            )
        )
        links.addStretch(1)
        layout.addLayout(links)
        layout.addStretch(1)
        return page

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _button(label: str, slot) -> QPushButton:
        button = QPushButton(label)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(slot)
        return button

    def _row(self, title: str, description: str, control: QWidget) -> FormRow:
        row = FormRow(title, description)
        row.add_control(control)
        return row

    @staticmethod
    def _open_url(url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))

    # ------------------------------------------------------------------
    # Category navigation
    # ------------------------------------------------------------------
    def _select_category(self, key: str) -> None:
        for index, (cat_key, label, _icon) in enumerate(_CATEGORIES):
            self._category_buttons[cat_key].set_checked(cat_key == key)
            if cat_key == key:
                self._stack.setCurrentIndex(index)
                self._page_title.setText(label)

    def _on_category(self, key: str) -> None:
        self._select_category(key)

    # ------------------------------------------------------------------
    # Control handlers
    # ------------------------------------------------------------------
    def _on_startup_toggled(self, checked: bool) -> None:
        ok = autostart.set_enabled(checked)
        self._store.update(launch_at_startup=checked and ok)
        if checked and not ok:
            self._hotkey_status.setText(
                "Could not update the Windows startup entry."
            )
            self._startup_switch.set_checked(False, animate=False)

    def _on_record_hotkey(self) -> None:
        self._record_button.setEnabled(False)
        self._record_button.setText("Press keys…")
        dialog = _HotkeyCaptureDialog(self)
        dialog.captured.connect(self._apply_hotkey)
        dialog.exec()
        self._record_button.setEnabled(True)
        self._record_button.setText("Record")

    def _apply_hotkey(self, combo: str) -> None:
        self._store.update(global_hotkey=combo)
        self._hotkey_field.setText(format_hotkey(combo))
        # The application re-registers via its settings listener; verify here.
        app = QApplication.instance()
        hotkey = getattr(app, "global_hotkey", None)
        if hotkey is None:
            return
        if hotkey.is_registered:
            self._hotkey_status.setText(
                f"Active — press {format_hotkey(combo)} from any window."
            )
            self._hotkey_status.setStyleSheet("")
        else:
            self._hotkey_status.setText(
                f"“{format_hotkey(combo)}” is already in use by another program. "
                "Choose a different combination."
            )
            self.hotkey_conflict.emit(combo)

    def _on_add_exclusion(self) -> None:
        name = self._exclusion_input.text().strip().lower()
        if not name:
            return
        existing = [
            self._exclusion_list.item(i).text()
            for i in range(self._exclusion_list.count())
        ]
        if name not in existing:
            self._exclusion_list.addItem(QListWidgetItem(name))
        self._exclusion_input.clear()
        self._persist_exclusions()

    def _on_remove_exclusion(self) -> None:
        for item in self._exclusion_list.selectedItems():
            self._exclusion_list.takeItem(self._exclusion_list.row(item))
        self._persist_exclusions()

    def _persist_exclusions(self) -> None:
        apps = [
            self._exclusion_list.item(i).text()
            for i in range(self._exclusion_list.count())
        ]
        self._store.update(excluded_apps=apps)

    def _on_settings_external_change(self, settings: Settings) -> None:
        """Keep the dialog in sync when the app changes settings elsewhere."""
        self._startup_switch.set_checked(settings.launch_at_startup, animate=False)
        self._tray_switch.set_checked(settings.minimize_to_tray, animate=False)
        self._start_minimized_switch.set_checked(settings.start_minimized, animate=False)
        self._monitoring_switch.set_checked(settings.monitoring_enabled, animate=False)
        self._hotkey_field.setText(format_hotkey(settings.global_hotkey))
        if self._max_spin.value() != settings.max_items:
            self._max_spin.setValue(settings.max_items)
        index = next(
            (
                i
                for i, (days, _label) in enumerate(_RETENTION_OPTIONS)
                if days == settings.retention_days
            ),
            -1,
        )
        if index >= 0 and self._retention_combo.currentIndex() != index:
            self._retention_combo.setCurrentIndex(index)
        dup_index = 0 if settings.duplicate_handling == "refresh" else 1
        if self._dup_combo.currentIndex() != dup_index:
            self._dup_combo.setCurrentIndex(dup_index)
        current_apps = [
            self._exclusion_list.item(i).text()
            for i in range(self._exclusion_list.count())
        ]
        if current_apps != list(settings.excluded_apps):
            self._exclusion_list.clear()
            for app_name in settings.excluded_apps:
                self._exclusion_list.addItem(QListWidgetItem(app_name))

    # ------------------------------------------------------------------
    def show_storage_path(self, path: str) -> None:
        self._storage_path_label.setText(path)

    def show_hotkey_status(self, registered: bool, combo: str) -> None:
        if registered:
            self._hotkey_status.setText(
                f"Active — press {format_hotkey(combo)} from any window."
            )
        else:
            self._hotkey_status.setText(
                f"“{format_hotkey(combo)}” could not be registered. It may be in "
                "use by another program."
            )


class _HotkeyCaptureDialog(QDialog):
    """Modal helper that captures the next pressed key combination."""

    captured = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Record shortcut")
        self.setFixedSize(340, 150)
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)
        label = QLabel("Press the new shortcut…")
        label.setObjectName("TitleLabel")
        label.setProperty("title", True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        hint = QLabel("Esc cancels. Include at least one modifier (Ctrl, Alt, Shift).")
        hint.setObjectName("HintLabel")
        hint.setProperty("muted", True)
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)
        cancel = QPushButton("Cancel")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(cancel)
        row.addStretch(1)
        layout.addLayout(row)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key in (Qt.Key.Key_unknown, Qt.Key.Key_Escape):
            self.reject()
            return
        modifiers = event.modifiers()
        parts = []
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            parts.append("Ctrl")
        if modifiers & Qt.KeyboardModifier.AltModifier:
            parts.append("Alt")
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            parts.append("Shift")
        if modifiers & Qt.KeyboardModifier.MetaModifier:
            parts.append("Win")
        key_name = QKeySequence(key).toString()
        if not key_name:
            self.reject()
            return
        if not parts:
            hint = self.findChild(QLabel)
            if hint is not None:
                hint.setText("Add a modifier: Ctrl, Alt, Shift or Win.")
            return
        parts.append(key_name)
        self.captured.emit("+".join(parts))
        self.accept()
