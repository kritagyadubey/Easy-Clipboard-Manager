"""Application composition root.

Creates and wires every subsystem: settings, storage, clipboard monitoring,
the global hotkey, the system tray and the main window.
"""

from __future__ import annotations

import argparse
import sys
import traceback

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from . import APP_NAME, __version__
from .clipboard import ClipboardMonitor
from .history import HistoryService
from .logging_setup import get_logger, setup_logging
from .settings import SettingsStore
from .storage import Database, DatabaseError
from .ui import theme as theme_mod
from .ui.main_window import MainWindow
from .ui.tray import TrayController
from .windows import autostart
from .windows.hotkey import GlobalHotkey
from .windows.single_instance import SingleInstance
from .windows.window_info import get_foreground_process

log = get_logger("app")

TRIM_INTERVAL_MS = 5 * 60 * 1000


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="easy-clipboard-manager", add_help=True)
    parser.add_argument(
        "--background",
        action="store_true",
        help="start minimised in the system tray",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="write debug-level diagnostics"
    )
    return parser.parse_args(argv)


def _offer_database_recovery(exc: DatabaseError) -> bool:
    """Ask the user what to do about an unusable database. True = retry."""
    box = QMessageBox(
        QMessageBox.Icon.Critical,
        f"{APP_NAME} — storage problem",
        "The clipboard database could not be opened.\n\n"
        f"{exc}\n\n"
        "Choose “Reset database” to delete the damaged file and start with an "
        "empty history, or exit the application.",
    )
    reset = box.addButton("Reset database", QMessageBox.ButtonRole.DestructiveRole)
    box.addButton(QMessageBox.StandardButton.Close)
    box.exec()
    return box.clickedButton() is reset


def run(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    setup_logging(verbose=args.verbose)
    log.info("Starting %s %s", APP_NAME, __version__)

    # Only one instance may run at a time ---------------------------------
    instance = SingleInstance()
    if not instance.acquire():
        log.info("Another instance is running; requesting it to show its window")
        return 0

    # Qt application -------------------------------------------------------
    QApplication.setOrganizationName("EasyClipboardManager")
    QApplication.setApplicationName(APP_NAME)
    QApplication.setApplicationVersion(__version__)
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    theme_mod.apply_application_font(app)

    from .paths import db_path, settings_path

    settings_store = SettingsStore(settings_path())
    settings = settings_store.get()
    app.theme_name = theme_mod.resolve_theme(settings.theme)
    pal = theme_mod.palette(app.theme_name)
    app.setStyleSheet(theme_mod.build_stylesheet(pal, settings.density))
    app.setWindowIcon(theme_mod.render_logo(64, pal.accent))

    # Storage ---------------------------------------------------------------
    from pathlib import Path

    def open_database() -> Database | None:
        while True:
            try:
                return Database(db_path())
            except DatabaseError as exc:
                log.error("Database unavailable: %s", exc)
                if not _offer_database_recovery(exc):
                    return None
                _quarantine_database()
                continue

    def _quarantine_database() -> None:
        target = db_path()
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(target) + suffix) if suffix else target
            try:
                if candidate.exists():
                    broken = candidate.with_name(candidate.name + ".broken")
                    if broken.exists():
                        broken.unlink()
                    candidate.replace(broken)
            except OSError:
                log.exception("Could not move damaged database file aside")

    database = open_database()
    if database is None:
        log.error("Exiting: no usable database")
        instance.release()
        return 1

    history = HistoryService(database, settings_store)

    # Keep the Start-with-Windows entry in sync with the stored preference.
    if settings.launch_at_startup:
        autostart.set_enabled(True)

    # Main window ------------------------------------------------------------
    window = MainWindow(settings_store, history)
    app.main_window = window

    # Tray -------------------------------------------------------------------
    tray = TrayController()
    tray_available = tray.create()
    tray.set_monitoring(settings.monitoring_enabled)

    # Clipboard monitor --------------------------------------------------------
    monitor = ClipboardMonitor()
    monitor.set_source_resolver(get_foreground_process)

    def on_captured(text: str, source_app: str) -> None:
        try:
            window.on_clipboard_captured(text, source_app)
        except Exception:  # noqa: BLE001 - capture must never crash the app
            log.error("Failed to store a captured entry:\n%s", traceback.format_exc())

    monitor.text_captured.connect(on_captured)
    monitor.monitor_error.connect(window.on_monitor_error)
    if settings.monitoring_enabled:
        monitor.start()
    else:
        monitor.start()
        monitor.set_paused(True)
    app.clipboard_monitor = monitor

    # Global hotkey -------------------------------------------------------------
    hotkey = GlobalHotkey()
    hotkey.activated.connect(window.bring_to_front)
    hotkey.register(settings.global_hotkey)
    app.global_hotkey = hotkey

    # Tray behaviour --------------------------------------------------------------
    def show_window() -> None:
        window.bring_to_front()

    def exit_app() -> None:
        log.info("Exiting on request from the tray")
        monitor.stop()
        hotkey.shutdown()
        window._save_geometry()
        tray.hide()
        database.close()
        instance.release()
        app.quit()

    if tray_available:
        tray.open_requested.connect(show_window)
        tray.monitoring_toggle_requested.connect(window.toggle_monitoring)
        tray.show_pinned_requested.connect(lambda: (window.show(), window.bring_to_front(), window.show_section("pinned")))
        tray.show_snippets_requested.connect(lambda: (window.show(), window.bring_to_front(), window.show_section("snippets")))
        tray.clear_history_requested.connect(window.clear_history)
        tray.settings_requested.connect(lambda: (window.bring_to_front(), window.open_settings()))
        tray.exit_requested.connect(exit_app)
    else:
        # Without a tray, closing the window must quit the application.
        settings_store.update(minimize_to_tray=False)

    # Keep every subsystem in sync with persisted settings ------------------------
    def on_settings_changed(new_settings) -> None:
        monitor.set_paused(not new_settings.monitoring_enabled)
        tray.set_monitoring(new_settings.monitoring_enabled)
        if hotkey.combo != new_settings.global_hotkey:
            hotkey.register(new_settings.global_hotkey)
            if not hotkey.is_registered and new_settings.global_hotkey:
                tray.show_notification(
                    "Shortcut unavailable",
                    f"{new_settings.global_hotkey} is in use by another program.",
                )
        window.apply_settings(new_settings)

    settings_store.add_listener(on_settings_changed)

    # Periodic maintenance: retention + size limits ---------------------------------
    trim_timer = QTimer()
    trim_timer.setInterval(TRIM_INTERVAL_MS)
    trim_timer.timeout.connect(
        lambda: history.run_pending_trim() or window.refresh_sidebar_counts()
    )
    trim_timer.start()

    # Apply startup state ------------------------------------------------------------
    if args.background or settings.start_minimized:
        window.hide()
        if tray_available:
            tray.show_notification(
                APP_NAME, "Running in the system tray — clipboard monitoring is active."
            )
    else:
        window.show()

    # A second launch asks us to surface the window ------------------------------------
    instance.set_show_handler(lambda: QTimer.singleShot(0, window.bring_to_front))

    code = app.exec()
    # Defensive cleanup if the app quit without going through exit_app.
    monitor.stop()
    hotkey.shutdown()
    database.close()
    instance.release()
    log.info("Shutdown complete (exit code %s)", code)
    return int(code)
