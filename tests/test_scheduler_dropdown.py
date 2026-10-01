"""Scheduler dropdown: the default selection must send NO ``scheduler`` key.

Commit f27fbb7 removed payload_builder's unconditional scheduler injection:
Forge Neo owns its own per-preset scheduler default (measured live from
``GET /sdapi/v1/options``: sd/xl=Automatic, flux/klein=Beta, qwen=Normal,
krea=Simple; the top-level ``scheduler`` option is null), and the value the
plugin used to hardcode from ``model_registry.default_scheduler`` was
provably wrong for FLUX (plugin sent ``Simple``; the backend preset is
``Beta``).

Contract locked here:

* the default / sentinel entry ("Default (per model)") produces
  generation data AND payload with NO ``scheduler`` key at all
* a user-picked backend label reaches the payload as exactly that label,
  passed through verbatim (payload_builder needs no change for this)
* ``SDAPI.get_schedulers()`` coerces a non-list body to ``[]`` and never
  raises when the backend is unreachable
* history reuse (set_generation_data -> get_generation_data) round-trips
  both the sentinel and a real label
* unknown/garbage stored values degrade to the sentinel, never to garbage
* ``hide_ui.scheduler`` only removes the row, never the payload safety

payload_builder, adapters/sd_api.py and widgets/models.py are loaded FRESH
under a private package (pattern from tests/test_vae_sentinel_fix.py and
tests/test_models_history_reuse.py): this module never imports ``forge``
directly (forge/__init__.py imports ``krita``), and the functional Qt
stand-ins are real classes - subclassing the shared conftest MagicMock Qt
yields mocks, not classes. The real SDAPI class is exercised without
networking: ``SDAPI.__new__`` skips the ``__init__``/``refresh`` request
loop and ``get`` is stubbed per test.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

FORGE_DIR = Path(__file__).resolve().parent.parent / "forge"
PKG = "scheddrop"

# The sentinel entry, pinned here as the spec states it: its text is NOT one
# of the backend's 17 scheduler labels, so it can never be sent as a value.
SENTINEL = "Default (per model)"
SCHEDULER_LABELS = ["Automatic", "Karras", "Exponential", "Beta"]


# ---------------------------------------------------------------------------
# Functional Qt stand-ins (pattern from tests/test_vae_sentinel_fix.py)
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

    def setVisible(self, visible):
        self._visible = bool(visible)

    def isVisible(self):
        return getattr(self, "_visible", True)


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
        self.toggled = _Signal()

    def setChecked(self, value):
        self._checked = bool(value)
        self.stateChanged.emit(self._checked)
        self.toggled.emit(self._checked)

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
    """Load payload_builder + sd_api + widgets/models fresh under a private
    package so nothing here executes forge/__init__.py."""
    for name, path in (
        (PKG, []),
        (f"{PKG}.widgets", [str(FORGE_DIR / "widgets")]),
        (f"{PKG}.domain", []),
        (f"{PKG}.adapters", [str(FORGE_DIR / "adapters")]),
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
        # sd_api.py imports these for its (untested here) image helpers.
        "QColor": _AttrChain(),
        "QPainter": _AttrChain(),
        "QByteArray": _AttrChain(),
        "QBuffer": _AttrChain(),
        "QImage": _AttrChain(),
        "QIODevice": _AttrChain(),
    }
    for name, obj in qt_names.items():
        setattr(qt_mod, name, obj)
    qt_mod.__all__ = list(qt_names)
    sys.modules[f"{PKG}.qt_compat"] = qt_mod

    # Pure-Python domain modules: loaded from source, no krita/Qt involved.
    _fresh_load("domain/model_registry.py", f"{PKG}.domain.model_registry")
    payload_mod = _fresh_load(
        "domain/payload_builder.py", f"{PKG}.domain.payload_builder"
    )

    # The REAL adapter, so get_schedulers() is production code under test.
    sd_api_mod = _fresh_load("adapters/sd_api.py", f"{PKG}.adapters.sd_api")

    settings_mod = types.ModuleType(f"{PKG}.settings_controller")

    class SettingsController:
        pass

    settings_mod.SettingsController = SettingsController
    sys.modules[f"{PKG}.settings_controller"] = settings_mod

    models_mod = _fresh_load("widgets/models.py", f"{PKG}.widgets.models")
    return payload_mod, sd_api_mod, models_mod


payload_module, sd_api_module, models_module = _install_private_package()
build_api_payload = payload_module.build_api_payload
SDAPI = sd_api_module.SDAPI
ModelsWidget = models_module.ModelsWidget


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_widget(
    settings_scheduler="",
    hide_scheduler=False,
    api_scheduler_default="",
    schedulers=SCHEDULER_LABELS,
    offline=False,
):
    settings = MagicMock()
    defaults = {
        "defaults.model": "",
        "defaults.vae": "",
        "defaults.refiner": "",
        "defaults.sampler": "",
        "defaults.scheduler": settings_scheduler,
        "defaults.sampling_steps": 20,
        "defaults.enable_refiner": False,
        "defaults.refiner_start": 0.8,
        "hide_ui.model": False,
        "hide_ui.vae": False,
        "hide_ui.refiner": False,
        "hide_ui.sampler": False,
        "hide_ui.scheduler": hide_scheduler,
    }
    settings.get.side_effect = lambda path, default=None: defaults.get(path, default)

    api = MagicMock()
    api.get_models_and_default.return_value = (
        ["model.safetensors"],
        "model.safetensors",
    )
    api.get_vaes_and_default.return_value = (["None"], "None")
    api.get_refiners_and_default.return_value = (["None"], "None")
    api.get_samplers_and_default.return_value = (["Euler a"], "Euler a")
    api.get_schedulers_and_default.return_value = (
        list(schedulers),
        api_scheduler_default,
    )
    if offline:
        # What SDAPI returns while disconnected: empty lists, "None" defaults.
        api.get_models_and_default.return_value = ([], "None")
        api.get_vaes_and_default.return_value = ([], "None")
        api.get_samplers_and_default.return_value = ([], "None")
        api.get_schedulers_and_default.return_value = ([], "")
    return ModelsWidget(settings, api), settings, api


def _stored(settings, key):
    """Last value written to ``key`` through settings.set, else None."""
    writes = [c.args[1] for c in settings.set.call_args_list if c.args[0] == key]
    return writes[-1] if writes else None


def _wrote(settings, key):
    return any(c.args[0] == key for c in settings.set.call_args_list)


def _pick(widget, label):
    """Simulate the user choosing a combo entry: set the text, fire the signal."""
    widget.scheduler_box.setCurrentText(label)
    widget.scheduler_box.currentTextChanged.emit()


def _adapter(get_stub=None, connected=True):
    """A real SDAPI instance with the networked __init__/refresh skipped and
    ``get`` replaced by the per-test stub."""
    api = SDAPI.__new__(SDAPI)
    api._cache = {}
    api._cache_ttl = 60.0
    api.connected = connected
    api.schedulers = []
    api.defaults = {"scheduler": ""}
    api.get = get_stub if get_stub is not None else (lambda path: [])
    return api


# ---------------------------------------------------------------------------
# 1. Default selection -> NO scheduler key anywhere
# ---------------------------------------------------------------------------


class TestBackendDefaultSendsNoKey:
    def test_default_state_uses_the_sentinel_entry_first(self):
        widget, _, _ = _make_widget()
        # The first combo entry is the sentinel, not a backend label.
        assert widget.scheduler_box.findText(SENTINEL) == 0
        assert widget.variables["scheduler"] == SENTINEL
        assert widget.scheduler_box.currentText() == SENTINEL

    def test_default_state_generation_data_has_no_scheduler_key(self):
        widget, _, _ = _make_widget()
        data = widget.get_generation_data()
        assert "scheduler" not in data

    def test_default_state_payload_has_no_scheduler_key(self):
        widget, _, _ = _make_widget()
        assert widget.scheduler_box.findText(SENTINEL) == 0
        payload = build_api_payload(widget.get_generation_data())
        assert "scheduler" not in payload

    def test_reselecting_the_sentinel_entry_sends_no_key(self):
        widget, _, _ = _make_widget()
        _pick(widget, "Karras")
        assert widget.get_generation_data()["scheduler"] == "Karras"  # sanity

        _pick(widget, SENTINEL)
        data = widget.get_generation_data()
        assert "scheduler" not in data
        payload = build_api_payload(data)
        assert "scheduler" not in payload

    def test_sentinel_entry_is_not_a_backend_label(self):
        # "Default (per model)" must never collide with the real
        # "Automatic" label: for FLUX the backend default is Beta, so an
        # accidental "Automatic" would override the preset.
        assert SENTINEL not in SCHEDULER_LABELS
        assert SENTINEL != "Automatic"


# ---------------------------------------------------------------------------
# 2. Real label selection -> exactly that label in the payload
# ---------------------------------------------------------------------------


class TestRealLabelSelection:
    def test_selected_label_reaches_payload_verbatim(self):
        widget, _, _ = _make_widget()
        _pick(widget, "Karras")
        data = widget.get_generation_data()
        assert data["scheduler"] == "Karras"
        payload = build_api_payload(data)
        assert payload["scheduler"] == "Karras"

    def test_explicit_automatic_pick_is_sent(self):
        # "Automatic" may only appear when the user explicitly picked it.
        widget, _, _ = _make_widget()
        _pick(widget, "Automatic")
        payload = build_api_payload(widget.get_generation_data())
        assert payload["scheduler"] == "Automatic"

    def test_every_backend_label_round_trips_to_the_payload(self):
        for label in SCHEDULER_LABELS:
            widget, _, _ = _make_widget()
            _pick(widget, label)
            payload = build_api_payload(widget.get_generation_data())
            assert payload["scheduler"] == label, label


# ---------------------------------------------------------------------------
# 3. Adapter: get_schedulers()/get_schedulers_and_default()
# ---------------------------------------------------------------------------


class TestGetSchedulers:
    def test_valid_list_is_returned(self):
        body = [{"name": "karras", "label": "Karras"}]
        api = _adapter(lambda path: body)
        assert api.get_schedulers() == body
        assert api.schedulers == body

    def test_non_list_body_coerces_to_empty(self):
        for body in ({"error": "boom"}, "nope", None, 42, b"raw"):
            api = _adapter(lambda path: body)
            assert api.get_schedulers() == [], repr(body)
            assert api.schedulers == [], repr(body)

    def test_disconnected_raising_get_returns_empty_without_raising(self):
        def boom(path):
            raise ConnectionRefusedError("refused")

        api = _adapter(boom)
        assert api.get_schedulers() == []

    def test_disconnected_error_object_body_returns_empty(self):
        # The real get() returns the exception instead of raising it.
        api = _adapter(lambda path: ConnectionRefusedError("refused"))
        assert api.get_schedulers() == []

    def test_result_is_ttl_cached_like_samplers(self):
        calls = []

        def fake(path):
            calls.append(path)
            return [{"name": "beta", "label": "Beta"}]

        api = _adapter(fake)
        first = api.get_schedulers()
        second = api.get_schedulers()
        assert first == second == [{"name": "beta", "label": "Beta"}]
        assert calls == ["/sdapi/v1/schedulers"]

    def test_and_default_returns_labels_and_backend_default(self):
        api = _adapter(
            lambda path: [
                {"name": "karras", "label": "Karras"},
                {"name": "beta", "label": "Beta"},
            ]
        )
        api.get_schedulers()  # populate the cached list, as refresh() does
        labels, default = api.get_schedulers_and_default()
        assert labels == ["Karras", "Beta"]
        assert default == ""  # empty = the backend owns the default

    def test_and_default_while_disconnected(self):
        api = _adapter(lambda path: [], connected=False)
        assert api.get_schedulers_and_default() == ([], "")


# ---------------------------------------------------------------------------
# 4. History reuse round-trip (set_generation_data <-> get_generation_data)
# ---------------------------------------------------------------------------


class TestHistoryRoundTrip:
    def test_real_label_round_trips(self):
        widget, _, _ = _make_widget()
        widget.set_generation_data({"scheduler": "Karras"})
        data = widget.get_generation_data()
        assert data["scheduler"] == "Karras"
        assert widget.variables["scheduler"] == "Karras"
        assert widget.scheduler_box.currentText() == "Karras"

    def test_sentinel_empty_string_round_trips_to_no_key(self):
        widget, _, _ = _make_widget()
        widget.set_generation_data({"scheduler": ""})
        data = widget.get_generation_data()
        assert "scheduler" not in data
        assert widget.scheduler_box.currentText() == SENTINEL

    def test_history_entry_without_the_key_restores_the_sentinel(self):
        # Entries saved before this feature (or with the default selected)
        # carry no scheduler key at all -> that generation used the backend
        # default, so reuse must go back to the sentinel.
        widget, _, _ = _make_widget()
        _pick(widget, "Beta")
        assert widget.get_generation_data()["scheduler"] == "Beta"

        widget.set_generation_data({"model": "model.safetensors"})
        data = widget.get_generation_data()
        assert "scheduler" not in data
        assert widget.scheduler_box.currentText() == SENTINEL

    def test_restored_label_is_deep_copied_not_shared(self):
        widget, _, _ = _make_widget()
        entry = {"scheduler": "Exponential"}
        widget.set_generation_data(entry)
        entry["scheduler"] = "mutated"
        assert widget.variables["scheduler"] == "Exponential"
        assert widget.get_generation_data()["scheduler"] == "Exponential"


# ---------------------------------------------------------------------------
# 5. Garbage degrades to the sentinel, never into the payload
# ---------------------------------------------------------------------------


class TestGarbageDegradesToSentinel:
    def test_unknown_label_degrades_to_sentinel(self):
        widget, _, _ = _make_widget()
        widget.set_generation_data({"scheduler": "TotallyBogus"})
        assert widget.variables["scheduler"] == SENTINEL
        assert widget.scheduler_box.currentText() == SENTINEL
        data = widget.get_generation_data()
        assert "scheduler" not in data
        assert "scheduler" not in build_api_payload(data)

    def test_non_string_value_degrades_to_sentinel(self):
        for value in (42, None, ["Karras"], {"label": "Karras"}):
            widget, _, _ = _make_widget()
            widget.set_generation_data({"scheduler": value})
            data = widget.get_generation_data()
            assert "scheduler" not in data, repr(value)
            assert widget.variables["scheduler"] == SENTINEL, repr(value)

    def test_garbage_stored_setting_falls_back_to_sentinel(self):
        widget, _, _ = _make_widget(settings_scheduler="BogusScheduler")
        assert widget.variables["scheduler"] == SENTINEL
        assert "scheduler" not in widget.get_generation_data()

    def test_valid_stored_setting_is_restored_as_default(self):
        widget, _, _ = _make_widget(settings_scheduler="Karras")
        assert widget.variables["scheduler"] == "Karras"
        assert widget.scheduler_box.currentText() == "Karras"
        assert widget.get_generation_data()["scheduler"] == "Karras"

    def test_backend_default_marker_from_api_maps_to_sentinel(self):
        # get_schedulers_and_default() reports "" (backend owns it); the
        # widget must show the sentinel entry, not an empty combo text.
        widget, _, _ = _make_widget(api_scheduler_default="")
        assert widget.variables["scheduler"] == SENTINEL
        assert widget.scheduler_box.currentText() == SENTINEL


# ---------------------------------------------------------------------------
# 6. hide_ui.scheduler only removes the row
# ---------------------------------------------------------------------------


class TestHideUiGate:
    def test_hidden_row_builds_no_box_but_payload_stays_safe(self):
        widget, _, _ = _make_widget(hide_scheduler=True)
        assert not hasattr(widget, "scheduler_box")
        assert "scheduler" not in widget.get_generation_data()

    def test_hidden_row_still_restores_history_values(self):
        widget, _, _ = _make_widget(hide_scheduler=True)
        widget.set_generation_data({"scheduler": "Beta"})
        assert widget.variables["scheduler"] == "Beta"
        assert widget.get_generation_data()["scheduler"] == "Beta"


# ---------------------------------------------------------------------------
# 7. Storage form: "" for backend-owned, never the UI label (grime-struct-9fa)
# ---------------------------------------------------------------------------


class TestStoredForm:
    def test_sentinel_is_stored_as_empty_string(self):
        widget, settings, _ = _make_widget()
        widget.save_settings()
        assert _stored(settings, "defaults.scheduler") == ""

    def test_real_label_is_stored_verbatim(self):
        widget, settings, _ = _make_widget()
        _pick(widget, "Karras")
        widget.save_settings()
        assert _stored(settings, "defaults.scheduler") == "Karras"

    def test_previously_stored_label_is_migrated_to_empty_string(self):
        widget, settings, _ = _make_widget(settings_scheduler=SENTINEL)
        widget.save_settings()
        assert _stored(settings, "defaults.scheduler") == ""

    def test_building_the_widget_writes_nothing_to_settings(self):
        _, settings, _ = _make_widget()
        assert not _wrote(settings, "defaults.scheduler")
        assert not _wrote(settings, "defaults.sampler")
        assert not _wrote(settings, "defaults.vae")


# ---------------------------------------------------------------------------
# 8. Offline build/save must not clobber saved choices (grime-res-7qd)
# ---------------------------------------------------------------------------


class TestOfflineDoesNotClobber:
    def test_offline_build_writes_no_defaults(self):
        _, settings, _ = _make_widget(
            settings_scheduler="Karras", offline=True
        )
        for key in ("model", "vae", "sampler", "scheduler"):
            assert not _wrote(settings, "defaults." + key), key

    def test_offline_save_keeps_saved_model_vae_sampler_scheduler(self):
        widget, settings, _ = _make_widget(
            settings_scheduler="Karras", offline=True
        )
        widget.save_settings()
        for key in ("model", "vae", "sampler", "scheduler"):
            assert not _wrote(settings, "defaults." + key), key

    def test_offline_generation_data_does_not_clobber_either(self):
        widget, settings, _ = _make_widget(offline=True)
        widget.get_generation_data()
        assert not _wrote(settings, "defaults.scheduler")

    def test_online_save_still_writes_all_four(self):
        widget, settings, _ = _make_widget()
        widget.save_settings()
        assert _stored(settings, "defaults.model") == "model.safetensors"
        assert _stored(settings, "defaults.sampler") == "Euler a"
        assert _wrote(settings, "defaults.scheduler")
