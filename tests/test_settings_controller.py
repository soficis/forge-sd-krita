"""Unit tests for forge.settings_controller — JSON-backed settings with
schema validation, deep merge, toggle/append/remove helpers, and migration.
"""

from __future__ import annotations

import json
import threading

import pytest

from forge.settings_controller import SettingsController


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_json(path, data):
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Load and merge
# ---------------------------------------------------------------------------


class TestLoadAndMerge:
    """Settings are loaded from defaults and merged with user overrides."""

    def test_defaults_used_when_no_user_file(self, tmp_path):
        defaults = {"server": {"host": "http://localhost"}}
        _write_json(tmp_path / "default_settings.json", defaults)

        controller = SettingsController(base_dir=tmp_path)
        assert controller.get("server.host") == "http://localhost"

    def test_user_overrides_defaults(self, tmp_path):
        defaults = {"server": {"host": "http://localhost", "port": 7860}}
        user = {"server": {"host": "http://example.com"}}
        _write_json(tmp_path / "default_settings.json", defaults)
        _write_json(tmp_path / "user_settings.json", user)

        controller = SettingsController(base_dir=tmp_path)
        assert controller.get("server.host") == "http://example.com"
        assert controller.get("server.port") == 7860

    def test_unknown_keys_in_user_are_ignored(self, tmp_path):
        defaults = {"server": {"host": "x"}}
        user = {"server": {"unknown_key": "value"}, "extra_top": True}
        _write_json(tmp_path / "default_settings.json", defaults)
        _write_json(tmp_path / "user_settings.json", user)

        controller = SettingsController(base_dir=tmp_path)
        assert controller.has("server.unknown_key") is False
        assert controller.has("extra_top") is False

    def test_wrong_type_in_user_is_ignored(self, tmp_path):
        defaults = {"previews": {"enabled": True, "refresh_seconds": 1.0}}
        user = {"previews": {"enabled": "yes"}}
        _write_json(tmp_path / "default_settings.json", defaults)
        _write_json(tmp_path / "user_settings.json", user)

        controller = SettingsController(base_dir=tmp_path)
        assert controller.get("previews.enabled") is True

    def test_missing_default_settings_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            SettingsController(base_dir=tmp_path)

    def test_schema_version_set(self, tmp_path):
        defaults = {"x": 1}
        _write_json(tmp_path / "default_settings.json", defaults)

        controller = SettingsController(base_dir=tmp_path)
        assert controller.get("_schema_version") == 1


# ---------------------------------------------------------------------------
# get / has / set
# ---------------------------------------------------------------------------


class TestGetHasSet:
    """Basic get/has/set operations."""

    def test_get_nested_value(self, tmp_path):
        defaults = {"a": {"b": {"c": 42}}}
        _write_json(tmp_path / "default_settings.json", defaults)
        controller = SettingsController(base_dir=tmp_path)
        assert controller.get("a.b.c") == 42

    def test_get_top_level(self, tmp_path):
        defaults = {"flag": True}
        _write_json(tmp_path / "default_settings.json", defaults)
        controller = SettingsController(base_dir=tmp_path)
        assert controller.get("flag") is True

    def test_has_existing_key(self, tmp_path):
        defaults = {"x": 1}
        _write_json(tmp_path / "default_settings.json", defaults)
        controller = SettingsController(base_dir=tmp_path)
        assert controller.has("x") is True

    def test_has_missing_key(self, tmp_path):
        defaults = {"x": 1}
        _write_json(tmp_path / "default_settings.json", defaults)
        controller = SettingsController(base_dir=tmp_path)
        assert controller.has("y") is False

    def test_set_valid_value(self, tmp_path):
        defaults = {"count": 0}
        _write_json(tmp_path / "default_settings.json", defaults)
        controller = SettingsController(base_dir=tmp_path)
        controller.set("count", 5)
        assert controller.get("count") == 5

    def test_set_wrong_type_raises(self, tmp_path):
        defaults = {"flag": True}
        _write_json(tmp_path / "default_settings.json", defaults)
        controller = SettingsController(base_dir=tmp_path)
        with pytest.raises(TypeError):
            controller.set("flag", "yes")

    def test_set_unknown_key_raises(self, tmp_path):
        defaults = {"x": 1}
        _write_json(tmp_path / "default_settings.json", defaults)
        controller = SettingsController(base_dir=tmp_path)
        with pytest.raises(KeyError):
            controller.set("nonexistent", 1)

    def test_set_float_accepts_int(self, tmp_path):
        defaults = {"ratio": 1.0}
        _write_json(tmp_path / "default_settings.json", defaults)
        controller = SettingsController(base_dir=tmp_path)
        controller.set("ratio", 2)
        assert controller.get("ratio") == 2


