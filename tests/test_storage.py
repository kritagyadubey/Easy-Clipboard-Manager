"""Storage layer: persistence, duplicates, limits, retention, unicode safety."""

from __future__ import annotations

import time

import pytest

from easy_clipboard.models import ClipItem, ContentType, Snippet, content_hash
from easy_clipboard.storage import Database


def make(text: str, **kw) -> ClipItem:
    kw.setdefault("content_type", ContentType.TEXT)
    return ClipItem(content=text, **kw)


# ----------------------------------------------------------------------
# Basics
# ----------------------------------------------------------------------
def test_add_and_get(database: Database):
    item = database.add_item(make("hello world"))
    assert item.id is not None
    fetched = database.get_item(item.id)
    assert fetched is not None
    assert fetched.content == "hello world"
    assert fetched.content_type == ContentType.TEXT


def test_find_by_hash(database: Database):
    database.add_item(make("abc"))
    found = database.find_by_hash(content_hash("abc"))
    assert found is not None
    assert found.content == "abc"
    assert database.find_by_hash(content_hash("nope")) is None


def test_persistence_across_reopen(data_dir):
    from easy_clipboard.storage import Database

    db = Database(data_dir / "persist.db")
    db.add_item(make("survives restart"))
    db.close()

    db2 = Database(data_dir / "persist.db")
    items = db2.get_items()
    assert len(items) == 1
    assert items[0].content == "survives restart"
    db2.close()


def test_unicode_and_long_content(database: Database):
    text = ("héllo wörld — 你好 🎉\n" * 50) + "x" * 100_000
    item = database.add_item(make(text))
    assert database.get_item(item.id).content == text


# ----------------------------------------------------------------------
# Duplicates
# ----------------------------------------------------------------------
def test_duplicate_add_refreshes_timestamp(database: Database):
    first = database.add_item(make("dup", created_at=100.0, last_copied_at=100.0))
    second = database.add_item(make("dup", created_at=200.0, last_copied_at=200.0))
    assert first.id == second.id
    assert second.copy_count == 2
    assert second.last_copied_at == 200.0
    assert len(database.get_items()) == 1


# ----------------------------------------------------------------------
# Sections, search, sorting
# ----------------------------------------------------------------------
@pytest.fixture()
def seeded(database: Database):
    from easy_clipboard.classifier import detect_type

    base = time.time()
    rows = [
        ("alpha one", base - 30),
        ("https://example.com", base - 20),
        ("gamma def f(): pass", base - 10),
    ]
    items = {}
    for text, ts in rows:
        items[text] = database.add_item(
            ClipItem(
                content=text,
                content_type=detect_type(text),
                created_at=ts,
                last_copied_at=ts,
            )
        )
    database.set_pinned(items["alpha one"].id, True)
    database.set_favorite(items["https://example.com"].id, True)
    items["types"] = {t: detect_type(t).value for t, _ in rows}
    return items


def test_section_pinned(database: Database, seeded):
    items = database.get_items(section="pinned")
    assert [i.content for i in items] == ["alpha one"]


def test_section_favorite(database: Database, seeded):
    items = database.get_items(section="favorite")
    assert [i.content for i in items] == ["https://example.com"]


def test_section_recent(database: Database, seeded):
    assert database.count_items("recent") == 3


def test_type_section_with_group(database: Database, seeded):
    assert seeded["types"]["https://example.com"] == "link"
    links = database.get_items(section="type", content_type="link")
    assert [i.content for i in links] == ["https://example.com"]
    mixed = database.get_items(section="type", content_type="text,multiline")
    assert len(mixed) == 2


def test_search_matches_content(database: Database, seeded):
    assert [i.content for i in database.get_items(search="EXAMPLE.com")] == [
        "https://example.com"
    ]
    assert len(database.get_items(search="alpha")) == 1
    assert database.get_items(search="zzz-nothing") == []


def test_search_escapes_like_wildcards(database: Database, seeded):
    database.add_item(make("100% done"))
    database.add_item(make("snake_case_value"))
    assert len(database.get_items(search="100%")) == 1
    assert len(database.get_items(search="snake_c")) == 1


def test_sort_newest_and_oldest(database: Database, seeded):
    newest = database.get_items(sort="newest")
    oldest = database.get_items(sort="oldest")
    # Pinned entries always lead the "newest" ordering.
    assert newest[0].is_pinned
    assert newest[1].content == "gamma def f(): pass"
    # "Oldest" puts unprotected entries first and the pinned entry last.
    assert oldest[0].content == "https://example.com"
    assert oldest[-1].is_pinned


