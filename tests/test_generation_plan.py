from forge.domain.generation_plan import (
    build_generation_plan,
    merge_generation_data,
    prune_generation_results,
)


def test_build_generation_plan_applies_min_size_and_preserves_output_size():
    plan = build_generation_plan(
        width=256,
        height=512,
        min_size=512,
        max_size=2048,
        enable_max_size=False,
    )

    assert plan.request_width == 512
    assert plan.request_height == 1024
    assert plan.output_width == 256
    assert plan.output_height == 512
    assert plan.resize is not None
    assert plan.resize.width == 256
    assert plan.resize.height == 512


def test_build_generation_plan_applies_max_size_when_enabled():
    plan = build_generation_plan(
        width=4096,
        height=2048,
        min_size=512,
        max_size=1024,
        enable_max_size=True,
    )

    assert plan.request_width == 1024
    assert plan.request_height == 512
    assert plan.resize is not None


def test_merge_generation_data_merges_nested_dicts_and_extracts_processing_keys():
    merged, processing = merge_generation_data(
        base_data={"width": 512, "alwayson_scripts": {"foo": 1}},
        widget_payloads=[
            {"alwayson_scripts": {"bar": 2}},
            {"prompt": "hello"},
            {"FORGE": {"results_below_layer_uuid": "abc"}},
        ],
    )

    assert merged["alwayson_scripts"] == {"foo": 1, "bar": 2}
    assert merged["prompt"] == "hello"
    assert "FORGE" not in merged
    assert processing == {"results_below_layer_uuid": "abc"}


def test_prune_generation_results_trims_grid_and_controlnet_images():
    results = {
        "images": ["grid", "img1", "img2", "extra"],
        "parameters": {"batch_size": 1, "n_iter": 2, "save_images": True},
    }

    pruned = prune_generation_results(results)
    assert pruned["images"] == ["img1", "img2"]
