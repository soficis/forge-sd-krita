from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ModelFamily(Enum):
    """All supported model architectures."""
    SD = "sd"
    SDXL = "sdxl"
    FLUX = "flux"
    FLUX2 = "flux2"
    ANIMA = "anima"
    ZIMAGE = "zimage"
    KREA2 = "krea2"
    QWEN_IMAGE = "qwen_image"
    WAN = "wan"


@dataclass
class ModelConfig:
    """Configuration for a model family."""
    family: ModelFamily
    forge_preset: str
    default_sampler: str
    default_scheduler: str
    default_steps: int
    default_cfg: float
    hide_negative_prompt: bool
    hide_styles: bool
    show_distilled_cfg: bool = False
    cfg_fixed: bool | None = None      # None=not fixed, float=value to force
    shift: float | None = None
    min_size: int = 256
    default_min_size: int = 512
    default_max_size: int = 2048
    text_encoder_files: list[str] = field(default_factory=list)
    vae_file: str = ""
    # For Krea2's different CFG convention
    krea2_cfg_convention: bool = False


# Pattern-based detection: (compiled_regex, ModelFamily)
# Priority-ordered — first match wins
DETECT_PATTERNS: list[tuple[re.Pattern, ModelFamily]] = [
    # Order matters: more specific patterns BEFORE general ones
    (re.compile(r'flux2|flux-2|flux\.2|klein[-_]?4b|klein[-_]?9b'), ModelFamily.FLUX2),
    (re.compile(r'anima|wai[-_]?anima'), ModelFamily.ANIMA),
    (re.compile(r'z[-_]?image[-_]?turbo|z[-_]?image(?:[-_])?|zimage'), ModelFamily.ZIMAGE),
    (re.compile(r'krea[_-]?2|krea2'), ModelFamily.KREA2),
    (re.compile(r'qwen[-_]?image'), ModelFamily.QWEN_IMAGE),
    (re.compile(r'flux|nunchaku|klein(?![-_]?(?:4b|9b))'), ModelFamily.FLUX),
    (re.compile(r'sdxl'), ModelFamily.SDXL),
    (re.compile(r'wan'), ModelFamily.WAN),
    # Default fallback
]


def detect_model_family(checkpoint_name: str) -> ModelFamily:
    """Detect model family from checkpoint filename or title.
    
    Uses priority-ordered regex patterns. Returns ModelFamily.SD as fallback
    when no pattern matches.
    """
    name_lower = checkpoint_name.lower()
    for pattern, family in DETECT_PATTERNS:
        if pattern.search(name_lower):
            return family
    return ModelFamily.SD


CONFIGS: dict[ModelFamily, ModelConfig] = {
    ModelFamily.SD: ModelConfig(
        family=ModelFamily.SD,
        forge_preset="sd",
        default_sampler="Euler a",
        default_scheduler="Automatic",
        default_steps=20,
        default_cfg=7.0,
        hide_negative_prompt=False,
        hide_styles=False,
        min_size=256,
        default_min_size=512,
        default_max_size=2048,
    ),
    ModelFamily.SDXL: ModelConfig(
        family=ModelFamily.SDXL,
        forge_preset="xl",
        default_sampler="Euler a",
        default_scheduler="Automatic",
        default_steps=20,
        default_cfg=5.0,
        hide_negative_prompt=False,
        hide_styles=False,
        min_size=512,
        default_min_size=512,
        default_max_size=2048,
    ),
    ModelFamily.FLUX: ModelConfig(
        family=ModelFamily.FLUX,
        forge_preset="flux",
        default_sampler="Euler",
        default_scheduler="Simple",
        default_steps=20,
        default_cfg=1.0,
        hide_negative_prompt=True,
        hide_styles=True,
        show_distilled_cfg=True,
        min_size=512,
        default_min_size=512,
        default_max_size=2048,
        text_encoder_files=["clip_l.safetensors", "t5xxl_fp16.safetensors"],
        vae_file="ae.safetensors",
    ),
    ModelFamily.FLUX2: ModelConfig(
        family=ModelFamily.FLUX2,
        forge_preset="klein",
        default_sampler="Euler",
        default_scheduler="Simple",
        default_steps=4,
        default_cfg=1.0,
        hide_negative_prompt=True,
        hide_styles=True,
        min_size=512,
        default_min_size=512,
        default_max_size=2048,
        text_encoder_files=["qwen_3_4b.safetensors"],
        vae_file="flux2-vae.safetensors",
    ),
    ModelFamily.ANIMA: ModelConfig(
        family=ModelFamily.ANIMA,
        forge_preset="anima",
        default_sampler="ER SDE",
        default_scheduler="Beta",
        default_steps=32,
        default_cfg=4.0,
        hide_negative_prompt=False,
        hide_styles=False,
        shift=3.0,
        min_size=512,
        default_min_size=512,
        default_max_size=2048,
        text_encoder_files=["qwen_3_06b_base.safetensors"],
        vae_file="qwen_image_vae.safetensors",
    ),
    ModelFamily.ZIMAGE: ModelConfig(
        family=ModelFamily.ZIMAGE,
        forge_preset="zit",
        default_sampler="Euler",
        default_scheduler="Beta",
        default_steps=9,
        default_cfg=1.0,
        hide_negative_prompt=True,
        hide_styles=False,
        cfg_fixed=1.0,
        shift=9.0,
        min_size=512,
        default_min_size=512,
        default_max_size=2048,
        text_encoder_files=["qwen_3_4b.safetensors"],
        vae_file="ae.safetensors",
    ),
    ModelFamily.KREA2: ModelConfig(
        family=ModelFamily.KREA2,
        forge_preset="krea",
        default_sampler="Euler",
        default_scheduler="Simple",
        default_steps=28,
        default_cfg=4.5,
        hide_negative_prompt=False,
        hide_styles=False,
        min_size=512,
        default_min_size=512,
        default_max_size=2048,
        text_encoder_files=["qwen3vl_4b_fp8_scaled.safetensors"],
        vae_file="qwen_image_vae.safetensors",
        krea2_cfg_convention=True,
    ),
    ModelFamily.QWEN_IMAGE: ModelConfig(
        family=ModelFamily.QWEN_IMAGE,
        forge_preset="qwen",
        default_sampler="Euler",
        default_scheduler="Simple",
        default_steps=30,
        default_cfg=4.0,
        hide_negative_prompt=False,
        hide_styles=False,
        min_size=512,
        default_min_size=512,
        default_max_size=2048,
        text_encoder_files=["qwen_2.5_vl_7b_fp8_scaled.safetensors"],
        vae_file="qwen_image_vae.safetensors",
    ),
    ModelFamily.WAN: ModelConfig(
        family=ModelFamily.WAN,
        forge_preset="wan",
        default_sampler="Euler a",
        default_scheduler="Automatic",
        default_steps=20,
        default_cfg=7.0,
        hide_negative_prompt=False,
        hide_styles=False,
        min_size=256,
        default_min_size=256,
        default_max_size=1024,
    ),
}


def get_model_config(family: ModelFamily) -> ModelConfig:
    """Get the ModelConfig for a given ModelFamily."""
    return CONFIGS[family]
