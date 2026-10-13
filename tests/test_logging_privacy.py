"""Privacy guarantee: clipboard contents never reach the log file."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from easy_clipboard import logging_setup

SECRET = "S3cr3t-password-do-not-log"
SNIPPET_TEXT = "private snippet body 4242"


@pytest.fixture()
def log_file(settings_path: Path, monkeypatch):
    """Route the application log into a temp file for inspection."""
    target = settings_path.parent / "privacy-test.log"
    monkeypatch.setattr(logging_setup, "log_path", lambda: target)

    logging_setup._CONFIGURED = False
    logger = logging_setup.setup_logging(verbose=True)
    yield target
    # Remove handlers so later tests do not write into this file.
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
    logging_setup._CONFIGURED = False


def test_setup_logging_returns_the_app_logger(log_file: Path):
    assert log_file.exists()
    logger = logging_setup.get_logger("unit")
    assert logger.name.startswith(logging_setup.LOGGER_NAME)


def test_history_capture_never_logs_clipboard_text(log_file: Path, history):
    history.capture(SECRET, source_app="keepassxc.exe")
    history.capture(SECRET + " copy two", source_app="keepassxc.exe")
    history.create_snippet("Private", SNIPPET_TEXT)
    history.clear_history(keep_protected=False)

    for handler in logging.getLogger(logging_setup.LOGGER_NAME).handlers:
        handler.flush()

    text = log_file.read_text(encoding="utf-8")
    assert SECRET not in text
    assert SNIPPET_TEXT not in text
    assert "private snippet body" not in text
    # Metadata *is* logged, proving the logger actually ran.
    assert "Captured entry" in text


def test_skipped_capture_logs_metadata_only(log_file: Path, history, settings_store):
    settings_store.update(excluded_apps=["keepass"])
    history.capture(SECRET, source_app="KeePass.exe")
    huge = "x" * 600_000
    history.capture(huge, source_app="notepad.exe")

    for handler in logging.getLogger(logging_setup.LOGGER_NAME).handlers:
        handler.flush()

    text = log_file.read_text(encoding="utf-8")
    assert SECRET not in text
    assert huge not in text
    assert "excluded_app" in text
    assert "too_large" in text


def test_settings_errors_do_not_leak_to_log_as_content(log_file: Path, settings_store):
    # Simulates a listener failure: the traceback is logged, but the
    # settings snapshot (which could contain private app names) is not.
    def bad_listener(settings):
        raise RuntimeError("boom")

    settings_store.add_listener(bad_listener)
    settings_store.update(excluded_apps=["super-secret-app.exe"])

    for handler in logging.getLogger(logging_setup.LOGGER_NAME).handlers:
        handler.flush()

    text = log_file.read_text(encoding="utf-8")
    assert "super-secret-app.exe" not in text
