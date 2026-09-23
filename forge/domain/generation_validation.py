"""Client-side generation input validation (docs High #5 + Medium #12).

Pure functions with no Qt/Krita dependencies so they are unit-testable.
Called at the UI->payload boundary (``GenerateWidget.generate``) to block
a generate with an inline message instead of sending a doomed request.

Policy (defensible defaults, no server semantics invented):
- empty or whitespace-only prompt: BLOCK (server would fail opaquely).
- prompt length cap: generous 10k chars, not a guess at model limits.
- prompt *content* is never judged: LoRA tags (``<lora:...>``),
  embeddings, and other syntax always pass.
- numerics: ``batch_count``/``batch_size``/``steps`` must be int >= 1;
  ``seed`` must be an int or a random-token (``""``/``"random"``/``"-1"``).
"""

from __future__ import annotations

from typing import Any, Mapping

MAX_PROMPT_CHARS = 10_000
MAX_NEGATIVE_PROMPT_CHARS = 10_000

RANDOM_SEED_TOKENS = frozenset({"", "random", "auto", "none", "-1"})


def validate_generation_inputs(
    prompt: Any,
    negative: Any = None,
    batch_count: Any = 1,
    batch_size: Any = 1,
    steps: Any = 20,
    seed: Any = -1,
) -> list:
    """Validate generation inputs; return a list of error strings (empty = valid)."""
    errors: list = []

    errors.extend(_validate_prompt(prompt))
    errors.extend(_validate_negative(negative))
    errors.extend(_validate_int_at_least_one("batch count", batch_count))
    errors.extend(_validate_int_at_least_one("batch size", batch_size))
    errors.extend(_validate_int_at_least_one("sampling steps", steps))
    errors.extend(_validate_seed(seed))

    return errors


def validate_generation_data(data: Mapping[str, Any]) -> list:
    """Validate a merged generation_data dict (widget payload shape).

    Accepts both ``steps`` and ``sampling_steps`` keys (models widget
    emits ``sampling_steps``; payload_builder renames it to ``steps``).
    """
    if not isinstance(data, Mapping):
        return ["Generation data must be a mapping."]
    steps = data.get("steps", data.get("sampling_steps", 20))
    return validate_generation_inputs(
        prompt=data.get("prompt"),
        negative=data.get("negative_prompt"),
        batch_count=data.get("batch_count", 1),
        batch_size=data.get("batch_size", 1),
        steps=steps,
        seed=data.get("seed", -1),
    )


def _validate_prompt(prompt: Any) -> list:
    if prompt is None:
        return ["Prompt is empty - enter a prompt before generating."]
    if not isinstance(prompt, str):
        return ["Prompt must be text - enter a prompt before generating."]
    if not prompt.strip():
        return ["Prompt is empty - enter a prompt before generating."]
    if len(prompt) > MAX_PROMPT_CHARS:
        return [
            "Prompt is too long (%d chars; limit %d)."
            % (len(prompt), MAX_PROMPT_CHARS)
        ]
    return []


def _validate_negative(negative: Any) -> list:
    if negative is None:
        return []
    if not isinstance(negative, str):
        return ["Negative prompt must be text."]
    if len(negative) > MAX_NEGATIVE_PROMPT_CHARS:
        return [
            "Negative prompt is too long (%d chars; limit %d)."
            % (len(negative), MAX_NEGATIVE_PROMPT_CHARS)
        ]
    return []


def _validate_int_at_least_one(label: str, value: Any) -> list:
    if isinstance(value, bool):
        return ["%s must be an integer >= 1 (got %r)." % (_cap(label), value)]
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = int(value.strip())
        except (TypeError, ValueError):
            return ["%s must be an integer >= 1 (got %r)." % (_cap(label), value)]
    else:
        return ["%s must be an integer >= 1 (got %r)." % (_cap(label), value)]
    if parsed < 1:
        return ["%s must be an integer >= 1 (got %r)." % (_cap(label), value)]
    return []


def _validate_seed(seed: Any) -> list:
    if seed is None:
        return []
    if isinstance(seed, bool):
        return ["Seed must be an integer or 'random' (got %r)." % (seed,)]
    if isinstance(seed, int):
        return []
    if isinstance(seed, str):
        text = seed.strip()
        if text.lower() in RANDOM_SEED_TOKENS:
            return []
        try:
            int(text)
        except (TypeError, ValueError):
            return ["Seed must be an integer or 'random' (got %r)." % (seed,)]
        return []
    return ["Seed must be an integer or 'random' (got %r)." % (seed,)]


def _cap(label: str) -> str:
    return label[:1].upper() + label[1:]


__all__ = [
    "MAX_NEGATIVE_PROMPT_CHARS",
    "MAX_PROMPT_CHARS",
    "RANDOM_SEED_TOKENS",
    "validate_generation_data",
    "validate_generation_inputs",
]
