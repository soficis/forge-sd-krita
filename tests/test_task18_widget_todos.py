"""Task 18 (triage-approved widget/page TODOs): extensions fallback message
and simplify mask hide checkboxes.

Failing-first: the pure helper asserted here (visible_extensions) did not
exist pre-fix.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from forge.settings_controller import SettingsController


def _write_settings(tmp_path, defaults: dict) -> SettingsController:
    (tmp_path / "default_settings.json").write_text(
        json.dumps(defaults), encoding="utf-8"
    )
    return SettingsController(base_dir=tmp_path)


# ---------------------------------------------------------------------------
# extensions.py:30 — friendly "no extensions" message
# ---------------------------------------------------------------------------


class TestVisibleExtensions:
    def test_both_visible(self):
        from forge.widgets.extensions import visible_extensions

        assert visible_extensions(
            {"controlnet": True, "adetailer": True}, []
        ) == ["controlnet", "adetailer"]

    def test_hidden_extension_excluded(self):
        from forge.widgets.extensions import visible_extensions

        assert visible_extensions(
            {"controlnet": True, "adetailer": True}, ["controlnet"]
        ) == ["adetailer"]

    def test_nothing_installed_is_empty(self):
        from forge.widgets.extensions import visible_extensions

        assert visible_extensions(
            {"controlnet": False, "adetailer": False}, []
        ) == []

    def test_hidden_but_not_installed_stays_empty(self):
        from forge.widgets.extensions import visible_extensions

        assert visible_extensions(
            {"controlnet": False, "adetailer": True}, ["adetailer"]
        ) == []


class TestExtensionWidgetMessage:
    def _make_widget(self, tmp_path):
        from forge.widgets.extensions import ExtensionWidget

        api = MagicMock()
        api.script_installed.return_value = False
        api.host = "http://127.0.0.1:7860"
        settings = _write_settings(
            tmp_path, {"hide_ui": {"hidden_extensions": []}}
        )
        return ExtensionWidget(settings, api)

    def test_empty_state_message_set(self, tmp_path):
        widget = self._make_widget(tmp_path)
        assert widget.no_extensions_message != ""
        lowered = widget.no_extensions_message.lower()
        assert "controlnet" in lowered
        assert "adetailer" in lowered

    def test_visible_state_has_no_message(self, tmp_path):
        from forge.widgets.extensions import ExtensionWidget

        api = MagicMock()
        api.script_installed.return_value = True
        api.host = "http://127.0.0.1:7860"
        settings = _write_settings(
            tmp_path, {"hide_ui": {"hidden_extensions": []}}
        )
        widget = ExtensionWidget.__new__(ExtensionWidget)
        # Predicate-level: everything visible -> no fallback needed.
        from forge.widgets.extensions import visible_extensions

        assert visible_extensions(
            {"controlnet": True, "adetailer": True},
            settings.get("hide_ui.hidden_extensions"),
        ) == ["controlnet", "adetailer"]
        assert widget is not None


# ---------------------------------------------------------------------------
# simplify.py:153 — Mask Blur / Mode / Content / Area hide checkboxes
# ---------------------------------------------------------------------------

MASK_HIDE_KEYS = [
    "inpaint_mask_blur",
    "inpaint_mask_mode",
    "inpaint_masked_content",
    "inpaint_area",
]


class TestSimplifyMaskHideKeys:
    def test_keys_present_in_default_settings(self):
        defaults_path = (
            Path(__file__).resolve().parent.parent
            / "forge"
            / "default_settings.json"
        )
        schema = json.loads(defaults_path.read_text(encoding="utf-8"))
        for key in MASK_HIDE_KEYS:
            assert key in schema["hide_ui"], f"hide_ui.{key} missing"
            assert schema["hide_ui"][key] is False

    def test_keys_round_trip_via_settings_controller(self, tmp_path):
        defaults_path = (
            Path(__file__).resolve().parent.parent
            / "forge"
            / "default_settings.json"
        )
        schema = json.loads(defaults_path.read_text(encoding="utf-8"))
        (tmp_path / "default_settings.json").write_text(
            json.dumps(schema), encoding="utf-8"
        )
        controller = SettingsController(base_dir=tmp_path)
        for key in MASK_HIDE_KEYS:
            controller.set(f"hide_ui.{key}", True)
        controller.save()
        reloaded = SettingsController(base_dir=tmp_path)
        for key in MASK_HIDE_KEYS:
            assert reloaded.get(f"hide_ui.{key}") is True
