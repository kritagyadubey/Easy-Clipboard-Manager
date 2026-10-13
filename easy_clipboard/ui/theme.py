"""Visual identity: colour palettes, typography and the generated stylesheet.

Both themes are designed together so they carry the same spacing, radii and
hierarchy.  Colours are resolved at runtime, so switching themes is a matter
of rebuilding the stylesheet and repolishing widgets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication

try:
    import winreg
except ImportError:  # pragma: no cover - non-Windows
    winreg = None  # type: ignore[assignment]


@dataclass(frozen=True)
class Palette:
    name: str
    bg: str
    bg_alt: str          # sidebar / chrome
    surface: str         # cards and inputs
    surface_hover: str
    surface_active: str
    border: str
    border_strong: str
    text: str
    text_secondary: str
    text_muted: str
    accent: str
    accent_hover: str
    accent_text: str     # text drawn on accent buttons
    accent_soft: str     # translucent accent fill (selection)
    danger: str
    danger_hover: str
    danger_soft: str
    pin: str
    favorite: str
    code: str
    link: str
    email: str
    number: str
    json_: str

    # Type-specific accent colours ------------------------------------
    def type_color(self, content_type: str) -> str:
        return {
            "link": self.link,
            "code": self.code,
            "email": self.email,
            "number": self.number,
            "json": self.json_,
        }.get(content_type, self.text_secondary)


DARK = Palette(
    name="dark",
    bg="#0f1116",
    bg_alt="#14171e",
    surface="#191d25",
    surface_hover="#20252f",
    surface_active="#252c39",
    border="#252b36",
    border_strong="#333b49",
    text="#e7eaf0",
    text_secondary="#9ba5b4",
    text_muted="#6c7684",
    accent="#5b8cff",
    accent_hover="#7aa1ff",
    accent_text="#0d1017",
    accent_soft="#1e2a44",
    danger="#e5615a",
    danger_hover="#f07a73",
    danger_soft="#2d1b1f",
    pin="#e0a63c",
    favorite="#ef7d9c",
    code="#b48cff",
    link="#5aa9ff",
    email="#4fc9a8",
    number="#dcae4e",
    json_="#82c98a",
)

LIGHT = Palette(
    name="light",
    bg="#f4f6f9",
    bg_alt="#eaeef3",
    surface="#ffffff",
    surface_hover="#f1f4f8",
    surface_active="#e7edf6",
    border="#dde2ea",
    border_strong="#c3cbd7",
    text="#1b2029",
    text_secondary="#586273",
    text_muted="#8a94a3",
    accent="#3567d8",
    accent_hover="#2b58c2",
    accent_text="#ffffff",
    accent_soft="#e6ecfa",
    danger="#cf4343",
    danger_hover="#b93a3a",
    danger_soft="#faeaea",
    pin="#b1791a",
    favorite="#d64a72",
    code="#7a56c7",
    link="#1f6feb",
    email="#12866c",
    number="#9a6b00",
    json_="#3a7b3a",
)

PALETTES: Dict[str, Palette] = {"dark": DARK, "light": LIGHT}

# Content-type metadata used across the UI.
TYPE_ICONS = {
    "text": "file-text",
    "multiline": "file-text",
    "link": "link",
    "code": "code",
    "email": "mail",
    "number": "hash",
    "json": "braces",
}


def system_prefers_light() -> bool:
    """Read the WindowsApps theme preference (light/dark)."""
    if winreg is None:
        return False
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return bool(value)
    except OSError:
        return False


def resolve_theme(theme_setting: str) -> str:
    if theme_setting == "system":
        return "light" if system_prefers_light() else "dark"
    return theme_setting if theme_setting in PALETTES else "dark"


def palette(theme_setting: str) -> Palette:
    return PALETTES[resolve_theme(theme_setting)]


# ----------------------------------------------------------------------
# Typography
# ----------------------------------------------------------------------
FONT_FAMILY = "Segoe UI"
MONO_FAMILY = "Cascadia Mono"


def base_font(size_px: int = 13, weight: int = QFont.Weight.Normal) -> QFont:
    font = QFont(FONT_FAMILY, size_px)
    font.setPixelSize(size_px)
    font.setWeight(weight)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return font


def mono_font(size_px: int = 13) -> QFont:
    font = QFont(MONO_FAMILY, size_px)
    font.setPixelSize(size_px)
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font


def apply_application_font(app: QApplication) -> None:
    app.setFont(base_font(13))


# ----------------------------------------------------------------------
# Stylesheet
# ----------------------------------------------------------------------
def build_stylesheet(pal: Palette, density: str = "comfortable") -> str:
    compact = density == "compact"
    radius = 8 if compact else 10
    pad_v = 8 if compact else 10
    return f"""
