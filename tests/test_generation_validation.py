"""Tests-after for plan todo 12 (docs High #5 + Medium #12): client-side
prompt/batch/steps/seed validation at the UI->payload boundary.

The validator is a pure function in ``forge.domain.generation_validation``
so these tests need no Qt/Krita mocks beyond ``conftest.py``.
"""

from __future__ import annotations

import pytest

from forge.domain.generation_validation import (
    MAX_PROMPT_CHARS,
    validate_generation_data,
    validate_generation_inputs,
)
from forge.domain.payload_builder import build_api_payload


def _valid_kwargs(**overrides):
    kwargs = {
        "prompt": "a beautiful sunset over mountains",
        "negative": "blurry, low quality",
        "batch_count": 1,
        "batch_size": 1,
        "steps": 20,
        "seed": -1,
    }
    kwargs.update(overrides)
    return kwargs


# ---------------------------------------------------------------------------
# Prompt policy: block empty / whitespace-only / over-long; allow everything else
# ---------------------------------------------------------------------------


class TestPromptPolicy:
    @pytest.mark.parametrize("prompt", ["", "   ", "\t\n  \n", None])
    def test_empty_or_whitespace_prompt_is_an_error(self, prompt):
        errors = validate_generation_inputs(**_valid_kwargs(prompt=prompt))
        assert len(errors) >= 1
        assert any("prompt" in e.lower() for e in errors)

    def test_non_string_prompt_is_an_error_not_a_crash(self):
        errors = validate_generation_inputs(**_valid_kwargs(prompt=12345))
        assert len(errors) >= 1

    def test_prompt_at_length_cap_passes(self):
        errors = validate_generation_inputs(**_valid_kwargs(prompt="x" * MAX_PROMPT_CHARS))
        assert errors == []

    def test_prompt_over_length_cap_is_an_error(self):
        errors = validate_generation_inputs(**_valid_kwargs(prompt="x" * (MAX_PROMPT_CHARS + 1)))
        assert len(errors) >= 1

    @pytest.mark.parametrize(
        "prompt",
        [
            "a cat <lora:detail_turbo:1.0>",
            "<lora:hyper-sd:0.125> a beautiful landscape",
            "masterpiece <lora:lcm:0.8> <embedding:neg>",
            "[::1]",
        ],
    )
    def test_lora_and_syntax_prompts_pass(self, prompt):
        errors = validate_generation_inputs(**_valid_kwargs(prompt=prompt))
        assert errors == []

    def test_empty_negative_prompt_is_allowed(self):
        errors = validate_generation_inputs(**_valid_kwargs(negative=""))
        assert errors == []


# ---------------------------------------------------------------------------
# Medium #12 numeric validation: batch_count / batch_size / steps / seed
# ---------------------------------------------------------------------------


class TestNumericValidation:
    @pytest.mark.parametrize("field", ["batch_count", "batch_size"])
    @pytest.mark.parametrize("value", [0, -1, -16])
    def test_batch_below_one_is_an_error(self, field, value):
        errors = validate_generation_inputs(**_valid_kwargs(**{field: value}))
        assert any(field.replace("_", " ") in e.lower() for e in errors), errors

    @pytest.mark.parametrize("field", ["batch_count", "batch_size"])
    @pytest.mark.parametrize("value", [1, 2, 16])
    def test_batch_at_least_one_passes(self, field, value):
        errors = validate_generation_inputs(**_valid_kwargs(**{field: value}))
        assert errors == []

    def test_bool_batch_is_rejected(self):
        errors = validate_generation_inputs(**_valid_kwargs(batch_count=True))
        assert len(errors) >= 1

    @pytest.mark.parametrize("value", [0, -5])
    def test_steps_below_one_is_an_error(self, value):
        errors = validate_generation_inputs(**_valid_kwargs(steps=value))
        assert any("step" in e.lower() for e in errors), errors

    def test_steps_at_least_one_passes(self):
        assert validate_generation_inputs(**_valid_kwargs(steps=1)) == []

    @pytest.mark.parametrize("seed", [-1, 0, 42, 2**31 - 1, "random", "Random", "", "-1", "12345"])
    def test_parseable_seed_or_random_token_passes(self, seed):
        errors = validate_generation_inputs(**_valid_kwargs(seed=seed))
        assert errors == [], seed

    @pytest.mark.parametrize("seed", ["abc", "12.5", "!!", True, 3.5])
    def test_unparseable_seed_is_an_error(self, seed):
        errors = validate_generation_inputs(**_valid_kwargs(seed=seed))
        assert any("seed" in e.lower() for e in errors), errors


# ---------------------------------------------------------------------------
# Dict-level entry point: merged generation_data (widget payload shape)
# ---------------------------------------------------------------------------


class TestGenerationDataDict:
    def test_empty_prompt_dict_returns_errors(self):
        errors = validate_generation_data({"prompt": "   ", "batch_count": 1})
        assert len(errors) >= 1

    def test_sampling_steps_key_is_validated(self):
        errors = validate_generation_data(
            {"prompt": "a cat", "sampling_steps": 0, "batch_count": 1, "batch_size": 1}
        )
        assert any("step" in e.lower() for e in errors)

    def test_valid_dict_passes_and_builds_payload_with_raw_values(self):
        data = {
            "prompt": "a cat <lora:detail_turbo:1.0>",
            "negative_prompt": "blurry",
            "batch_count": 2,
            "batch_size": 1,
            "sampling_steps": 20,
            "seed": -1,
        }
        assert validate_generation_data(data) == []
        payload = build_api_payload(data)
        assert payload["prompt"] == "a cat <lora:detail_turbo:1.0>"
        assert payload["n_iter"] == 2
        assert payload["steps"] == 20

    def test_missing_prompt_key_is_an_error(self):
        assert len(validate_generation_data({"batch_count": 1})) >= 1
