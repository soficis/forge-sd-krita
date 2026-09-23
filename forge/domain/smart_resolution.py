"""Smart Resolution suggestion helper (artist tools, Phase 2).

Suggests a width/height pair for a model family that honors an
aspect-ratio lock and the current megapixel budget without exceeding the
family's maximum generation size.

The suggestion is purely local math over :mod:`forge.domain.model_registry`
bounds (``min_size`` / ``default_max_size``) snapped down to the family
pixel-alignment step — no backend calls, no Qt, stdlib only.

Budget semantics
----------------
``current_w`` / ``current_h`` (usually the active selection or canvas size)
define the megapixel budget ``current_w * current_h``, clamped into the
family range ``[min_size**2, default_max_size**2]``. The suggested pair
keeps the locked aspect while using as much of that budget as possible;
each side always stays within ``[min_size, default_max_size]``.

Extreme aspects (e.g. 100:1) cannot preserve the ratio inside those bounds,
so the result clamps to the nearest in-bounds step multiple instead.
"""

from __future__ import annotations

import math
from typing import Union

from .model_registry import ModelFamily, get_model_config

__all__ = [
    "FAMILY_STEPS",
    "family_step",
    "suggest_resolution",
]

# Pixel-alignment step per family. SD 1.5 / Wan tolerate 8px alignment;
# the transformer families (SDXL and newer) need 16px.
FAMILY_STEPS: dict[ModelFamily, int] = {
    ModelFamily.SD: 8,
    ModelFamily.WAN: 8,
    ModelFamily.SDXL: 16,
    ModelFamily.FLUX: 16,
    ModelFamily.FLUX2: 16,
    ModelFamily.ANIMA: 16,
    ModelFamily.ZIMAGE: 16,
    ModelFamily.KREA2: 16,
    ModelFamily.QWEN_IMAGE: 16,
}

_DEFAULT_STEP = 16
_ASPECT_TOLERANCE = 0.01  # 1% relative aspect error
_NEIGHBOUR_STEPS = 2  # candidate grid extends +/- this many steps

FamilyLike = Union[ModelFamily, str]
AspectLike = Union[int, float, tuple, list]


def family_step(family: FamilyLike) -> int:
    """Return the pixel-alignment step (8 or 16) for a model family."""
    return FAMILY_STEPS.get(_resolve_family(family), _DEFAULT_STEP)


def suggest_resolution(
    family: FamilyLike,
    aspect: AspectLike,
    current_w: int,
    current_h: int,
) -> tuple[int, int]:
    """Suggest a (width, height) pair for ``family`` at locked ``aspect``.

    ``aspect`` is the width/height ratio as a positive number, or a
    ``(w, h)`` pair it is derived from. ``current_w`` / ``current_h`` set
    the megapixel budget. The result is snapped to the family step, each
    side within ``[min_size, default_max_size]``.
    """
    resolved = _resolve_family(family)
    ratio = _parse_aspect(aspect)
    _require_positive_int("current_w", current_w)
    _require_positive_int("current_h", current_h)

    config = get_model_config(resolved)
    min_size = config.min_size
    max_size = config.default_max_size
    step = FAMILY_STEPS.get(resolved, _DEFAULT_STEP)

    budget = current_w * current_h
    budget = max(min_size * min_size, min(budget, max_size * max_size))

    ideal_w, ideal_h = _fit_budget(ratio, budget, min_size, max_size)
    return _snap_to_step(ideal_w, ideal_h, ratio, budget, min_size, max_size, step)


def _resolve_family(family: FamilyLike) -> ModelFamily:
    if isinstance(family, ModelFamily):
        return family
    if isinstance(family, str):
        key = family.strip().lower()
        for member in ModelFamily:
            if key in (member.value.lower(), member.name.lower()):
                return member
    raise ValueError("unknown model family: %r" % (family,))


