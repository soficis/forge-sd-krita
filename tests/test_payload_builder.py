"""Unit tests for forge.domain.payload_builder — the pure-function API
payload transformation used to convert plugin data into A1111/Forge format.
"""

from __future__ import annotations

import copy

import pytest

from forge.domain.payload_builder import build_api_payload


# ---------------------------------------------------------------------------
# Basic field transformations
# ---------------------------------------------------------------------------


class TestBasicTransformations:
    """build_api_payload moves, renames, and wraps fields correctly."""

    def test_moves_model_to_override_settings(self):
        result = build_api_payload({"model": "dreamshaper"})
        assert result["override_settings"]["sd_model_checkpoint"] == "dreamshaper"
        assert "model" not in result

    def test_moves_vae_to_override_settings(self):
        result = build_api_payload({"vae": "vae-ft-mse"})
        assert result["override_settings"]["sd_vae"] == "vae-ft-mse"
        assert "vae" not in result

    def test_moves_color_correction_to_override(self):
        result = build_api_payload({"color_correction": True})
        assert result["override_settings"]["img2img_color_correction"] is True
        assert "color_correction" not in result

    def test_moves_forge_preset_to_override(self):
        result = build_api_payload({"forge_preset": "neo"})
        # forge_preset "neo" is user-set and no model is detected -> SD fallback
        # user's preset is respected when no specific model family detected
        assert result["override_settings"]["forge_preset"] == "neo"

    def test_moves_forge_preset_flux_overrides_user(self):
        """Flux models always override user-set forge_preset."""
        result = build_api_payload({"model": "flux-dev", "forge_preset": "something_else"})
        assert result["override_settings"]["forge_preset"] == "flux"

    def test_moves_forge_additional_modules_to_override(self):
        result = build_api_payload({"forge_additional_modules": ["mod1", "mod2"]})
        assert result["override_settings"]["forge_additional_modules"] == ["mod1", "mod2"]

    def test_renames_sampler(self):
        result = build_api_payload({"sampler": "Euler"})
        # sampler_name is now also set by the model registry default (SD -> Euler a)
        # but the user's sampler choice should override the default
        assert result["sampler_name"] == "Euler"
        assert "sampler" not in result

    def test_renames_sampling_steps(self):
        result = build_api_payload({"sampling_steps": 30})
        assert result["steps"] == 30
        assert "sampling_steps" not in result

    def test_renames_hr_steps(self):
        result = build_api_payload({"hr_steps": 5})
        assert result["hr_second_pass_steps"] == 5
        assert "hr_steps" not in result

    def test_wraps_img2img_img_as_list(self):
        result = build_api_payload({"img2img_img": "BASE64DATA"})
        assert result["init_images"] == ["BASE64DATA"]
        assert "img2img_img" not in result

    def test_wraps_inpaint_img_as_list(self):
        result = build_api_payload({"inpaint_img": "INPAINT_B64"})
        assert result["init_images"] == ["INPAINT_B64"]
        assert "inpaint_img" not in result

    def test_renames_mask_img(self):
        result = build_api_payload({"mask_img": "MASKDATA"})
        assert result["mask"] == "MASKDATA"
        assert "mask_img" not in result

    def test_renames_batch_count(self):
        result = build_api_payload({"batch_count": 2})
        assert result["n_iter"] == 2
        assert "batch_count" not in result

    def test_sets_override_settings_restore_afterwards_false(self):
        result = build_api_payload({})
        assert result["override_settings_restore_afterwards"] is False


# ---------------------------------------------------------------------------
# Complete payload transformation
# ---------------------------------------------------------------------------


class TestFullPayload:
    """A realistic payload with all common fields."""

    def test_full_txt2img_payload(self):
        data = {
            "prompt": "a cat",
            "negative_prompt": "ugly",
            "model": "sdxl",
            "vae": "vaeA",
            "sampler": "DPM++ 2M",
            "sampling_steps": 25,
            "cfg_scale": 7,
            "width": 512,
            "height": 512,
            "seed": 42,
            "batch_count": 1,
            "refiner": "refinerA",
            "refiner_start": 0.8,
        }

        result = build_api_payload(data)

        assert result["prompt"] == "a cat"
        assert result["negative_prompt"] == "ugly"
        assert result["override_settings"]["sd_model_checkpoint"] == "sdxl"
        assert result["override_settings"]["sd_vae"] == "vaeA"
        # SDXL model detected -> default sampler is "Euler a" (from config)
        # but user's sampler "DPM++ 2M" should override
        assert result["sampler_name"] == "DPM++ 2M"
        assert result["steps"] == 25
        # User explicitly set cfg_scale=7 in data, model default is overridden
        assert result["cfg_scale"] == 7
        assert result["width"] == 512
        assert result["height"] == 512
        assert result["seed"] == 42
        assert result["n_iter"] == 1
        assert result["refiner_checkpoint"] == "refinerA"
        assert result["refiner_switch_at"] == 0.8
        assert result["override_settings"]["forge_preset"] == "xl"

    def test_does_not_mutate_input(self):
        data = {"model": "test", "sampler": "Euler"}
        original = copy.deepcopy(data)
        build_api_payload(data)
        assert data == original


# ---------------------------------------------------------------------------
# override_settings handling
# ---------------------------------------------------------------------------


