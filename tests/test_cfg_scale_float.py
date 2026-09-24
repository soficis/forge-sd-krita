"""F3 regression: ``defaults.cfg_scale`` must be a float end-to-end.

Manual QA against build 1.1.0 raised on every generation mode::

    TypeError: Invalid type for 'defaults.cfg_scale': expected int, got float

(traceback: generate.py -> CFGWidget.get_generation_data -> CFGWidget.save_settings
-> SettingsController.set). A 1.0.0-era ``user_settings.json`` persisted
``defaults.cfg_scale`` as the int ``7``; the deep merge kept that int, pinning
the runtime schema so ``set()`` rejected the spinbox's float
(``round(value, 2)``) *before* ``debounced_save()`` could repair it.

Covers:
- declared schema: ``forge/default_settings.json`` declares cfg_scale as a JSON float
- merge: legacy int user value normalizes to float at load time (real + isolated schema)
- merge: float user value is preserved (no coercion / no rounding)
- merge: a genuinely wrong type (string) is still ignored
- strict ``set()``: int-expected keys (defaults.sampling_steps) still raise
  TypeError on a float; bools still rejected for int and float keys
- end-to-end: ``CFGWidget.save_settings()`` with a float succeeds through a
  real ``SettingsController`` seeded from the real schema + legacy int user file
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import shutil
import sys
import types
from unittest.mock import MagicMock

import pytest

from forge.settings_controller import SettingsController

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_REAL_DEFAULTS = _REPO_ROOT / "forge" / "default_settings.json"


# ---------------------------------------------------------------------------
# Fresh stub-Qt module loader for forge/widgets/cfg.py
# (pattern copied from tests/test_flux_ui.py / tests/test_controlnet_dict_guards.py)
# ---------------------------------------------------------------------------

_QT_NAMES = [
    "Qt", "QWidget", "QVBoxLayout", "QHBoxLayout", "QFormLayout",
    "QGridLayout", "QLabel", "QComboBox", "QPushButton", "QCheckBox",
    "QTabWidget", "QGroupBox", "QSlider", "QSpinBox", "QDoubleSpinBox",
    "QPlainTextEdit", "QTextEdit", "QLineEdit", "QScrollArea", "QColor",
    "QPainter", "QByteArray", "QBuffer", "QImage", "QIODevice", "QObject",
    "QThread", "QTimer", "QProgressBar", "QListWidget", "QListWidgetItem",
    "pyqtSignal", "QSize", "QIcon", "QPixmap", "QPointF", "qAlpha", "qRgb",
]


def _load_cfg_module():
    """Import forge/widgets/cfg.py fresh with stub-Qt classes; return it."""
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
    mod_name = "forge.widgets.cfg_f3fix"
    try:
        path = _REPO_ROOT / "forge" / "widgets" / "cfg.py"
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
                     and k != mod_name]:
            sys.modules.pop(_key, None)


cfg_mod = _load_cfg_module()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_json(path, data):
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _copy_real_defaults(tmp_path):
    shutil.copy(_REAL_DEFAULTS, tmp_path / "default_settings.json")


def _legacy_int_controller(tmp_path):
    """Real schema + a 1.0.0-era user file persisting cfg_scale as int 7."""
    _copy_real_defaults(tmp_path)
    _write_json(
        tmp_path / "user_settings.json",
        {"defaults": {"cfg_scale": 7}, "_schema_version": 1},
    )
    return SettingsController(base_dir=tmp_path)


# ---------------------------------------------------------------------------
# Declared schema
# ---------------------------------------------------------------------------


class TestDeclaredSchema:
    """forge/default_settings.json must declare cfg_scale as a JSON float."""

    def test_declared_cfg_scale_default_is_json_float(self):
        data = json.loads(_REAL_DEFAULTS.read_text(encoding="utf-8"))
        assert type(data["defaults"]["cfg_scale"]) is float
        assert data["defaults"]["cfg_scale"] == 7.0


# ---------------------------------------------------------------------------
# Load-time merge normalization
# ---------------------------------------------------------------------------


class TestLegacyIntMerge:
    """A legacy int user value merges to float; floats pass through; bad
    types stay ignored."""

    def test_legacy_int_user_value_merges_to_float(self, tmp_path):
        # Isolated schema authored as float: proves the MERGE normalizes,
        # independently of the shipped default_settings.json change.
        _write_json(tmp_path / "default_settings.json",
                    {"defaults": {"cfg_scale": 7.0}})
        _write_json(tmp_path / "user_settings.json",
                    {"defaults": {"cfg_scale": 7}})

        controller = SettingsController(base_dir=tmp_path)
        value = controller.get("defaults.cfg_scale")
        assert type(value) is float
        assert value == 7.0

    def test_real_schema_with_legacy_int_user_merges_to_float(self, tmp_path):
        controller = _legacy_int_controller(tmp_path)
        value = controller.get("defaults.cfg_scale")
        assert type(value) is float
        assert value == 7.0

    def test_set_float_after_legacy_int_load_succeeds(self, tmp_path):
        # The F3 failure itself: set() compared against the stale int and
        # raised "expected int, got float" before debounced_save could run.
        controller = _legacy_int_controller(tmp_path)
        controller.set("defaults.cfg_scale", 3.5)
        assert controller.get("defaults.cfg_scale") == 3.5

    def test_float_user_value_is_preserved(self, tmp_path):
        _write_json(tmp_path / "default_settings.json",
                    {"defaults": {"cfg_scale": 7.0}})
        _write_json(tmp_path / "user_settings.json",
                    {"defaults": {"cfg_scale": 3.5}})

        controller = SettingsController(base_dir=tmp_path)
        value = controller.get("defaults.cfg_scale")
        assert type(value) is float
        assert value == 3.5

    def test_wrong_type_string_user_value_is_ignored(self, tmp_path):
        _write_json(tmp_path / "default_settings.json",
                    {"defaults": {"cfg_scale": 7.0}})
        _write_json(tmp_path / "user_settings.json",
                    {"defaults": {"cfg_scale": "seven"}})

        controller = SettingsController(base_dir=tmp_path)
        value = controller.get("defaults.cfg_scale")
        assert type(value) is float
        assert value == 7.0


# ---------------------------------------------------------------------------
# Strict set() contract (must NOT weaken)
# ---------------------------------------------------------------------------


class TestStrictSetValidation:
    """set() keeps exact-type validation — no silent coercion anywhere."""

    def test_int_expected_key_still_rejects_float(self, tmp_path):
        _copy_real_defaults(tmp_path)
        controller = SettingsController(base_dir=tmp_path)
        with pytest.raises(TypeError, match="expected int, got float"):
            controller.set("defaults.sampling_steps", 20.5)

    def test_int_expected_key_still_rejects_bool(self, tmp_path):
        _copy_real_defaults(tmp_path)
        controller = SettingsController(base_dir=tmp_path)
        with pytest.raises(TypeError, match="expected int, got bool"):
            controller.set("defaults.sampling_steps", True)

    def test_float_expected_key_still_rejects_bool(self, tmp_path):
        _copy_real_defaults(tmp_path)
        controller = SettingsController(base_dir=tmp_path)
        with pytest.raises(TypeError, match="Invalid type for 'defaults.cfg_scale'"):
            controller.set("defaults.cfg_scale", True)


# ---------------------------------------------------------------------------
# CFGWidget end-to-end
# ---------------------------------------------------------------------------


class TestCFGWidgetEndToEnd:
    """CFGWidget.save_settings() round-trips a float through a real
    SettingsController seeded from the real schema + legacy int user file."""

    def test_widget_reads_legacy_int_cfg_as_float(self, tmp_path):
        controller = _legacy_int_controller(tmp_path)
        try:
            widget = cfg_mod.CFGWidget(controller, MagicMock())
            assert type(widget.variables["cfg"]) is float
            assert widget.variables["cfg"] == 7.0
        finally:
            controller.close()

    def test_save_settings_with_float_succeeds(self, tmp_path):
        controller = _legacy_int_controller(tmp_path)
        try:
            widget = cfg_mod.CFGWidget(controller, MagicMock())
            # What the spinbox valueChanged handler runs (round -> float):
            widget._update_variable("cfg", 3.5)
            widget.save_settings()  # must not raise
            assert controller.get("defaults.cfg_scale") == 3.5
        finally:
            controller.close()