def test_pinned_sort_to_top(database: Database, seeded):
    items = database.get_items(sort="newest")
    assert items[0].is_pinned


def test_count_items(database: Database, seeded):
    assert database.count_items("all") == 3
    assert database.count_items("all", "alpha") == 1


# ----------------------------------------------------------------------
# Deletion / clearing
# ----------------------------------------------------------------------
def test_delete_item(database: Database, seeded):
    database.delete_item(seeded["alpha one"].id)
    assert database.get_item(seeded["alpha one"].id) is None
    assert database.count_items() == 2


def test_clear_history_keeps_protected(database: Database, seeded):
    removed = database.clear_history(keep_protected=True)
    assert removed == 1
    remaining = database.get_items()
    assert {i.content for i in remaining} == {"alpha one", "https://example.com"}


def test_clear_history_all(database: Database, seeded):
    removed = database.clear_history(keep_protected=False)
    assert removed == 3
    assert database.get_items() == []


# ----------------------------------------------------------------------
# Limits & retention
# ----------------------------------------------------------------------
def test_enforce_limits_by_count(database: Database):
    base = time.time()
    for i in range(30):
        database.add_item(
            make(f"item {i}", created_at=base - i, last_copied_at=base - i)
        )
    removed = database.enforce_limits(max_items=10, retention_days=0)
    assert removed == 20
    assert database.count_items() == 10


def test_enforce_limits_keeps_pinned_and_favorites(database: Database):
    base = time.time()
    ids = []
    for i in range(20):
        item = database.add_item(
            make(f"item {i}", created_at=base - i, last_copied_at=base - i)
        )
        ids.append(item.id)
    database.set_pinned(ids[19], True)
    database.set_favorite(ids[18], True)
    removed = database.enforce_limits(max_items=5, retention_days=0)
    # 18 unprotected entries, 5 survive -> 13 removed. The pinned and
    # favourite entries are never trimmed, so 7 rows remain in total.
    assert removed == 13
    assert database.count_items() == 7
    assert database.count_items("pinned") == 1
    assert database.count_items("favorite") == 1


def test_enforce_limits_by_retention(database: Database):
    base = time.time()
    database.add_item(make("old", created_at=base - 40 * 86400,
                           last_copied_at=base - 40 * 86400))
    database.add_item(make("new", created_at=base - 1 * 86400,
                           last_copied_at=base - 1 * 86400))
    removed = database.enforce_limits(max_items=100, retention_days=30)
    assert removed == 1
    assert [i.content for i in database.get_items()] == ["new"]


def test_retention_zero_keeps_everything(database: Database):
    base = time.time()
    database.add_item(make("ancient", created_at=base - 900 * 86400,
                           last_copied_at=base - 900 * 86400))
    assert database.enforce_limits(max_items=100, retention_days=0) == 0
    assert database.count_items() == 1


# ----------------------------------------------------------------------
# Snippets
# ----------------------------------------------------------------------
def test_snippet_crud(database: Database):
    snippet = database.add_snippet(Snippet(title="T", content="body", tags=["a", "b"]))
    assert snippet.id is not None
    fetched = database.get_snippet(snippet.id)
    assert fetched.title == "T"
    assert fetched.tags == ["a", "b"]

    snippet.title = "Updated"
    database.update_snippet(snippet)
    assert database.get_snippet(snippet.id).title == "Updated"

    database.delete_snippet(snippet.id)
    assert database.get_snippet(snippet.id) is None


def test_snippet_search_by_tag_and_content(database: Database):
    database.add_snippet(Snippet(title="Deploy", content="kubectl apply -f x.yaml",
                                 tags=["k8s"]))
    database.add_snippet(Snippet(title="Greeting", content="Hello there"))
    assert len(database.get_snippets(search="k8s")) == 1
    assert len(database.get_snippets(search="kubectl")) == 1
    assert len(database.get_snippets(search="greet")) == 1
    assert len(database.get_snippets()) == 2


def test_snippet_exists_by_hash(database: Database):
    database.add_snippet(Snippet(title="x", content="same"))
    assert database.snippet_exists(content_hash("same"))
    assert not database.snippet_exists(content_hash("different"))


# ----------------------------------------------------------------------
# Stats
# ----------------------------------------------------------------------
def test_stats(database: Database, seeded):
    stats = database.stats()
    assert stats.item_count == 3
    assert stats.pinned_count == 1
    assert stats.favorite_count == 1
    assert stats.bytes_used > 0
    assert "B" in stats.size_label
