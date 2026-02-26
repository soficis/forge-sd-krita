from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ProgressState:
    is_active: bool
    is_interrupted: bool
    percent: int
    current_image: str | None


def parse_progress_state(response: Mapping[str, Any] | None) -> ProgressState:
    if not isinstance(response, Mapping):
        return ProgressState(
            is_active=False,
            is_interrupted=False,
            percent=0,
            current_image=None,
        )

    state = response.get("state")
    is_interrupted = False
    if isinstance(state, Mapping):
        is_interrupted = bool(state.get("skipped") or state.get("interrupted"))

    progress_value = response.get("progress")
    if isinstance(progress_value, (float, int)):
        bounded = max(0.0, min(float(progress_value), 1.0))
        percent = int(bounded * 100)
    else:
        percent = 0

    current_image = response.get("current_image")
    if not isinstance(current_image, str) or not current_image:
        current_image = None

    return ProgressState(
        is_active=not is_interrupted,
        is_interrupted=is_interrupted,
        percent=percent,
        current_image=current_image,
    )


__all__ = ["ProgressState", "parse_progress_state"]
