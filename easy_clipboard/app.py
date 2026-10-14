"""Application composition root.

Creates and wires every subsystem: settings, storage, clipboard monitoring,
the global hotkey, the system tray and the main window.
"""

from __future__ import annotations

import argparse
import sys
import threading
import traceback

from PySide6.QtCore import QObject, QTimer, Signal
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


class _ShowBridge(QObject):
    """Marshals "show the window" requests from the single-instance thread.

    The named-event listener lives in a plain Python thread with no Qt
    event loop, so it cannot call Qt directly (a ``QTimer.singleShot``
    posted from there never fires).  Emitting a Qt signal is thread-safe:
    the slot runs on the GUI thread via a queued connection.
    """

    requested = Signal()


def _install_excepthook() -> None:
    """Log unexpected exceptions and show the user one friendly dialog."""
    previous = sys.excepthook
    shown = False

    def _hook(exc_type, exc, tb) -> None:
        nonlocal shown
        try:
            log.error(
                "Unhandled exception:\n%s",
                "".join(traceback.format_exception(exc_type, exc, tb)),
            )
        except Exception:  # noqa: BLE001 - logging must never raise here
            pass
        if not shown:
            shown = True
            try:
                if QApplication.instance() is not None:
                    QMessageBox.critical(
                        None,
                        f"{APP_NAME} — unexpected error",
                        "Something went wrong, but the error was recorded in "
                        "the diagnostic log.\n\n"
                        "You can open the log folder from Settings → "
                        "Privacy & data → Open data folder.",
                    )
            except Exception:  # noqa: BLE001 - never raise while handling a crash
                pass
        if previous is not None:
            previous(exc_type, exc, tb)

    sys.excepthook = _hook


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
    _install_excepthook()
    log.info("Starting %s %s", APP_NAME, __version__)

    # Only one instance may run at a time ---------------------------------
    instance = SingleInstance()
    if not instance.acquire():
        log.info("Another instance is running; requesting it to show its window")
        return 0

    # Buffer "show my window" requests that arrive before Qt is ready (the
    # named-event listener runs from the moment acquire() succeeds).
    _show_lock = threading.Lock()
    _early_show = threading.Event()
    _bridge_cell: dict[str, _ShowBridge | None] = {"bridge": None}

    def _on_show_request() -> None:
        with _show_lock:
            bridge = _bridge_cell["bridge"]
            if bridge is None:
                _early_show.set()
        if bridge is not None:
            # Thread-safe: emitted over a queued connection to the GUI thread.
            bridge.requested.emit()

    instance.set_show_handler(_on_show_request)

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
    app.tray_available = tray_available

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
    # (Without a tray there is nothing to connect; MainWindow checks
    # app.tray_available in closeEvent and quits instead of hiding.  The
    # user's minimize_to_tray preference is deliberately NOT rewritten —
    # a headless session is a per-run condition, not a preference.)

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
    def run_maintenance() -> None:
        try:
            # Retention must run even when no new copies happened, and the
            # sidebar counts must refresh either way (refreshing only when
            # entries were removed used to be skipped exactly when it was
            # needed, because `run_pending_trim() or refresh()` short-circuits
            # on a non-zero removal count).
            history.run_pending_trim()
            history.trim_history()
        except Exception:  # noqa: BLE001 - maintenance must never crash the app
            log.exception("Periodic history maintenance failed")
        try:
            window.refresh_sidebar_counts()
        except Exception:  # noqa: BLE001
            log.exception("Sidebar count refresh failed")

    trim_timer = QTimer()
    trim_timer.setInterval(TRIM_INTERVAL_MS)
    trim_timer.timeout.connect(run_maintenance)
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
    # (QTimer.singleShot from the listener thread never fires: that thread
    # has no Qt event loop.  A signal emitted there is queued to the GUI
    # thread instead, which works.)
    show_bridge = _ShowBridge()
    show_bridge.requested.connect(window.bring_to_front)
    with _show_lock:
        _bridge_cell["bridge"] = show_bridge
        pending_show = _early_show.is_set()
    if pending_show:
        show_bridge.requested.emit()

    code = app.exec()
    # Defensive cleanup if the app quit without going through exit_app.
    monitor.stop()
    hotkey.shutdown()
    database.close()
    instance.release()
    log.info("Shutdown complete (exit code %s)", code)
    return int(code)
