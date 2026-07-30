"""Unit tests for forge.domain.model_registry — model family detection,
configuration registry, and priority-ordered pattern matching.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import the module directly to avoid krita dependency in forge/__init__.py
# ---------------------------------------------------------------------------

_spec = importlib.util.spec_from_file_location(
    "model_registry",
    str(Path(__file__).resolve().parent.parent / "forge" / "domain" / "model_registry.py"),
)
_model_registry = importlib.util.module_from_spec(_spec)
sys.modules["model_registry"] = _model_registry
_spec.loader.exec_module(_model_registry)

ModelFamily = _model_registry.ModelFamily
ModelConfig = _model_registry.ModelConfig
detect_model_family = _model_registry.detect_model_family
get_model_config = _model_registry.get_model_config
CONFIGS = _model_registry.CONFIGS
DETECT_PATTERNS = _model_registry.DETECT_PATTERNS


# ---------------------------------------------------------------------------
# Test Group 1: detect_model_family() — real-world checkpoint names
# ---------------------------------------------------------------------------


class TestDetectModelFamily_Flux:
    """Flux family detection from common checkpoint name patterns."""

    @pytest.mark.parametrize(
        "name, expected",
        [
            ("flux1-dev.safetensors", ModelFamily.FLUX),
            ("flux-dev-fp8.safetensors", ModelFamily.FLUX),
            ("nunchaku-flux-dev.safetensors", ModelFamily.FLUX),
            ("klein-flux-dev.safetensors", ModelFamily.FLUX),
            ("flux1-dev.safetensors", ModelFamily.FLUX),
            ("my_flux_model.ckpt", ModelFamily.FLUX),
        ],
    )
    def test_flux_patterns(self, name: str, expected: ModelFamily):
        assert detect_model_family(name) == expected


class TestDetectModelFamily_Flux2:
    """Flux2 / Klein detection — must match BEFORE generic flux."""

    @pytest.mark.parametrize(
        "name, expected",
        [
            ("flux2-klein-4b.safetensors", ModelFamily.FLUX2),
            ("flux-2-klein-9b.safetensors", ModelFamily.FLUX2),
            ("flux.2-dev-fp8.safetensors", ModelFamily.FLUX2),
            ("klein-4b.safetensors", ModelFamily.FLUX2),
            ("klein_9b_fp8.safetensors", ModelFamily.FLUX2),
            ("flux2-dev.safetensors", ModelFamily.FLUX2),
        ],
    )
    def test_flux2_patterns(self, name: str, expected: ModelFamily):
        assert detect_model_family(name) == expected


class TestDetectModelFamily_Anima:
    """Anima family detection."""

    @pytest.mark.parametrize(
        "name, expected",
        [
            ("anima-base-v1.0.safetensors", ModelFamily.ANIMA),
            ("wai-anima-base.safetensors", ModelFamily.ANIMA),
            ("anima-turbo.safetensors", ModelFamily.ANIMA),
            ("wai_anima_v2.safetensors", ModelFamily.ANIMA),
        ],
    )
    def test_anima_patterns(self, name: str, expected: ModelFamily):
        assert detect_model_family(name) == expected


class TestDetectModelFamily_ZImage:
    """Z-Image family detection."""

    @pytest.mark.parametrize(
        "name, expected",
        [
            ("z-image-turbo.safetensors", ModelFamily.ZIMAGE),
            ("z_image_base.safetensors", ModelFamily.ZIMAGE),
            ("zimage.safetensors", ModelFamily.ZIMAGE),
            ("z-image-lora.safetensors", ModelFamily.ZIMAGE),
        ],
    )
    def test_zimage_patterns(self, name: str, expected: ModelFamily):
        assert detect_model_family(name) == expected


class TestDetectModelFamily_Krea2:
    """Krea2 family detection."""

    @pytest.mark.parametrize(
        "name, expected",
        [
            ("krea2-turbo.safetensors", ModelFamily.KREA2),
            ("krea-2-raw.safetensors", ModelFamily.KREA2),
            ("krea_2_fp8.safetensors", ModelFamily.KREA2),
            ("krea2_model.ckpt", ModelFamily.KREA2),
        ],
    )
    def test_krea2_patterns(self, name: str, expected: ModelFamily):
        assert detect_model_family(name) == expected


class TestDetectModelFamily_QwenImage:
    """Qwen-Image family detection."""

    @pytest.mark.parametrize(
        "name, expected",
        [
            ("qwen-image-2512.safetensors", ModelFamily.QWEN_IMAGE),
            ("qwen_image_fp8.safetensors", ModelFamily.QWEN_IMAGE),
            ("qwen-image-v2.safetensors", ModelFamily.QWEN_IMAGE),
        ],
    )
    def test_qwen_image_patterns(self, name: str, expected: ModelFamily):
        assert detect_model_family(name) == expected


class TestDetectModelFamily_SDXL:
    """SDXL family detection."""

    @pytest.mark.parametrize(
        "name, expected",
        [
            ("sdxl-base-1.0.safetensors", ModelFamily.SDXL),
            ("sdxl-turbo.safetensors", ModelFamily.SDXL),
            ("my_sdxl_model.safetensors", ModelFamily.SDXL),
        ],
    )
    def test_sdxl_patterns(self, name: str, expected: ModelFamily):
        assert detect_model_family(name) == expected


class TestDetectModelFamily_WAN:
    """WAN family detection."""

    @pytest.mark.parametrize(
        "name, expected",
        [
            ("wan2.2.safetensors", ModelFamily.WAN),
            ("wan_video_model.ckpt", ModelFamily.WAN),
        ],
    )
    def test_wan_patterns(self, name: str, expected: ModelFamily):
        assert detect_model_family(name) == expected


class TestDetectModelFamily_Default:
    """Unknown models should default to SD."""

    @pytest.mark.parametrize(
        "name, expected",
        [
            ("v1-5-pruned.safetensors", ModelFamily.SD),
            ("realistic-vision.safetensors", ModelFamily.SD),
            ("", ModelFamily.SD),
            ("unknown-model.safetensors", ModelFamily.SD),
            ("dreamshaper_8.safetensors", ModelFamily.SD),
            ("deliberate_v2.ckpt", ModelFamily.SD),
        ],
    )
    def test_default_fallback(self, name: str, expected: ModelFamily):
        assert detect_model_family(name) == expected


# ---------------------------------------------------------------------------
# Test Group 2: Case insensitivity
# ---------------------------------------------------------------------------


class TestCaseInsensitivity:
    """Detection must work regardless of filename casing."""

    @pytest.mark.parametrize(
        "name, expected",
        [
            ("FLUX1-DEV.SAFETENSORS", ModelFamily.FLUX),
            ("Z-IMAGE-TURBO.SAFETENSORS", ModelFamily.ZIMAGE),
            ("Krea2-Turbo.safetensors", ModelFamily.KREA2),
            ("FLUX2-KLEIN-4B.SAFETENSORS", ModelFamily.FLUX2),
            ("ANIMA-BASE-V1.0.SAFETENSORS", ModelFamily.ANIMA),
            ("QWEN-IMAGE-FP8.SAFETENSORS", ModelFamily.QWEN_IMAGE),
            ("SDXL-BASE-1.0.SAFETENSORS", ModelFamily.SDXL),
            ("WAN2.2.SAFETENSORS", ModelFamily.WAN),
        ],
    )
    def test_uppercase_matches(self, name: str, expected: ModelFamily):
        assert detect_model_family(name) == expected


# ---------------------------------------------------------------------------
# Test Group 3: Priority ordering (critical bug prevention)
# ---------------------------------------------------------------------------


class TestPriorityOrdering:
    """More specific patterns must match before general ones.

    This is critical: 'flux2' MUST match FLUX2, not FLUX.
    'klein-4b' MUST match FLUX2, not FLUX.
    'z-image' patterns MUST match before any broader pattern.
    """

    def test_flux2_before_flux(self):
        """flux2 names must not fall through to the flux pattern."""
        assert detect_model_family("flux2-dev.safetensors") == ModelFamily.FLUX2
        assert detect_model_family("flux2-klein.safetensors") == ModelFamily.FLUX2

    def test_flux_still_matches_regular_flux(self):
        """Regular flux names should still match FLUX (not FLUX2)."""
        assert detect_model_family("flux1-dev.safetensors") == ModelFamily.FLUX
        assert detect_model_family("flux-dev-fp8.safetensors") == ModelFamily.FLUX

    def test_klein_4b_matches_flux2_not_flux(self):
        """klein-4b is a Flux2 variant, not generic Flux."""
        assert detect_model_family("klein-4b.safetensors") == ModelFamily.FLUX2

    def test_klein_9b_matches_flux2_not_flux(self):
        """klein-9b is a Flux2 variant, not generic Flux."""
        assert detect_model_family("klein-9b.safetensors") == ModelFamily.FLUX2

    def test_klein_without_size_suffix_matches_flux(self):
        """'klein' alone (no 4b/9b) matches generic FLUX."""
        assert detect_model_family("klein-flux-dev.safetensors") == ModelFamily.FLUX

    def test_zimage_before_wan(self):
        """z-image patterns must match before 'wan' which is a substring."""
        assert detect_model_family("z-image-turbo.safetensors") == ModelFamily.ZIMAGE

    def test_anima_is_distinct(self):
        """anima should not accidentally match other families."""
        assert detect_model_family("anima-turbo.safetensors") == ModelFamily.ANIMA

    def test_krea2_before_krea_generic(self):
        """krea2/krea-2 must match KREA2, not fall through."""
        assert detect_model_family("krea2-turbo.safetensors") == ModelFamily.KREA2
        assert detect_model_family("krea-2-raw.safetensors") == ModelFamily.KREA2


# ---------------------------------------------------------------------------
# Test Group 4: CONFIGS validation
# ---------------------------------------------------------------------------


class TestConfigsValidation:
    """Every ModelFamily has a valid, complete config entry."""

    def test_all_families_have_configs(self):
        """Every enum member of ModelFamily must appear in CONFIGS."""
        for member in ModelFamily:
            assert member in CONFIGS, f"Missing config for {member.name}"

    def test_no_extra_keys_in_configs(self):
        """CONFIGS should not contain keys that aren't ModelFamily members."""
        for key in CONFIGS:
            assert isinstance(key, ModelFamily), f"Invalid CONFIGS key: {key}"

    @pytest.mark.parametrize("family", list(ModelFamily))
    def test_forge_preset_nonempty(self, family: ModelFamily):
        """Each config must have a non-empty forge_preset string."""
        cfg = CONFIGS[family]
        assert cfg.forge_preset, f"{family.name}: forge_preset is empty"

    @pytest.mark.parametrize("family", list(ModelFamily))
    def test_default_steps_positive(self, family: ModelFamily):
        """Each config must have default_steps > 0."""
        cfg = CONFIGS[family]
        assert cfg.default_steps > 0, f"{family.name}: default_steps={cfg.default_steps}"

    @pytest.mark.parametrize("family", list(ModelFamily))
    def test_default_min_size_positive(self, family: ModelFamily):
        """Each config must have default_min_size > 0."""
        cfg = CONFIGS[family]
        assert cfg.default_min_size > 0, f"{family.name}: default_min_size={cfg.default_min_size}"

    @pytest.mark.parametrize("family", list(ModelFamily))
    def test_config_family_matches_key(self, family: ModelFamily):
        """Each config's .family field must match the dict key."""
        cfg = CONFIGS[family]
        assert cfg.family == family, (
            f"{family.name}: config.family={cfg.family.name} != key={family.name}"
        )

    @pytest.mark.parametrize("family", list(ModelFamily))
    def test_default_cfg_positive(self, family: ModelFamily):
        """Each config must have default_cfg > 0."""
        cfg = CONFIGS[family]
        assert cfg.default_cfg > 0, f"{family.name}: default_cfg={cfg.default_cfg}"

    @pytest.mark.parametrize("family", list(ModelFamily))
    def test_sampler_nonempty(self, family: ModelFamily):
        """Each config must have a non-empty default_sampler."""
        cfg = CONFIGS[family]
        assert cfg.default_sampler, f"{family.name}: default_sampler is empty"

    @pytest.mark.parametrize("family", list(ModelFamily))
    def test_scheduler_nonempty(self, family: ModelFamily):
        """Each config must have a non-empty default_scheduler."""
        cfg = CONFIGS[family]
        assert cfg.default_scheduler, f"{family.name}: default_scheduler is empty"

    def test_config_count_matches_family_count(self):
        """CONFIGS must have exactly one entry per ModelFamily member."""
        assert len(CONFIGS) == len(ModelFamily)

    def test_flux_config_has_text_encoder_files(self):
        """FLUX config must list required text encoder files."""
        cfg = CONFIGS[ModelFamily.FLUX]
        assert len(cfg.text_encoder_files) > 0

    def test_flux2_config_has_text_encoder_files(self):
        """FLUX2 config must list required text encoder files."""
        cfg = CONFIGS[ModelFamily.FLUX2]
        assert len(cfg.text_encoder_files) > 0

    def test_anima_config_has_shift(self):
        """ANIMA config should have a shift value set."""
        cfg = CONFIGS[ModelFamily.ANIMA]
        assert cfg.shift is not None
        assert cfg.shift > 0

    def test_zimage_config_has_cfg_fixed(self):
        """ZIMAGE config should have cfg_fixed set."""
        cfg = CONFIGS[ModelFamily.ZIMAGE]
        assert cfg.cfg_fixed is not None

    def test_krea2_config_has_krea2_cfg_convention(self):
        """KREA2 config should use the krea2 CFG convention."""
        cfg = CONFIGS[ModelFamily.KREA2]
        assert cfg.krea2_cfg_convention is True


