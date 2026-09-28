"""F3 regression: the backend VAE UI sentinel must never reach the API payload.

Forge Neo's ``/sdapi/v1/options`` reports ``sd_vae: "Automatic"`` - a UI
sentinel, not a filename. Two layers had to agree for generation to work:

* ``payload_builder`` used to forward ANY vae string into
  ``override_settings["sd_vae"]``, so the backend ran
  ``reload_vae_weights("Automatic")`` -> ``load_torch_file`` ->
  FileNotFoundError -> HTTP 500.
* ``ModelsWidget`` stored the sentinel in ``variables['vae']`` even though
  the VAE combo can only represent real filenames plus ``"None"``, so the
  combo and the payload could disagree silently.

Contract under test: sentinels (``Automatic``/``None``, any case, blank or
whitespace-only) and non-strings are DROPPED from the payload entirely -
omitting ``sd_vae`` is the only correct "use the checkpoint's VAE" signal -
while a real, user-selected VAE filename passes through byte-identical.

Both modules are loaded FRESH from their source files under a private
package (pattern from tests/test_controlnet_dict_guards.py and
tests/test_models_history_reuse.py): this module never imports ``forge``
directly, because ``forge/__init__.py`` imports ``krita``.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

FORGE_DIR = Path(__file__).resolve().parent.parent / "forge"
PKG = "f3vae"


# ---------------------------------------------------------------------------
# Functional Qt stand-ins (pattern from tests/test_models_history_reuse.py):
# the shared conftest Qt mock cannot define real widget classes.
# ---------------------------------------------------------------------------


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

    def setPlaceholderText(self, text):
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


def _fresh_load(relpath: str, mod_name: str):
    spec = importlib.util.spec_from_file_location(mod_name, str(FORGE_DIR / relpath))
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


def _install_private_package():
    """Load payload_builder + widgets/models fresh under a private package."""
    for name, path in (
        (PKG, []),
        (f"{PKG}.widgets", [str(FORGE_DIR / "widgets")]),
        (f"{PKG}.domain", []),
        (f"{PKG}.adapters", []),
    ):
        pkg = types.ModuleType(name)
        pkg.__path__ = path
        sys.modules[name] = pkg

    qt_mod = types.ModuleType(f"{PKG}.qt_compat")
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
    sys.modules[f"{PKG}.qt_compat"] = qt_mod

    # Pure-Python domain modules: loaded from source, no krita/Qt involved.
    _fresh_load("domain/model_registry.py", f"{PKG}.domain.model_registry")
    payload_mod = _fresh_load("domain/payload_builder.py", f"{PKG}.domain.payload_builder")

    # models.py only needs these two names from its adapter/settings imports.
    sd_api_mod = types.ModuleType(f"{PKG}.adapters.sd_api")

    class SDAPI:
        pass

    class ConnectionState:
        CONNECTING = "connecting"

    sd_api_mod.SDAPI = SDAPI
    sd_api_mod.ConnectionState = ConnectionState
    sys.modules[f"{PKG}.adapters.sd_api"] = sd_api_mod

    settings_mod = types.ModuleType(f"{PKG}.settings_controller")

    class SettingsController:
        pass

    settings_mod.SettingsController = SettingsController
    sys.modules[f"{PKG}.settings_controller"] = settings_mod

    models_mod = _fresh_load("widgets/models.py", f"{PKG}.widgets.models")
    return payload_mod, models_mod


payload_module, models_module = _install_private_package()
build_api_payload = payload_module.build_api_payload
ModelsWidget = models_module.ModelsWidget


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _collect_vae_values(payload):
    """Every value stored under a VAE-bearing key anywhere in the payload.

    Only ``vae`` / ``sd_vae`` keys count: other keys (e.g. scheduler) have
    their own legitimate default strings that are backend-accepted.
    """
    found = []

    def _walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("vae", "sd_vae"):
                    found.append(value)
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(payload)
    return found


def _make_widget(api_vaes, api_vae_default, settings_vae=""):
    settings = MagicMock()
    defaults = {
        "defaults.model": "",
        "defaults.vae": settings_vae,
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
    api.get_models_and_default.return_value = (["model.safetensors"], "model.safetensors")
    api.get_vaes_and_default.return_value = (list(api_vaes), api_vae_default)
    api.get_refiners_and_default.return_value = (["None"], "None")
    api.get_samplers_and_default.return_value = (["Euler a"], "Euler a")
    return ModelsWidget(settings, api), settings


# ---------------------------------------------------------------------------
# Payload layer: sentinels are dropped, real filenames pass unchanged
# ---------------------------------------------------------------------------


class TestPayloadVaeSentinels:
    """build_api_payload must omit sd_vae for every non-filename value."""

    def test_sentinel_vae_never_reaches_override_settings(self):
        for sentinel in ("Automatic", "automatic", "None", "none", "", "   "):
            result = build_api_payload({"vae": sentinel})
            assert "sd_vae" not in result["override_settings"], sentinel
            assert "vae" not in result, sentinel

    def test_absent_vae_produces_no_override(self):
        result = build_api_payload({"prompt": "x"})
        assert "sd_vae" not in result["override_settings"]

    def test_real_vae_filename_passes_byte_identical(self):
        name = "vae-ft-mse-840000-pruned.safetensors"
        result = build_api_payload({"vae": name})
        assert result["override_settings"]["sd_vae"] == name
        assert "vae" not in result

    def test_filename_containing_sentinel_word_is_not_dropped(self):
        name = "none-of-your-business.vae.safetensors"
        result = build_api_payload({"vae": name})
        assert result["override_settings"]["sd_vae"] == name

    def test_non_string_vae_is_dropped_without_crash(self):
        for value in (None, 123, ["vae.safetensors"], {"name": "vae"}):
            result = build_api_payload({"vae": value})
            assert "sd_vae" not in result["override_settings"], repr(value)
            assert "vae" not in result, repr(value)

    def test_sentinel_vae_dropped_alongside_other_overrides(self):
        result = build_api_payload({
            "model": "sdxl_base.safetensors",
            "vae": "Automatic",
            "prompt": "a cat",
        })
        assert "sd_vae" not in result["override_settings"]
        assert result["override_settings"]["sd_model_checkpoint"] == "sdxl_base.safetensors"


# ---------------------------------------------------------------------------
# Backend contract: the literal "Automatic" is never a VAE value
# ---------------------------------------------------------------------------


class TestBackendVaeContract:
    """Forge treats any provided sd_vae as a literal filename; the literal
    sentinel "Automatic" must therefore never appear as a VAE value."""

    def test_payload_never_contains_automatic_as_vae_value(self):
        payload = build_api_payload({
            "prompt": "a cat",
            "model": "sdxl_base.safetensors",
            "vae": "Automatic",
            "sampler": "Euler a",
            "sampling_steps": 20,
        })
        vae_values = _collect_vae_values(payload)
        assert vae_values == [], vae_values

    def test_payload_never_contains_sentinel_in_any_case(self):
        for sentinel in ("AUTOMATIC", "AuToMaTiC", "None", "NONE"):
            payload = build_api_payload({"prompt": "x", "vae": sentinel})
            offenders = [
                value for value in _collect_vae_values(payload)
                if isinstance(value, str) and value.strip().lower() in ("automatic", "none")
            ]
            assert offenders == [], sentinel


# ---------------------------------------------------------------------------
# Widget layer: variables and combo can no longer disagree on the sentinel
# ---------------------------------------------------------------------------


class TestWidgetVaeReconcile:
    """An unrepresentable backend default falls back to the combo's
    representable no-VAE state ("None") instead of being retained."""

    def test_widget_falls_back_to_none_when_backend_default_not_selectable(self):
        widget, _ = _make_widget(
            api_vaes=["real-vae.safetensors"], api_vae_default="Automatic"
        )
        assert widget.variables["vae"] == "None"
        assert widget.variables["vae"] != "Automatic"

    def test_widget_combo_and_variable_agree_on_sentinel_default(self):
        widget, _ = _make_widget(
            api_vaes=["real-vae.safetensors"], api_vae_default="Automatic"
        )
        assert widget.vae_box.currentText() == widget.variables["vae"]

    def test_widget_sentinel_default_never_reaches_payload(self):
        widget, _ = _make_widget(
            api_vaes=["real-vae.safetensors"], api_vae_default="Automatic"
        )
        payload = build_api_payload(widget.get_generation_data())
        assert "sd_vae" not in payload["override_settings"]
        assert _collect_vae_values(payload) == []

    def test_widget_does_not_persist_sentinel_into_settings(self):
        widget, settings = _make_widget(
            api_vaes=["real-vae.safetensors"], api_vae_default="Automatic"
        )
        widget.get_generation_data()
        vae_writes = [
            call.args[1]
            for call in settings.set.call_args_list
            if call.args and call.args[0] == "defaults.vae"
        ]
        assert vae_writes, "expected the VAE default to be written to settings"
        assert "Automatic" not in vae_writes, vae_writes

    def test_widget_keeps_selectable_backend_default(self):
        widget, _ = _make_widget(
            api_vaes=["real-vae.safetensors"], api_vae_default="real-vae.safetensors"
        )
        assert widget.variables["vae"] == "real-vae.safetensors"
        assert widget.vae_box.currentText() == "real-vae.safetensors"
        payload = build_api_payload(widget.get_generation_data())
        assert payload["override_settings"]["sd_vae"] == "real-vae.safetensors"
