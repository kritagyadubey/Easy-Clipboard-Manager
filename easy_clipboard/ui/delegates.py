"""Custom item delegates that paint the clipboard and snippet cards."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QModelIndex, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QStyleOptionViewItem, QStyledItemDelegate, QStyle

from ..models import ClipItem, Snippet
from . import format as fmt
from . import icons
from .models import ITEM_ROLE
from .theme import TYPE_ICONS, base_font, palette


def row_height(density: str = "comfortable", kind: str = "clip") -> int:
    compact = density == "compact"
    if kind == "snippet":
        return 84 if compact else 96
    return 62 if compact else 84


def _theme_name() -> str:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    return getattr(app, "theme_name", "dark") if app else "dark"


def _two_line_split(metrics, text: str, width: int) -> tuple[str, str]:
    """Split ``text`` into at most two lines that fit ``width``."""
    if width <= 0:
        return "", ""
    if metrics.horizontalAdvance(text) <= width:
        return text, ""
    ellipsis_width = metrics.horizontalAdvance("…")
    target = max(10, width - ellipsis_width)
    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if metrics.horizontalAdvance(text[:mid]) <= target:
            low = mid
        else:
            high = mid - 1
    first = text[:low].rstrip()
    rest = text[low:].lstrip()
    second = metrics.elidedText(rest, Qt.TextElideMode.ElideRight, width)
    return first, second


class ClipItemDelegate(QStyledItemDelegate):
    """Paints one clipboard history card."""

    def __init__(self, view=None):
        super().__init__(view)
        self._view = view

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802
        density = getattr(self._view, "density", "comfortable")
        return QSize(option.rect.width(), row_height(density))

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        item: Optional[ClipItem] = index.data(ITEM_ROLE)
        if item is None:
            return

        pal = palette(_theme_name())
        density = getattr(self._view, "density", "comfortable")
        compact = density == "compact"
        radius = 8 if compact else 10

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        hovered = getattr(self._view, "hovered_row", -1) == index.row()
        selected = bool(option.state & QStyle.StateFlag.State_Selected)

        card = QRectF(option.rect).adjusted(6, 4, -6, -4)

        # Background ----------------------------------------------------
        if selected:
            border = QColor(pal.accent)
            fill = QColor(pal.surface_active)
        elif hovered:
            border = QColor(pal.border_strong)
            fill = QColor(pal.surface_hover)
        else:
            border = QColor(pal.border)
            fill = QColor(pal.surface)

        painter.setPen(QPen(border, 1))
        painter.setBrush(fill)
        painter.drawRoundedRect(card, radius, radius)

        if selected:
            bar = QRectF(card.left() + 1, card.top() + 8, 3, card.height() - 16)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(pal.accent))
            painter.drawRoundedRect(bar, 1.5, 1.5)

        # Type icon -----------------------------------------------------
        icon_name = TYPE_ICONS.get(item.content_type.value, "file-text")
        icon_size = 18
        icon_x = int(card.left() + 14)
        text_left = icon_x + icon_size + 12
        text_right = int(card.right() - 16)

        # Pin / favourite badges ---------------------------------------
        right_edge = text_right
        if item.is_favorite:
            star = icons.pixmap("star-filled", pal.favorite, 15)
            painter.drawPixmap(right_edge - 15, int(card.top() + 13), star)
            right_edge -= 22
        if item.is_pinned:
            pin = icons.pixmap("pin-filled", pal.pin, 15)
            painter.drawPixmap(right_edge - 15, int(card.top() + 13), pin)
            right_edge -= 22

        # Preview text --------------------------------------------------
        text_font = base_font(13)
        painter.setFont(text_font)
        metrics = painter.fontMetrics()
        available = max(60, right_edge - text_left)

        first, second = _two_line_split(metrics, item.preview_text, available)
        text_color = QColor(pal.text)
        painter.setPen(text_color)
        icon_y = int(card.top() + (15 if second else card.height() / 2 - icon_size / 2))
        painter.drawPixmap(icon_x, icon_y - 1, icons.pixmap(icon_name, pal.type_color(item.content_type.value), icon_size))

        first_y = int(card.top() + (26 if not compact else 22))
        second_y = None
        if second:
            # Two-line preview: a compact card is only 54 px tall once the
            # margins are removed, so the lines and the meta line need
            # tighter spacing than in comfortable density.
            if compact:
                first_y = int(card.top() + 12)
                second_y = first_y + 16
            else:
                first_y = int(card.top() + 19)
                second_y = first_y + 18
        painter.drawText(text_left, first_y, first)
        if second_y is not None:
            painter.setPen(QColor(pal.text_secondary))
            painter.drawText(text_left, second_y, second)

        # Meta line -----------------------------------------------------
        meta_font = base_font(11)
        painter.setFont(meta_font)
        meta_metrics = painter.fontMetrics()
        parts = [fmt.relative_time(item.last_copied_at)]
        parts.append(item.content_type.label)
        if item.source_app:
            parts.append(item.source_app)
        parts.append(fmt.char_label(item.char_count))
        if item.copy_count > 1:
            parts.append(f"used {item.copy_count}×")
        meta = "  ·  ".join(parts)
        if compact:
            # A two-line compact card fills the row, so the meta line sits
            # closer to the bottom edge than on a single-line card.
            meta_bottom = 8 if second else 17
        else:
            meta_bottom = 22
        meta_y = int(card.bottom() - meta_bottom)
        painter.setPen(QColor(pal.text_muted))
        painter.drawText(
            text_left,
            meta_y,
            meta_metrics.elidedText(meta, Qt.TextElideMode.ElideRight, available),
        )

        painter.restore()


class SnippetDelegate(QStyledItemDelegate):
    """Paints one saved-snippet card."""

    def __init__(self, view=None):
        super().__init__(view)
        self._view = view

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802
        density = getattr(self._view, "density", "comfortable")
        return QSize(option.rect.width(), row_height(density, kind="snippet"))

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        snippet: Optional[Snippet] = index.data(ITEM_ROLE)
        if snippet is None:
            return

        pal = palette(_theme_name())
        density = getattr(self._view, "density", "comfortable")
        compact = density == "compact"
        radius = 8 if compact else 10

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        hovered = getattr(self._view, "hovered_row", -1) == index.row()
        selected = bool(option.state & QStyle.StateFlag.State_Selected)

        card = QRectF(option.rect).adjusted(6, 4, -6, -4)
        if selected:
            border, fill = QColor(pal.accent), QColor(pal.surface_active)
        elif hovered:
            border, fill = QColor(pal.border_strong), QColor(pal.surface_hover)
        else:
            border, fill = QColor(pal.border), QColor(pal.surface)

        painter.setPen(QPen(border, 1))
        painter.setBrush(fill)
        painter.drawRoundedRect(card, radius, radius)

        left = int(card.left() + 16)
        right = int(card.right() - 16)

        # Title + bookmark glyph
        painter.setFont(base_font(13, QFont.Weight.DemiBold))
        metrics = painter.fontMetrics()
        painter.setPen(QColor(pal.text))
        title = metrics.elidedText(snippet.title, Qt.TextElideMode.ElideRight, right - left - 30)
        title_y = int(card.top() + (26 if not compact else 22))
        painter.drawText(left, title_y, title)
        painter.drawPixmap(
            right - 16, int(card.top() + 13), icons.pixmap("bookmark", pal.accent, 15)
        )

        # Description or content preview
        painter.setFont(base_font(12))
        sub_metrics = painter.fontMetrics()
        painter.setPen(QColor(pal.text_secondary))
        subtitle = snippet.description or snippet.content.replace("\n", " ").strip()
        sub_y = title_y + 18
        painter.drawText(
            left,
            sub_y,
            sub_metrics.elidedText(subtitle, Qt.TextElideMode.ElideRight, right - left),
        )

        # Tags
        tag_y = int(card.bottom() - 24)
        tag_font = base_font(10)
        painter.setFont(tag_font)
        tag_metrics = painter.fontMetrics()
        x = left
        for tag in snippet.tags[:4]:
            label = f"#{tag}"
            width = tag_metrics.horizontalAdvance(label) + 14
            if x + width > right - 60:
                break
            chip = QRectF(x, tag_y, width, 18)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(pal.surface_active))
            painter.drawRoundedRect(chip, 9, 9)
            painter.setPen(QColor(pal.text_muted))
            painter.drawText(chip, Qt.AlignmentFlag.AlignCenter, label)
            x += width + 6

        painter.setPen(QColor(pal.text_muted))
        painter.setFont(base_font(11))
        updated = fmt.relative_time(snippet.updated_at)
        painter.drawText(right - 70, tag_y + 13, updated)

        painter.restore()
