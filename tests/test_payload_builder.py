from forge.domain.payload_builder import build_api_payload

def test_build_api_payload_moves_and_renames_fields():
    payload = build_api_payload(
        {
            "model": "dream",
            "vae": "vaeA",
            "sampler": "Euler",
            "sampling_steps": 30,
            "img2img_img": "BASE64",
            "mask_img": "MASK",
            "batch_count": 2,
            "refiner": "refinerA",
            "refiner_start": 0.75,
            "color_correction": False,
        }
    )

    assert payload["override_settings"]["sd_model_checkpoint"] == "dream"
    assert payload["override_settings"]["sd_vae"] == "vaeA"
    assert payload["override_settings"]["img2img_color_correction"] is False
    assert payload["sampler_name"] == "Euler"
    assert payload["steps"] == 30
    assert payload["init_images"] == ["BASE64"]
    assert payload["mask"] == "MASK"
    assert payload["n_iter"] == 2
    assert payload["refiner_checkpoint"] == "refinerA"
    assert payload["refiner_switch_at"] == 0.75
    assert payload["override_settings_restore_afterwards"] is False

    assert "model" not in payload
    assert "sampling_steps" not in payload
    assert "img2img_img" not in payload

    assert "refiner" not in payload
    assert "refiner_start" not in payload
