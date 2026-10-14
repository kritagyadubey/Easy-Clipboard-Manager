"""System tray icon and menu."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .. import APP_NAME
from ..logging_setup import get_logger
from .theme import palette, render_logo

log = get_logger("tray")


class TrayController(QObject):
    """Owns the QSystemTrayIcon and translates menu clicks into signals."""

    open_requested = Signal()
    monitoring_toggle_requested = Signal()
    show_pinned_requested = Signal()
    show_snippets_requested = Signal()
    clear_history_requested = Signal()
    settings_requested = Signal()
    exit_requested = Signal()

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._tray: Optional[QSystemTrayIcon] = None
        self._menu: Optional[QMenu] = None
        self._monitoring_action: Optional[QAction] = None
        self._available = False

    # ------------------------------------------------------------------
    @property
    def available(self) -> bool:
        return self._available

    def create(self) -> bool:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            log.warning("No system tray available in this session")
            return False
        # NOTE: QSystemTrayIcon takes (icon, parent) or (parent) — a bare
        # string for the first positional argument raises TypeError.  The
        # app name belongs in the tooltip.
        self._tray = QSystemTrayIcon(self)
        self._tray.setToolTip(APP_NAME)
        self._menu = QMenu()
        self._build_menu()
        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_activated)
        self.apply_theme()
        self._tray.show()
        self._available = True
        return True

    def _build_menu(self) -> None:
        assert self._menu is not None
        self._menu.addAction("Open Easy Clipboard Manager", self.open_requested.emit)
        self._menu.addSeparator()

        self._monitoring_action = QAction("Pause monitoring", self)
        self._monitoring_action.triggered.connect(self.monitoring_toggle_requested)
        self._menu.addAction(self._monitoring_action)

        self._menu.addAction("Pinned items", self.show_pinned_requested.emit)
        self._menu.addAction("Saved snippets", self.show_snippets_requested.emit)
        self._menu.addSeparator()
        self._menu.addAction("Clear history…", self.clear_history_requested.emit)
        self._menu.addAction("Settings", self.settings_requested.emit)
        self._menu.addSeparator()
        self._menu.addAction("Exit", self.exit_requested.emit)

    # ------------------------------------------------------------------
    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.open_requested.emit()

    def set_monitoring(self, enabled: bool) -> None:
        if self._monitoring_action is not None:
            self._monitoring_action.setText(
                "Pause monitoring" if enabled else "Resume monitoring"
            )

    def show_notification(self, title: str, message: str) -> None:
        if self._tray is not None:
            self._tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 2500)

    def apply_theme(self) -> None:
        pal = palette(self._theme_name())
        if self._tray is not None:
            icon = render_logo(64, pal.accent)
            self._tray.setIcon(icon)
        if self._menu is not None:
            self._menu.setStyleSheet("")

    def hide(self) -> None:
        if self._tray is not None:
            self._tray.hide()

    @staticmethod
    def _theme_name() -> str:
        app = QApplication.instance()
        return getattr(app, "theme_name", "dark") if app else "dark"
