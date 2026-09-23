"""Regression tests for Critical #1: history reuse via ModelsWidget.set_generation_data.

Re-selecting a history entry must populate every attribute read by the
generate-flow ``get_generation_data()``, using copy-on-reuse semantics
(deep-copy so later mutation of the source entry cannot corrupt widget state).

The real ``forge/widgets/models.py`` file is loaded in isolation under a
private package with functional Qt stand-ins: the shared conftest Qt mock
cannot define real widget classes (subclassing a MagicMock yields a mock),
and this module must not alter shared mock state used by sibling suites.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

FORGE_DIR = Path(__file__).resolve().parent.parent / "forge"


class _Signal:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)
        return slot

    def emit(self, *args, **kwargs):
        for slot in list(self._slots):
            slot(*args, **kwargs)


class _AttrChain:
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _AttrChain()

    def __call__(self, *args, **kwargs):
        return _AttrChain()


class _Widget:
    def __init__(self, *args, **kwargs):
        self._layout = None
        self._tooltip = ""

    def setLayout(self, layout):
        self._layout = layout

    def layout(self):
        return self._layout

    def setToolTip(self, text):
        self._tooltip = text


class _Layout:
    def __init__(self, *args, **kwargs):
        self.rows = []
        self.widgets = []

    def setContentsMargins(self, *args):
        pass

    def addRow(self, *args):
        self.rows.append(args)

    def addWidget(self, widget):
        self.widgets.append(widget)

    def addLayout(self, layout):
        self.widgets.append(layout)


class _ComboBox(_Widget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._items = []
        self._current = ""
        self.currentTextChanged = _Signal()

    def addItems(self, items):
        for item in items:
            if item not in self._items:
                self._items.append(item)

    def addItem(self, item):
        self.addItems([item])

    def findText(self, text):
        try:
            return self._items.index(text)
        except ValueError:
            return -1

    def setCurrentIndex(self, index):
        if 0 <= index < len(self._items):
            self._current = self._items[index]

    def setCurrentText(self, text):
        if text in self._items:
            self._current = text

    def currentText(self):
        return self._current

    def setMinimumContentsLength(self, value):
        pass

    def setMaxVisibleItems(self, value):
        pass


class _CheckBox(_Widget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._checked = False
        self.stateChanged = _Signal()

    def setChecked(self, value):
        self._checked = bool(value)

    def isChecked(self):
        return self._checked


class _SpinBox(_Widget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._value = 0
        self.valueChanged = _Signal()

    def setMinimum(self, value):
        pass

    def setMaximum(self, value):
        pass

    def setValue(self, value):
        self._value = int(value)

    def value(self):
        return self._value


class _Slider(_SpinBox):
    TickPosition = _AttrChain()

    def setTickInterval(self, value):
        pass

    def setTickPosition(self, value):
        pass


class _Label(_Widget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.text = ""

    def setText(self, text):
        self.text = text


def _install_isolated_package():
    pkg = types.ModuleType("t8pkg")
    pkg.__path__ = []
    sys.modules["t8pkg"] = pkg

    widgets_pkg = types.ModuleType("t8pkg.widgets")
    widgets_pkg.__path__ = [str(FORGE_DIR / "widgets")]
    sys.modules["t8pkg.widgets"] = widgets_pkg

    adapters_pkg = types.ModuleType("t8pkg.adapters")
    adapters_pkg.__path__ = []
    sys.modules["t8pkg.adapters"] = adapters_pkg

    qt_mod = types.ModuleType("t8pkg.qt_compat")
    qt_names = {
        "Qt": _AttrChain(),
        "QWidget": _Widget,
        "QVBoxLayout": _Layout,
        "QHBoxLayout": _Layout,
        "QFormLayout": _Layout,
        "QLabel": _Label,
        "QComboBox": _ComboBox,
        "QCheckBox": _CheckBox,
        "QSpinBox": _SpinBox,
        "QSlider": _Slider,
    }
    for name, obj in qt_names.items():
        setattr(qt_mod, name, obj)
    qt_mod.__all__ = list(qt_names)
    sys.modules["t8pkg.qt_compat"] = qt_mod

    from forge.domain import model_registry as real_registry

    domain_pkg = types.ModuleType("t8pkg.domain")
    domain_pkg.__path__ = []
    sys.modules["t8pkg.domain"] = domain_pkg
    sys.modules["t8pkg.domain.model_registry"] = real_registry

    sd_api_mod = types.ModuleType("t8pkg.adapters.sd_api")

    class SDAPI:
        pass

    sd_api_mod.SDAPI = SDAPI

    # models.py imports ConnectionState for the dropdown loading probe.
    from forge.adapters.sd_api import ConnectionState as _ConnectionState

    sd_api_mod.ConnectionState = _ConnectionState
    sys.modules["t8pkg.adapters.sd_api"] = sd_api_mod

    settings_mod = types.ModuleType("t8pkg.settings_controller")

    class SettingsController:
        pass

    settings_mod.SettingsController = SettingsController
    sys.modules["t8pkg.settings_controller"] = settings_mod

    spec = importlib.util.spec_from_file_location(
        "t8pkg.widgets.models", str(FORGE_DIR / "widgets" / "models.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["t8pkg.widgets.models"] = module
    spec.loader.exec_module(module)
    return module


_models_module = _install_isolated_package()
ModelsWidget = _models_module.ModelsWidget


def _make_widget():
    settings = MagicMock()
    defaults = {
        "defaults.model": "",
        "defaults.vae": "",
        "defaults.refiner": "",
        "defaults.sampler": "",
        "defaults.sampling_steps": 20,
        "defaults.enable_refiner": False,
        "defaults.refiner_start": 0.8,
        "hide_ui.model": False,
        "hide_ui.vae": False,
        "hide_ui.refiner": False,
        "hide_ui.sampler": False,
    }
    settings.get.side_effect = lambda path, default=None: defaults.get(path, default)
    api = MagicMock()
    api.get_models_and_default.return_value = (
        ["old-model.safetensors", "reuse-model.safetensors"],
        "old-model.safetensors",
    )
    api.get_vaes_and_default.return_value = (
        ["old-vae.safetensors", "reuse-vae.safetensors"],
        "old-vae.safetensors",
    )
    api.get_refiners_and_default.return_value = (
        ["old-refiner.safetensors", "reuse-refiner.safetensors"],
        "old-refiner.safetensors",
    )
    api.get_samplers_and_default.return_value = (
        ["Old Sampler", "Reuse Sampler"],
        "Old Sampler",
    )
    widget = ModelsWidget(settings, api)
    widget.variables = {
        "model": "old-model.safetensors",
        "vae": "old-vae.safetensors",
        "enable_refiner": False,
        "refiner": "old-refiner.safetensors",
        "refiner_start": 0.8,
        "sampler": "Old Sampler",
        "sampling_steps": 10,
    }
    widget.model_box.setCurrentText("old-model.safetensors")
    widget.vae_box.setCurrentText("old-vae.safetensors")
    widget.refiner_box.setCurrentText("old-refiner.safetensors")
    widget.sampler_box.setCurrentText("Old Sampler")
    widget.sampling_steps.setValue(10)
    widget.refiner_enable.setChecked(False)
    widget.refiner_start_slider.setValue(80)
    return widget


def _history_entry():
    """Fake history entry shaped like HistoryManager.save_generation output."""
    return {
        "timestamp": 1234567890.0,
        "thumbnail": "/tmp/fake-thumb.png",
        "prompt": "a reusable sunset",
        "model": "reuse-model.safetensors",
        "vae": "reuse-vae.safetensors",
        "sampler": "Reuse Sampler",
        "sampling_steps": 32,
        "enable_refiner": True,
        "refiner": "reuse-refiner.safetensors",
        "refiner_start": 0.5,
        "seed": 42,
        "cfg_scale": 4.0,
    }


class TestHistoryReuse:
    """Re-selecting a history entry restores all generate-flow fields."""

    def test_set_generation_data_restores_all_generate_flow_fields(self):
        widget = _make_widget()
        entry = _history_entry()

        widget.set_generation_data(entry)
        data = widget.get_generation_data()

        assert data["model"] == entry["model"]
        assert data["vae"] == entry["vae"]
        assert data["sampler"] == entry["sampler"]
        assert data["sampling_steps"] == entry["sampling_steps"]
        assert data["refiner"] == entry["refiner"]
        assert data["refiner_start"] == entry["refiner_start"]
        assert widget.model_box.currentText() == entry["model"]
        assert widget.vae_box.currentText() == entry["vae"]
        assert widget.sampler_box.currentText() == entry["sampler"]
        assert widget.sampling_steps.value() == entry["sampling_steps"]

    def test_set_generation_data_supports_api_alias_keys(self):
        widget = _make_widget()
        entry = {
            "sd_model_checkpoint": "reuse-model.safetensors",
            "sampler_name": "Reuse Sampler",
            "steps": 24,
        }

        widget.set_generation_data(entry)
        data = widget.get_generation_data()

        assert data["model"] == "reuse-model.safetensors"
        assert data["sampler"] == "Reuse Sampler"
        assert data["sampling_steps"] == 24

    def test_set_generation_data_deep_copies_source(self):
        widget = _make_widget()
        entry = _history_entry()

        widget.set_generation_data(entry)
        before = dict(widget.variables)

        entry["model"] = "mutated-model.safetensors"
        entry["vae"] = "mutated-vae.safetensors"
        entry["sampler"] = "Mutated Sampler"
        entry["sampling_steps"] = 99
        entry["refiner"] = "mutated-refiner.safetensors"
        entry["refiner_start"] = 0.01

        assert widget.variables["model"] == before["model"]
        assert widget.variables["vae"] == before["vae"]
        assert widget.variables["sampler"] == before["sampler"]
        assert widget.variables["sampling_steps"] == before["sampling_steps"]
        assert widget.variables["refiner"] == before["refiner"]
        assert widget.variables["refiner_start"] == before["refiner_start"]

    def test_set_generation_data_does_not_trigger_generation(self):
        widget = _make_widget()
        widget.set_generation_data(_history_entry())
        widget.get_generation_data()
        assert not widget.api.txt2img.called
        assert not widget.api.img2img.called
