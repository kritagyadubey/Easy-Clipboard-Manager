"""Capture policy, duplicate handling, trimming and snippet CRUD."""

from __future__ import annotations

import time

from easy_clipboard.history import MAX_CAPTURE_CHARS


# ----------------------------------------------------------------------
# should_capture / capture policy
# ----------------------------------------------------------------------
def test_capture_stores_ordinary_text(history):
    item = history.capture("hello world", source_app="notepad.exe")
    assert item is not None
    assert item.content == "hello world"
    assert history.count() == 1


def test_capture_rejects_empty_and_whitespace(history):
    assert history.capture("") is None
    assert history.capture("   \n\t  ") is None
    assert history.capture(None) is None  # type: ignore[arg-type]
    assert history.count() == 0


def test_capture_respects_paused_monitoring(history, settings_store):
    settings_store.update(monitoring_enabled=False)
    assert history.capture("while paused") is None
    allowed, reason = history.should_capture("while paused")
    assert (allowed, reason) == (False, "monitoring_paused")

    settings_store.update(monitoring_enabled=True)
    assert history.capture("after resume") is not None
    assert history.count() == 1


def test_capture_rejects_oversized_content(history):
    huge = "x" * (MAX_CAPTURE_CHARS + 1)
    allowed, reason = history.should_capture(huge)
    assert (allowed, reason) == (False, "too_large")
    assert history.capture(huge) is None
    assert history.count() == 0


def test_capture_excludes_configured_app(history, settings_store):
    settings_store.update(excluded_apps=["keepass"])
    assert history.capture("secret", source_app="KeePass.exe") is None
    allowed, reason = history.should_capture("secret", "KeePass.exe")
    assert (allowed, reason) == (False, "excluded_app")
    # A different application is still captured.
    assert history.capture("secret", source_app="notepad.exe") is not None
    # Empty source app is never excluded.
    assert history.capture("no source") is not None
    assert history.count() == 2


def test_capture_unicode_and_long_text(history):
    text = "emoji 👩🏽‍💻 ünïcödé 中文 русский\n" * 50
    item = history.capture(text)
    assert item is not None
    assert history.get(item.id).content == text


# ----------------------------------------------------------------------
# Duplicate handling
# ----------------------------------------------------------------------
def test_duplicate_refresh_moves_item_to_top(history, settings_store):
    settings_store.update(duplicate_handling="refresh")
    first = history.capture("repeat me")
    time.sleep(0.01)
    second = history.capture("repeat me")
    assert second is not None
    assert second.id == first.id
    assert history.count() == 1
    assert history.query()[0].content == "repeat me"


def test_duplicate_ignore_keeps_original_and_skips(history, settings_store):
    settings_store.update(duplicate_handling="ignore")
    first = history.capture("repeat me")
    time.sleep(0.01)
    history.capture("other")
    time.sleep(0.01)
    assert history.capture("repeat me") is None
    # Nothing new was written; ordering untouched.
    assert history.count() == 2
    assert history.get(first.id) is not None


# ----------------------------------------------------------------------
# Trimming / limits
# ----------------------------------------------------------------------
def test_trim_history_enforces_settings(history, settings_store):
    settings_store.update(max_items=25)  # the enforced minimum
    for i in range(40):
        history.capture(f"entry {i}")
    removed = history.trim_history()
    assert removed == 15
    assert history.count() == 25


def test_pending_trim_is_coalesced(history, settings_store):
    settings_store.update(max_items=25)
    for i in range(30):
        history.capture(f"burst {i}")
    # Nothing is trimmed until the deferred pass runs.
    assert history.count() == 30
    assert history.run_pending_trim() == 5
    assert history.count() == 25
    # A second pass with nothing pending is a no-op.
    assert history.run_pending_trim() == 0


def test_trim_never_removes_pinned_or_favorites(history, settings_store):
    settings_store.update(max_items=25)
    for i in range(30):
        history.capture(f"entry {i}")
    pinned = history.query()[0]
    history.set_pinned(pinned.id, True)
    history.trim_history()
    assert history.count() == 26
    assert history.count("pinned") == 1
    assert history.get(pinned.id) is not None


# ----------------------------------------------------------------------
# Mutations & queries
# ----------------------------------------------------------------------
def test_mark_copied_updates_timestamp(history):
    item = history.capture("touch me")
    before = history.get(item.id).last_copied_at
    time.sleep(0.02)
    history.mark_copied(item.id)
    assert history.get(item.id).last_copied_at > before


def test_pin_favorite_delete_clear(history):
    a = history.capture("alpha")
    b = history.capture("beta")
    history.set_favorite(a.id, True)
    assert history.count("favorite") == 1

    history.delete(b.id)
    assert history.get(b.id) is None
    assert history.count() == 1

    removed = history.clear_history(keep_protected=True)
    assert removed == 0  # alpha is a favourite
    assert history.count() == 1

    removed = history.clear_history(keep_protected=False)
    assert removed == 1
    assert history.count() == 0


def test_query_search_sort_and_paging(history):
    for text in ("alpha one", "beta two", "gamma three"):
        history.capture(text)
    assert [i.content for i in history.query(search="BETA")] == ["beta two"]
    assert history.count("all", "gamma") == 1
    oldest = history.query(sort="oldest")
    assert oldest[0].content == "alpha one"
    assert len(history.query(limit=2)) == 2
    # Newest-first paging: page one is the two newest, page two the oldest.
    assert [i.content for i in history.query(limit=2, offset=2)] == ["alpha one"]
    assert [i.content for i in history.query(sort="oldest", limit=1)] == ["alpha one"]


def test_stats_reports_counts(history):
    history.capture("one")
    history.capture("two")
    stats = history.stats()
    assert stats.item_count >= 2
    assert stats.snippet_count == 0
    assert stats.bytes_used > 0


# ----------------------------------------------------------------------
# Snippets
# ----------------------------------------------------------------------
def test_snippet_crud(history):
    snippet = history.create_snippet(
        "Signature",
        "Best regards,\nAda",
        description="Email footer",
        tags=["email", " work "],
    )
    assert snippet.id
    assert snippet.title == "Signature"
    assert snippet.tags == ["email", "work"]

    assert history.get_snippet(snippet.id).content == "Best regards,\nAda"
    assert [s.title for s in history.snippets("signature")] == ["Signature"]
    assert history.snippet_tags() == ["email", "work"]

    snippet.description = "Updated footer"
    history.update_snippet(snippet)
    assert history.get_snippet(snippet.id).description == "Updated footer"

    history.delete_snippet(snippet.id)
    assert history.get_snippet(snippet.id) is None
    assert history.snippets() == []


def test_snippet_title_is_derived_when_blank(history):
    snippet = history.create_snippet("   ", "First line of the body\nsecond")
    assert snippet.title == "First line of the body"

    long_title = history.create_snippet("", "y" * 80)
    assert len(long_title.title) == 61
    assert long_title.title.endswith("…")


def test_snippets_are_searchable_by_content(history):
    history.create_snippet("Greeting", "Hello there")
    assert len(history.snippets("hello")) == 1
    assert history.snippets("nope") == []