/* ---------- Base ---------- */
QWidget {{
    color: {pal.text};
    background: transparent;
    font-size: 13px;
}}
QMainWindow, QDialog {{ background: {pal.bg}; }}
QToolTip {{
    background: {pal.surface_active};
    color: {pal.text};
    border: 1px solid {pal.border_strong};
    border-radius: 6px;
    padding: 6px 8px;
    font-size: 12px;
}}
QLabel[muted="true"] {{ color: {pal.text_muted}; }}
QLabel[secondary="true"] {{ color: {pal.text_secondary}; }}
QLabel[heading="true"] {{
    color: {pal.text};
    font-size: 18px;
    font-weight: 600;
}}
QLabel[subheading="true"] {{
    color: {pal.text_secondary};
    font-size: 13px;
}}
QLabel[title="true"] {{
    color: {pal.text};
    font-size: 14px;
    font-weight: 600;
}}

/* ---------- Sidebar ---------- */
QFrame#Sidebar {{
    background: {pal.bg_alt};
    border-right: 1px solid {pal.border};
}}
QLabel#BrandName {{ font-size: 14px; font-weight: 700; color: {pal.text}; }}
QLabel#BrandTagline {{ font-size: 11px; color: {pal.text_muted}; }}
QLabel#SectionCaption {{
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
    color: {pal.text_muted};
}}

/* ---------- Buttons ---------- */
QPushButton {{
    background: {pal.surface};
    color: {pal.text};
    border: 1px solid {pal.border};
    border-radius: {radius}px;
    padding: 7px 14px;
    font-size: 13px;
}}
QPushButton:hover {{ background: {pal.surface_hover}; border-color: {pal.border_strong}; }}
QPushButton:pressed {{ background: {pal.surface_active}; }}
QPushButton:focus {{ outline: none; border-color: {pal.accent}; }}

QPushButton#Primary {{
    background: {pal.accent};
    color: {pal.accent_text};
    border: 1px solid transparent;
    font-weight: 600;
}}
QPushButton#Primary:hover {{ background: {pal.accent_hover}; }}
QPushButton#Primary:pressed {{ background: {pal.accent}; }}

QPushButton#Danger {{
    background: {pal.danger_soft};
    color: {pal.danger};
    border: 1px solid {pal.danger};
}}
QPushButton#Danger:hover {{ background: {pal.danger}; color: {pal.accent_text}; }}

QPushButton#DangerSolid {{
    background: {pal.danger};
    color: #ffffff;
    border: 1px solid transparent;
    font-weight: 600;
}}
QPushButton#DangerSolid:hover {{ background: {pal.danger_hover}; }}

QPushButton#Ghost {{
    background: transparent;
    border: 1px solid transparent;
    color: {pal.text_secondary};
    padding: 6px 10px;
}}
QPushButton#Ghost:hover {{
    background: {pal.surface_hover};
    color: {pal.text};
    border-radius: {radius}px;
}}
QPushButton#Ghost:pressed {{ background: {pal.surface_active}; }}

QPushButton#IconBtn {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: {radius - 2}px;
    padding: 5px;
}}
QPushButton#IconBtn:hover {{ background: {pal.surface_hover}; border-color: {pal.border}; }}
QPushButton#IconBtn:checked {{ background: {pal.accent_soft}; border-color: {pal.accent}; }}

QPushButton:disabled {{ color: {pal.text_muted}; background: {pal.surface}; border-color: {pal.border}; }}

