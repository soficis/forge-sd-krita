"""Todo 9 (Critical #2): dual-layer non-dict guards.

Widget layer: forge.extension_widgets.controlnet (ControlNetAPI fetchers,
update_model_options, set_preprocessor_settings, gen_preview).
Adapter layer: forge.adapters.sd_api response-parse / payload-build paths.

All tests feed non-dict inputs (None, list, str, int) and assert no
exception escapes plus a graceful error state is surfaced (empty
list/dict, None result, tabs fallback, rows hidden).
"""

from __future__ import annotations

import importlib.util
import io
import json
import pathlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from forge.adapters.sd_api import BackendType, ConnectionState, SDAPI


# ---------------------------------------------------------------------------
# Real-Qt-stub loader for the widget layer
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
    from unittest.mock import MagicMock

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
        mod_name = "forge.extension_widgets.controlnet_task9"
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
                     and k != "forge.extension_widgets.controlnet_task9"]:
            sys.modules.pop(_key, None)


cn_mod = _load_controlnet_real()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_body(data) -> bytes:
    return json.dumps(data).encode()


def _urlopen_json(data) -> MagicMock:
    response = MagicMock()
    response.read.return_value = _json_body(data)
    response.status = 200
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    return response


def _blank_api() -> SDAPI:
    api = SDAPI.__new__(SDAPI)
    api.timeout_seconds = 30.0
    api.max_retries = 0
    api.status_connect_timeout = 3.05
    api.status_read_timeout = 10.0
    api.gen_connect_timeout = 5.05
    api.gen_read_timeout = 600.0
    api.host = "http://127.0.0.1:7860"
    api.state = ConnectionState.CONNECTED
    api.connected = True
    api.backend_type = BackendType.UNKNOWN
    api.last_url = ""
    api.last_error = None
    api.last_error_message = ""
    api._in_flight = 0
    api.models = []
    api.vaes = []
    api.samplers = []
    api.upscalers = []
    api.facerestorers = []
    api.styles = []
    api.scripts = {}
    api.loras = []
    api.embeddings = {}
    api.hypernetworks = []
    api.additional_modules = []
    api.default_settings = {}
    api.defaults = {
        "sampler": "", "model": "", "vae": "",
        "upscaler": "", "refiner": "", "face_restorer": "",
        "color_correction": True,
    }
    api._cache = {}
    api._cache_ttl = 60.0
    return api


def _cn_api_for(payload) -> cn_mod.ControlNetAPI:
    """ControlNetAPI instance whose backend always returns `payload`."""
    inst = cn_mod.ControlNetAPI.__new__(cn_mod.ControlNetAPI)
    inst.api = SimpleNamespace(get=MagicMock(return_value=payload))
    inst.kc = MagicMock()
    inst.models = []
    inst.module_list = []
    inst.module_details = {}
    inst.control_types = {}
    inst.settings = {}
    inst.tabs = 0
    return inst


NON_DICTS = [None, [], "err", 42]


# ---------------------------------------------------------------------------
# sd_api layer
# ---------------------------------------------------------------------------

class TestSdApiDictGuards:
    @pytest.mark.parametrize("bad", NON_DICTS)
    def test_normalize_generation_results_nondict_returns_none(self, bad):
        api = _blank_api()
        assert api._normalize_generation_results({}, bad) is None

    @pytest.mark.parametrize("bad", NON_DICTS)
    def test_get_options_nondict_response_returns_empty(self, bad):
        api = _blank_api()
        with patch("forge.adapters.sd_api.urllib.request.urlopen") as m:
            m.return_value = _urlopen_json(bad)
            assert api.get_options() == {}
        assert api.backend_type == BackendType.UNKNOWN

    @pytest.mark.parametrize("bad", NON_DICTS)
    def test_list_getters_nondict_response_return_empty(self, bad):
        api = _blank_api()
        with patch("forge.adapters.sd_api.urllib.request.urlopen") as m:
            m.return_value = _urlopen_json(bad)
            assert api.get_models() == []
            api._cache.clear()
            m.return_value = _urlopen_json(bad)
            assert api.get_samplers() == []

    def test_get_style_prompts_skips_nondict_entries(self):
        api = _blank_api()
        api.styles = ["junk", None, 42, {"name": "s1", "prompt": "p1",
                                         "negative_prompt": "n1"}]
        assert api.get_style_prompts(["s1"]) == ("p1", "n1")

    @pytest.mark.parametrize("bad", NON_DICTS)
    def test_get_embedding_names_nondict_returns_empty(self, bad):
        api = _blank_api()
        api.embeddings = bad
        assert api.get_embedding_names() == []

    def test_script_installed_skips_nondict_items(self):
        api = _blank_api()
        api.scripts = {"txt2img": ["controlnet", None, 42]}
        assert api.script_installed("controlnet") is True
        assert api.script_installed("missing") is False

    @pytest.mark.parametrize("bad", NON_DICTS)
    def test_build_payload_nondict_returns_dict(self, bad):
        api = _blank_api()
        assert isinstance(api.build_payload(bad), dict)

    @pytest.mark.parametrize("bad", NON_DICTS)
    def test_generation_entrypoints_refuse_nondict_without_request(self, bad):
        api = _blank_api()
        with patch("forge.adapters.sd_api.urllib.request.urlopen") as m:
            assert api.txt2img(bad) is None
            assert api.img2img(bad) is None
            assert api.extra(bad) is None
            assert api.interrogate(bad) is None
            assert api.tiled_generate(bad) is None
            m.assert_not_called()

    @pytest.mark.parametrize("bad", NON_DICTS)
    def test_txt2img_nondict_response_returns_none(self, bad):
        api = _blank_api()
        with patch("forge.adapters.sd_api.urllib.request.urlopen") as m:
            m.return_value = _urlopen_json(bad)
            with patch.object(SDAPI, "log_request_and_response"):
                assert api.txt2img({}) is None