# ---------------------------------------------------------------------------
# toggle / append / remove
# ---------------------------------------------------------------------------


class TestMutationHelpers:
    """toggle, append, remove helpers."""

    def test_toggle_bool(self, tmp_path):
        defaults = {"flags": {"enabled": False}}
        _write_json(tmp_path / "default_settings.json", defaults)
        controller = SettingsController(base_dir=tmp_path)

        controller.toggle("flags.enabled")
        assert controller.get("flags.enabled") is True

        controller.toggle("flags.enabled")
        assert controller.get("flags.enabled") is False

    def test_append_to_list(self, tmp_path):
        defaults = {"items": {"list": ["a", "b"]}}
        _write_json(tmp_path / "default_settings.json", defaults)
        controller = SettingsController(base_dir=tmp_path)

        controller.append("items.list", "c")
        assert controller.get("items.list") == ["a", "b", "c"]

    def test_append_deduplicates(self, tmp_path):
        defaults = {"items": {"list": ["a"]}}
        _write_json(tmp_path / "default_settings.json", defaults)
        controller = SettingsController(base_dir=tmp_path)

        controller.append("items.list", "a")
        assert controller.get("items.list") == ["a"]

    def test_remove_from_list(self, tmp_path):
        defaults = {"items": {"list": ["a", "b", "c"]}}
        _write_json(tmp_path / "default_settings.json", defaults)
        controller = SettingsController(base_dir=tmp_path)

        controller.remove("items.list", "b")
        assert controller.get("items.list") == ["a", "c"]

    def test_remove_nonexistent_value_noop(self, tmp_path):
        defaults = {"items": {"list": ["a"]}}
        _write_json(tmp_path / "default_settings.json", defaults)
        controller = SettingsController(base_dir=tmp_path)

        controller.remove("items.list", "z")
        assert controller.get("items.list") == ["a"]

    def test_toggle_list_adds_and_removes(self, tmp_path):
        defaults = {"items": {"list": ["a"]}}
        _write_json(tmp_path / "default_settings.json", defaults)
        controller = SettingsController(base_dir=tmp_path)

        controller.toggle("items.list", "b")
        assert controller.get("items.list") == ["a", "b"]

        controller.toggle("items.list", "a")
        assert controller.get("items.list") == ["b"]

    def test_toggle_non_bool_non_list_raises(self, tmp_path):
        defaults = {"count": 5}
        _write_json(tmp_path / "default_settings.json", defaults)
        controller = SettingsController(base_dir=tmp_path)
        with pytest.raises(ValueError):
            controller.toggle("count")

    def test_toggle_list_without_value_raises(self, tmp_path):
        defaults = {"items": {"list": ["a"]}}
        _write_json(tmp_path / "default_settings.json", defaults)
        controller = SettingsController(base_dir=tmp_path)
        with pytest.raises(ValueError):
            controller.toggle("items.list")

    def test_append_non_list_raises(self, tmp_path):
        defaults = {"flag": True}
        _write_json(tmp_path / "default_settings.json", defaults)
        controller = SettingsController(base_dir=tmp_path)
        with pytest.raises(TypeError):
            controller.append("flag", "x")

    def test_remove_non_list_raises(self, tmp_path):
        defaults = {"flag": True}
        _write_json(tmp_path / "default_settings.json", defaults)
        controller = SettingsController(base_dir=tmp_path)
        with pytest.raises(TypeError):
            controller.remove("flag", "x")


# ---------------------------------------------------------------------------
# Save / restore defaults
# ---------------------------------------------------------------------------