/* ---------- Search field ---------- */
QLineEdit#SearchField {{
    background: {pal.surface};
    border: 1px solid {pal.border};
    border-radius: {radius}px;
    padding: {pad_v}px 12px {pad_v}px 34px;
    font-size: 13px;
    color: {pal.text};
    selection-background-color: {pal.accent};
    selection-color: {pal.accent_text};
}}
QLineEdit#SearchField:hover {{ border-color: {pal.border_strong}; }}
QLineEdit#SearchField:focus {{ border-color: {pal.accent}; background: {pal.surface}; }}

QLineEdit#Field, QPlainTextEdit#Field, QTextEdit#Field, QSpinBox#Field {{
    background: {pal.surface};
    border: 1px solid {pal.border};
    border-radius: {radius - 2}px;
    padding: 8px 10px;
    color: {pal.text};
    selection-background-color: {pal.accent};
    selection-color: {pal.accent_text};
}}
QLineEdit#Field:focus, QPlainTextEdit#Field:focus, QTextEdit#Field:focus, QSpinBox#Field:focus {{
    border-color: {pal.accent};
}}
QLineEdit#Field:read-only {{ color: {pal.text_secondary}; background: {pal.bg_alt}; }}
QSpinBox#Field {{ padding: 6px 10px; }}

/* ---------- List views ---------- */
QListView#ItemList {{
    background: transparent;
    border: none;
    outline: none;
    padding: 4px 6px;
}}
QListView#ItemList:focus {{ outline: none; }}

/* ---------- Scrollbars ---------- */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 4px 2px 4px 2px;
}}
QScrollBar::handle:vertical {{
    background: {pal.border_strong};
    border-radius: 5px;
    min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{ background: {pal.text_muted}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px 4px;
}}
QScrollBar::handle:horizontal {{
    background: {pal.border_strong};
    border-radius: 5px;
    min-width: 32px;
}}
QScrollBar::handle:horizontal:hover {{ background: {pal.text_muted}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ---------- Tool buttons (menus) ---------- */
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: {radius - 2}px;
    padding: 6px 10px;
    color: {pal.text_secondary};
    font-size: 13px;
}}
QToolButton:hover {{ background: {pal.surface_hover}; color: {pal.text}; border-color: {pal.border}; }}
QToolButton:pressed {{ background: {pal.surface_active}; }}
QToolButton::menu-indicator {{ image: none; width: 0; height: 0; }}

/* ---------- Dialogs ---------- */
QMessageBox {{ background: {pal.bg}; }}
QMessageBox QLabel {{ color: {pal.text}; background: transparent; }}

/* ---------- Menus ---------- */
QMenu {{
    background: {pal.surface_active};
    color: {pal.text};
    border: 1px solid {pal.border_strong};
    border-radius: {radius - 2}px;
    padding: 6px;
}}
QMenu::item {{
    background: transparent;
    border-radius: 6px;
    padding: 7px 26px 7px 12px;
    margin: 1px 2px;
}}
QMenu::item:selected {{ background: {pal.accent_soft}; color: {pal.text}; }}
QMenu::item:disabled {{ color: {pal.text_muted}; }}
QMenu::separator {{ height: 1px; background: {pal.border}; margin: 6px 8px; }}

/* ---------- Combo / Spin ---------- */
QComboBox {{
    background: {pal.surface};
    border: 1px solid {pal.border};
    border-radius: {radius - 2}px;
    padding: 6px 10px;
    color: {pal.text};
    min-height: 20px;
}}
QComboBox:hover {{ border-color: {pal.border_strong}; }}
QComboBox:focus {{ border-color: {pal.accent}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{
    image: none;
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {pal.text_secondary};
    margin-right: 10px;
}}
QComboBox QAbstractItemView {{
    background: {pal.surface_active};
    border: 1px solid {pal.border_strong};
    border-radius: 6px;
    selection-background-color: {pal.accent_soft};
    selection-color: {pal.text};
    outline: none;
    padding: 4px;
}}
QSpinBox {{ padding: 4px; }}

/* ---------- Checkbox ---------- */
QCheckBox {{ spacing: 10px; color: {pal.text}; background: transparent; }}
QCheckBox::indicator {{
    width: 18px; height: 18px;
    border-radius: 5px;
    border: 1px solid {pal.border_strong};
    background: {pal.surface};
}}
QCheckBox::indicator:hover {{ border-color: {pal.accent}; }}
QCheckBox::indicator:checked {{
    background: {pal.accent};
    border-color: {pal.accent};
    image: none;
}}
QCheckBox:disabled {{ color: {pal.text_muted}; }}

/* ---------- Splitter ---------- */
QSplitter::handle {{ background: {pal.border}; width: 1px; }}
QSplitter::handle:hover {{ background: {pal.border_strong}; }}

/* ---------- Scroll areas / dialogs ---------- */
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QFrame#Card {{
    background: {pal.surface};
    border: 1px solid {pal.border};
    border-radius: {radius + 2}px;
}}
QFrame#PanelDivider {{ background: {pal.border}; }}