# ---------------------------------------------------------------------------
# ControlNetAPI fetch layer
# ---------------------------------------------------------------------------

class TestControlNetDictApi:
    def test_really_real_classes(self):
        assert isinstance(cn_mod.ControlNetAPI, type)
        assert isinstance(cn_mod.ControlNetUnit, type)

    @pytest.mark.parametrize("bad", NON_DICTS)
    def test_get_models_nondict(self, bad):
        inst = _cn_api_for(bad)
        inst.get_models()
        assert inst.models == []

    def test_get_models_nondict_model_list_value(self):
        inst = _cn_api_for({"model_list": "junk"})
        inst.get_models()
        assert inst.models == []

    @pytest.mark.parametrize("bad", NON_DICTS)
    def test_get_modules_nondict(self, bad):
        inst = _cn_api_for(bad)
        inst.get_modules()
        assert inst.module_list == []
        assert inst.module_details == {}

    def test_get_modules_nondict_inner_values(self):
        inst = _cn_api_for({"module_list": "junk", "module_detail": ["x"]})
        inst.get_modules()
        assert inst.module_list == []
        assert inst.module_details == {}

    @pytest.mark.parametrize("bad", NON_DICTS)
    def test_get_control_types_nondict_falls_back(self, bad):
        inst = _cn_api_for(bad)
        inst.get_control_types()
        assert isinstance(inst.control_types, dict) and inst.control_types

    def test_get_control_types_nondict_inner_value_falls_back(self):
        inst = _cn_api_for({"control_types": ["junk"]})
        inst.get_control_types()
        assert isinstance(inst.control_types, dict) and inst.control_types

    @pytest.mark.parametrize("bad", NON_DICTS)
    def test_get_settings_nondict_tabs_fallback(self, bad):
        inst = _cn_api_for(bad)
        inst.get_settings()
        assert inst.tabs == 1

    @pytest.mark.parametrize("bad", [None, "x", [3], {"control_net_unit_count": "3"}])
    def test_get_settings_bad_count_falls_back(self, bad):
        inst = _cn_api_for(bad)
        inst.get_settings()
        assert inst.tabs == 1

    @pytest.mark.parametrize("bad", NON_DICTS)
    def test_get_version_nondict_returns_default(self, bad):
        inst = _cn_api_for(bad)
        assert inst.get_version() == 3

    def test_accessors_unknown_type_return_empty(self):
        inst = _cn_api_for(None)
        inst.control_types = {"All": {"module_list": ["m"], "model_list": ["x"],
                                      "default_option": "none", "default_model": "None"}}
        assert inst.get_preprocessors_for_control_type("Nope") == []
        assert inst.get_models_for_control_type("Nope") == []
        assert list(inst.get_control_types_list()) == ["All"]

    def test_accessors_nondict_control_types(self):
        inst = _cn_api_for(None)
        inst.control_types = ["junk"]
        assert inst.get_preprocessors_for_control_type("All") == []
        assert inst.get_models_for_control_type("All") == []
        assert list(inst.get_control_types_list()) == []

    @pytest.mark.parametrize("bad", NON_DICTS)
    def test_preview_nondict_no_raise(self, bad):
        inst = _cn_api_for(None)
        inst.api = SimpleNamespace(
            post=MagicMock(return_value=bad),
            get=MagicMock(return_value=None),
        )
        assert inst.preview("img", "mod", 512, 1, 2) is bad