class TestOverrideSettings:
    """override_settings dict is created/populated correctly."""

    def test_creates_override_settings_if_missing(self):
        result = build_api_payload({"model": "x"})
        assert isinstance(result["override_settings"], dict)

    def test_preserves_existing_override_settings(self):
        result = build_api_payload({
            "model": "x",
            "override_settings": {"clip_skip": 2},
        })
        assert result["override_settings"]["clip_skip"] == 2
        assert result["override_settings"]["sd_model_checkpoint"] == "x"

    def test_replaces_non_dict_override_settings(self):
        result = build_api_payload({
            "model": "x",
            "override_settings": "invalid",
        })
        assert isinstance(result["override_settings"], dict)
        assert result["override_settings"]["sd_model_checkpoint"] == "x"

    def test_empty_override_settings_when_no_fields_need_it(self):
        result = build_api_payload({"prompt": "hello"})
        # model_registry now sets forge_preset for SD (default) even when no model field present
        assert result["override_settings"].get("forge_preset") == "sd"


# ---------------------------------------------------------------------------
# Refiner field mapping
# ---------------------------------------------------------------------------


class TestRefinerMapping:
    """Refiner fields are mapped to API format."""

    def test_refiner_name_and_start(self):
        result = build_api_payload({
            "refiner": "modelA.safetensors",
            "refiner_start": 0.5,
        })
        assert result["refiner_checkpoint"] == "modelA.safetensors"
        assert result["refiner_switch_at"] == 0.5
        assert "refiner" not in result
        assert "refiner_start" not in result

    def test_refiner_name_none_string(self):
        """A refiner set to 'none' should not produce a checkpoint."""
        result = build_api_payload({"refiner": "none"})
        assert "refiner_checkpoint" not in result
        assert "refiner" not in result

    def test_refiner_name_empty_string(self):
        result = build_api_payload({"refiner": ""})
        assert "refiner_checkpoint" not in result

    def test_refiner_name_whitespace_only(self):
        result = build_api_payload({"refiner": "   "})
        assert "refiner_checkpoint" not in result

    def test_refiner_start_without_name(self):
        result = build_api_payload({"refiner_start": 0.7})
        assert result.get("refiner_switch_at") == 0.7

    def test_no_refiner_fields(self):
        result = build_api_payload({"prompt": "test"})
        assert "refiner_checkpoint" not in result
        assert "refiner_switch_at" not in result


# ---------------------------------------------------------------------------
# Flux model detection and overrides
# ---------------------------------------------------------------------------


class TestFluxModel:
    """Flux models get special override treatment."""

    def test_flux_model_lowercase(self):
        result = build_api_payload({"model": "flux-dev-fp16"})
        assert result["override_settings"]["forge_preset"] == "flux"
        assert result["cfg_scale"] == 1
        assert result["scheduler"] == "Simple"

    def test_flux_model_mixed_case(self):
        result = build_api_payload({"model": "FLUX-Dev"})
        assert result["override_settings"]["forge_preset"] == "flux"
        assert result["cfg_scale"] == 1

    def test_flux_model_with_existing_forge_preset(self):
        """If user already set a forge_preset, flux overrides it."""
        result = build_api_payload({
            "model": "flux-schnell",
            "forge_preset": "something_else",
        })
        assert result["override_settings"]["forge_preset"] == "flux"

    def test_flux_model_with_additional_modules(self):
        result = build_api_payload({
            "model": "flux-dev",
            "forge_additional_modules": ["module1"],
        })
        assert result["override_settings"]["forge_additional_modules"] == ["module1"]

    def test_flux_model_without_additional_modules(self):
        result = build_api_payload({"model": "flux-dev"})
        # model_registry auto-populates forge_additional_modules for known model families
        assert "forge_additional_modules" in result.get("override_settings", {})
        assert "ae.safetensors" in result["override_settings"]["forge_additional_modules"]

    def test_non_flux_model_no_flux_overrides(self):
        result = build_api_payload({"model": "dreamshaper"})
        # dreamshaper -> SD family -> cfg_scale from config (7.0), scheduler from config (Automatic)
        assert result.get("cfg_scale") == 7.0
        assert result.get("scheduler") == "Automatic"

    def test_flux_model_non_string_checkpoint(self):
        """Non-string checkpoint should fall back to SD defaults."""
        result = build_api_payload({"model": 123})
        # model gets moved to override_settings as-is
        assert result["override_settings"]["sd_model_checkpoint"] == 123
        # Non-string checkpoint falls back to SD family defaults
        assert result.get("cfg_scale") == 7.0


# ---------------------------------------------------------------------------
# Missing / empty fields
# ---------------------------------------------------------------------------


class TestMissingFields:
    """Missing fields should be silently ignored."""

    def test_empty_data(self):
        result = build_api_payload({})
        # model_registry now sets forge_preset for SD (default)
        assert result["override_settings"]["forge_preset"] == "sd"
        assert result["override_settings_restore_afterwards"] is False

    def test_only_prompt(self):
        result = build_api_payload({"prompt": "a castle"})
        assert result["prompt"] == "a castle"
        # model_registry now sets forge_preset for SD (default)
        assert result["override_settings"]["forge_preset"] == "sd"

    def test_extra_keys_pass_through(self):
        result = build_api_payload({"prompt": "x", "custom_key": "value"})
        assert result["custom_key"] == "value"