/* ---------- Toast ---------- */
QFrame#Toast {{
    background: {pal.surface_active};
    border: 1px solid {pal.border_strong};
    border-radius: {radius}px;
    color: {pal.text};
}}

/* ---------- Status pill ---------- */
QLabel#Pill {{
    background: {pal.surface_active};
    color: {pal.text_secondary};
    border-radius: 9px;
    padding: 3px 9px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel#PillAccent {{
    background: {pal.accent_soft};
    color: {pal.accent};
    border-radius: 9px;
    padding: 3px 9px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel#PillWarn {{
    background: {pal.danger_soft};
    color: {pal.danger};
    border-radius: 9px;
    padding: 3px 9px;
    font-size: 11px;
    font-weight: 600;
}}

/* ---------- Settings form ---------- */
QLabel#FormLabel {{ color: {pal.text}; font-size: 13px; }}
QLabel#FormHint {{ color: {pal.text_muted}; font-size: 12px; }}
QFrame#FormRow:hover {{ background: {pal.surface_hover}; border-radius: 8px; }}
"""


# ----------------------------------------------------------------------
# Application icon / logo
# ----------------------------------------------------------------------
def render_logo(size: int = 64, accent: str = "#5b8cff", dark: bool = True) -> QPixmap:
    """Draw the app mark: a rounded tile with a clipboard glyph."""
    pixmap = QPixmap(size, size)
    pixmap.setDevicePixelRatio(1)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    margin = size * 0.06
    rect = pixmap.rect().adjusted(int(margin), int(margin), -int(margin), -int(margin))

    gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
    if dark:
        gradient.setColorAt(0.0, QColor(accent).lighter(118))
        gradient.setColorAt(1.0, QColor(accent).darker(125))
    else:
        gradient.setColorAt(0.0, QColor(accent))
        gradient.setColorAt(1.0, QColor(accent).darker(118))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    rounded = pixmap.rect().adjusted(int(margin), int(margin), -int(margin), -int(margin))
    painter.drawRoundedRect(rounded, size * 0.22, size * 0.22)

    # Clipboard body
    body = pixmap.rect().adjusted(
        int(size * 0.24), int(size * 0.24), -int(size * 0.24), -int(size * 0.26)
    )
    painter.setBrush(QColor("#ffffff"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(body, size * 0.07, size * 0.07)

    # Clip on top
    clip = pixmap.rect().adjusted(
        int(size * 0.37), int(size * 0.16), -int(size * 0.37), -int(size * 0.70)
    )
    painter.drawRoundedRect(clip, size * 0.05, size * 0.05)
    painter.setBrush(QColor(accent))
    inner = pixmap.rect().adjusted(
        int(size * 0.44), int(size * 0.21), -int(size * 0.44), -int(size * 0.75)
    )
    painter.drawRoundedRect(inner, size * 0.03, size * 0.03)

    # "Lines" of text
    pen = QPen(QColor(accent), max(1.5, size * 0.055))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    left = int(size * 0.33)
    right = int(size * 0.67)
    for frac in (0.50, 0.62, 0.74):
        y = int(size * frac)
        end = right if frac != 0.74 else int(size * 0.56)
        painter.drawLine(left, y, end, y)

    painter.end()
    return pixmap
