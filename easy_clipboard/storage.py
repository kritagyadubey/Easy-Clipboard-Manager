"""SQLite persistence for clipboard history and saved snippets.

Design notes
------------
* One connection per :class:`Database`, guarded by a lock; all public methods
  are safe to call from the Qt main thread (they are fast, local operations).
* WAL journaling keeps the database responsive if a write ever races with a
  read and improves crash resilience.
* Content identity is the SHA-256 hash of the exact stored text, so duplicate
  detection never depends on lossy previews.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Iterable, Optional

from .models import ClipItem, ContentType, Snippet, StorageStats, content_hash

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    content       TEXT    NOT NULL,
    content_hash  TEXT    NOT NULL,
    content_type  TEXT    NOT NULL,
    created_at    REAL    NOT NULL,
    last_copied_at REAL   NOT NULL,
    is_pinned     INTEGER NOT NULL DEFAULT 0,
    is_favorite   INTEGER NOT NULL DEFAULT 0,
    source_app    TEXT    NOT NULL DEFAULT '',
    copy_count    INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_items_hash      ON items(content_hash);
CREATE INDEX IF NOT EXISTS idx_items_last_used ON items(last_copied_at DESC);

CREATE TABLE IF NOT EXISTS snippets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    content     TEXT    NOT NULL,
    description TEXT    NOT NULL DEFAULT '',
    tags        TEXT    NOT NULL DEFAULT '',
    created_at  REAL    NOT NULL,
    updated_at  REAL    NOT NULL,
    content_hash TEXT   NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snippets_hash ON snippets(content_hash);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_SELECT_COLUMNS = (
    "id, content, content_type, created_at, last_copied_at, "
    "is_pinned, is_favorite, source_app, copy_count"
)

_SORTS = {
    "newest": "is_pinned DESC, last_copied_at DESC",
    "oldest": "is_pinned ASC, last_copied_at ASC",
    "most_used": "is_pinned DESC, copy_count DESC, last_copied_at DESC",
}


class DatabaseError(RuntimeError):
    """Raised when the database cannot be opened or is unrecoverable."""


def _row_to_item(row: sqlite3.Row) -> ClipItem:
    try:
        content_type = ContentType(row["content_type"])
    except ValueError:
        content_type = ContentType.TEXT
    return ClipItem(
        id=row["id"],
        content=row["content"],
        content_type=content_type,
        created_at=row["created_at"],
        last_copied_at=row["last_copied_at"],
        is_pinned=bool(row["is_pinned"]),
        is_favorite=bool(row["is_favorite"]),
        source_app=row["source_app"] or "",
        copy_count=row["copy_count"],
    )


def _row_to_snippet(row: sqlite3.Row) -> Snippet:
    tags = [t for t in (row["tags"] or "").split("|") if t]
    return Snippet(
        id=row["id"],
        title=row["title"],
        content=row["content"],
        description=row["description"] or "",
        tags=tags,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class Database:
    """Thin, thread-safe data-access layer."""

    def __init__(self, path: Path):
        self._path = Path(path)
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self._open()

    # ------------------------------------------------------------------
    def _open(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self._path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.executescript(_SCHEMA)
            conn.commit()
            self._conn = conn
        except sqlite3.Error as exc:
            raise DatabaseError(
                f"Could not open the clipboard database at {self._path}"
            ) from exc

    @property
    def path(self) -> Path:
        return self._path

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.commit()
                    self._conn.close()
                except sqlite3.Error:
                    pass
                self._conn = None

    def _execute(self, sql: str, params: Iterable = ()) -> sqlite3.Cursor:
        with self._lock:
            if self._conn is None:
                raise DatabaseError("Database is closed")
            try:
                cur = self._conn.execute(sql, tuple(params))
                self._conn.commit()
                return cur
            except sqlite3.Error as exc:
                self._conn.rollback()
                raise DatabaseError(str(exc)) from exc

    def _query(self, sql: str, params: Iterable = ()) -> list[sqlite3.Row]:
        with self._lock:
            if self._conn is None:
                raise DatabaseError("Database is closed")
            try:
                return list(self._conn.execute(sql, tuple(params)).fetchall())
            except sqlite3.Error as exc:
                raise DatabaseError(str(exc)) from exc

    # ------------------------------------------------------------------
    # Items
    # ------------------------------------------------------------------
    def add_item(self, item: ClipItem) -> ClipItem:
        """Insert a new item, or refresh an existing duplicate.

        Duplicate policy is applied by the caller; this method always stores
        the row and returns the authoritative :class:`ClipItem`.
        """
        digest = content_hash(item.content)
        existing = self.find_by_hash(digest)
        if existing is not None:
            copy_count = existing.copy_count + 1
            self._execute(
                "UPDATE items SET last_copied_at = ?, copy_count = ? WHERE id = ?",
                (item.last_copied_at, copy_count, existing.id),
            )
            existing.last_copied_at = item.last_copied_at
            existing.copy_count = copy_count
            return existing

        cur = self._execute(
            "INSERT INTO items (content, content_hash, content_type, created_at,"
            " last_copied_at, is_pinned, is_favorite, source_app, copy_count)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                item.content,
                digest,
                item.content_type.value,
                item.created_at,
                item.last_copied_at,
                int(item.is_pinned),
                int(item.is_favorite),
                item.source_app,
                item.copy_count,
            ),
        )
        item.id = cur.lastrowid
        return item

    def find_by_hash(self, digest: str) -> Optional[ClipItem]:
        rows = self._query(
            f"SELECT {_SELECT_COLUMNS} FROM items WHERE content_hash = ? LIMIT 1",
            (digest,),
        )
        return _row_to_item(rows[0]) if rows else None

    def get_item(self, item_id: int) -> Optional[ClipItem]:
        rows = self._query(
            f"SELECT {_SELECT_COLUMNS} FROM items WHERE id = ?", (item_id,)
        )
        return _row_to_item(rows[0]) if rows else None

    def get_items(
        self,
        *,
        section: str = "all",
        search: str = "",
        content_type: str = "",
        sort: str = "newest",
        limit: int = 500,
        offset: int = 0,
    ) -> list[ClipItem]:
        clauses: list[str] = []
        params: list[object] = []

        if section == "pinned":
            clauses.append("is_pinned = 1")
        elif section == "favorite":
            clauses.append("is_favorite = 1")
        elif section == "recent":
            cutoff = time.time() - 24 * 3600
            clauses.append("last_copied_at >= ?")
            params.append(cutoff)
        elif section == "type":
            types = [t for t in content_type.split(",") if t]
            if len(types) == 1:
                clauses.append("content_type = ?")
                params.append(types[0])
            elif types:
                clauses.append(
                    "content_type IN (%s)" % ",".join("?" * len(types))
                )
                params.extend(types)

        if search:
            clauses.append("content LIKE ? ESCAPE '\\'")
            escaped = (
                search.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
            )
            params.append(f"%{escaped}%")

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        order = _SORTS.get(sort, _SORTS["newest"])
        sql = (
            f"SELECT {_SELECT_COLUMNS} FROM items {where} ORDER BY {order} "
            "LIMIT ? OFFSET ?"
        )
        params.extend([max(1, int(limit)), max(0, int(offset))])
        return [_row_to_item(r) for r in self._query(sql, params)]

    def count_items(
        self,
        section: str = "all",
        search: str = "",
        content_type: str = "",
    ) -> int:
        clauses: list[str] = []
        params: list[object] = []
        if section == "pinned":
            clauses.append("is_pinned = 1")
        elif section == "favorite":
            clauses.append("is_favorite = 1")
        elif section == "recent":
            clauses.append("last_copied_at >= ?")
            params.append(time.time() - 24 * 3600)
        elif section == "type":
            types = [t for t in content_type.split(",") if t]
            if len(types) == 1:
                clauses.append("content_type = ?")
                params.append(types[0])
            elif types:
                clauses.append(
                    "content_type IN (%s)" % ",".join("?" * len(types))
                )
                params.extend(types)
        if search:
            clauses.append("content LIKE ? ESCAPE '\\'")
            escaped = (
                search.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
            )
            params.append(f"%{escaped}%")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._query(f"SELECT COUNT(*) AS n FROM items {where}", params)
        return int(rows[0]["n"])

    def touch_item(self, item_id: int) -> None:
        """Mark an item as copied now and bump its usage counter."""
        self._execute(
            "UPDATE items SET last_copied_at = ?, copy_count = copy_count + 1"
            " WHERE id = ?",
            (time.time(), item_id),
        )

    def set_item_timestamps(
        self, item_id: int, created_at: float, last_copied_at: float
    ) -> None:
        """Overwrite an item's timestamps (used by tests and demo seeding)."""
        self._execute(
            "UPDATE items SET created_at = ?, last_copied_at = ? WHERE id = ?",
            (created_at, last_copied_at, item_id),
        )

    def set_pinned(self, item_id: int, pinned: bool) -> None:
        self._execute(
            "UPDATE items SET is_pinned = ? WHERE id = ?", (int(pinned), item_id)
        )

    def set_favorite(self, item_id: int, favorite: bool) -> None:
        self._execute(
            "UPDATE items SET is_favorite = ? WHERE id = ?", (int(favorite), item_id)
        )

    def delete_item(self, item_id: int) -> None:
        self._execute("DELETE FROM items WHERE id = ?", (item_id,))

    def clear_history(self, *, keep_protected: bool = True) -> int:
        """Delete ordinary history; optionally keep pinned/favourite entries."""
        if keep_protected:
            cur = self._execute(
                "DELETE FROM items WHERE is_pinned = 0 AND is_favorite = 0"
            )
        else:
            cur = self._execute("DELETE FROM items")
        return cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else 0

    def enforce_limits(self, max_items: int, retention_days: int) -> int:
        """Trim ordinary (unprotected) history by age and size.

        Pinned and favourite entries are never removed by this routine.
        Returns the number of entries removed.
        """
        removed = 0
        with self._lock:
            if retention_days > 0:
                cutoff = time.time() - retention_days * 24 * 3600
                cur = self._execute(
                    "DELETE FROM items WHERE is_pinned = 0 AND is_favorite = 0"
                    " AND last_copied_at < ?",
                    (cutoff,),
                )
                removed += max(0, cur.rowcount)
            rows = self._query(
                "SELECT id FROM items WHERE is_pinned = 0 AND is_favorite = 0"
                " ORDER BY last_copied_at DESC"
            )
            overflow = len(rows) - max_items
            if overflow > 0:
                stale_ids = [r["id"] for r in rows[:overflow]]
                placeholders = ",".join("?" * len(stale_ids))
                cur = self._execute(
                    f"DELETE FROM items WHERE id IN ({placeholders})", stale_ids
                )
                removed += max(0, cur.rowcount)
        return removed

    # ------------------------------------------------------------------
    # Snippets
    # ------------------------------------------------------------------
    def add_snippet(self, snippet: Snippet) -> Snippet:
        cur = self._execute(
            "INSERT INTO snippets (title, content, description, tags, created_at,"
            " updated_at, content_hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                snippet.title,
                snippet.content,
                snippet.description,
                "|".join(snippet.tags),
                snippet.created_at,
                snippet.updated_at,
                content_hash(snippet.content),
            ),
        )
        snippet.id = cur.lastrowid
        return snippet

    def update_snippet(self, snippet: Snippet) -> None:
        if snippet.id is None:
            raise ValueError("Cannot update a snippet without an id")
        snippet.updated_at = time.time()
        self._execute(
            "UPDATE snippets SET title = ?, content = ?, description = ?,"
            " tags = ?, updated_at = ?, content_hash = ? WHERE id = ?",
            (
                snippet.title,
                snippet.content,
                snippet.description,
                "|".join(snippet.tags),
                snippet.updated_at,
                content_hash(snippet.content),
                snippet.id,
            ),
        )

    def delete_snippet(self, snippet_id: int) -> None:
        self._execute("DELETE FROM snippets WHERE id = ?", (snippet_id,))

    def get_snippet(self, snippet_id: int) -> Optional[Snippet]:
        rows = self._query("SELECT * FROM snippets WHERE id = ?", (snippet_id,))
        return _row_to_snippet(rows[0]) if rows else None

    def get_snippets(self, *, search: str = "", limit: int = 1000) -> list[Snippet]:
        if search:
            escaped = (
                search.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
            )
            pattern = f"%{escaped}%"
            rows = self._query(
                "SELECT * FROM snippets WHERE title LIKE ? ESCAPE '\\'"
                " OR content LIKE ? ESCAPE '\\' OR tags LIKE ? ESCAPE '\\'"
                " OR description LIKE ? ESCAPE '\\'"
                " ORDER BY updated_at DESC LIMIT ?",
                (pattern, pattern, pattern, pattern, limit),
            )
        else:
            rows = self._query(
                "SELECT * FROM snippets ORDER BY updated_at DESC LIMIT ?", (limit,)
            )
        return [_row_to_snippet(r) for r in rows]

    def snippet_exists(self, digest: str) -> bool:
        rows = self._query(
            "SELECT 1 FROM snippets WHERE content_hash = ? LIMIT 1", (digest,)
        )
        return bool(rows)

    # ------------------------------------------------------------------
    # Bulk helpers (import / export)
    # ------------------------------------------------------------------
    def all_items(self, limit: int = 100_000) -> list[ClipItem]:
        rows = self._query(
            f"SELECT {_SELECT_COLUMNS} FROM items ORDER BY last_copied_at DESC LIMIT ?",
            (limit,),
        )
        return [_row_to_item(r) for r in rows]

    def all_snippets(self, limit: int = 100_000) -> list[Snippet]:
        rows = self._query(
            "SELECT * FROM snippets ORDER BY updated_at DESC LIMIT ?", (limit,)
        )
        return [_row_to_snippet(r) for r in rows]

    def stats(self) -> StorageStats:
        rows = self._query(
            "SELECT COUNT(*) AS n,"
            " COALESCE(SUM(LENGTH(content)), 0) AS bytes,"
            " COALESCE(SUM(is_pinned), 0) AS pinned,"
            " COALESCE(SUM(is_favorite), 0) AS favs"
            " FROM items"
        )
        snip = self._query(
            "SELECT COUNT(*) AS n, COALESCE(SUM(LENGTH(content)), 0) AS bytes"
            " FROM snippets"
        )
        db_bytes = 0
        try:
            db_bytes = self._path.stat().st_size
        except OSError:
            pass
        return StorageStats(
            item_count=int(rows[0]["n"]),
            snippet_count=int(snip[0]["n"]),
            pinned_count=int(rows[0]["pinned"]),
            favorite_count=int(rows[0]["favs"]),
            bytes_used=db_bytes + int(rows[0]["bytes"]) + int(snip[0]["bytes"]),
        )

    def vacuum(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.execute("VACUUM")
                except sqlite3.Error:
                    pass
