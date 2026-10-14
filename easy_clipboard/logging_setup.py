"""Diagnostic logging that never records clipboard contents.

Privacy rule: this module (and everything that uses it) must only ever log
metadata — never the text of a clipboard entry or a saved snippet.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys

from . import __version__
from .paths import log_path

_CONFIGURED = False

# Messages that are known to be content-free are logged normally.  Anything
# else is expected to be pre-formatted by the caller with metadata only.
LOGGER_NAME = "easy_clipboard"


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure file + stderr logging. Safe to call more than once."""
    global _CONFIGURED
    logger = logging.getLogger(LOGGER_NAME)
    if _CONFIGURED:
        return logger

    level = logging.DEBUG if verbose else logging.INFO
    logger.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_path(), maxBytes=512 * 1024, backupCount=2, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        logger.addHandler(file_handler)
    except OSError:
        # A broken log location must never prevent the app from starting.
        pass

    # In a windowed (no-console) build sys.stderr can be None; a stream
    # handler pointing at None would fail on every emit.
    if sys.stderr is not None:
        stream_handler = logging.StreamHandler(stream=sys.stderr)
        stream_handler.setFormatter(formatter)
        stream_handler.setLevel(logging.WARNING)
        logger.addHandler(stream_handler)

    logger.debug("Easy Clipboard Manager %s starting", __version__)
    _CONFIGURED = True
    return logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"{LOGGER_NAME}.{name}")
