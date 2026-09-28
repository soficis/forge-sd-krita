"""Denoise-strength guard for distilled/turbo checkpoints.

Real user report: inpaint with `krea2_turbo_fp8_scaled.safetensors` at 70%
denoise / 8 steps returned a melted image with no error — a distilled model
cannot rebuild structure once img2img/inpaint has discarded most of the
latent.

Covers:
- model_registry.max_denoise_for_model: 0.5 ceiling for distilled names,
  1.0 (unchanged behaviour) for regular checkpoints, defensive on bad input
- DenoiseWidget.update_for_model: slider max, clamped value + label sync,
  tooltip only while capped, idempotent, switch-back regression, user can
  still drag below the cap
- get_generation_data stays slider-derived and within 0..1
- page wiring: img2img/inpaint register the widget on model change

denoise.py is loaded FRESH under stub-Qt classes with real slider/label
semantics (pattern from tests/test_flux_ui.py): subclassing conftest's
MagicMock Qt classes yields mocks, not classes.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

from forge.domain import model_registry


# ---------------------------------------------------------------------------
# Behaviour-recording stub Qt (real classes, not mocks)
# ---------------------------------------------------------------------------

class _Signal:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def emit(self):
        for slot in list(self._slots):
            slot()


class _FakeSlider:
    """Qt clamping semantics: setMaximum clamps the value and notifies."""

    TickPosition = SimpleNamespace(TicksAbove="above")

    def __init__(self, *args, **kwargs):
        self._min = 0
        self._max = 99
        self._value = 0
        self._tooltip = ""
        self.valueChanged = _Signal()

    def setMinimum(self, value):
        self._min = value

    def setMaximum(self, value):
        self._max = value
        if self._value > value:
            self._value = value
            self.valueChanged.emit()

    def setValue(self, value):
        clamped = max(self._min, min(self._max, int(value)))
        if clamped != self._value:
            self._value = clamped
            self.valueChanged.emit()

    def value(self):
        return self._value

    def maximum(self):
        return self._max

    def setTickInterval(self, interval):
        pass

    def setTickPosition(self, position):
        pass

    def setToolTip(self, text):
        self._tooltip = text

    def toolTip(self):
        return self._tooltip


class _FakeLabel:
    def __init__(self, text="", *args, **kwargs):
        self._text = text
        self._tooltip = ""

    def setText(self, text):
        self._text = text

    def text(self):
        return self._text

    def setToolTip(self, text):
        self._tooltip = text

    def toolTip(self):
        return self._tooltip


class _FakeLayout:
    def __init__(self, *args, **kwargs):
        self._widgets = []

    def setContentsMargins(self, *args):
        pass

    def addWidget(self, widget):
        self._widgets.append(widget)


class _FakeWidget:
    def __init__(self, *args, **kwargs):
        self._layout = None
        self._tooltip = ""

    def setLayout(self, layout):
        self._layout = layout

    def layout(self):
        return self._layout

    def setToolTip(self, text):
        self._tooltip = text

    def toolTip(self):
        return self._tooltip


class _Meta(type):
    def __getattr__(cls, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return MagicMock(name="%s.%s" % (cls.__name__, name))


_QT_NAMES = ["Qt", "QWidget", "QVBoxLayout", "QHBoxLayout", "QLabel", "QSlider"]


def _load_denoise_real():
    """Import denoise.py fresh with stub-Qt classes; return the module."""
    class _StubBase(metaclass=_Meta):
        def __init__(self, *args, **kwargs):
            pass

        def __getattr__(self, name):
            if name.startswith("__"):
                raise AttributeError(name)
            return MagicMock(name=name)

    stub = types.ModuleType("forge.qt_compat")
    for _name in _QT_NAMES:
        setattr(stub, _name, _Meta(_name, (_StubBase,), {}))
    stub.QWidget = _FakeWidget
    stub.QVBoxLayout = _FakeLayout
    stub.QHBoxLayout = _FakeLayout
    stub.QLabel = _FakeLabel
    stub.QSlider = _FakeSlider
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
            / "forge" / "widgets" / "denoise.py"
        )
        mod_name = "forge.widgets.denoise_turbo_guard"
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
                     and k != "forge.widgets.denoise_turbo_guard"]:
            sys.modules.pop(_key, None)


denoise_mod = _load_denoise_real()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TURBO_NAME = "krea2_turbo_fp8_scaled.safetensors"
NORMAL_NAMES = [
    "krea2_raw_fp8_scaled.safetensors",  # same family, non-turbo sibling
    "qwen-image-20b-fp8.safetensors",
    "sdxl_base_1.0.safetensors",
    "flux1-dev_fp8.safetensors",
    "v1-5-pruned-emaonly.safetensors",
]


def _settings(default_denoise=0.7):
    values = {"defaults.denoise_strength": default_denoise}
    return SimpleNamespace(
        get=lambda key, default=None: values.get(key, default),
        set=MagicMock(),
        save=MagicMock(),
        debounced_save=MagicMock(),
    )


def _widget(default_denoise=0.7):
    return denoise_mod.DenoiseWidget(_settings(default_denoise))


# ---------------------------------------------------------------------------
# 1-3. Registry predicate
# ---------------------------------------------------------------------------

class TestMaxDenoiseForModel:
    def test_turbo_checkpoint_returns_capped_ceiling(self):
        assert model_registry.max_denoise_for_model(TURBO_NAME) == 0.5

    def test_turbo_detection_is_case_insensitive(self):
        assert model_registry.max_denoise_for_model("KREA2_Turbo.SAFETENSORS") == 0.5

    def test_non_turbo_siblings_return_no_cap(self):
        for name in NORMAL_NAMES:
            assert model_registry.max_denoise_for_model(name) == 1.0, name

    def test_zimage_and_flux2_klein_families_are_capped(self):
        assert model_registry.max_denoise_for_model("z-image-turbo.safetensors") == 0.5
        assert model_registry.max_denoise_for_model("flux2-klein-4b.safetensors") == 0.5

    def test_bad_input_returns_no_cap_without_raising(self):
        for bad in (None, 123, b"x", "", object()):
            assert model_registry.max_denoise_for_model(bad) == 1.0, repr(bad)


# ---------------------------------------------------------------------------
# 4-6. Widget cap behaviour
# ---------------------------------------------------------------------------

class TestDenoiseWidgetCap:
    def test_turbo_caps_slider_and_clamps_over_cap_value(self):
        widget = _widget(default_denoise=0.7)  # the reported 70% case
        widget.update_for_model(TURBO_NAME)
        assert widget.denoise_slider.maximum() == 50
        assert widget.denoise_slider.value() == 50
        assert widget.denoise_percent.text() == "50%"

    def test_cap_explains_why_via_tooltip(self):
        widget = _widget()
        widget.update_for_model(TURBO_NAME)
        assert widget.denoise_slider.toolTip() != ""
        assert "50" in widget.denoise_slider.toolTip()

    def test_user_can_still_drag_below_cap(self):
        widget = _widget()
        widget.update_for_model(TURBO_NAME)
        widget.denoise_slider.setValue(30)
        assert widget.denoise_slider.value() == 30
        assert widget.denoise_percent.text() == "30%"

    def test_normal_model_restores_maximum_and_clears_tooltip(self):
        widget = _widget()
        widget.update_for_model(TURBO_NAME)
        widget.update_for_model("sdxl_base_1.0.safetensors")
        assert widget.denoise_slider.maximum() == 100
        assert widget.denoise_slider.toolTip() == ""

    def test_repeated_calls_are_idempotent(self):
        widget = _widget(default_denoise=0.7)
        widget.update_for_model(TURBO_NAME)
        first = (widget.denoise_slider.maximum(), widget.denoise_slider.value(),
                 widget.denoise_percent.text(), widget.denoise_slider.toolTip())
        widget.update_for_model(TURBO_NAME)
        second = (widget.denoise_slider.maximum(), widget.denoise_slider.value(),
                  widget.denoise_percent.text(), widget.denoise_slider.toolTip())
        assert first == second
        # ...and a cap -> normal -> cap round trip stays correct.
        widget.update_for_model("qwen-image-20b-fp8.safetensors")
        widget.update_for_model(TURBO_NAME)
        assert widget.denoise_slider.maximum() == 50
        assert widget.denoise_percent.text() == "50%"


# ---------------------------------------------------------------------------
# 7. Generation-data regression
# ---------------------------------------------------------------------------

class TestGenerationDataRegression:
    def test_denoising_strength_tracks_slider_within_bounds(self):
        widget = _widget(default_denoise=0.7)
        widget.update_for_model(TURBO_NAME)
        data = widget.get_generation_data()
        assert data["denoising_strength"] == widget.denoise_slider.value() / 100
        assert 0.0 <= data["denoising_strength"] <= 1.0
        assert data["denoising_strength"] == 0.5

    def test_uncapped_generation_data_unchanged(self):
        widget = _widget(default_denoise=0.7)
        data = widget.get_generation_data()
        assert data["denoising_strength"] == 0.7


# ---------------------------------------------------------------------------
# Page wiring: model-change propagation reaches the denoise widget
# ---------------------------------------------------------------------------

class TestPageWiring:
    def test_img2img_and_inpaint_register_denoise_widget(self):
        root = pathlib.Path(__file__).resolve().parent.parent
        for page in ("img2img", "inpaint"):
            source = (root / "forge" / "pages" / ("%s.py" % page)).read_text(
                encoding="utf-8"
            )
            assert (
                "register_model_changed_signal(self.denoise_widget.update_for_model)"
                in source
            ), page
