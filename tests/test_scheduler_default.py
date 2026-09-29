"""Backend-owned scheduler default: build_api_payload must NOT inject a
`scheduler` key unless the user supplied one.

Forge Neo computes its own per-preset scheduler default (measured live from
`GET /sdapi/v1/options`: sd/xl=Automatic, flux/klein=Beta, qwen=Normal,
krea=Simple). The plugin used to inject a hardcoded per-family value from
model_registry on EVERY request, silently overriding that backend default —
FLUX was sent `Simple` where the backend would have used `Beta`. Omitting the
key is byte-identical to what the Forge web UI does; the backend's
`processing.py` treats an omitted scheduler as its own preset default.

Contract locked here:
- no user scheduler  -> payload carries NO `scheduler` key
- user scheduler     -> passed through verbatim
- non-string values  -> passed through uncorrupted (never replaced by the
                        registry value)
- other family defaults (sampler, cfg, forge_preset) keep being applied

payload_builder is Qt-free; it is loaded under a private package name so this
module never executes forge/__init__.py (which imports `krita`).
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types

import pytest

_DOMAIN = pathlib.Path(__file__).resolve().parents[1] / "forge" / "domain"
_PRIVATE_PKG = "_scheduler_default_tests"


def _load_payload_builder():
    """Load forge/domain/{model_registry,payload_builder}.py under a private
    package name — never `import forge` (forge/__init__.py imports krita).
    """
    if _PRIVATE_PKG not in sys.modules:
        pkg = types.ModuleType(_PRIVATE_PKG)
        pkg.__path__ = [str(_DOMAIN)]
        sys.modules[_PRIVATE_PKG] = pkg
    for name in ("model_registry", "payload_builder"):
        full = f"{_PRIVATE_PKG}.{name}"
        if full in sys.modules:
            continue
        spec = importlib.util.spec_from_file_location(full, _DOMAIN / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[full] = mod
        spec.loader.exec_module(mod)
    return sys.modules[f"{_PRIVATE_PKG}.payload_builder"]


build_api_payload = _load_payload_builder().build_api_payload


# ---------------------------------------------------------------------------
# 1. No user scheduler -> no `scheduler` key at all (the defect)
# ---------------------------------------------------------------------------

_FAMILY_CHECKPOINTS = [
    ("SD", "dreamshaper_8.safetensors"),
    ("SDXL", "sdxl_base_1.0.safetensors"),
    ("FLUX", "flux-dev-fp16.safetensors"),
    ("FLUX2", "flux2-klein-4b.safetensors"),
    ("FLUX2", "klein-9b.safetensors"),
    ("ANIMA", "wai-anima-v1.safetensors"),
    ("ZIMAGE", "z-image-turbo.safetensors"),
    ("KREA2", "krea2-raw.safetensors"),
    ("QWEN", "qwen-image-v1.safetensors"),
    ("WAN", "wan-2.1.safetensors"),
]


@pytest.mark.parametrize(
    "family, checkpoint",
    _FAMILY_CHECKPOINTS,
    ids=[f"{fam}-{ckpt.split('.')[0]}" for fam, ckpt in _FAMILY_CHECKPOINTS],
)
def test_no_scheduler_key_when_user_supplied_none(family, checkpoint):
    """The backend's per-preset default must win: omit the key entirely."""
    result = build_api_payload({"model": checkpoint})
    assert "scheduler" not in result, (
        f"{family}: injected scheduler={result.get('scheduler')!r} would "
        "override the backend's own per-preset default"
    )


def test_flux_never_receives_registry_simple():
    """The wrong FLUX value can no longer be injected (registry says Simple,
    backend default is Beta — sending anything here overrides it)."""
    result = build_api_payload({"model": "flux-dev-fp16.safetensors"})
    assert "scheduler" not in result
    assert result.get("scheduler") != "Simple"


def test_flux2_klein_never_receives_registry_simple():
    result = build_api_payload({"model": "klein-9b.safetensors"})
    assert "scheduler" not in result


# ---------------------------------------------------------------------------
# 2. Explicit user scheduler passes through untouched
# ---------------------------------------------------------------------------


def test_user_scheduler_preserved_verbatim_flux():
    result = build_api_payload({"model": "flux-dev-fp16.safetensors",
                                "scheduler": "Karras"})
    assert result["scheduler"] == "Karras"


def test_user_scheduler_preserved_verbatim_sd():
    result = build_api_payload({"model": "dreamshaper_8.safetensors",
                                "scheduler": "Exponential"})
    assert result["scheduler"] == "Exponential"


# ---------------------------------------------------------------------------
# 3. Non-string scheduler does not corrupt the payload
# ---------------------------------------------------------------------------


def test_none_scheduler_passes_through_uncorrupted():
    result = build_api_payload({"model": "sdxl_base_1.0.safetensors",
                                "scheduler": None})
    assert result["scheduler"] is None
    # The rest of the family defaults still applied normally:
    assert result["override_settings"]["forge_preset"] == "xl"


def test_int_scheduler_passes_through_uncorrupted():
    result = build_api_payload({"model": "flux-dev-fp16.safetensors",
                                "scheduler": 42})
    assert result["scheduler"] == 42
    assert result["override_settings"]["forge_preset"] == "flux"


# ---------------------------------------------------------------------------
# 4. Removing the scheduler injection must not disturb other defaults
# ---------------------------------------------------------------------------


def test_sampler_and_cfg_defaults_still_injected():
    result = build_api_payload({"model": "flux-dev-fp16.safetensors"})
    assert result["sampler_name"] == "Euler"
    assert result["cfg_scale"] == 1
    assert result["distilled_cfg_scale"] == 3.5
    assert result["override_settings"]["forge_preset"] == "flux"