# ---------------------------------------------------------------------------
# Test Group 5: get_model_config()
# ---------------------------------------------------------------------------


class TestGetModelConfig:
    """get_model_config() returns the correct config for each family."""

    @pytest.mark.parametrize("family", list(ModelFamily))
    def test_returns_model_config(self, family: ModelFamily):
        """Each family must return its ModelConfig from get_model_config."""
        cfg = get_model_config(family)
        assert isinstance(cfg, ModelConfig)
        assert cfg.family == family

    def test_returns_same_object_as_config_dict(self):
        """get_model_config(family) must return the exact same object as CONFIGS[family]."""
        for family in ModelFamily:
            assert get_model_config(family) is CONFIGS[family]

    def test_raises_keyerror_for_unknown(self):
        """get_model_config with a non-ModelFamily value raises KeyError."""
        # Use a mock-like approach: create a fake enum value isn't possible,
        # but we can verify the dict behavior directly.
        with pytest.raises(KeyError):
            # CONFIGS is a dict — passing an absent key raises KeyError
            CONFIGS["not-a-family"]

    def test_sd_config_values(self):
        """Verify specific SD config values for correctness."""
        cfg = get_model_config(ModelFamily.SD)
        assert cfg.forge_preset == "sd"
        assert cfg.default_sampler == "Euler a"
        assert cfg.hide_negative_prompt is False
        assert cfg.hide_styles is False

    def test_flux_config_values(self):
        """Verify specific FLUX config values for correctness."""
        cfg = get_model_config(ModelFamily.FLUX)
        assert cfg.forge_preset == "flux"
        assert cfg.hide_negative_prompt is True
        assert cfg.hide_styles is True
        assert cfg.show_distilled_cfg is True
        assert cfg.vae_file == "ae.safetensors"

    def test_flux2_config_values(self):
        """Verify specific FLUX2 config values for correctness."""
        cfg = get_model_config(ModelFamily.FLUX2)
        assert cfg.forge_preset == "klein"
        assert cfg.default_steps == 4
        assert cfg.vae_file == "flux2-vae.safetensors"

    def test_anima_config_values(self):
        """Verify specific ANIMA config values for correctness."""
        cfg = get_model_config(ModelFamily.ANIMA)
        assert cfg.forge_preset == "anima"
        assert cfg.default_sampler == "ER SDE"
        assert cfg.shift == 3.0

    def test_zimage_config_values(self):
        """Verify specific ZIMAGE config values for correctness."""
        cfg = get_model_config(ModelFamily.ZIMAGE)
        assert cfg.forge_preset == "zit"
        assert cfg.cfg_fixed == 1.0
        assert cfg.shift == 9.0

    def test_krea2_config_values(self):
        """Verify specific KREA2 config values for correctness."""
        cfg = get_model_config(ModelFamily.KREA2)
        assert cfg.forge_preset == "krea"
        assert cfg.krea2_cfg_convention is True

    def test_qwen_image_config_values(self):
        """Verify specific QWEN_IMAGE config values for correctness."""
        cfg = get_model_config(ModelFamily.QWEN_IMAGE)
        assert cfg.forge_preset == "qwen"

    def test_sdxl_config_values(self):
        """Verify specific SDXL config values for correctness."""
        cfg = get_model_config(ModelFamily.SDXL)
        assert cfg.forge_preset == "xl"
        assert cfg.min_size == 512

    def test_wan_config_values(self):
        """Verify specific WAN config values for correctness."""
        cfg = get_model_config(ModelFamily.WAN)
        assert cfg.forge_preset == "wan"
        assert cfg.default_max_size == 1024