def _parse_aspect(aspect: AspectLike) -> float:
    if isinstance(aspect, (tuple, list)) and len(aspect) == 2:
        num, den = aspect
        if not isinstance(num, (int, float)) or not isinstance(den, (int, float)):
            raise ValueError("aspect pair must hold numbers: %r" % (aspect,))
        if isinstance(num, bool) or isinstance(den, bool):
            raise ValueError("aspect pair must hold numbers: %r" % (aspect,))
        if den == 0:
            raise ValueError("aspect pair height must be non-zero: %r" % (aspect,))
        ratio = num / den
    elif isinstance(aspect, (int, float)) and not isinstance(aspect, bool):
        ratio = float(aspect)
    else:
        raise ValueError("aspect must be a positive number or (w, h) pair")
    if not math.isfinite(ratio) or ratio <= 0:
        raise ValueError("aspect must be a positive finite number: %r" % (aspect,))
    return ratio


def _require_positive_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("%s must be a positive int: %r" % (name, value))


def _fit_budget(
    ratio: float, budget: int, min_size: int, max_size: int
) -> tuple[float, float]:
    """Aspect-locked float dims filling ``budget``, clamped to bounds."""
    height = math.sqrt(budget / ratio)
    width = ratio * height
    peak = max(width, height)
    if peak > max_size:
        scale = peak / max_size
        width /= scale
        height /= scale
    # Extreme ratios can push the small side under the floor after the
    # max clamp; pin it (ratio is unachievable in bounds anyway).
    if width < min_size:
        width = float(min_size)
    if height < min_size:
        height = float(min_size)
    return min(width, float(max_size)), min(height, float(max_size))


def _snap_to_step(
    ideal_w: float,
    ideal_h: float,
    ratio: float,
    budget: int,
    min_size: int,
    max_size: int,
    step: int,
) -> tuple[int, int]:
    """Pick the best step-aligned pair near the ideal dims.

    Prefers pairs inside the pixel budget with <1% aspect error and the
    most pixels; falls back to the smallest aspect error in bounds (covers
    extreme ratios where the locked aspect cannot fit).
    """
    candidates = sorted(
        _candidate_grid(ideal_w, ideal_h, min_size, max_size, step)
    )
    if not candidates:
        fallback = max(min_size, min(max_size, _floor_to_step(ideal_w, step)))
        other = max(min_size, min(max_size, _floor_to_step(ideal_h, step)))
        return fallback, other

    def error(pair: tuple[int, int]) -> float:
        w, h = pair
        return abs((w / h) - ratio) / ratio

    within_budget = [p for p in candidates if p[0] * p[1] <= budget]
    accurate = [p for p in within_budget if error(p) < _ASPECT_TOLERANCE]
    if accurate:
        return max(accurate, key=lambda p: (p[0] * p[1], -error(p)))
    pool = within_budget or candidates
    return min(pool, key=lambda p: (error(p), -(p[0] * p[1])))


def _candidate_grid(
    ideal_w: float, ideal_h: float, min_size: int, max_size: int, step: int
) -> set[tuple[int, int]]:
    lo_w = max(min_size, _floor_to_step(ideal_w - _NEIGHBOUR_STEPS * step, step))
    hi_w = min(max_size, _ceil_to_step(ideal_w + _NEIGHBOUR_STEPS * step, step))
    lo_h = max(min_size, _floor_to_step(ideal_h - _NEIGHBOUR_STEPS * step, step))
    hi_h = min(max_size, _ceil_to_step(ideal_h + _NEIGHBOUR_STEPS * step, step))
    widths = _multiples_between(lo_w, hi_w, step)
    heights = _multiples_between(lo_h, hi_h, step)
    if not widths:
        widths = [_snap_single(ideal_w, min_size, max_size, step)]
    if not heights:
        heights = [_snap_single(ideal_h, min_size, max_size, step)]
    return {(w, h) for w in widths for h in heights}


def _multiples_between(lo: int, hi: int, step: int) -> list[int]:
    if hi < lo:
        return []
    first = lo + (-lo % step)
    return list(range(first, hi + 1, step))


def _snap_single(value: float, min_size: int, max_size: int, step: int) -> int:
    snapped = _floor_to_step(value, step)
    return max(min_size + (-min_size % step), min(snapped, max_size - (max_size % step)))


def _floor_to_step(value: float, step: int) -> int:
    return max(step, int(math.floor(value / step)) * step)


def _ceil_to_step(value: float, step: int) -> int:
    return max(step, int(math.ceil(value / step)) * step)