# ---------------------------------------------------------------------------
# Widget consumer layer (unbound methods over stub selves, no Qt needed)
# ---------------------------------------------------------------------------

def _unit_stub(**overrides):
    stub = SimpleNamespace(
        preprocessor_select=MagicMock(),
        model_select=MagicMock(),
        preprocessor_settings=MagicMock(),
        resolution_row=MagicMock(),
        threshold_a_row_int=MagicMock(),
        threshold_a_row_float=MagicMock(),
        threshold_b_row_int=MagicMock(),
        threshold_b_row_float=MagicMock(),
        settings_controller=SimpleNamespace(get=MagicMock(return_value=False)),
        cnapi=SimpleNamespace(control_types={}, module_details={}),
        preprocessor_list=[],
        model_list=[],
        update=MagicMock(),
        _update_row=MagicMock(),
    )
    for key, value in overrides.items():
        setattr(stub, key, value)
    return stub


class TestControlNetDictWidget:
    def test_update_model_options_unknown_type_no_raise(self):
        stub = _unit_stub()
        stub.cnapi = SimpleNamespace(control_types={"All": {
            "module_list": ["m"], "model_list": ["x"],
            "default_option": "none", "default_model": "None"}})
        cn_mod.ControlNetUnit.update_model_options(stub, "Nope")
        stub.preprocessor_select.setCurrentText.assert_not_called()

    def test_update_model_options_happy_path(self):
        stub = _unit_stub()
        stub.cnapi = SimpleNamespace(control_types={"All": {
            "module_list": ["m"], "model_list": ["x"],
            "default_option": "none", "default_model": "None"}})
        cn_mod.ControlNetUnit.update_model_options(stub, "All")
        assert stub.preprocessor_list == ["m"]
        assert stub.model_list == ["x"]

    @pytest.mark.parametrize("bad", NON_DICTS)
    def test_set_preprocessor_settings_nondict_details(self, bad):
        stub = _unit_stub()
        stub.cnapi = SimpleNamespace(module_details={"canny": bad})
        cn_mod.ControlNetUnit.set_preprocessor_settings(stub, "canny")
        stub._update_row.assert_not_called()

    @pytest.mark.parametrize("bad", [None, "x", 42, {"sliders": "junk"},
                                     {"sliders": ["junk", None, 42]},
                                     {"sliders": [{"name": "Preprocessor Resolution"}]},
                                     {"model_free": False, "sliders": [
                                         {"name": "Preprocessor Resolution", "min": "a",
                                          "max": 2048, "value": 512}]}])
    def test_set_preprocessor_settings_bad_sliders_no_raise(self, bad):
        details = bad if isinstance(bad, dict) else {"model_free": False, "sliders": bad}
        stub = _unit_stub()
        stub.cnapi = SimpleNamespace(module_details={"canny": details})
        cn_mod.ControlNetUnit.set_preprocessor_settings(stub, "canny")

    def test_set_preprocessor_settings_happy_path_updates_rows(self):
        stub = _unit_stub()
        stub.cnapi = SimpleNamespace(module_details={"canny": {
            "model_free": False,
            "sliders": [
                {"name": "Preprocessor Resolution", "min": 64, "max": 2048,
                 "value": 512, "step": 1},
                {"name": "Threshold A", "min": 0, "max": 100, "value": 50},
            ],
        }})
        cn_mod.ControlNetUnit.set_preprocessor_settings(stub, "canny")
        assert stub._update_row.call_count == 2

    @pytest.mark.parametrize("bad", NON_DICTS)
    def test_gen_preview_nondict_result_no_layers(self, bad):
        stub = SimpleNamespace(
            img_in=SimpleNamespace(
                get_generation_data=MagicMock(return_value={"input_image": "img"})),
            cnapi=SimpleNamespace(preview=MagicMock(return_value=bad)),
            variables={"preprocessor_resolution": 512, "threshold_a": 1,
                       "threshold_b": 2},
            size_dict={"x": 0, "y": 0, "w": 8, "h": 8},
            preprocessor="canny",
        )
        with patch.object(cn_mod, "KritaAdapter") as mock_kc:
            cn_mod.ControlNetUnit.gen_preview(stub)
            mock_kc.return_value.results_to_layers.assert_not_called()

    def test_slider_spec_helper(self):
        assert cn_mod._slider_spec(None) is None
        assert cn_mod._slider_spec([]) is None
        assert cn_mod._slider_spec({"name": "A"}) is None
        assert cn_mod._slider_spec({"name": "A", "min": 0, "max": 1,
                                    "value": 0}) is not None
