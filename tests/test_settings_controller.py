import json

import pytest

from forge.settings_controller import SettingsController


def _write_json(path, data):
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def test_settings_controller_merges_user_values_with_schema(tmp_path):
    defaults = {
        "server": {"host": "http://127.0.0.1:7860", "save_imgs": False},
        "prompts": {"exclude_sharing": ["inpaint"]},
        "previews": {"enabled": True, "refresh_seconds": 1.0},
    }
    user = {
        "server": {"host": "http://example.com", "unknown": 123},
        "prompts": {"exclude_sharing": ["txt2img"]},
        "previews": {"enabled": "yes"},  # wrong type, should be ignored
        "unknown_top": True,
    }

    _write_json(tmp_path / "default_settings.json", defaults)
    _write_json(tmp_path / "user_settings.json", user)

    controller = SettingsController(base_dir=tmp_path)

    assert controller.get("server.host") == "http://example.com"
    assert controller.get("server.save_imgs") is False
    assert controller.get("prompts.exclude_sharing") == ["txt2img"]
    assert controller.get("previews.enabled") is True
    assert controller.has("server.host") is True
    assert controller.has("server.unknown") is False


def test_settings_controller_mutation_helpers(tmp_path):
    defaults = {
        "flags": {"enabled": False},
        "items": {"list": ["a", "b"]},
    }

    _write_json(tmp_path / "default_settings.json", defaults)
    controller = SettingsController(base_dir=tmp_path)

    controller.toggle("flags.enabled")
    assert controller.get("flags.enabled") is True

    controller.append("items.list", "c")
    controller.append("items.list", "c")
    assert controller.get("items.list") == ["a", "b", "c"]

    controller.remove("items.list", "b")
    assert controller.get("items.list") == ["a", "c"]

    controller.toggle("items.list", "a")
    assert controller.get("items.list") == ["c"]


def test_settings_controller_set_validates_types(tmp_path):
    defaults = {"previews": {"enabled": True, "refresh_seconds": 1.0}}
    _write_json(tmp_path / "default_settings.json", defaults)

    controller = SettingsController(base_dir=tmp_path)

    controller.set("previews.enabled", False)
    assert controller.get("previews.enabled") is False

    with pytest.raises(TypeError):
        controller.set("previews.enabled", "false")

    with pytest.raises(KeyError):
        controller.set("previews.missing", 1)


def test_settings_controller_restore_defaults_rewrites_user_settings(tmp_path):
    defaults = {"server": {"host": "http://127.0.0.1:7860", "save_imgs": False}}
    _write_json(tmp_path / "default_settings.json", defaults)

    controller = SettingsController(base_dir=tmp_path)
    controller.set("server.save_imgs", True)
    controller.save()

    controller.restore_defaults()

    assert controller.get("server.save_imgs") is False
    saved_user_settings = json.loads(
        (tmp_path / "user_settings.json").read_text(encoding="utf-8")
    )
    assert saved_user_settings == defaults
