"""Shortcut parsing / formatting (pure logic; no OS registration)."""

from __future__ import annotations

import pytest

from easy_clipboard.windows.hotkey import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_NOREPEAT,
    MOD_SHIFT,
    MOD_WIN,
    HotkeyError,
    format_hotkey,
    parse_hotkey,
)


def test_parse_default_shortcut():
    modifiers, key = parse_hotkey("Ctrl+Shift+V")
    assert modifiers & MOD_CONTROL
    assert modifiers & MOD_SHIFT
    assert modifiers & MOD_NOREPEAT
    assert not modifiers & MOD_ALT
    assert key == 0x56  # 'V'


def test_parse_is_case_and_separator_agnostic():
    expected = parse_hotkey("Ctrl+Shift+V")
    assert parse_hotkey("ctrl+shift+v") == expected
    assert parse_hotkey("CTRL-SHIFT-V") == expected
    assert parse_hotkey("  Ctrl + Shift + V  ") == expected


def test_parse_all_modifier_flavours():
    modifiers, key = parse_hotkey("Alt+Win+Space")
    assert modifiers & MOD_ALT
    assert modifiers & MOD_WIN
    assert key == 0x20

    modifiers, _ = parse_hotkey("Control+Alt+Delete")
    assert modifiers & MOD_CONTROL
    assert modifiers & MOD_ALT


@pytest.mark.parametrize(
    "combo,keycode",
    [
        ("Ctrl+A", 0x41),
        ("Ctrl+Shift+P", 0x50),
        ("Ctrl+F1", 0x70),
        ("Ctrl+Tab", 0x09),
        ("Shift+F12", 0x7B),
    ],
)
def test_parse_keys(combo, keycode):
    modifiers, key = parse_hotkey(combo)
    assert key == keycode
    if combo.startswith("Ctrl"):
        assert modifiers & MOD_CONTROL


@pytest.mark.parametrize(
    "bad",
    ["", "   ", "Ctrl+", "+V", "Hyper+V", "Ctrl+Nope", "V", "Ctrl+Alt", "Shift"],
)
def test_parse_rejects_invalid_shortcuts(bad):
    with pytest.raises(HotkeyError):
        parse_hotkey(bad)


def test_format_hotkey_for_display():
    assert format_hotkey("ctrl+shift+v") == "Ctrl+Shift+V"
    assert format_hotkey("Ctrl+Shift+V") == "Ctrl+Shift+V"
    assert format_hotkey("alt+f4") == "Alt+F4"
    assert format_hotkey("win+g") == "Win+G"
    assert format_hotkey("shift+f5") == "Shift+F5"


def test_format_hotkey_passes_through_garbage():
    # Displaying an invalid combo must never raise.
    assert format_hotkey("not a shortcut") == "not a shortcut"
    assert format_hotkey("") == ""


def test_roundtrip_stability():
    combo = format_hotkey("ctrl+alt+shift+k")
    assert combo == "Ctrl+Alt+Shift+K"
    assert format_hotkey(combo) == combo
