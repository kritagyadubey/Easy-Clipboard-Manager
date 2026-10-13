"""Settings defaults, persistence, validation and corruption recovery."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from easy_clipboard.settings import (
    DEFAULT_HOTKEY,
    MAX_HISTORY_LIMIT,
    MIN_HISTORY_LIMIT,
    Settings,
    SettingsStore,
)


def test_defaults(settings_store: SettingsStore):
    s = settings_store.get()
    assert s.theme == "dark"
    assert s.density == "comfortable"
    assert s.monitoring_enabled is True
    assert s.duplicate_handling == "refresh"
    assert s.global_hotkey == DEFAULT_HOTKEY
    assert s.max_items == 500
    assert s.retention_days == 30
    assert s.launch_at_startup is False
    assert s.minimize_to_tray is True
    assert s.excluded_apps == []


def test_update_persists_to_disk(settings_path: Path):
    store = SettingsStore(settings_path)
    store.update(theme="light", max_items=120, monitoring_enabled=False)

    assert settings_path.exists()
    reloaded = SettingsStore(settings_path)
    s = reloaded.get()
    assert s.theme == "light"
    assert s.max_items == 120
    assert s.monitoring_enabled is False


def test_get_returns_a_copy(settings_store: SettingsStore):
    snapshot = settings_store.get()
    snapshot.theme = "light"
    assert settings_store.get().theme == "dark"


def test_unknown_key_raises(settings_store: SettingsStore):
    with pytest.raises(KeyError):
        settings_store.update(not_a_real_setting=1)
    assert settings_store.get() == settings_store.get()


def test_invalid_values_are_normalised(settings_store: SettingsStore):
    s = settings_store.update(
        theme="neon",
        density="spacious",
        duplicate_handling="merge",
        max_items=999_999,
        retention_days=-5,
        excluded_apps=["  ", "  Notepad.EXE ", 42],
        global_hotkey="   ",
    )
    assert s.theme == "dark"
    assert s.density == "comfortable"
    assert s.duplicate_handling == "refresh"
    assert s.max_items == MAX_HISTORY_LIMIT
    assert s.retention_days == 0
    assert s.excluded_apps == ["notepad.exe", "42"]
    assert s.global_hotkey == DEFAULT_HOTKEY

    s = settings_store.update(max_items=1, retention_days=10**9)
    assert s.max_items == MIN_HISTORY_LIMIT
    assert s.retention_days == 3650


def test_non_numeric_limits_fall_back_to_defaults(settings_store: SettingsStore):
    s = settings_store.update(max_items="lots", retention_days=None)
    assert s.max_items == 500
    assert s.retention_days == 30


def test_load_ignores_unknown_keys(settings_path: Path):
    payload = asdict_defaults()
    payload["theme"] = "light"
    payload["from_the_future"] = {"nested": True}
    settings_path.write_text(json.dumps(payload), encoding="utf-8")

    store = SettingsStore(settings_path)
    assert store.get().theme == "light"
    assert not hasattr(store.get(), "from_the_future")


def test_corrupted_file_recovers_to_defaults(settings_path: Path):
    settings_path.write_text("{ definitely not json", encoding="utf-8")
    store = SettingsStore(settings_path)

    # App keeps working with defaults and the broken file is quarantined.
    assert store.get().theme == "dark"
    quarantine = settings_path.with_suffix(".json.corrupt")
    assert quarantine.exists()
    assert settings_path.exists()  # a fresh, valid file was written
    json.loads(settings_path.read_text(encoding="utf-8"))


def test_wrong_types_in_file_are_normalised(settings_path: Path):
    settings_path.write_text(
        json.dumps({"theme": 5, "excluded_apps": "notepad", "max_items": []}),
        encoding="utf-8",
    )
    store = SettingsStore(settings_path)
    s = store.get()
    assert s.theme == "dark"
    assert s.excluded_apps == []
    assert s.max_items == 500


def test_missing_file_uses_defaults_and_save_is_atomic(settings_path: Path):
    store = SettingsStore(settings_path)
    store.update(theme="light")
    assert not settings_path.with_suffix(".json.tmp").exists()
    raw = json.loads(settings_path.read_text(encoding="utf-8"))
    assert raw["theme"] == "light"


def test_listeners_are_notified(settings_store: SettingsStore):
    seen = []
    settings_store.add_listener(lambda s: seen.append(s.theme))
    settings_store.update(theme="light")
    assert seen == ["light"]


def test_failing_listener_does_not_break_update(settings_store: SettingsStore):
    def boom(_settings):
        raise RuntimeError("listener bug")

    settings_store.add_listener(boom)
    result = settings_store.update(theme="light")  # must not raise
    assert result.theme == "light"


def asdict_defaults() -> dict:
    from dataclasses import asdict

    return asdict(Settings())
