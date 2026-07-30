"""Unit tests for forge.domain.generation_plan — plan building, size
scaling, data merging, and result pruning.
"""

from __future__ import annotations

import pytest

from forge.domain.generation_plan import (
    FORGE_PROCESSING_KEY,
    GenerationPlan,
    ResizeInstruction,
    build_generation_plan,
    merge_generation_data,
    prune_generation_results,
    scale_to_target_max,
    scale_to_target_min,
)


# ---------------------------------------------------------------------------
# build_generation_plan
# ---------------------------------------------------------------------------


class TestBuildGenerationPlan:
    """Plan building with min/max size constraints."""

    def test_no_scaling_needed(self):
        plan = build_generation_plan(
            width=512, height=512,
            min_size=256, max_size=2048, enable_max_size=False,
        )
        assert plan.request_width == 512
        assert plan.request_height == 512
        assert plan.output_width == 512
        assert plan.output_height == 512
        assert plan.resize is None

    def test_min_size_scales_up(self):
        plan = build_generation_plan(
            width=256, height=512,
            min_size=512, max_size=2048, enable_max_size=False,
        )
        assert plan.request_width == 512
        assert plan.request_height == 1024
        assert plan.output_width == 256
        assert plan.output_height == 512
        assert plan.resize is not None
        assert plan.resize.width == 256
        assert plan.resize.height == 512

    def test_max_size_scales_down_when_enabled(self):
        plan = build_generation_plan(
            width=4096, height=2048,
            min_size=512, max_size=1024, enable_max_size=True,
        )
        assert plan.request_width == 1024
        assert plan.request_height == 512
        assert plan.resize is not None

    def test_max_size_ignored_when_disabled(self):
        plan = build_generation_plan(
            width=4096, height=2048,
            min_size=512, max_size=1024, enable_max_size=False,
        )
        assert plan.request_width == 4096
        assert plan.request_height == 2048

    def test_both_min_and_max_apply(self):
        """Small image needs min scaling; max is irrelevant."""
        plan = build_generation_plan(
            width=128, height=256,
            min_size=512, max_size=2048, enable_max_size=True,
        )
        # min_size applies first
        assert plan.request_width == 512
        assert plan.request_height == 1024

    def test_width_equals_height_square(self):
        plan = build_generation_plan(
            width=100, height=100,
            min_size=512, max_size=2048, enable_max_size=False,
        )
        assert plan.request_width == 512
        assert plan.request_height == 512

    def test_invalid_zero_width_raises(self):
        with pytest.raises(ValueError):
            build_generation_plan(
                width=0, height=512,
                min_size=256, max_size=2048, enable_max_size=False,
            )

    def test_invalid_negative_height_raises(self):
        with pytest.raises(ValueError):
            build_generation_plan(
                width=512, height=-1,
                min_size=256, max_size=2048, enable_max_size=False,
            )

    def test_output_always_matches_original_size(self):
        plan = build_generation_plan(
            width=300, height=600,
            min_size=512, max_size=2048, enable_max_size=False,
        )
        assert plan.output_width == 300
        assert plan.output_height == 600


# ---------------------------------------------------------------------------
# scale_to_target_min
# ---------------------------------------------------------------------------


class TestScaleToTargetMin:
    """Min-size scaling preserves aspect ratio."""

    def test_width_less_than_height(self):
        w, h = scale_to_target_min(width=256, height=512, min_size=512)
        assert w == 512
        assert h == 1024

    def test_height_less_than_width(self):
        w, h = scale_to_target_min(width=512, height=256, min_size=512)
        assert w == 1024
        assert h == 512

    def test_square_input(self):
        w, h = scale_to_target_min(width=100, height=100, min_size=512)
        assert w == 512
        assert h == 512

    def test_already_at_min(self):
        w, h = scale_to_target_min(width=512, height=1024, min_size=512)
        assert w == 512
        assert h == 1024

    def test_zero_width_raises(self):
        with pytest.raises(ValueError):
            scale_to_target_min(width=0, height=512, min_size=512)

    def test_zero_height_raises(self):
        with pytest.raises(ValueError):
            scale_to_target_min(width=512, height=0, min_size=512)


# ---------------------------------------------------------------------------
# scale_to_target_max
# ---------------------------------------------------------------------------


class TestScaleToTargetMax:
    """Max-size scaling preserves aspect ratio."""

    def test_width_greater_than_height(self):
        w, h = scale_to_target_max(width=2048, height=1024, max_size=1024)
        assert w == 1024
        assert h == 512

    def test_height_greater_than_width(self):
        w, h = scale_to_target_max(width=1024, height=2048, max_size=1024)
        assert w == 512
        assert h == 1024

    def test_square_input(self):
        w, h = scale_to_target_max(width=2048, height=2048, max_size=1024)
        assert w == 1024
        assert h == 1024

    def test_already_at_max(self):
        w, h = scale_to_target_max(width=1024, height=512, max_size=1024)
        assert w == 1024
        assert h == 512

    def test_zero_width_raises(self):
        with pytest.raises(ValueError):
            scale_to_target_max(width=0, height=512, max_size=1024)

    def test_zero_height_raises(self):
        with pytest.raises(ValueError):
            scale_to_target_max(width=512, height=0, max_size=1024)


