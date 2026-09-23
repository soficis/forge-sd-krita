"""Todo 28: Smart Resolution suggestion helper.

Pure-function tests for forge.domain.smart_resolution.suggest_resolution
plus a widget smoke test for the shared SmartSizeWidget row.

The pure function is Qt-free; domain tests import it directly (conftest
mocks krita/Qt). The widget test loads forge/widgets/smart_size.py fresh
under stub-Qt real classes (pattern: tests/test_controlnet_dict_guards.py)
because subclassing the conftest MagicMock Qt does NOT work.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types

import pytest

from forge.domain.model_registry import ModelFamily, get_model_config
from forge.domain.smart_resolution import (
    FAMILY_STEPS,
    family_step,
    suggest_resolution,
)


def _aspect(w: int, h: int) -> float:
    return w / h


def _aspect_error(w: int, h: int, aspect: float) -> float:
    return abs((w / h) - aspect) / aspect


# ---------------------------------------------------------------------------
# Pure function: contract
# ---------------------------------------------------------------------------


class TestSuggestResolutionContract:
    def test_sd_square_512_budget_returns_512x512(self):
        assert suggest_resolution(ModelFamily.SD, 1.0, 512, 512) == (512, 512)

    def test_accepts_family_name_string(self):
        assert suggest_resolution("sd", 1.0, 512, 512) == (512, 512)

    def test_no_qt_import(self):
        import forge.domain.smart_resolution as mod

        source = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
        assert "qt_compat" not in source
        assert "PyQt" not in source
        assert "krita_adapter" not in source
        assert "QWidget" not in source

    @pytest.mark.parametrize("bad_aspect", [0, -1.0, float("nan"), float("inf")])
    def test_bad_aspect_raises(self, bad_aspect):
        with pytest.raises(ValueError):
            suggest_resolution(ModelFamily.SD, bad_aspect, 512, 512)

    @pytest.mark.parametrize("w,h", [(0, 512), (512, 0), (-4, 512), (512, -4)])
    def test_bad_current_size_raises(self, w, h):
        with pytest.raises(ValueError):
            suggest_resolution(ModelFamily.SD, 1.0, w, h)

    def test_unknown_family_raises(self):
        with pytest.raises(ValueError):
            suggest_resolution("nope-not-a-family", 1.0, 512, 512)


# ---------------------------------------------------------------------------
# Pure function: parametrized families/aspects
# ---------------------------------------------------------------------------


_FAMILIES = list(ModelFamily)
_ASPECTS = [1.0, 16 / 9, 9 / 16, 4 / 3, 3 / 2, 2.0]


class TestSuggestResolutionFamilies:
    @pytest.mark.parametrize("family", _FAMILIES)
    @pytest.mark.parametrize("aspect", _ASPECTS)
    def test_in_bounds_and_step_aligned(self, family, aspect):
        cfg = get_model_config(family)
        w, h = suggest_resolution(family, aspect, 1024, 768)
        assert cfg.min_size <= w <= cfg.default_max_size, (family, w, h)
        assert cfg.min_size <= h <= cfg.default_max_size, (family, w, h)
        step = family_step(family)
        assert w % step == 0, (family, w, h)
        assert h % step == 0, (family, w, h)

    @pytest.mark.parametrize("family", _FAMILIES)
    @pytest.mark.parametrize("aspect", _ASPECTS)
    def test_aspect_error_under_one_percent(self, family, aspect):
        w, h = suggest_resolution(family, aspect, 1024, 768)
        assert _aspect_error(w, h, aspect) < 0.01, (family, w, h, aspect)

    def test_family_steps_are_8_or_16(self):
        assert set(FAMILY_STEPS.values()) <= {8, 16}
        for family in ModelFamily:
            assert family_step(family) in (8, 16)

    def test_extreme_aspect_clamps_in_bounds(self):
        for family in ModelFamily:
            cfg = get_model_config(family)
            step = family_step(family)
            w, h = suggest_resolution(family, 100.0, 512, 512)
            assert cfg.min_size <= w <= cfg.default_max_size, (family, w, h)
            assert cfg.min_size <= h <= cfg.default_max_size, (family, w, h)
            assert w % step == 0 and h % step == 0, (family, w, h)

    def test_extreme_portrait_aspect_clamps_in_bounds(self):
        for family in ModelFamily:
            cfg = get_model_config(family)
            step = family_step(family)
            w, h = suggest_resolution(family, 0.01, 512, 512)
            assert cfg.min_size <= w <= cfg.default_max_size, (family, w, h)
            assert cfg.min_size <= h <= cfg.default_max_size, (family, w, h)
            assert w % step == 0 and h % step == 0, (family, w, h)

    def test_budget_scales_up_with_current(self):
        small = suggest_resolution(ModelFamily.SDXL, 1.0, 512, 512)
        large = suggest_resolution(ModelFamily.SDXL, 1.0, 1024, 1024)
        assert small == (512, 512)
        assert large == (1024, 1024)

    def test_never_exceeds_family_max(self):
        w, h = suggest_resolution(ModelFamily.WAN, 1.0, 4096, 4096)
        assert w <= 1024 and h <= 1024

    def test_tuple_aspect(self):
        w, h = suggest_resolution(ModelFamily.SD, (16, 9), 1024, 768)
        assert _aspect_error(w, h, 16 / 9) < 0.01


# ---------------------------------------------------------------------------
# Widget smoke test (stub-Qt real classes)
# ---------------------------------------------------------------------------

_QT_NAMES = [
    "Qt", "QWidget", "QVBoxLayout", "QHBoxLayout", "QFormLayout",
    "QLabel", "QComboBox", "QPushButton", "QCheckBox", "QTabWidget",
    "QGroupBox", "QSlider", "QSpinBox", "QDoubleSpinBox", "QPlainTextEdit",
    "QScrollArea", "QColor", "QPainter", "QByteArray", "QBuffer", "QImage",
    "QIODevice", "QObject", "QThread", "QTimer", "pyqtSignal", "QSize",
    "QIcon", "QPixmap", "QPointF", "QLineEdit", "QTextEdit", "qAlpha", "qRgb",
]


def _load_smart_size_real():
    """Import smart_size.py fresh with stub-Qt classes; return the module."""
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
            / "forge" / "widgets" / "smart_size.py"
        )
        mod_name = "forge.widgets.smart_size_task28"
        spec = importlib.util.spec_from_file_location(mod_name, str(path))
        mod = importlib.util.module_from_spec(spec)
        mod.__package__ = "forge.widgets"
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        if old is not None:
            sys.modules["forge.qt_compat"] = old
        else:
            sys.modules.pop("forge.qt_compat", None)
        for _key in [k for k in sys.modules if k not in pre_keys
                     and k != "forge.widgets.smart_size_task28"]:
            sys.modules.pop(_key, None)


def _stub_controller_and_api():
    from unittest.mock import MagicMock

    controller = MagicMock()
    controller.get = MagicMock(return_value=None)
    api = MagicMock()
    api.defaults = {"model": "sd-v1-5"}
    return controller, api


class TestSmartSizeWidget:
    def test_really_real_classes(self):
        mod = _load_smart_size_real()
        assert isinstance(mod.SmartSizeWidget, type)

    def test_button_applies_suggestion_to_size_dict(self):
        mod = _load_smart_size_real()
        controller, api = _stub_controller_and_api()
        size_dict = {"x": 0, "y": 0, "w": 512, "h": 512}
        widget = mod.SmartSizeWidget(controller, api, size_dict)
        widget.apply_smart_size()
        assert (size_dict["w"], size_dict["h"]) == (512, 512)

    def test_does_not_touch_size_dict_until_pressed(self):
        mod = _load_smart_size_real()
        controller, api = _stub_controller_and_api()
        size_dict = {"x": 0, "y": 0, "w": 300, "h": 200}
        mod.SmartSizeWidget(controller, api, size_dict)
        assert (size_dict["w"], size_dict["h"]) == (300, 200)

    def test_get_generation_data_returns_empty_dict(self):
        mod = _load_smart_size_real()
        controller, api = _stub_controller_and_api()
        widget = mod.SmartSizeWidget(controller, api, {"x": 0, "y": 0, "w": 1, "h": 1})
        assert widget.get_generation_data() == {}
