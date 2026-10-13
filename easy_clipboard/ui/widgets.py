"""Small reusable widgets that give the interface its consistent feel."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import icons
from .theme import base_font, palette

# ----------------------------------------------------------------------
# Animated toggle switch
# ----------------------------------------------------------------------
class Switch(QWidget):
    """A compact on/off switch backed by a boolean value."""

    toggled = Signal(bool)

    def __init__(self, checked: bool = False, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._checked = checked
        self._position = 1.0 if checked else 0.0
        self._hover = False
        self.setFixedSize(40, 22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("Toggle")

        self._anim = QPropertyAnimation(self, b"position", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    # position is animated ------------------------------------------------
    def get_position(self) -> float:
        return self._position

    def set_position(self, value: float) -> None:
        self._position = value
        self.update()

    position = property(get_position, set_position)

    # ------------------------------------------------------------------
    @property
    def checked(self) -> bool:
        return self._checked

    def set_checked(self, checked: bool, animate: bool = True) -> None:
        if checked == self._checked:
            return
        self._checked = checked
        if animate:
            self._anim.stop()
            self._anim.setStartValue(self._position)
            self._anim.setEndValue(1.0 if checked else 0.0)
            self._anim.start()
        else:
            self._position = 1.0 if checked else 0.0
        self.toggled.emit(checked)
        self.update()

    # ------------------------------------------------------------------
    def enterEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.set_checked(not self._checked)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.set_checked(not self._checked)
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        pal = palette(self._theme_name())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        track = QRectF(1, 1, self.width() - 2, self.height() - 2)
        if self._checked:
            fill = QColor(pal.accent)
            if self._hover:
                fill = fill.lighter(108)
        else:
            fill = QColor(pal.surface_active if not self._hover else pal.border_strong)
        painter.setPen(QPen(QColor(pal.border_strong) if not self._checked else fill, 1))
        painter.setBrush(fill)
        painter.drawRoundedRect(track, track.height() / 2, track.height() / 2)

        knob_radius = (self.height() - 8) / 2
        center_x = 4 + knob_radius + self._position * (self.width() - 8 - 2 * knob_radius)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QRectF(center_x - knob_radius, 4 + 0, knob_radius * 2, knob_radius * 2))
        painter.end()

    @staticmethod
    def _theme_name() -> str:
        app = QApplication.instance()
        return getattr(app, "theme_name", "dark") if app else "dark"


# ----------------------------------------------------------------------
# Search field with leading icon and clear button
# ----------------------------------------------------------------------
class SearchField(QLineEdit):
    """Text input with a search glyph, a clear affordance and Esc support."""

    def __init__(self, placeholder: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("SearchField")
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(False)
        self.setAccessibleName("Search clipboard history")
        self.textChanged.connect(self._sync_clear_button)
        self._clear_button = QPushButton(self)
        self._clear_button.setObjectName("IconBtn")
        self._clear_button.setFixedSize(26, 26)
        self._clear_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_button.clicked.connect(self.clear)
        self._clear_button.hide()
        self._sync_clear_button(self.text())

    def _refresh_icons(self) -> None:
        pal = palette(self._theme_name())
        self._clear_button.setIcon(
            icons.icon("x", pal.text_muted, 14)
        )
        self.update()

    def _theme_name(self) -> str:
        app = QApplication.instance()
        return getattr(app, "theme_name", "dark") if app else "dark"

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        frame_width = 1
        self._clear_button.move(
            self.width() - self._clear_button.width() - frame_width - 6,
            (self.height() - self._clear_button.height()) // 2,
        )

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().paintEvent(event)
        pal = palette(self._theme_name())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        icon_size = 16
        y = (self.height() - icon_size) / 2
        painter.drawPixmap(
            11, int(y), icons.pixmap("search", pal.text_muted, icon_size)
        )
        painter.end()

    def _sync_clear_button(self, text: str) -> None:
        self._clear_button.setVisible(bool(text))

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape and self.text():
            self.clear()
            event.accept()
            return
        super().keyPressEvent(event)


# ----------------------------------------------------------------------
# Sidebar navigation button
# ----------------------------------------------------------------------
class NavButton(QWidget):
    """Icon + label + optional count badge, used in the sidebar."""

    clicked = Signal()

    def __init__(
        self,
        key: str,
        label: str,
        icon_name: str,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.key = key
        self.label = label
        self.icon_name = icon_name
        self.count: Optional[int] = None
        self._checked = False
        self._hover = False
        self._alert = False  # used for the "paused" indicator
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(34)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(label)

    def set_checked(self, checked: bool) -> None:
        if checked != self._checked:
            self._checked = checked
            self.update()

    def set_count(self, count: Optional[int]) -> None:
        if count != self.count:
            self.count = count
            self.update()

    def set_alert(self, alert: bool) -> None:
        if alert != self._alert:
            self._alert = alert
            self.update()

    # ------------------------------------------------------------------
    def enterEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        pal = palette(self._theme_name())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(8, 3, -8, -3)
        if self._checked:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(pal.accent_soft))
            painter.drawRoundedRect(rect, 8, 8)
            text_color = pal.accent
            icon_color = pal.accent
        elif self._hover:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(pal.surface_hover))
            painter.drawRoundedRect(rect, 8, 8)
            text_color = pal.text
            icon_color = pal.text_secondary
        else:
            text_color = pal.text_secondary
            icon_color = pal.text_muted

        icon_size = 16
        icon_x = rect.left() + 8
        icon_y = (self.height() - icon_size) // 2
        painter.setFont(base_font(13))
        metrics = painter.fontMetrics()
        text_x = icon_x + icon_size + 10
        text_y = (self.height() + metrics.ascent() - metrics.descent()) // 2

        if self._alert:
            icon_color = pal.danger
        painter.drawPixmap(icon_x, icon_y, icons.pixmap(self.icon_name, icon_color, icon_size))

        painter.setPen(QColor(text_color))
        label_font = base_font(13, QFont.Weight.DemiBold if self._checked else QFont.Weight.Normal)
        painter.setFont(label_font)
        max_text_width = rect.width() - (text_x - rect.left()) - 46
        display = metrics.elidedText(
            self.label, Qt.TextElideMode.ElideRight, max(40, max_text_width)
        )
        painter.drawText(text_x, text_y, display)

        if self.count is not None or self._alert:
            badge_text = str(self.count) if self.count is not None else "Paused"
            badge_font = base_font(10, QFont.Weight.DemiBold)
            painter.setFont(badge_font)
            badge_metrics = painter.fontMetrics()
            badge_width = badge_metrics.horizontalAdvance(badge_text) + 12
            badge_height = 18
            badge_rect = QRectF(
                rect.right() - badge_width - 6,
                (self.height() - badge_height) / 2,
                badge_width,
                badge_height,
            )
            if self._alert:
                painter.setBrush(QColor(pal.danger_soft))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(badge_rect, 9, 9)
                painter.setPen(QColor(pal.danger))
            elif self._checked:
                painter.setBrush(QColor(pal.accent).lighter(140))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(badge_rect, 9, 9)
                painter.setPen(QColor(pal.accent_text))
            else:
                painter.setBrush(QColor(pal.surface_active))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(badge_rect, 9, 9)
                painter.setPen(QColor(pal.text_muted))
            painter.drawText(
                badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text
            )
        painter.end()

    def _theme_name(self) -> str:
        app = QApplication.instance()
        return getattr(app, "theme_name", "dark") if app else "dark"


# ----------------------------------------------------------------------
# Empty state
# ----------------------------------------------------------------------
class EmptyState(QWidget):
    """Friendly placeholder shown when a list has nothing to display."""

    action_clicked = Signal()

    def __init__(
        self,
        icon_name: str,
        title: str,
        message: str,
        action_label: str = "",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.icon_name = icon_name
        self._action_label = action_label

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)

        self._icon_label = QLabel()
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_label.setFixedSize(56, 56)
        layout.addWidget(self._icon_label, 0, Qt.AlignmentFlag.AlignCenter)

        title_label = QLabel(title)
        title_label.setProperty("title", True)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        message_label = QLabel(message)
        message_label.setProperty("secondary", True)
        message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message_label.setWordWrap(True)
        message_label.setFixedWidth(380)
        layout.addWidget(message_label, 0, Qt.AlignmentFlag.AlignCenter)

        if action_label:
            self._action_button = QPushButton(action_label)
            self._action_button.setObjectName("Primary")
            self._action_button.setCursor(Qt.CursorShape.PointingHandCursor)
            self._action_button.clicked.connect(self.action_clicked)
            row = QHBoxLayout()
            row.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row.addStretch(1)
            row.addWidget(self._action_button)
            row.addStretch(1)
            layout.addLayout(row)
            layout.addSpacing(6)

    def set_icon(self, icon_name: str) -> None:
        self.icon_name = icon_name
        self._refresh()

    def _refresh(self) -> None:
        pal = palette(self._theme_name())
        self._icon_label.setPixmap(
            icons.pixmap(self.icon_name, pal.border_strong, 44, 1.5)
        )

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._refresh()
        super().showEvent(event)

    @staticmethod
    def _theme_name() -> str:
        app = QApplication.instance()
        return getattr(app, "theme_name", "dark") if app else "dark"


# ----------------------------------------------------------------------
# Card container
# ----------------------------------------------------------------------
class Card(QFrame):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("Card")


# ----------------------------------------------------------------------
# Toast notifications
# ----------------------------------------------------------------------
class Toast(QFrame):
    """Small transient message with an optional action button."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(46)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 10, 0)
        layout.setSpacing(10)

        self._icon_label = QLabel()
        self._icon_label.setFixedSize(18, 18)
        layout.addWidget(self._icon_label)

        self._message = QLabel()
        layout.addWidget(self._message, 1)

        self._action_button = QPushButton()
        self._action_button.setObjectName("Ghost")
        self._action_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._action_button.clicked.connect(self._on_action)
        layout.addWidget(self._action_button)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)

        self.hide()

    # ------------------------------------------------------------------
    _on_action_callback = None

    def show_message(
        self,
        message: str,
        *,
        icon_name: str = "check",
        icon_color: str = "#4fc9a8",
        duration_ms: int = 3200,
        action_label: str = "",
        action=None,
    ) -> None:
        self._message.setText(message)
        self._icon_label.setPixmap(icons.pixmap(icon_name, icon_color, 16))
        self._on_action_callback = action
        if action_label and action is not None:
            self._action_button.setText(action_label)
            self._action_button.show()
        else:
            self._action_button.hide()
        self.adjustSize()
        self.show()
        self.raise_()
        self._timer.start(duration_ms)

    def dismiss(self) -> None:
        self.hide()

    def _on_action(self) -> None:
        callback = self._on_action_callback
        self.dismiss()
        if callback is not None:
            callback()
