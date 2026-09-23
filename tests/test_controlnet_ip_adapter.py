"""Todo 31: IP-Adapter reference image slot with capability gate.

Loads controlnet.py fresh under stub-Qt REAL classes (same proven pattern as
tests/test_controlnet_dict_guards.py — conftest's MagicMock Qt cannot be
subclassing-tested). Covers:

- capability detection via ControlNet dropdowns plus SDAPI get_scripts() /
  forge-additional-modules introspection (read-only; no new HTTP endpoints),
- the hidden-unless-detected slot gate,
- reference-image b64 landing in the ControlNet unit ``image`` payload key,
- graceful no-crash when introspection returns junk or methods are absent,
- todo 9 non-dict guard regressions stay green (test_controlnet_dict_guards).
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import pathlib
import sys
import time
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# Pre-loads the `forge` package (and sd_api under conftest's Qt mocks) BEFORE
# the stub-Qt loader below runs; otherwise the loader's cleanup would pop the
# just-imported `forge` package out of sys.modules. SDAPI is used directly in
# TestDetectViaRealSdApiIntrospection.
from forge.adapters.sd_api import SDAPI


# ---------------------------------------------------------------------------
# Real-Qt-stub loader for the widget layer (dict_guards pattern)
# ---------------------------------------------------------------------------

_QT_NAMES = [
    "Qt", "QWidget", "QVBoxLayout", "QHBoxLayout", "QFormLayout",
    "QLabel", "QComboBox", "QPushButton", "QCheckBox", "QTabWidget",
    "QGroupBox", "QSlider", "QSpinBox", "QDoubleSpinBox", "QPlainTextEdit",
    "QScrollArea", "QColor", "QPainter", "QByteArray", "QBuffer", "QImage",
    "QIODevice", "QObject", "QThread", "QTimer", "pyqtSignal", "QSize",
    "QIcon", "QPixmap", "QPointF", "qAlpha", "qRgb",
]


def _load_controlnet_real():
    """Import controlnet.py fresh with stub-Qt classes; return the module."""
    _dummy = MagicMock()

    class _Meta(type):
        def __getattr__(cls, name):
            if name.startswith("__"):
                raise AttributeError(name)
            return _dummy

    class _StubBase(metaclass=_Meta):
        def __init__(self, *args, **kwargs):
            pass

        def __getattr__(self, name):
            if name.startswith("__"):
                raise AttributeError(name)
            return _dummy

    stub = types.ModuleType("forge.qt_compat")
    for _name in _QT_NAMES:
        setattr(stub, _name, _Meta(_name, (_StubBase,), {}))
    stub.__all__ = list(_QT_NAMES)

    def __getattr__(name):
        if name.startswith("__"):
            raise AttributeError(name)
        cls = _Meta(name, (_StubBase,), {})
        setattr(stub, name, cls)
        return cls

    stub.__getattr__ = __getattr__

    pre_keys = set(sys.modules)
    old = sys.modules.get("forge.qt_compat")
    sys.modules["forge.qt_compat"] = stub
    try:
        path = (
            pathlib.Path(__file__).resolve().parent.parent
            / "forge" / "extension_widgets" / "controlnet.py"
        )
        mod_name = "forge.extension_widgets.controlnet_task31"
        spec = importlib.util.spec_from_file_location(mod_name, str(path))
        mod = importlib.util.module_from_spec(spec)
        mod.__package__ = "forge.extension_widgets"
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        if old is not None:
            sys.modules["forge.qt_compat"] = old
        else:
            sys.modules.pop("forge.qt_compat", None)
        for _key in [k for k in sys.modules if k not in pre_keys
                     and k != "forge.extension_widgets.controlnet_task31"]:
            sys.modules.pop(_key, None)


cn_mod = _load_controlnet_real()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NON_DICTS = [None, [], "err", 42]

# Canned ControlNet endpoint payloads for a stub server WITHOUT IP-Adapter.
_CLEAN_ENDPOINTS = {
    "/controlnet/model_list?update=true": {
        "model_list": ["control_v11p_sd15_canny"],
    },
    "/controlnet/module_list?alias_names=true": {
        "module_list": ["canny", "none"],
        "module_detail": {},
    },
    "/controlnet/control_types": {
        "control_types": {
            "All": {
                "module_list": ["canny"],
                "model_list": ["control_v11p_sd15_canny"],
                "default_option": "canny",
                "default_model": "control_v11p_sd15_canny",
            }
        }
    },
    "/controlnet/settings": {"control_net_unit_count": 1},
    "/controlnet/version": {"version": 3},
}


def _fake_api(responses=None, scripts=None, modules=None):
    """Minimal SDAPI-shaped fake: get() per-path, plus introspection methods."""
    responses = responses if responses is not None else dict(_CLEAN_ENDPOINTS)
    return SimpleNamespace(
        get=MagicMock(side_effect=lambda path: responses.get(path)),
        post=MagicMock(return_value=None),
        get_scripts=MagicMock(
            return_value=scripts if scripts is not None else {}
        ),
        get_additional_modules=MagicMock(
            return_value=modules if modules is not None else []
        ),
    )


def _build_cnapi(api) -> "cn_mod.ControlNetAPI":
    """Real ControlNetAPI.__init__ (KritaAdapter patched out — no Krita)."""
    with patch.object(cn_mod, "KritaAdapter"):
        return cn_mod.ControlNetAPI(api)


def _detect_only(api, module_list=None, models=None, control_types=None):
    """ControlNetAPI via __new__ with only the fields detect_ip_adapter reads."""
    inst = cn_mod.ControlNetAPI.__new__(cn_mod.ControlNetAPI)
    inst.api = api
    inst.models = models if models is not None else []
    inst.module_list = module_list if module_list is not None else []
    inst.module_details = {}
    inst.control_types = (
        control_types if control_types is not None else {}
    )
    inst.settings = {}
    inst.tabs = 0
    return inst


# ---------------------------------------------------------------------------
# Detection (ControlNetAPI) — get_scripts / forge-additional-modules /
# ControlNet dropdown introspection, read-only against sd_api.py
# ---------------------------------------------------------------------------

class TestIpAdapterDetection:
    def test_stub_server_without_ip_adapter_false_no_crash(self):
        api = _fake_api(
            _CLEAN_ENDPOINTS,
            scripts={"txt2img": ["controlnet"]},
            modules=[],
        )
        inst = _build_cnapi(api)
        assert inst.ip_adapter is False
        # Detection actually ran the documented introspection calls:
        api.get_scripts.assert_called_once_with()
        api.get_additional_modules.assert_called_once_with()

    def test_detects_ip_adapter_preprocessor_dropdown(self):
        responses = dict(_CLEAN_ENDPOINTS)
        responses["/controlnet/module_list?alias_names=true"] = {
            "module_list": ["canny", "ip-adapter_clip_sd15"],
            "module_detail": {},
        }
        inst = _build_cnapi(_fake_api(responses, scripts={}, modules=[]))
        assert inst.ip_adapter is True

    def test_detects_ip_adapter_model_dropdown(self):
        responses = dict(_CLEAN_ENDPOINTS)
        responses["/controlnet/model_list?update=true"] = {
            "model_list": ["control_v11p_sd15_canny", "ip-adapter_sd15_plus"],
        }
        inst = _build_cnapi(_fake_api(responses, scripts={}, modules=[]))
        assert inst.ip_adapter is True

    def test_detects_ip_adapter_in_control_types_entry(self):
        responses = dict(_CLEAN_ENDPOINTS)
        responses["/controlnet/control_types"] = {
            "control_types": {
                "IP-Adapter": {
                    "module_list": ["ip_adapter_face_id_plus"],
                    "model_list": [],
                    "default_option": "none",
                    "default_model": "None",
                }
            }
        }
        inst = _build_cnapi(_fake_api(responses, scripts={}, modules=[]))
        assert inst.ip_adapter is True

    def test_detects_ip_adapter_via_get_scripts(self):
        api = _fake_api(
            _CLEAN_ENDPOINTS,
            scripts={"txt2img": ["controlnet", "ip-adapter"]},
            modules=[],
        )
        inst = _build_cnapi(api)
        assert inst.ip_adapter is True

    def test_detects_ip_adapter_via_forge_additional_modules(self):
        api = _fake_api(
            _CLEAN_ENDPOINTS,
            scripts={},
            modules=[{"name": "ip_adapter_plus_sd15", "type": "clip"}],
        )
        inst = _build_cnapi(api)
        assert inst.ip_adapter is True

    @pytest.mark.parametrize(
        "name",
        [
            "ip-adapter_clip_sd15",
            "ip_adapter_sd15",
            "IP-Adapter-Plus",
            "ip adapter quickimports",
            "ipadapter_face_id",
        ],
    )
    def test_ip_name_variants_match(self, name):
        assert cn_mod._is_ip_adapter_name(name) is True

    @pytest.mark.parametrize(
        "name",
        ["canny", "depth_midas", "control_v11p_sd15_canny", "clip_vit", ""],
    )
    def test_non_ip_names_rejected(self, name):
        assert cn_mod._is_ip_adapter_name(name) is False

    @pytest.mark.parametrize("bad_scripts,bad_modules", [
        (None, None),
        (["x"], "err"),
        (42, {"name": "ip_adapter"}),
    ])
    def test_nondict_introspection_no_crash(self, bad_scripts, bad_modules):
        api = _fake_api(
            _CLEAN_ENDPOINTS,
            scripts=bad_scripts,
            modules=bad_modules,
        )
        inst = _build_cnapi(api)
        assert inst.ip_adapter is False

    @pytest.mark.parametrize("bad", NON_DICTS)
    def test_junk_controlnet_endpoints_no_crash(self, bad):
        responses = {path: bad for path in _CLEAN_ENDPOINTS}
        inst = _build_cnapi(
            _fake_api(responses, scripts={}, modules=[])
        )
        assert inst.ip_adapter is False

    def test_missing_introspection_methods_no_crash(self):
        # API without get_scripts/get_additional_modules at all → no raise
        api = SimpleNamespace(get=MagicMock(return_value=None))
        inst = _build_cnapi(api)
        assert inst.ip_adapter is False

    def test_introspection_exception_no_crash(self):
        api = _fake_api(_CLEAN_ENDPOINTS)
        api.get_scripts = MagicMock(side_effect=RuntimeError("boom"))
        api.get_additional_modules = MagicMock(side_effect=RuntimeError("boom"))
        inst = _build_cnapi(api)
        assert inst.ip_adapter is False


class TestDetectViaRealSdApiIntrospection:
    """Detection drives the REAL SDAPI.get_scripts / get_additional_modules
    methods (TTL cache pre-seeded — no network, sd_api.py untouched)."""

    @staticmethod
    def _real_sdapi(scripts, modules):
        api = SDAPI.__new__(SDAPI)
        api._cache = {
            "scripts": (time.time(), scripts),
            "additional_modules": (time.time(), modules),
        }
        api._cache_ttl = 60.0
        return api

    def test_real_sdapi_scripts_hit_detects(self):
        api = self._real_sdapi(
            {"txt2img": ["controlnet", "ip-adapter"]}, []
        )
        inst = _detect_only(api)
        assert inst.detect_ip_adapter() is True

    def test_real_sdapi_additional_modules_hit_detects(self):
        api = self._real_sdapi({}, [{"name": "ip_adapter_sd15"}])
        inst = _detect_only(api)
        assert inst.detect_ip_adapter() is True

    def test_real_sdapi_clean_lists_no_detect(self):
        api = self._real_sdapi({"txt2img": ["controlnet"]}, [])
        inst = _detect_only(
            api,
            module_list=["canny"],
            models=["control_v11p_sd15_canny"],
        )
        assert inst.detect_ip_adapter() is False


# ---------------------------------------------------------------------------
# Capability gate — slot hidden unless introspection detected IP-Adapter
# ---------------------------------------------------------------------------

def _bind_gate(stub):
    """Bind the real ref_image_supported onto a SimpleNamespace stub so that
    unbound sibling calls (self.ref_image_supported()) execute real code."""
    stub.ref_image_supported = types.MethodType(
        cn_mod.ControlNetUnit.ref_image_supported, stub
    )
    return stub


class TestIpAdapterCapabilityGate:
    def test_gate_false_slot_hidden_predicate(self):
        stub = _bind_gate(SimpleNamespace(
            cnapi=SimpleNamespace(ip_adapter=False),
            ref_slot=MagicMock(),
        ))
        assert cn_mod.ControlNetUnit.ref_image_supported(stub) is False
        assert cn_mod.ControlNetUnit.apply_ref_slot_gate(stub) is False
        stub.ref_slot.setVisible.assert_called_once_with(False)

    def test_gate_true_slot_visible(self):
        stub = _bind_gate(SimpleNamespace(
            cnapi=SimpleNamespace(ip_adapter=True),
            ref_slot=MagicMock(),
        ))
        assert cn_mod.ControlNetUnit.ref_image_supported(stub) is True
        assert cn_mod.ControlNetUnit.apply_ref_slot_gate(stub) is True
        stub.ref_slot.setVisible.assert_called_once_with(True)

    def test_gate_missing_capability_attr_defaults_hidden(self):
        stub = _bind_gate(SimpleNamespace(
            cnapi=SimpleNamespace(),
            ref_slot=MagicMock(),
        ))
        assert cn_mod.ControlNetUnit.ref_image_supported(stub) is False
        cn_mod.ControlNetUnit.apply_ref_slot_gate(stub)
        stub.ref_slot.setVisible.assert_called_once_with(False)

    def test_constructor_applies_gate(self):
        source = inspect.getsource(cn_mod.ControlNetUnit.__init__)
        assert "apply_ref_slot_gate()" in source

    def test_constructor_builds_reference_slot(self):
        source = inspect.getsource(cn_mod.ControlNetUnit.__init__)
        assert "ImageInWidget" in source
        assert "'reference_image'" in source


# ---------------------------------------------------------------------------
# Payload — reference b64 lands in the ControlNet unit `image` key
# ---------------------------------------------------------------------------

def _unit_stub(**overrides):
    stub = SimpleNamespace(
        enabled=True,
        preprocessor="ip-adapter_clip_sd15",
        model="ip-adapter_sd15",
        variables={
            "weight": 100,
            "preprocessor_resolution": 512,
            "threshold_a": -2,
            "threshold_b": -3,
            "start": 0,
            "end": 100,
        },
        resize_mode=0,
        resize_mode_options=["Just Resize", "Crop and Resize", "Resize and Fill"],
        control_mode=0,
        control_mode_options=[
            "Balanced",
            "My prompt is more important",
            "ControlNet is more important",
        ],
        low_vram=False,
        pixel_perfect=False,
        debug=False,
        use_mask=SimpleNamespace(isChecked=MagicMock(return_value=False)),
        img_in=SimpleNamespace(
            get_generation_data=MagicMock(
                return_value={"input_image": "CTRLB64"}
            )
        ),
        mask_in=SimpleNamespace(
            get_generation_data=MagicMock(
                return_value={"inpaint_img": "MASKB64", "mask_img": "MASKMASK"}
            )
        ),
        cnapi=SimpleNamespace(ip_adapter=True),
        ref_in=SimpleNamespace(
            image=object(),
            get_generation_data=MagicMock(
                return_value={"reference_image": "REFB64"}
            ),
        ),
    )
    for key, value in overrides.items():
        setattr(stub, key, value)
    stub.ref_image_supported = types.MethodType(
        cn_mod.ControlNetUnit.ref_image_supported, stub
    )
    return stub


class TestIpAdapterReferencePayload:
    def test_reference_b64_lands_in_unit_image_key(self):
        unit = _unit_stub()
        data = cn_mod.ControlNetUnit.get_generation_data(unit)
        assert data["image"] == "REFB64"
        unit.ref_in.get_generation_data.assert_called_once_with()

    def test_reference_payload_keeps_unit_fields(self):
        unit = _unit_stub()
        data = cn_mod.ControlNetUnit.get_generation_data(unit)
        assert data["enabled"] is True
        assert data["module"] == "ip-adapter_clip_sd15"
        assert data["model"] == "ip-adapter_sd15"
        assert data["control_mode"] == "Balanced"
        assert data["pixel_perfect"] is False

    def test_gate_false_reference_ignored(self):
        unit = _unit_stub(cnapi=SimpleNamespace(ip_adapter=False))
        data = cn_mod.ControlNetUnit.get_generation_data(unit)
        assert data["image"] == {"image": "CTRLB64"}
        unit.ref_in.get_generation_data.assert_not_called()

    def test_reference_not_captured_falls_back(self):
        unit = _unit_stub(
            ref_in=SimpleNamespace(
                image=None, get_generation_data=MagicMock()
            )
        )
        data = cn_mod.ControlNetUnit.get_generation_data(unit)
        assert data["image"] == {"image": "CTRLB64"}
        unit.ref_in.get_generation_data.assert_not_called()

    @pytest.mark.parametrize("bad_ref", [
        None,
        "junk",
        42,
        [],
        {},
        {"reference_image": None},
        {"reference_image": ""},
        {"reference_image": 42},
    ])
    def test_bad_reference_payload_falls_back(self, bad_ref):
        unit = _unit_stub(
            ref_in=SimpleNamespace(
                image=object(),
                get_generation_data=MagicMock(return_value=bad_ref),
            )
        )
        data = cn_mod.ControlNetUnit.get_generation_data(unit)
        assert data["image"] == {"image": "CTRLB64"}

    def test_mask_path_unchanged_without_reference(self):
        unit = _unit_stub(
            use_mask=SimpleNamespace(isChecked=MagicMock(return_value=True)),
            cnapi=SimpleNamespace(ip_adapter=False),
        )
        data = cn_mod.ControlNetUnit.get_generation_data(unit)
        assert data["image"] == {"image": "MASKB64", "mask": "MASKMASK"}

    def test_reference_overrides_mask_path_when_active(self):
        unit = _unit_stub(
            use_mask=SimpleNamespace(isChecked=MagicMock(return_value=True)),
        )
        data = cn_mod.ControlNetUnit.get_generation_data(unit)
        assert data["image"] == "REFB64"

    def test_disabled_unit_returns_empty(self):
        unit = _unit_stub(enabled=False)
        assert cn_mod.ControlNetUnit.get_generation_data(unit) == {}