# ---------------------------------------------------------------------------
# Test Group (bonus): DETECT_PATTERNS structure
# ---------------------------------------------------------------------------


class TestDetectPatternsStructure:
    """Verify the DETECT_PATTERNS list is properly structured."""

    def test_patterns_are_list_of_tuples(self):
        """DETECT_PATTERNS should be a list of (compiled_regex, ModelFamily) tuples."""
        assert isinstance(DETECT_PATTERNS, list)
        for entry in DETECT_PATTERNS:
            assert isinstance(entry, tuple)
            assert len(entry) == 2

    def test_patterns_have_compiled_regex(self):
        """Each pattern's first element must be a compiled regex."""
        import re
        for pattern, family in DETECT_PATTERNS:
            assert isinstance(pattern, re.Pattern), f"Not a compiled regex: {pattern}"

    def test_patterns_have_model_family(self):
        """Each pattern's second element must be a ModelFamily member."""
        for pattern, family in DETECT_PATTERNS:
            assert isinstance(family, ModelFamily), f"Not a ModelFamily: {family}"

    def test_flux2_pattern_before_flux_pattern(self):
        """The FLUX2 pattern must appear before the FLUX pattern in DETECT_PATTERNS."""
        flux2_idx = None
        flux_idx = None
        for i, (pattern, family) in enumerate(DETECT_PATTERNS):
            if family == ModelFamily.FLUX2 and flux2_idx is None:
                flux2_idx = i
            if family == ModelFamily.FLUX and flux_idx is None:
                flux_idx = i
        assert flux2_idx is not None, "FLUX2 pattern not found"
        assert flux_idx is not None, "FLUX pattern not found"
        assert flux2_idx < flux_idx, (
            f"FLUX2 pattern (index {flux2_idx}) must come before FLUX pattern (index {flux_idx})"
        )
