from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

FORGE_PROCESSING_KEY = "FORGE"


@dataclass(frozen=True)
class ResizeInstruction:
    width: int
    height: int


@dataclass(frozen=True)
class GenerationPlan:
    request_width: int
    request_height: int
    output_width: int
    output_height: int
    resize: ResizeInstruction | None


def build_generation_plan(
    width: int,
    height: int,
    *,
    min_size: int,
    max_size: int,
    enable_max_size: bool,
) -> GenerationPlan:
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be greater than zero")

    output_width = width
    output_height = height
    request_width = width
    request_height = height
    resize: ResizeInstruction | None = None

    if request_width < min_size or request_height < min_size:
        resize = ResizeInstruction(width=output_width, height=output_height)
        request_width, request_height = scale_to_target_min(
            width=request_width,
            height=request_height,
            min_size=min_size,
        )

    if enable_max_size and (request_width > max_size or request_height > max_size):
        resize = ResizeInstruction(width=output_width, height=output_height)
        request_width, request_height = scale_to_target_max(
            width=request_width,
            height=request_height,
            max_size=max_size,
        )

    return GenerationPlan(
        request_width=request_width,
        request_height=request_height,
        output_width=output_width,
        output_height=output_height,
        resize=resize,
    )


def scale_to_target_min(*, width: int, height: int, min_size: int) -> tuple[int, int]:
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be greater than zero")

    if width < height:
        ratio = height / width
        return min_size, max(int(ratio * min_size), 1)

    ratio = width / height
    return max(int(ratio * min_size), 1), min_size


def scale_to_target_max(*, width: int, height: int, max_size: int) -> tuple[int, int]:
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be greater than zero")

    if width < height:
        ratio = width / height
        return max(int(ratio * max_size), 1), max_size

    ratio = height / width
    return max_size, max(int(ratio * max_size), 1)


def merge_generation_data(
    *,
    base_data: Mapping[str, Any],
    widget_payloads: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    merged = dict(base_data)
    processing_instructions: dict[str, Any] = {}

    for widget_payload in widget_payloads:
        for key, value in widget_payload.items():
            if key == FORGE_PROCESSING_KEY:
                if not isinstance(value, dict):
                    raise TypeError(f"{FORGE_PROCESSING_KEY} value must be a dict")
                processing_instructions.update(value)
                continue

            if (
                key in merged
                and isinstance(merged[key], dict)
                and isinstance(value, dict)
            ):
                merged[key] = {**merged[key], **value}
            else:
                merged[key] = value

    return merged, processing_instructions


def prune_generation_results(
    results: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    if not isinstance(results, dict):
        return results

    images = results.get("images")
    parameters = results.get("parameters")
    if not isinstance(images, list) or not isinstance(parameters, dict):
        return results

    batch_size = parameters.get("batch_size")
    batch_count = parameters.get("n_iter")
    if not isinstance(batch_size, int) or not isinstance(batch_count, int):
        return results

    expected_images = batch_size * batch_count
    if expected_images <= 0 or len(images) <= expected_images:
        return results

    pruned = dict(results)
    pruned_images = list(images)

    if parameters.get("save_images") and pruned_images:
        pruned_images = pruned_images[1:]

    if len(pruned_images) > expected_images:
        pruned_images = pruned_images[:expected_images]

    pruned["images"] = pruned_images
    return pruned


__all__ = [
    "FORGE_PROCESSING_KEY",
    "GenerationPlan",
    "ResizeInstruction",
    "build_generation_plan",
    "merge_generation_data",
    "prune_generation_results",
    "scale_to_target_max",
    "scale_to_target_min",
]
