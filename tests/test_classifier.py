"""Content-type detection."""

from __future__ import annotations

import pytest

from easy_clipboard.classifier import detect_type, is_probably_link
from easy_clipboard.models import ContentType


@pytest.mark.parametrize(
    "text,expected",
    [
        ("https://github.com/kritagyadubey/Easy-Clipboard-Manager", ContentType.LINK),
        ("http://example.com/path?q=1", ContentType.LINK),
        ("www.example.com", ContentType.LINK),
        ("example.com", ContentType.LINK),
        ("user@example.com", ContentType.EMAIL),
        ("first.last+tag@sub.domain.co.uk", ContentType.EMAIL),
        ("42", ContentType.NUMBER),
        ("-3.14159", ContentType.NUMBER),
        ("1.2e10", ContentType.NUMBER),
        ('{"a": 1, "b": [2, 3]}', ContentType.JSON),
        ('[{"id": 1}, {"id": 2}]', ContentType.JSON),
        ("def add(a, b):\n    return a + b", ContentType.CODE),
        ("function greet() {\n  console.log('hi');\n}", ContentType.CODE),
        ("git commit -m 'fix' && git push", ContentType.CODE),
        ("line one\nline two", ContentType.MULTILINE),
        ("hello world", ContentType.TEXT),
        ("", ContentType.TEXT),
        ("   ", ContentType.TEXT),
        ("SELECT id FROM items ORDER BY created_at DESC;", ContentType.CODE),
        ("#include <stdio.h>\nint main() { return 0; }", ContentType.CODE),
    ],
)
def test_detect_type(text, expected):
    assert detect_type(text) == expected


def test_plain_prose_is_not_code():
    assert detect_type("The quarterly report is ready for review by the team.") == (
        ContentType.TEXT
    )


def test_long_multiline_is_still_fast():
    text = "\n".join(f"paragraph {i} with ordinary words" for i in range(5000))
    assert detect_type(text) == ContentType.MULTILINE


def test_is_probably_link():
    assert is_probably_link("https://example.com")
    assert not is_probably_link("just some text")


def test_multiline_url_is_not_link():
    assert detect_type("https://example.com\nhttps://example.org") != ContentType.LINK
