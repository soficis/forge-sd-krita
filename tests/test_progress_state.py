"""Unit tests for forge.domain.progress_state — parsing generation progress
responses from the SD API into a typed ProgressState.
"""

from __future__ import annotations

import pytest

from forge.domain.progress_state import ProgressState, parse_progress_state


# ---------------------------------------------------------------------------
# Active job states
# ---------------------------------------------------------------------------


class TestActiveJob:
    """Progress for an actively generating job."""

    def test_active_job_with_progress(self):
        state = parse_progress_state({
            "progress": 0.42,
            "state": {"skipped": False, "interrupted": False},
            "current_image": "BASE64",
        })
        assert state.is_active is True
        assert state.is_interrupted is False
        assert state.percent == 42
        assert state.current_image == "BASE64"

    def test_progress_at_zero(self):
        state = parse_progress_state({
            "progress": 0.0,
            "state": {},
            "current_image": None,
        })
        assert state.is_active is True
        assert state.percent == 0

    def test_progress_at_one_hundred(self):
        state = parse_progress_state({
            "progress": 1.0,
            "state": {},
            "current_image": "DONE",
        })
        assert state.is_active is True
        assert state.percent == 100

    def test_progress_half(self):
        state = parse_progress_state({"progress": 0.5})
        assert state.percent == 50


# ---------------------------------------------------------------------------
# Interrupted / skipped states
# ---------------------------------------------------------------------------


class TestInterruptedJob:
    """Progress for an interrupted or skipped job."""

    def test_interrupted(self):
        state = parse_progress_state({
            "progress": 0.75,
            "state": {"interrupted": True},
            "current_image": "BASE64",
        })
        assert state.is_active is False
        assert state.is_interrupted is True

    def test_skipped(self):
        state = parse_progress_state({
            "progress": 0.3,
            "state": {"skipped": True},
        })
        assert state.is_active is False
        assert state.is_interrupted is True

    def test_both_skipped_and_interrupted(self):
        state = parse_progress_state({
            "progress": 0.5,
            "state": {"skipped": True, "interrupted": True},
        })
        assert state.is_active is False
        assert state.is_interrupted is True


# ---------------------------------------------------------------------------
# Null / missing payloads
# ---------------------------------------------------------------------------


class TestNullPayload:
    """Null or empty payloads should return a default inactive state."""

    def test_none_input(self):
        state = parse_progress_state(None)
        assert state.is_active is False
        assert state.is_interrupted is False
        assert state.percent == 0
        assert state.current_image is None

    def test_non_mapping_input(self):
        state = parse_progress_state("not a dict")
        assert state.is_active is False
        assert state.percent == 0

    def test_empty_dict(self):
        state = parse_progress_state({})
        assert state.is_active is True
        assert state.percent == 0

    def test_integer_input(self):
        state = parse_progress_state(42)
        assert state.is_active is False


# ---------------------------------------------------------------------------
# Edge cases for progress values
# ---------------------------------------------------------------------------


class TestProgressEdgeCases:
    """Various progress value edge cases."""

    def test_progress_above_one_clamped(self):
        state = parse_progress_state({"progress": 1.5})
        assert state.percent == 100

    def test_progress_below_zero_clamped(self):
        state = parse_progress_state({"progress": -0.5})
        assert state.percent == 0

    def test_progress_string_ignored(self):
        state = parse_progress_state({"progress": "almost done"})
        assert state.percent == 0

    def test_progress_integer_value(self):
        state = parse_progress_state({"progress": 0})
        assert state.percent == 0

    def test_progress_integer_value_one(self):
        state = parse_progress_state({"progress": 1})
        assert state.percent == 100


# ---------------------------------------------------------------------------
# current_image handling
# ---------------------------------------------------------------------------


class TestCurrentImage:
    """current_image is parsed correctly."""

    def test_valid_base64_string(self):
        state = parse_progress_state({"current_image": "iVBORw0KGgo..."})
        assert state.current_image == "iVBORw0KGgo..."

    def test_empty_string_treated_as_none(self):
        state = parse_progress_state({"current_image": ""})
        assert state.current_image is None

    def test_non_string_treated_as_none(self):
        state = parse_progress_state({"current_image": 123})
        assert state.current_image is None

    def test_none_current_image(self):
        state = parse_progress_state({"current_image": None})
        assert state.current_image is None

    def test_missing_current_image(self):
        state = parse_progress_state({"progress": 0.5})
        assert state.current_image is None


# ---------------------------------------------------------------------------
# State dict handling
# ---------------------------------------------------------------------------


class TestStateDict:
    """The nested 'state' dict is parsed correctly."""

    def test_missing_state_dict(self):
        state = parse_progress_state({"progress": 0.5})
        assert state.is_active is True
        assert state.is_interrupted is False

    def test_empty_state_dict(self):
        state = parse_progress_state({"progress": 0.5, "state": {}})
        assert state.is_active is True

    def test_non_dict_state_value(self):
        state = parse_progress_state({"progress": 0.5, "state": "running"})
        assert state.is_active is True


# ---------------------------------------------------------------------------
# ProgressState dataclass
# ---------------------------------------------------------------------------


class TestProgressStateDataclass:
    """ProgressState is a frozen dataclass."""

    def test_frozen(self):
        state = ProgressState(
            is_active=True, is_interrupted=False,
            percent=50, current_image="x",
        )
        with pytest.raises(AttributeError):
            state.percent = 75

    def test_equality(self):
        a = ProgressState(True, False, 50, "img")
        b = ProgressState(True, False, 50, "img")
        assert a == b
