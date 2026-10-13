"""Business logic that sits between the UI, the clipboard monitor and storage.

The service is the single place where capture policy is decided:
monitoring state, size caps, application exclusions, duplicate handling,
history limits and retention all funnel through :meth:`HistoryService.capture`.
"""

from __future__ import annotations

import time
from typing import Optional

from .classifier import detect_type
from .logging_setup import get_logger
from .models import ClipItem, Snippet, StorageStats, content_hash
from .settings import Settings, SettingsStore
from .storage import Database

log = get_logger("history")

# Hard cap so an accidental multi-megabyte paste cannot make the UI unusable.
# The full text is still stored; only automatic capture is refused above this.
MAX_CAPTURE_CHARS = 500_000


class HistoryService:
    def __init__(self, db: Database, settings_store: SettingsStore):
        self._db = db
        self._settings_store = settings_store
        self._pending_trim = False

    # ------------------------------------------------------------------
    @property
    def db(self) -> Database:
        return self._db

    @property
    def settings(self) -> Settings:
        return self._settings_store.get()

    # ------------------------------------------------------------------
    # Capture
    # ------------------------------------------------------------------
    def should_capture(self, text: str, source_app: str = "") -> tuple[bool, str]:
        """Return ``(capture?, reason)`` without touching storage."""
        settings = self.settings
        if not settings.monitoring_enabled:
            return False, "monitoring_paused"
        if text is None:
            return False, "empty"
        if not text.strip():
            return False, "empty"
        if len(text) > MAX_CAPTURE_CHARS:
            return False, "too_large"
        if source_app and self._is_excluded(source_app, settings):
            return False, "excluded_app"
        return True, "ok"

    def _is_excluded(self, source_app: str, settings: Settings) -> bool:
        name = source_app.strip().lower()
        if not name:
            return False
        for rule in settings.excluded_apps:
            rule = rule.strip().lower()
            if not rule:
                continue
            if name == rule or name.startswith(rule):
                return True
        return False

    def capture(self, text: str, source_app: str = "") -> Optional[ClipItem]:
        """Store a newly captured clipboard entry.

        Returns the stored :class:`ClipItem`, or ``None`` when the content was
        intentionally skipped (paused monitoring, duplicate with ``ignore``
        policy, excluded application, empty or oversized content).
        """
        allowed, reason = self.should_capture(text, source_app)
        if not allowed:
            if reason not in ("empty", "monitoring_paused"):
                log.info("Capture skipped (%s), %d chars, source=%s",
                         reason, len(text or ""), source_app or "unknown")
            return None

        digest = content_hash(text)
        existing = self._db.find_by_hash(digest)
        settings = self.settings

        if existing is not None:
            if settings.duplicate_handling == "ignore":
                return None
            item = self._db.add_item(
                ClipItem(
                    content=text,
                    content_type=detect_type(text),
                    last_copied_at=time.time(),
                    source_app=source_app,
                )
            )
            self.request_trim()
            return item

        item = self._db.add_item(
            ClipItem(
                content=text,
                content_type=detect_type(text),
                created_at=time.time(),
                last_copied_at=time.time(),
                source_app=source_app,
            )
        )
        self.request_trim()
        log.info("Captured entry #%s (%s, %d chars, source=%s)",
                 item.id, item.content_type.value, item.char_count,
                 source_app or "unknown")
        return item

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------
    def request_trim(self) -> None:
        """Schedule a cheap deferred cleanup (coalesces bursts of copies)."""
        self._pending_trim = True

    def run_pending_trim(self) -> int:
        if not self._pending_trim:
            return 0
        self._pending_trim = False
        return self.trim_history()

    def trim_history(self) -> int:
        settings = self.settings
        removed = self._db.enforce_limits(settings.max_items, settings.retention_days)
        if removed:
            log.info("History trim removed %d entr%s", removed,
                     "y" if removed == 1 else "ies")
        return removed

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def query(
        self,
        *,
        section: str = "all",
        search: str = "",
        content_type: str = "",
        sort: str = "newest",
        limit: int = 500,
        offset: int = 0,
    ) -> list[ClipItem]:
        return self._db.get_items(
            section=section,
            search=search.strip(),
            content_type=content_type,
            sort=sort,
            limit=limit,
            offset=offset,
        )

    def count(self, section: str = "all", search: str = "", content_type: str = "") -> int:
        return self._db.count_items(section, search.strip(), content_type)

    def get(self, item_id: int) -> Optional[ClipItem]:
        return self._db.get_item(item_id)

    def stats(self) -> StorageStats:
        return self._db.stats()

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------
    def mark_copied(self, item_id: int) -> None:
        self._db.touch_item(item_id)

    def set_pinned(self, item_id: int, pinned: bool) -> None:
        self._db.set_pinned(item_id, pinned)

    def set_favorite(self, item_id: int, favorite: bool) -> None:
        self._db.set_favorite(item_id, favorite)

    def delete(self, item_id: int) -> None:
        self._db.delete_item(item_id)

    def clear_history(self, *, keep_protected: bool = True) -> int:
        removed = self._db.clear_history(keep_protected=keep_protected)
        log.info("Cleared %d entr%s (protected kept=%s)", removed,
                 "y" if removed == 1 else "ies", keep_protected)
        return removed

    # ------------------------------------------------------------------
    # Snippets
    # ------------------------------------------------------------------
    def create_snippet(
        self,
        title: str,
        content: str,
        description: str = "",
        tags: Optional[list[str]] = None,
    ) -> Snippet:
        title = title.strip() or self._derive_title(content)
        snippet = Snippet(
            title=title,
            content=content,
            description=description.strip(),
            tags=[t.strip() for t in (tags or []) if t.strip()],
        )
        self._db.add_snippet(snippet)
        log.info("Created snippet #%s (%d chars)", snippet.id, len(content))
        return snippet

    def update_snippet(self, snippet: Snippet) -> None:
        self._db.update_snippet(snippet)

    def delete_snippet(self, snippet_id: int) -> None:
        self._db.delete_snippet(snippet_id)

    def get_snippet(self, snippet_id: int) -> Optional[Snippet]:
        return self._db.get_snippet(snippet_id)

    def snippets(self, search: str = "") -> list[Snippet]:
        return self._db.get_snippets(search=search.strip())

    def snippet_tags(self) -> list[str]:
        tags: set[str] = set()
        for snippet in self._db.all_snippets():
            tags.update(snippet.tags)
        return sorted(tags, key=str.lower)

    @staticmethod
    def _derive_title(content: str) -> str:
        first = content.strip().splitlines()[0] if content.strip() else "Untitled snippet"
        return first[:60] + ("…" if len(first) > 60 else "")
