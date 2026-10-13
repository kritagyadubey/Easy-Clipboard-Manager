"""Content-type detection for captured clipboard text.

The classifier only inspects text — it never modifies it.  Detection is
deliberately conservative: when in doubt an entry is treated as ordinary
text, which is always safe to display and copy back.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from .models import ContentType

_URL_RE = re.compile(
    r"^(?:(?:https?|ftp|file|mailto|ws|wss)://|www\.)\S+$", re.IGNORECASE
)
# Bare domains such as "example.com" or "docs.python.org/3/library"
_DOMAIN_RE = re.compile(
    r"^(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}(?::\d{2,5})?(?:[/?#]\S*)?$"
)
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")
_NUMBER_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?%?$")

# Indicators that strongly suggest source code rather than prose.
_CODE_TOKENS = (
    ";", "{}", "();", "=>", "&&", "||", "!=", "===", "//", "/*", "*/",
    "#include", "def ", "class ", "import ", "return ", "function ",
    "const ", "let ", "var ", "public ", "private ", "void ", "printf(",
    "console.log", "<?php", "<html", "</", "git ", "sudo ", "npm ",
)
_CODE_LINE_RE = re.compile(
    r"^\s*(?:def |class |import |from |return |if |for |while |public |private "
    r"|void |const |let |var |function |#include|using |package )"
)

# Maximum characters scanned for JSON / code detection (keeps huge pastes fast).
_ANALYSIS_LIMIT = 200_000


def _looks_like_url(text: str) -> bool:
    if "\n" in text or len(text) > 2048:
        return False
    if _URL_RE.match(text):
        candidate = text if "://" in text else f"https://{text}"
        parsed = urlparse(candidate)
        host = parsed.hostname or ""
        return "." in host and all(part.strip() for part in host.split("."))
    # Bare domain — never confuse it with an email address.
    if "@" in text:
        return False
    return bool(_DOMAIN_RE.match(text))


def _looks_like_json(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 2 or len(stripped) > _ANALYSIS_LIMIT:
        return False
    if stripped[0] not in "[{":
        return False
    try:
        parsed = json.loads(stripped)
    except (ValueError, RecursionError):
        return False
    return isinstance(parsed, (dict, list))


def _looks_like_code(text: str) -> bool:
    sample = text[:_ANALYSIS_LIMIT]
    lines = sample.splitlines()
    if not lines:
        return False

    hits = 0
    for token in _CODE_TOKENS:
        if token in sample:
            hits += 1
    if hits >= 2:
        return True
    if hits == 1 and ("\n" in sample or ";" in sample or "{" in sample):
        return True

    code_lines = sum(1 for line in lines[:50] if _CODE_LINE_RE.match(line))
    if code_lines >= 2:
        return True

    # Deep indentation or tab indentation is a strong code signal.
    indented = sum(1 for line in lines[:50] if line.startswith(("    ", "\t")))
    if "\n" in sample and indented >= 2 and hits >= 1:
        return True
    return False


def detect_type(text: str) -> ContentType:
    """Classify a piece of clipboard text."""
    if not text:
        return ContentType.TEXT

    stripped = text.strip()
    if not stripped:
        return ContentType.TEXT

    if _looks_like_url(stripped):
        return ContentType.LINK
    if _EMAIL_RE.match(stripped):
        return ContentType.EMAIL
    if _NUMBER_RE.match(stripped):
        return ContentType.NUMBER
    if _looks_like_json(stripped):
        return ContentType.JSON

    has_newline = "\n" in text
    if _looks_like_code(text):
        return ContentType.CODE
    if has_newline:
        return ContentType.MULTILINE
    return ContentType.TEXT


def is_probably_link(text: str) -> bool:
    """Helper used by the preview panel to enable an 'open link' affordance."""
    return detect_type(text.strip()) == ContentType.LINK
