"""Task 18 (triage-approved widget/page TODOs): extensions fallback message,
interrogate caption replace/append/prepend, simplify mask hide checkboxes,
interrogate-model clip-failure hint + deepdanbooru info.

Failing-first: the pure helpers asserted here (visible_extensions,
apply_caption_mode, deepdanbooru_available, CLIP_DOWNLOAD_HINT) do not exist
pre-fix, and threadable_return unconditionally OVERWRITES the prompt.
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
# interrogate.py:55 — replace / append / prepend caption mode
# ---------------------------------------------------------------------------


class TestApplyCaptionMode:
    def test_replace(self):
        from forge.widgets.interrogate import apply_caption_mode

        assert apply_caption_mode("old prompt", "new caption", "replace") == "new caption"

    def test_append(self):
        from forge.widgets.interrogate import apply_caption_mode

        assert apply_caption_mode("old prompt", "new caption", "append") == "old prompt, new caption"

    def test_append_empty_existing(self):
        from forge.widgets.interrogate import apply_caption_mode

        assert apply_caption_mode("", "new caption", "append") == "new caption"

    def test_prepend(self):
        from forge.widgets.interrogate import apply_caption_mode

        assert apply_caption_mode("old prompt", "new caption", "prepend") == "new caption, old prompt"

    def test_prepend_empty_existing(self):
        from forge.widgets.interrogate import apply_caption_mode

        assert apply_caption_mode("", "new caption", "prepend") == "new caption"

    def test_unknown_mode_falls_back_to_replace(self):
        from forge.widgets.interrogate import apply_caption_mode

        assert apply_caption_mode("old prompt", "new caption", "bogus") == "new caption"


class TestCaptionModeThreadableReturn:
    def _make_widget(self, tmp_path, caption_mode):
        from forge.widgets.interrogate import InterrogateWidget

        settings = _write_settings(
            tmp_path,
            {
                "interrogate": {
                    "model": "clip",
                    "prompt_mode": "img2img",
                    "caption_mode": caption_mode,
                },
                "hide_ui": {"hidden_extensions": []},
            },
        )
        model_widget = MagicMock()
        model_widget.get_prompt_mode.return_value = "img2img"
        prompt_widget = MagicMock()
        prompt_widget.prompt_text_edit.toPlainText.return_value = "old prompt"
        widget = InterrogateWidget(
            settings, MagicMock(), model_widget, prompt_widget, MagicMock()
        )
        return widget, prompt_widget

    def test_append_preserves_user_prompt(self, tmp_path):
        widget, prompt_widget = self._make_widget(tmp_path, "append")
        widget.results = {"caption": "new caption"}
        widget.threadable_return()
        prompt_widget.prompt_text_edit.setPlainText.assert_called_once_with(
            "old prompt, new caption"
        )

    def test_replace_overwrites(self, tmp_path):
        widget, prompt_widget = self._make_widget(tmp_path, "replace")
        widget.results = {"caption": "new caption"}
        widget.threadable_return()
        prompt_widget.prompt_text_edit.setPlainText.assert_called_once_with(
            "new caption"
        )

    def test_prepend_puts_caption_first(self, tmp_path):
        widget, prompt_widget = self._make_widget(tmp_path, "prepend")
        widget.results = {"caption": "new caption"}
        widget.threadable_return()
        prompt_widget.prompt_text_edit.setPlainText.assert_called_once_with(
            "new caption, old prompt"
        )


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


# ---------------------------------------------------------------------------
# interrogate_model.py:33 + :37 — clip-failure hint + deepdanbooru info
# ---------------------------------------------------------------------------


class TestInterrogateModelInfo:
    def test_deepdanbooru_unavailable(self):
        from forge.widgets.interrogate_model import deepdanbooru_available

        api = MagicMock()
        api.default_settings = {}
        assert deepdanbooru_available(api) is False

    def test_deepdanbooru_available(self):
        from forge.widgets.interrogate_model import deepdanbooru_available

        api = MagicMock()
        api.default_settings = {"deepbooru_sort_alpha": {"key": "value"}}
        assert deepdanbooru_available(api) is True

    def test_clip_hint_present(self):
        from forge.widgets.interrogate_model import CLIP_DOWNLOAD_HINT

        assert "clip" in CLIP_DOWNLOAD_HINT.lower()
        assert len(CLIP_DOWNLOAD_HINT) > 20

    def test_widget_surfaces_deepdanbooru_info(self, tmp_path):
        from forge.widgets.interrogate_model import InterrogateModelWidget

        api = MagicMock()
        api.default_settings = {}
        settings = _write_settings(
            tmp_path,
            {
                "interrogate": {"model": "clip", "prompt_mode": "img2img"},
                "hide_ui": {"interrogate_model": False},
            },
        )
        widget = InterrogateModelWidget(
            settings, api, {"x": 0, "y": 0, "w": 0, "h": 0}
        )
        assert widget.deepdanbooru_available is False
        assert "deepdanbooru" in widget.model_status_text.lower()

    def test_widget_surfaces_clip_hint(self, tmp_path):
        from forge.widgets.interrogate_model import (
            CLIP_DOWNLOAD_HINT,
            InterrogateModelWidget,
        )

        api = MagicMock()
        api.default_settings = {}
        settings = _write_settings(
            tmp_path,
            {
                "interrogate": {"model": "clip", "prompt_mode": "img2img"},
                "hide_ui": {"interrogate_model": False},
            },
        )
        widget = InterrogateModelWidget(
            settings, api, {"x": 0, "y": 0, "w": 0, "h": 0}
        )
        assert widget.clip_hint_text == CLIP_DOWNLOAD_HINT
