"""Data models shared across the application."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ContentType(str, Enum):
    """Automatically detected classification of a clipboard entry."""

    TEXT = "text"
    MULTILINE = "multiline"
    LINK = "link"
    EMAIL = "email"
    NUMBER = "number"
    JSON = "json"
    CODE = "code"

    @property
    def label(self) -> str:
        return _TYPE_LABELS[self]


_TYPE_LABELS = {
    ContentType.TEXT: "Text",
    ContentType.MULTILINE: "Multiline",
    ContentType.LINK: "Link",
    ContentType.EMAIL: "Email",
    ContentType.NUMBER: "Number",
    ContentType.JSON: "JSON",
    ContentType.CODE: "Code",
}


def content_hash(content: str) -> str:
    """Stable identity for a piece of clipboard text (UTF-8, SHA-256)."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass
class ClipItem:
    """One captured clipboard entry."""

    id: Optional[int] = None
    content: str = ""
    content_type: ContentType = ContentType.TEXT
    created_at: float = field(default_factory=time.time)
    last_copied_at: float = field(default_factory=time.time)
    is_pinned: bool = False
    is_favorite: bool = False
    source_app: str = ""
    copy_count: int = 1

    # ------------------------------------------------------------------
    @property
    def char_count(self) -> int:
        return len(self.content)

    @property
    def line_count(self) -> int:
        return self.content.count("\n") + 1

    @property
    def hash(self) -> str:
        return content_hash(self.content)

    @property
    def preview_text(self) -> str:
        """Single-line preview safe to show in a list."""
        return " ".join(self.content.split())

    @property
    def is_protected(self) -> bool:
        """Pinned or favourited entries survive routine history cleanup."""
        return self.is_pinned or self.is_favorite


@dataclass
class Snippet:
    """A deliberately saved piece of text with its own metadata."""

    id: Optional[int] = None
    title: str = ""
    content: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def hash(self) -> str:
        return content_hash(self.content)


@dataclass
class StorageStats:
    """Small summary shown in the sidebar footer."""

    item_count: int = 0
    snippet_count: int = 0
    pinned_count: int = 0
    favorite_count: int = 0
    bytes_used: int = 0

    @property
    def size_label(self) -> str:
        size = float(self.bytes_used)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                if unit == "B":
                    return f"{int(size)} {unit}"
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{int(self.bytes_used)} B"
