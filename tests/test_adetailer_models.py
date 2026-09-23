"""Todo 16 (Medium #10): ADetailer model list fetched from API.

Getter layer: forge.adapters.sd_api.SDAPI.get_adetailer_models (60s TTL
cached, primary /adetailer/v1/models with /sdapi/v1/script-info fallback,
[] when script absent or backend unreachable).
Widget layer: forge.extension_widgets.adetailer populates its model
combobox from the getter (no hardcoded names asserted anywhere).
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import types
import urllib.error
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from forge.adapters.sd_api import BackendType, ConnectionState, SDAPI


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
    api.models = []
    api.vaes = []
    api.samplers = []
    api.upscalers = []
    api.facerestorers = []
    api.styles = []
    api.scripts = {"txt2img": ["adetailer"]}
    api.loras = []
    api.embeddings = {}
    api.hypernetworks = []
    api.additional_modules = []
    api.adetailer_models = []
    api.default_settings = {}
    api.defaults = {
        "sampler": "", "model": "", "vae": "",
        "upscaler": "", "refiner": "", "face_restorer": "",
        "color_correction": True,
    }
    api._cache = {}
    api._cache_ttl = 60.0
    return api


DYN_MODELS = ["dyn_face_a.pt", "dyn_hand_b.pt", "dyn_person_c-seg.pt"]


class TestGetAdetailerModels:
    def test_primary_endpoint_populates(self):
        api = _blank_api()
        with patch("forge.adapters.sd_api.urllib.request.urlopen") as m:
            m.return_value = _urlopen_json(DYN_MODELS)
            assert api.get_adetailer_models() == DYN_MODELS
        assert api.adetailer_models == DYN_MODELS

    def test_script_absent_returns_empty_without_network(self):
        api = _blank_api()
        api.scripts = {}
        with patch("forge.adapters.sd_api.urllib.request.urlopen") as m:
            assert api.get_adetailer_models() == []
            m.assert_not_called()

    def test_urlopen_raises_returns_empty(self):
        api = _blank_api()
        with patch("forge.adapters.sd_api.urllib.request.urlopen") as m:
            m.side_effect = urllib.error.URLError("down")
            with patch("forge.adapters.sd_api.time.sleep"):
                assert api.get_adetailer_models() == []

    def test_nondict_response_returns_empty(self):
        api = _blank_api()
        with patch("forge.adapters.sd_api.urllib.request.urlopen") as m:
            m.return_value = _urlopen_json("junk")
            assert api.get_adetailer_models() == []

    def test_script_info_fallback(self):
        api = _blank_api()
        with patch("forge.adapters.sd_api.urllib.request.urlopen") as m:
            m.side_effect = [_urlopen_json([]), _urlopen_json(DYN_MODELS)]
            assert api.get_adetailer_models() == DYN_MODELS

    def test_cached_within_ttl(self):
        api = _blank_api()
        with patch("forge.adapters.sd_api.urllib.request.urlopen") as m:
            m.return_value = _urlopen_json(DYN_MODELS)
            assert api.get_adetailer_models() == DYN_MODELS
            assert api.get_adetailer_models() == DYN_MODELS
            assert m.call_count == 1

    def test_cache_ttl_value(self):
        assert _blank_api()._cache_ttl == 60.0


def _load_adetailer_real():
    """Import adetailer.py fresh with recording stub-Qt; return module."""
    recorded = {}

    class _Layout:
        def __init__(self, *a, **k):
            self.widgets = []

        def setContentsMargins(self, *a):
            pass

        def addWidget(self, w):
            self.widgets.append(w)

    class _Widget:
        def __init__(self, *a, **k):
            self._layout = None

        def setLayout(self, layout):
            self._layout = layout

        def layout(self):
            return self._layout

    class _Label(_Widget):
        def __init__(self, text="", *a, **k):
            super().__init__()
            self.text = text

    class _Signal:
        def connect(self, *a, **k):
            pass

    class _Check(_Widget):
        def __init__(self, *a, **k):
            super().__init__()
            self.stateChanged = _Signal()

        def isChecked(self):
            return False

    class _Combo(_Widget):
        def __init__(self, *a, **k):
            super().__init__()
            self.items = []
            self.current = ""

        def addItems(self, items):
            self.items.extend(items)

        def addItem(self, item):
            self.items.append(item)

        def setCurrentText(self, text):
            self.current = text

        def currentText(self):
            return self.current

        def setMaxVisibleItems(self, *a):
            pass

        def setMinimumContentsLength(self, *a):
            pass

    stub = types.ModuleType("forge.qt_compat")
    for _name, _cls in (
        ("QWidget", _Widget), ("QVBoxLayout", _Layout),
        ("QLabel", _Label), ("QCheckBox", _Check),
        ("QComboBox", _Combo),
    ):
        setattr(stub, _name, _cls)
    stub.__all__ = ["QWidget", "QVBoxLayout", "QLabel", "QCheckBox", "QComboBox"]

    def __getattr__(name):
        if name.startswith("__"):
            raise AttributeError(name)

        class _Any(_Widget):
            def __init__(self, *a, **k):
                super().__init__()

            def __getattr__(self, attr):
                if attr.startswith("__"):
                    raise AttributeError(attr)
                return MagicMock()

        _Any.__name__ = name
        setattr(stub, name, _Any)
        return _Any

    stub.__getattr__ = __getattr__

    widgets_stub = types.ModuleType("forge.widgets")

    class _PromptStub(_Widget):
        def __init__(self, *a, **k):
            super().__init__()

        def get_generation_data(self):
            return {"prompt": "", "negative_prompt": ""}

        def save_prompt(self):
            pass

    widgets_stub.PromptWidget = _PromptStub
    widgets_stub.CollapsibleWidget = _Widget

    pre_keys = set(sys.modules)
    old_qt = sys.modules.get("forge.qt_compat")
    old_widgets = sys.modules.get("forge.widgets")
    sys.modules["forge.qt_compat"] = stub
    sys.modules["forge.widgets"] = widgets_stub
    try:
        path = (
            pathlib.Path(__file__).resolve().parent.parent
            / "forge" / "extension_widgets" / "adetailer.py"
        )
        mod_name = "forge.extension_widgets.adetailer_task16"
        spec = importlib.util.spec_from_file_location(mod_name, str(path))
        mod = importlib.util.module_from_spec(spec)
        mod.__package__ = "forge.extension_widgets"
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        recorded["combo"] = _Combo
        return mod
    finally:
        if old_qt is not None:
            sys.modules["forge.qt_compat"] = old_qt
        else:
            sys.modules.pop("forge.qt_compat", None)
        if old_widgets is not None:
            sys.modules["forge.widgets"] = old_widgets
        else:
            sys.modules.pop("forge.widgets", None)
        for _key in [k for k in sys.modules if k not in pre_keys
                     and k != "forge.extension_widgets.adetailer_task16"]:
            sys.modules.pop(_key, None)


ad_mod = _load_adetailer_real()


def _widget_api(models, installed=True):
    return SimpleNamespace(
        host="http://127.0.0.1:7860",
        script_installed=MagicMock(return_value=installed),
        get_adetailer_models=MagicMock(return_value=models),
    )


class TestAdetailerWidget:
    def test_really_real_classes(self):
        assert isinstance(ad_mod.ADetailerExtension, type)

    def test_widget_populates_from_api_response(self):
        api = _widget_api(list(DYN_MODELS))
        widget = ad_mod.ADetailerExtension.__new__(ad_mod.ADetailerExtension)
        ad_mod.ADetailerExtension.__init__(widget, MagicMock(), api)
        assert widget.model_select.items == DYN_MODELS
        assert widget.model_select.currentText() == DYN_MODELS[0]
        api.get_adetailer_models.assert_called_once_with()

    def test_widget_empty_response_survives(self):
        api = _widget_api([])
        widget = ad_mod.ADetailerExtension.__new__(ad_mod.ADetailerExtension)
        ad_mod.ADetailerExtension.__init__(widget, MagicMock(), api)
        assert widget.model_select.items == ["None"]

    def test_widget_getter_raises_survives(self):
        api = _widget_api(None)
        api.get_adetailer_models = MagicMock(side_effect=RuntimeError("boom"))
        widget = ad_mod.ADetailerExtension.__new__(ad_mod.ADetailerExtension)
        ad_mod.ADetailerExtension.__init__(widget, MagicMock(), api)
        assert widget.model_select.items == ["None"]

    def test_widget_script_absent_no_crash(self):
        api = _widget_api([], installed=False)
        widget = ad_mod.ADetailerExtension.__new__(ad_mod.ADetailerExtension)
        ad_mod.ADetailerExtension.__init__(widget, MagicMock(), api)
        assert not hasattr(widget, "model_select")
        api.get_adetailer_models.assert_not_called()

    def test_no_hardcoded_model_names_in_source(self):
        path = (
            pathlib.Path(__file__).resolve().parent.parent
            / "forge" / "extension_widgets" / "adetailer.py"
        )
        source = path.read_text(encoding="utf-8")
        for stale in ("face_yolov8n.pt", "mediapipe_face_full"):
            assert stale not in source
