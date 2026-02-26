from __future__ import annotations

import copy
from typing import Any, Mapping


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

    _rename_key(payload, "sampler", "sampler_name")
    _rename_key(payload, "sampling_steps", "steps")
    _rename_key(payload, "hr_steps", "hr_second_pass_steps")

    _rename_key(payload, "img2img_img", "init_images", wrap_as_list=True)
    _rename_key(payload, "inpaint_img", "init_images", wrap_as_list=True)
    _rename_key(payload, "mask_img", "mask")
    _rename_key(payload, "batch_count", "n_iter")

    _map_refiner_fields(payload)

    payload["override_settings_restore_afterwards"] = False
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


__all__ = [
    "build_api_payload",
]
