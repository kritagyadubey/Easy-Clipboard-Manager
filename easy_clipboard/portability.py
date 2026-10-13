"""Export and import of clipboard history and saved snippets.

Two formats are supported:

``json``
    Full fidelity — content, timestamps, pins, favourites, tags, descriptions.
    This is the recommended backup format.

``text``
    Plain text, one entry separated by a horizontal rule.  Convenient for
    humans and diff tools; importing it back creates ordinary entries.

Imports are strictly additive: existing history and snippets are never
overwritten.  Entries whose exact content already exists are skipped.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import __version__
from .models import ClipItem, ContentType, Snippet, content_hash

EXPORT_FORMAT = "easy-clipboard-manager"
EXPORT_VERSION = 1

TEXT_SEPARATOR = "\n\n———\n\n"


class ImportError_(ValueError):
    """Raised when an import file cannot be understood."""


@dataclass
class ImportResult:
    added_items: int = 0
    added_snippets: int = 0
    skipped_duplicates: int = 0
    invalid_entries: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        parts = []
        if self.added_items:
            parts.append(f"{self.added_items} clipboard entries")
        if self.added_snippets:
            parts.append(f"{self.added_snippets} snippets")
        if self.skipped_duplicates:
            parts.append(f"{self.skipped_duplicates} duplicates skipped")
        if self.invalid_entries:
            parts.append(f"{self.invalid_entries} invalid entries skipped")
        return ", ".join(parts) if parts else "nothing new to import"


# ----------------------------------------------------------------------
# Export
# ----------------------------------------------------------------------
def export_json(items: list[ClipItem], snippets: list[Snippet], path: Path) -> int:
    payload = {
        "format": EXPORT_FORMAT,
        "version": EXPORT_VERSION,
        "app_version": __version__,
        "exported_at": time.time(),
        "items": [
            {
                "content": item.content,
                "content_type": item.content_type.value,
                "created_at": item.created_at,
                "last_copied_at": item.last_copied_at,
                "is_pinned": item.is_pinned,
                "is_favorite": item.is_favorite,
                "source_app": item.source_app,
                "copy_count": item.copy_count,
            }
            for item in items
        ],
        "snippets": [
            {
                "title": snippet.title,
                "content": snippet.content,
                "description": snippet.description,
                "tags": snippet.tags,
                "created_at": snippet.created_at,
                "updated_at": snippet.updated_at,
            }
            for snippet in snippets
        ],
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(items) + len(snippets)


def export_text(items: list[ClipItem], path: Path) -> int:
    blocks = []
    for item in items:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(item.last_copied_at))
        marker = " [pinned]" if item.is_pinned else (" [favorite]" if item.is_favorite else "")
        blocks.append(f"# {stamp}{marker}\n{item.content}")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(TEXT_SEPARATOR.join(blocks), encoding="utf-8")
    return len(items)


# ----------------------------------------------------------------------
# Import
# ----------------------------------------------------------------------
def _parse_item(raw: object, result: ImportResult) -> Optional[ClipItem]:
    if not isinstance(raw, dict):
        result.invalid_entries += 1
        return None
    content = raw.get("content")
    if not isinstance(content, str) or not content.strip():
        result.invalid_entries += 1
        return None
    try:
        content_type = ContentType(str(raw.get("content_type", "text")))
    except ValueError:
        content_type = ContentType.TEXT

    def _ts(key: str, default: float) -> float:
        value = raw.get(key)
        return float(value) if isinstance(value, (int, float)) else default

    now = time.time()
    return ClipItem(
        content=content,
        content_type=content_type,
        created_at=_ts("created_at", now),
        last_copied_at=_ts("last_copied_at", _ts("created_at", now)),
        is_pinned=bool(raw.get("is_pinned", False)),
        is_favorite=bool(raw.get("is_favorite", False)),
        source_app=str(raw.get("source_app", "") or ""),
        copy_count=max(1, int(raw.get("copy_count", 1) or 1)),
    )


def _parse_snippet(raw: object, result: ImportResult) -> Optional[Snippet]:
    if not isinstance(raw, dict):
        result.invalid_entries += 1
        return None
    content = raw.get("content")
    title = raw.get("title")
    if not isinstance(content, str) or not content.strip():
        result.invalid_entries += 1
        return None
    if not isinstance(title, str) or not title.strip():
        result.invalid_entries += 1
        return None
    tags = raw.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    now = time.time()
    return Snippet(
        title=title.strip()[:200],
        content=content,
        description=str(raw.get("description", "") or ""),
        tags=[str(t).strip() for t in tags if str(t).strip()][:32],
        created_at=float(raw.get("created_at", now) or now),
        updated_at=float(raw.get("updated_at", now) or now),
    )


def import_from_file(path: Path, db) -> ImportResult:
    """Import a previously exported file into ``db`` (additive only)."""
    path = Path(path)
    result = ImportResult()
    if not path.exists():
        raise ImportError_(f"File not found: {path}")

    try:
        raw_text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ImportError_(f"Could not read file: {exc}") from exc

    if path.suffix.lower() == ".json" or raw_text.lstrip()[:1] in ("[", "{"):
        return _import_json(raw_text, db, result)
    return _import_text(raw_text, db, result)


def _import_json(raw_text: str, db, result: ImportResult) -> ImportResult:
    try:
        payload = json.loads(raw_text)
    except ValueError as exc:
        raise ImportError_("The file is not valid JSON.") from exc

    if not isinstance(payload, dict):
        raise ImportError_("Unexpected JSON structure.")

    fmt = payload.get("format")
    if fmt is not None and fmt != EXPORT_FORMAT:
        raise ImportError_(f"Unsupported file format: {fmt!r}")

    items = payload.get("items") or []
    snippets = payload.get("snippets") or []
    if not isinstance(items, list) or not isinstance(snippets, list):
        raise ImportError_("Unexpected JSON structure: 'items' and 'snippets' must be lists.")

    for raw in items:
        item = _parse_item(raw, result)
        if item is None:
            continue
        if db.find_by_hash(content_hash(item.content)) is not None:
            result.skipped_duplicates += 1
            continue
        db.add_item(item)
        result.added_items += 1

    for raw in snippets:
        snippet = _parse_snippet(raw, result)
        if snippet is None:
            continue
        if db.snippet_exists(content_hash(snippet.content)):
            result.skipped_duplicates += 1
            continue
        db.add_snippet(snippet)
        result.added_snippets += 1

    db.enforce_limits(100_000, 0)  # imported protected flags already applied
    return result


def _import_text(raw_text: str, db, result: ImportResult) -> ImportResult:
    now = time.time()
    blocks = [b.strip() for b in raw_text.split(TEXT_SEPARATOR)]
    for block in blocks:
        if not block:
            continue
        content = block
        if content.startswith("# "):
            first_newline = content.find("\n")
            header, content = (
                content[:first_newline], content[first_newline + 1 :]
            ) if first_newline != -1 else (content, "")
            content = content.strip("\n")
            if not content.strip():
                result.invalid_entries += 1
                continue
        if db.find_by_hash(content_hash(content)) is not None:
            result.skipped_duplicates += 1
            continue
        db.add_item(
            ClipItem(
                content=content,
                created_at=now,
                last_copied_at=now,
            )
        )
        result.added_items += 1
    return result