# ---------------------------------------------------------------------------
# merge_generation_data
# ---------------------------------------------------------------------------


class TestMergeGenerationData:
    """Widget payloads are merged into base data correctly."""

    def test_flat_keys_override(self):
        merged, proc = merge_generation_data(
            base_data={"prompt": "old"},
            widget_payloads=[{"prompt": "new"}],
        )
        assert merged["prompt"] == "new"
        assert proc == {}

    def test_nested_dicts_merge(self):
        merged, _ = merge_generation_data(
            base_data={"alwayson_scripts": {"foo": 1}},
            widget_payloads=[{"alwayson_scripts": {"bar": 2}}],
        )
        assert merged["alwayson_scripts"] == {"foo": 1, "bar": 2}

    def test_forge_key_extracts_processing(self):
        merged, proc = merge_generation_data(
            base_data={},
            widget_payloads=[{"FORGE": {"layer_uuid": "abc"}}],
        )
        assert "FORGE" not in merged
        assert proc == {"layer_uuid": "abc"}

    def test_multiple_forge_keys_merge(self):
        _, proc = merge_generation_data(
            base_data={},
            widget_payloads=[
                {"FORGE": {"a": 1}},
                {"FORGE": {"b": 2}},
            ],
        )
        assert proc == {"a": 1, "b": 2}

    def test_forge_non_dict_raises(self):
        with pytest.raises(TypeError):
            merge_generation_data(
                base_data={},
                widget_payloads=[{"FORGE": "invalid"}],
            )

    def test_empty_payloads(self):
        merged, proc = merge_generation_data(
            base_data={"x": 1},
            widget_payloads=[],
        )
        assert merged == {"x": 1}
        assert proc == {}

    def test_non_dict_nested_value_overrides(self):
        """If base has a non-dict and payload has a dict, it overrides."""
        merged, _ = merge_generation_data(
            base_data={"key": "string"},
            widget_payloads=[{"key": {"nested": True}}],
        )
        assert merged["key"] == {"nested": True}


# ---------------------------------------------------------------------------
# prune_generation_results
# ---------------------------------------------------------------------------


class TestPruneGenerationResults:
    """Extra grid images are trimmed from results."""

    def test_no_pruning_needed(self):
        results = {
            "images": ["img1", "img2"],
            "parameters": {"batch_size": 1, "n_iter": 2},
        }
        assert prune_generation_results(results) is results

    def test_prunes_grid_image_with_save_images(self):
        results = {
            "images": ["grid", "img1", "img2", "extra"],
            "parameters": {"batch_size": 1, "n_iter": 2, "save_images": True},
        }
        pruned = prune_generation_results(results)
        assert pruned["images"] == ["img1", "img2"]

    def test_prunes_without_grid_if_too_many(self):
        results = {
            "images": ["img1", "img2", "img3", "img4"],
            "parameters": {"batch_size": 1, "n_iter": 2},
        }
        pruned = prune_generation_results(results)
        assert len(pruned["images"]) == 2

    def test_none_input_returns_none(self):
        assert prune_generation_results(None) is None

    def test_non_dict_input_returns_as_is(self):
        assert prune_generation_results("not a dict") == "not a dict"

    def test_missing_parameters_returns_as_is(self):
        results = {"images": ["img1"]}
        assert prune_generation_results(results) is results

    def test_missing_images_returns_as_is(self):
        results = {"parameters": {"batch_size": 1, "n_iter": 2}}
        assert prune_generation_results(results) is results

    def test_non_int_batch_size_returns_as_is(self):
        results = {
            "images": ["img1"],
            "parameters": {"batch_size": "a", "n_iter": 2},
        }
        assert prune_generation_results(results) is results

    def test_batch_size_zero_returns_as_is(self):
        results = {
            "images": ["img1"],
            "parameters": {"batch_size": 0, "n_iter": 2},
        }
        assert prune_generation_results(results) is results


# ---------------------------------------------------------------------------
# Dataclass identity
# ---------------------------------------------------------------------------


class TestPlanDataclasses:
    """GenerationPlan and ResizeInstruction are frozen dataclasses."""

    def test_plan_is_frozen(self):
        plan = GenerationPlan(
            request_width=512, request_height=512,
            output_width=512, output_height=512,
            resize=None,
        )
        with pytest.raises(AttributeError):
            plan.request_width = 1024

    def test_resize_is_frozen(self):
        r = ResizeInstruction(width=100, height=200)
        with pytest.raises(AttributeError):
            r.width = 300

    def test_forge_processing_key_constant(self):
        assert FORGE_PROCESSING_KEY == "FORGE"
