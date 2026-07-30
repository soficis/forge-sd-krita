from __future__ import annotations

import copy
from typing import Any, Mapping

from .model_registry import ModelFamily, ModelConfig, detect_model_family, get_model_config


def build_api_payload(data: Mapping[str, Any]) -> dict[str, Any]:
    """Translate plugin generation data into Stable Diffusion API payload format.

    The function is deterministic and side-effect free.
    Specifically optimized for Forge/A1111 API baseline.
    """

    payload = copy.deepcopy(dict(data))

    override_settings = payload.get("override_settings")
    if not isinstance(override_settings, dict):
        override_settings = {}
    payload["override_settings"] = override_settings

    _move_to_override(payload, "model", "sd_model_checkpoint")
    _move_to_override(payload, "vae", "sd_vae")
    _move_to_override(payload, "color_correction", "img2img_color_correction")
    _move_to_override(payload, "forge_preset", "forge_preset")
    _move_to_override(payload, "forge_additional_modules", "forge_additional_modules")

    _rename_key(payload, "sampler", "sampler_name")
    _rename_key(payload, "sampling_steps", "steps")
    _rename_key(payload, "hr_steps", "hr_second_pass_steps")

    _rename_key(payload, "img2img_img", "init_images", wrap_as_list=True)
    _rename_key(payload, "inpaint_img", "init_images", wrap_as_list=True)
    _rename_key(payload, "mask_img", "mask")
    _rename_key(payload, "batch_count", "n_iter")

    _map_refiner_fields(payload)

    payload["override_settings_restore_afterwards"] = False

    family = _detect_family(data, override_settings)
    config = get_model_config(family)
    _apply_model_overrides(payload, data, family, config)

    return payload


def _move_to_override(
    payload: dict[str, Any], source_key: str, target_key: str
) -> None:
    if source_key not in payload:
        return
    payload["override_settings"][target_key] = payload.pop(source_key)


def _rename_key(
    payload: dict[str, Any],
    source_key: str,
    target_key: str,
    wrap_as_list: bool = False,
) -> None:
    if source_key not in payload:
        return

    value = payload.pop(source_key)
    if wrap_as_list:
        value = [value]
    payload[target_key] = value


def _map_refiner_fields(payload: dict[str, Any]) -> None:
    refiner_name = payload.pop("refiner", None)
    refiner_start = payload.pop("refiner_start", None)

    has_refiner = (
        isinstance(refiner_name, str)
        and bool(refiner_name.strip())
        and refiner_name.lower() != "none"
    )

    if has_refiner:
        payload["refiner_checkpoint"] = refiner_name
    if refiner_start is not None:
        payload["refiner_switch_at"] = refiner_start


def _detect_family(data: dict[str, Any], override_settings: dict[str, Any]) -> ModelFamily:
    """Detect model family from checkpoint name in data or override_settings."""
    checkpoint = data.get("sd_model_checkpoint") or override_settings.get("sd_model_checkpoint", "")
    if not isinstance(checkpoint, str) or not checkpoint:
        checkpoint = data.get("model", "")
    if not isinstance(checkpoint, str) or not checkpoint:
        checkpoint = override_settings.get("sd_model_checkpoint", "")
    if not isinstance(checkpoint, str) or not checkpoint:
        return ModelFamily.SD
    return detect_model_family(checkpoint)


def _apply_model_overrides(
    payload: dict[str, Any],
    data: dict[str, Any],
    family: ModelFamily,
    config: ModelConfig,
) -> None:
    """Apply model-family-specific payload adjustments."""
    # Only override forge_preset if we detected a specific model family,
    # or if the user didn't explicitly set one
    user_set_preset = "forge_preset" in payload["override_settings"]
    if not user_set_preset:
        payload["override_settings"]["forge_preset"] = config.forge_preset
    elif family != ModelFamily.SD:
        payload["override_settings"]["forge_preset"] = config.forge_preset

    existing_modules = payload["override_settings"].get("forge_additional_modules")
    if not existing_modules:
        modules = list(config.text_encoder_files)
        if config.vae_file:
            modules.append(config.vae_file)
        if modules:
            payload["override_settings"]["forge_additional_modules"] = modules

    # Only set sampler/scheduler/cfg if user hasn't explicitly provided them
    if "sampler_name" not in payload:
        payload["sampler_name"] = config.default_sampler
    if "scheduler" not in payload:
        payload["scheduler"] = config.default_scheduler
    if "cfg_scale" not in payload:
        if config.cfg_fixed is not None:
            payload["cfg_scale"] = config.cfg_fixed
        elif family == ModelFamily.FLUX:
            payload["cfg_scale"] = config.default_cfg
            payload["distilled_cfg_scale"] = payload.get("distilled_cfg_scale", 3.5)
        else:
            payload["cfg_scale"] = config.default_cfg
    elif config.cfg_fixed is not None and family != ModelFamily.SD:
        # Force cfg_fixed only for specific model types (Z-Image, Krea2 Turbo)
        payload["cfg_scale"] = config.cfg_fixed

    if config.shift is not None:
        payload["shift"] = config.shift


__all__ = [
    "build_api_payload",
]