class TestSaveAndRestore:
    """Settings are persisted and restored correctly."""

    def test_save_creates_user_settings_file(self, tmp_path):
        defaults = {"x": 1}
        _write_json(tmp_path / "default_settings.json", defaults)
        controller = SettingsController(base_dir=tmp_path)
        controller.set("x", 2)
        controller.save()

        user_data = json.loads(
            (tmp_path / "user_settings.json").read_text(encoding="utf-8")
        )
        assert user_data["x"] == 2

    def test_restore_defaults_resets_all(self, tmp_path):
        defaults = {"a": 1, "b": {"c": 2}}
        _write_json(tmp_path / "default_settings.json", defaults)
        controller = SettingsController(base_dir=tmp_path)
        controller.set("a", 99)
        controller.set("b.c", 99)
        controller.save()

        controller.restore_defaults()
        assert controller.get("a") == 1
        assert controller.get("b.c") == 2

    def test_save_roundtrips(self, tmp_path):
        defaults = {"x": 1}
        _write_json(tmp_path / "default_settings.json", defaults)
        controller = SettingsController(base_dir=tmp_path)
        controller.set("x", 42)
        controller.save()

        controller2 = SettingsController(base_dir=tmp_path)
        assert controller2.get("x") == 42


# ---------------------------------------------------------------------------
# Debounced save
# ---------------------------------------------------------------------------


class TestDebouncedSave:
    """debounced_save coalesces rapid calls into a single write."""

    def test_debounced_save_writes_eventually(self, tmp_path):
        defaults = {"x": 1}
        _write_json(tmp_path / "default_settings.json", defaults)
        controller = SettingsController(base_dir=tmp_path)
        controller.set("x", 99)
        controller.debounced_save()

        import time
        time.sleep(0.5)

        user_data = json.loads(
            (tmp_path / "user_settings.json").read_text(encoding="utf-8")
        )
        assert user_data["x"] == 99

    def test_debounced_save_coalesces(self, tmp_path):
        defaults = {"x": 1}
        _write_json(tmp_path / "default_settings.json", defaults)
        controller = SettingsController(base_dir=tmp_path)

        controller.set("x", 10)
        controller.debounced_save()
        controller.set("x", 20)
        controller.debounced_save()

        import time
        time.sleep(0.5)

        user_data = json.loads(
            (tmp_path / "user_settings.json").read_text(encoding="utf-8")
        )
        assert user_data["x"] == 20


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


class TestMigration:
    """Schema migration from old versions."""

    def test_old_schema_version_gets_migrated(self, tmp_path):
        defaults = {"x": 1}
        user = {"x": 2, "_schema_version": 0}
        _write_json(tmp_path / "default_settings.json", defaults)
        _write_json(tmp_path / "user_settings.json", user)

        controller = SettingsController(base_dir=tmp_path)
        assert controller.get("_schema_version") == 1
        assert controller.get("x") == 2


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Various edge cases and error conditions."""

    def test_empty_path_raises(self, tmp_path):
        defaults = {"x": 1}
        _write_json(tmp_path / "default_settings.json", defaults)
        controller = SettingsController(base_dir=tmp_path)
        with pytest.raises(ValueError):
            controller.get("")

    def test_corrupt_user_settings_uses_defaults(self, tmp_path):
        defaults = {"x": 1}
        _write_json(tmp_path / "default_settings.json", defaults)
        (tmp_path / "user_settings.json").write_text("not json {{{")

        controller = SettingsController(base_dir=tmp_path)
        assert controller.get("x") == 1

    def test_non_dict_user_settings_uses_defaults(self, tmp_path):
        defaults = {"x": 1}
        _write_json(tmp_path / "default_settings.json", defaults)
        (tmp_path / "user_settings.json").write_text(json.dumps([1, 2, 3]))

        controller = SettingsController(base_dir=tmp_path)
        assert controller.get("x") == 1

    def test_non_dict_default_settings_raises(self, tmp_path):
        _write_json(tmp_path / "default_settings.json", [1, 2, 3])
        with pytest.raises(RuntimeError):
            SettingsController(base_dir=tmp_path)

    def test_resolve_parent_traverses_non_dict_raises(self, tmp_path):
        defaults = {"a": "string"}
        _write_json(tmp_path / "default_settings.json", defaults)
        controller = SettingsController(base_dir=tmp_path)
        with pytest.raises(TypeError):
            controller.set("a.b", 1)
