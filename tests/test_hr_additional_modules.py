"""Regression tests: build_api_payload must always send hr_additional_modules.

Backend modules/processing.py:1220 declares `hr_additional_modules: list =
field(default=None)`, and line 1404 runs on EVERY txt2img request (not gated
on enable_hr):

    if hasattr(self, "hr_additional_modules") and "Use same choices" not in self.hr_additional_modules:

Omitting the key makes the field None, so `... not in None` raises
`TypeError: argument of type 'NoneType' is not iterable` and crashes the
backend. Forge's own UI (modules/ui.py:287) always sends
`["Use same choices"]`, which skips that branch entirely.
"""

from __future__ import annotations

import json

from forge.domain.payload_builder import build_api_payload

USE_SAME_CHOICES = ["Use same choices"]


# ---------------------------------------------------------------------------
# hr_additional_modules always present as a list
# ---------------------------------------------------------------------------


class TestHrAdditionalModulesAlwaysSent:
    """Outgoing payload carries a usable hr_additional_modules list."""

    def test_minimal_hires_payload_gets_default(self):
        payload = build_api_payload({"prompt": "a cat", "enable_hr": True, "hr_steps": 5})
        assert payload["hr_additional_modules"] == USE_SAME_CHOICES

    def test_non_hires_txt2img_payload_still_gets_default(self):
        # The reported crash: plain txt2img with NO enable_hr still reaches
        # processing.py:1404, so the key must be present regardless.
        payload = build_api_payload({"prompt": "a cat", "width": 512, "height": 512})
        assert "enable_hr" not in payload
        assert payload["hr_additional_modules"] == USE_SAME_CHOICES

    def test_explicit_non_empty_list_is_preserved(self):
        payload = build_api_payload({
            "enable_hr": True,
            "hr_additional_modules": ["qwen_image_vae.safetensors"],
        })
        assert payload["hr_additional_modules"] == ["qwen_image_vae.safetensors"]

    def test_empty_list_is_upgraded_to_default(self):
        # `[]` means "Built-in" server-side (processing.py:1310-1313) but an
        # empty list from the plugin is not a deliberate choice, and it still
        # trips line 1404's modules_change()/model-reload branch — so we
        # substitute the Forge UI's safe default instead of passing it through.
        payload = build_api_payload({"enable_hr": True, "hr_additional_modules": []})
        assert payload["hr_additional_modules"] == USE_SAME_CHOICES

    def test_output_is_json_serializable(self):
        payload = build_api_payload({"prompt": "a cat"})
        json.dumps(payload)


# ---------------------------------------------------------------------------
# Regression: existing hires key mapping is undisturbed
# ---------------------------------------------------------------------------


class TestExistingHiresKeysUnchanged:
    """The new default must not disturb the established hires key mapping."""

    def test_hires_keys_still_map_correctly(self):
        payload = build_api_payload({
            "hr_steps": 7,
            "enable_hr": True,
            "hr_upscaler": "Latent",
            "hr_resize_x": 1024,
            "hr_resize_y": 768,
            "denoising_strength": 0.45,
        })

        assert payload["hr_second_pass_steps"] == 7
        assert "hr_steps" not in payload
        assert payload["enable_hr"] is True
        assert payload["hr_upscaler"] == "Latent"
        assert payload["hr_resize_x"] == 1024
        assert payload["hr_resize_y"] == 768
        assert payload["denoising_strength"] == 0.45
        assert payload["hr_additional_modules"] == USE_SAME_CHOICES
