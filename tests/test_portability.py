"""Export / import round trips and the additive-only guarantee."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from easy_clipboard import portability
from easy_clipboard.models import ContentType, Snippet
from easy_clipboard.portability import ImportError_


def _seed(db):
    from easy_clipboard.models import ClipItem

    items = [
        db.add_item(ClipItem(content="plain text", content_type=ContentType.TEXT)),
        db.add_item(ClipItem(content="https://example.com",
                             content_type=ContentType.LINK, is_pinned=True)),
        db.add_item(ClipItem(content="emoji 🎉 payload 中文",
                             content_type=ContentType.TEXT, is_favorite=True)),
    ]
    snippet = db.add_snippet(Snippet(title="Sign-off", content="Best regards"))
    return items, [snippet]


# ----------------------------------------------------------------------
# JSON
# ----------------------------------------------------------------------
def test_json_roundtrip_preserves_everything(database, tmp_path: Path):
    items, snippets = _seed(database)
    out = tmp_path / "backup.json"
    assert portability.export_json(items, snippets, out) == 4

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["format"] == portability.EXPORT_FORMAT
    assert payload["version"] == 1
    assert len(payload["items"]) == 3

    # Import into a brand-new, empty database.
    from easy_clipboard.storage import Database

    other_db = Database(tmp_path / "other.db")
    result = portability.import_from_file(out, other_db)
    assert result.added_items == 3
    assert result.added_snippets == 1
    assert result.errors == []

    restored = {i.content: i for i in other_db.get_items()}
    assert set(restored) == {"plain text", "https://example.com", "emoji 🎉 payload 中文"}
    assert restored["https://example.com"].is_pinned
    assert restored["emoji 🎉 payload 中文"].is_favorite
    assert restored["plain text"].content_type is ContentType.TEXT
    assert other_db.get_snippets()[0].title == "Sign-off"
    other_db.close()


def test_json_import_is_additive_and_skips_duplicates(database, tmp_path: Path):
    items, snippets = _seed(database)
    out = tmp_path / "backup.json"
    portability.export_json(items, snippets, out)

    before = database.count_items()
    result = portability.import_from_file(out, database)
    # Everything already exists -> nothing added, nothing overwritten.
    assert result.added_items == 0
    assert result.added_snippets == 0
    assert result.skipped_duplicates == 4
    assert database.count_items() == before
    # Pins/favourites on the original rows are untouched.
    assert database.get_items(section="pinned")[0].content == "https://example.com"


def test_json_import_partial_overlap(database, tmp_path: Path):
    payload = {
        "format": portability.EXPORT_FORMAT,
        "version": 1,
        "items": [
            {"content": "already here"},
            {"content": "brand new"},
            {"content": ""},           # invalid -> skipped
            {"content": 42},           # invalid -> skipped
            "not an object",           # invalid -> skipped
        ],
        "snippets": [],
    }
    path = tmp_path / "partial.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    from easy_clipboard.models import ClipItem

    database.add_item(ClipItem(content="already here"))
    result = portability.import_from_file(path, database)
    assert result.added_items == 1
    assert result.invalid_entries == 3
    assert result.skipped_duplicates == 1
    assert {i.content for i in database.get_items()} == {"already here", "brand new"}


# ----------------------------------------------------------------------
# Text format
# ----------------------------------------------------------------------
def test_text_roundtrip(database, tmp_path: Path):
    items, _ = _seed(database)
    out = tmp_path / "backup.txt"
    assert portability.export_text(items, out) == 3
    text = out.read_text(encoding="utf-8")
    assert "plain text" in text
    assert "[pinned]" in text

    from easy_clipboard.storage import Database

    other_db = Database(tmp_path / "text-import.db")
    result = portability.import_from_file(out, other_db)
    assert result.added_items == 3
    contents = {i.content for i in other_db.get_items()}
    assert "plain text" in contents
    assert "https://example.com" in contents
    assert "emoji 🎉 payload 中文" in contents
    other_db.close()


def test_text_import_skips_duplicates(database, tmp_path: Path):
    items, _ = _seed(database)
    out = tmp_path / "backup.txt"
    portability.export_text(items, out)
    before = database.count_items()
    result = portability.import_from_file(out, database)
    assert result.added_items == 0
    assert result.skipped_duplicates == 3
    assert database.count_items() == before


# ----------------------------------------------------------------------
# Error handling
# ----------------------------------------------------------------------
def test_import_missing_file(database, tmp_path: Path):
    with pytest.raises(ImportError_):
        portability.import_from_file(tmp_path / "nope.json", database)


def test_import_malformed_json(database, tmp_path: Path):
    path = tmp_path / "broken.json"
    path.write_text("{ this is not json", encoding="utf-8")
    with pytest.raises(ImportError_):
        portability.import_from_file(path, database)
    assert database.count_items() == 0


def test_import_wrong_format_tag(database, tmp_path: Path):
    path = tmp_path / "foreign.json"
    path.write_text(
        json.dumps({"format": "someone-elses-app", "items": []}), encoding="utf-8"
    )
    with pytest.raises(ImportError_):
        portability.import_from_file(path, database)


def test_import_unexpected_structure(database, tmp_path: Path):
    path = tmp_path / "list.json"
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with pytest.raises(ImportError_):
        portability.import_from_file(path, database)

    path2 = tmp_path / "wrongtypes.json"
    path2.write_text(
        json.dumps({"format": portability.EXPORT_FORMAT, "items": "nope"}),
        encoding="utf-8",
    )
    with pytest.raises(ImportError_):
        portability.import_from_file(path2, database)


def test_import_bom_and_empty_text_file(database, tmp_path: Path):
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")
    result = portability.import_from_file(path, database)
    assert result.added_items == 0
    assert database.count_items() == 0


def test_import_result_summary_is_human_readable():
    result = portability.ImportResult(added_items=3, skipped_duplicates=2)
    assert "3 clipboard entries" in result.summary
    assert "2 duplicates skipped" in result.summary
    assert portability.ImportResult().summary == "nothing new to import"
