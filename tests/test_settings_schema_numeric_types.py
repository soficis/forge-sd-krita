"""F3 regression: ``soft_inpaint`` slider keys must be declared as JSON floats.

Manual QA in Krita 5.3.2.1 raised on every inpaint generate::

    TypeError: Invalid type for 'soft_inpaint.transition_contrast_boost': expected int, got float

(traceback: generate.py -> SoftInpaintWidget.get_generation_data ->
save_settings -> SettingsController.set).

``forge/default_settings.json`` declared three QSlider-backed keys as JSON
ints (``transition_contrast_boost``, ``mask_influence``,
``difference_contrast``) while every Soft Inpainting slider emits
``value() / multiplier`` -- a Python float -- so ``set()`` correctly
rejected them. Commit 52fff3b only covers the opposite direction (legacy
int user value merged into a float-declared key), so the schema itself is
what had to be corrected.

Covers:
- declared schema: the three keys are JSON floats, values unchanged
- set(): floats accepted for all three keys (real controller, real schema)
- merge: a legacy int user file still coerces to float (52fff3b path)
- strict set(): ``defaults.sampling_steps`` still raises TypeError on a
  float and float-declared keys still reject bool/str (validation intact)
- end-to-end: ``SoftInpaintWidget.get_generation_data()`` with slider-style
  float values saves cleanly through a real SettingsController, and the
  ``alwayson_scripts`` args payload keeps its 7-entry shape
- audit guard: every numeric leaf in ``default_settings.json`` is registered
  with the emission types of its producing widget, and each declared type is
  exactly what those emissions require -- a future widget cannot reintroduce
  an int/float mismatch silently
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import shutil
import sys
import types

import pytest

from forge.settings_controller import SettingsController, _value_matches_type
from forge.widgets import CollapsibleWidget  # noqa: F401  (import package once)

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_REAL_DEFAULTS = _REPO_ROOT / "forge" / "default_settings.json"


# ---------------------------------------------------------------------------
# Fresh stub-Qt module loader for forge/widgets/soft_inpaint.py
# (pattern from tests/test_cfg_scale_float.py -- forge/__init__ imports krita,
# so the module is exec'd from its file path instead of imported normally)
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


def _load_soft_inpaint_module():
    """Import forge/widgets/soft_inpaint.py fresh with stub-Qt classes."""
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
    mod_name = "forge.widgets.soft_inpaint_f3schema"
    try:
        path = _REPO_ROOT / "forge" / "widgets" / "soft_inpaint.py"
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


soft_inpaint_mod = _load_soft_inpaint_module()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_json(path, data):
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _copy_real_defaults(tmp_path):
    shutil.copy(_REAL_DEFAULTS, tmp_path / "default_settings.json")


def _real_schema():
    return json.loads(_REAL_DEFAULTS.read_text(encoding="utf-8"))


def _lookup(schema, dotted):
    node = schema
    for part in dotted.split("."):
        node = node[part]
    return node


def _legacy_int_controller(tmp_path):
    """Real schema + a user file persisting the three keys as legacy ints."""
    _copy_real_defaults(tmp_path)
    _write_json(
        tmp_path / "user_settings.json",
        {
            "soft_inpaint": {
                "transition_contrast_boost": 4,
                "mask_influence": 0,
                "difference_contrast": 2,
            },
            "_schema_version": 1,
        },
    )
    return SettingsController(base_dir=tmp_path)


# ---------------------------------------------------------------------------
# Declared schema
# ---------------------------------------------------------------------------


class TestDeclaredSchema:
    """forge/default_settings.json must declare the three slider keys as floats."""

    @pytest.mark.parametrize(
        "key,expected",
        [
            ("transition_contrast_boost", 4.0),
            ("mask_influence", 0.0),
            ("difference_contrast", 2.0),
        ],
    )
    def test_key_is_json_float_with_unchanged_value(self, key, expected):
        schema = _real_schema()
        value = schema["soft_inpaint"][key]
        assert type(value) is float, f"{key} declared as {type(value).__name__}"
        assert value == expected

    @pytest.mark.parametrize(
        "key,expected",
        [
            ("schedule_bias", 1.0),
            ("preservation_strength", 0.5),
            ("difference_threshold", 0.5),
        ],
    )
    def test_already_float_keys_untouched(self, key, expected):
        schema = _real_schema()
        value = schema["soft_inpaint"][key]
        assert type(value) is float
        assert value == expected


# ---------------------------------------------------------------------------
# set() accepts floats for the three keys
# ---------------------------------------------------------------------------


class TestFloatSetAccepted:
    """The exact call from soft_inpaint.save_settings() must succeed."""

    @pytest.mark.parametrize(
        "key,value",
        [
            ("transition_contrast_boost", 1.5),
            ("mask_influence", 0.25),
            ("difference_contrast", 3.25),
        ],
    )
    def test_set_accepts_slider_float(self, tmp_path, key, value):
        _copy_real_defaults(tmp_path)
        controller = SettingsController(base_dir=tmp_path)
        try:
            controller.set(f"soft_inpaint.{key}", value)
            assert controller.get(f"soft_inpaint.{key}") == value
        finally:
            controller.close()

    def test_set_accepts_slider_zero(self, tmp_path):
        _copy_real_defaults(tmp_path)
        controller = SettingsController(base_dir=tmp_path)
        try:
            controller.set("soft_inpaint.mask_influence", 0.0)
            assert controller.get("soft_inpaint.mask_influence") == 0.0
        finally:
            controller.close()


# ---------------------------------------------------------------------------
# Legacy int user files still merge (52fff3b coercion)
# ---------------------------------------------------------------------------


class TestLegacyIntMerge:
    """A 1.x-era user_settings.json holding plain ints must still load."""

    def test_legacy_ints_coerce_to_float(self, tmp_path):
        controller = _legacy_int_controller(tmp_path)
        try:
            for key, expected in [
                ("transition_contrast_boost", 4.0),
                ("mask_influence", 0.0),
                ("difference_contrast", 2.0),
            ]:
                value = controller.get(f"soft_inpaint.{key}")
                assert type(value) is float, key
                assert value == expected, key
        finally:
            controller.close()

    def test_set_float_after_legacy_int_load_succeeds(self, tmp_path):
        controller = _legacy_int_controller(tmp_path)
        try:
            controller.set("soft_inpaint.transition_contrast_boost", 1.5)
            assert controller.get("soft_inpaint.transition_contrast_boost") == 1.5
        finally:
            controller.close()


# ---------------------------------------------------------------------------
# Strict set() contract (must NOT weaken)
# ---------------------------------------------------------------------------


class TestStrictValidationIntact:
    """Validation stays strict -- only the schema declaration changed."""

    def test_int_expected_key_still_rejects_float(self, tmp_path):
        _copy_real_defaults(tmp_path)
        controller = SettingsController(base_dir=tmp_path)
        try:
            with pytest.raises(TypeError, match="expected int, got float"):
                controller.set("defaults.sampling_steps", 20.5)
        finally:
            controller.close()

    def test_int_expected_key_still_rejects_bool(self, tmp_path):
        _copy_real_defaults(tmp_path)
        controller = SettingsController(base_dir=tmp_path)
        try:
            with pytest.raises(TypeError, match="expected int, got bool"):
                controller.set("defaults.sampling_steps", True)
        finally:
            controller.close()

    def test_float_expected_key_still_rejects_bool(self, tmp_path):
        _copy_real_defaults(tmp_path)
        controller = SettingsController(base_dir=tmp_path)
        try:
            with pytest.raises(
                TypeError,
                match="Invalid type for 'soft_inpaint.schedule_bias'",
            ):
                controller.set("soft_inpaint.schedule_bias", True)
        finally:
            controller.close()

    def test_float_expected_key_still_rejects_str(self, tmp_path):
        _copy_real_defaults(tmp_path)
        controller = SettingsController(base_dir=tmp_path)
        try:
            with pytest.raises(TypeError, match="expected float, got str"):
                controller.set("soft_inpaint.preservation_strength", "0.5")
        finally:
            controller.close()


# ---------------------------------------------------------------------------
# SoftInpaintWidget end-to-end
# ---------------------------------------------------------------------------


class TestSoftInpaintWidgetEndToEnd:
    """The generate-time save path with float slider values must succeed
    against a real SettingsController seeded from the real schema."""

    def test_get_generation_data_saves_float_slider_values(self, tmp_path):
        _copy_real_defaults(tmp_path)
        controller = SettingsController(base_dir=tmp_path)
        try:
            widget = soft_inpaint_mod.SoftInpaintWidget(controller)
            label = soft_inpaint_mod.QLabel()
            # Mirror create_row's valueChanged handler: raw slider int /
            # multiplier -- step 0.5 -> x10, step 0.05/0.25 -> x100.
            widget.update_row(label, "transition_contrast_boost", 15 / 10)
            widget.update_row(label, "mask_influence", 25 / 100)
            widget.update_row(label, "difference_contrast", 50 / 100)
            widget.update_enabled(True)

            data = widget.get_generation_data()  # exact crash path

            args = data["alwayson_scripts"]["Soft Inpainting"]["args"]
            assert len(args) == 7
            assert args[0] is True
            assert args[3] == 1.5
            assert args[4] == 0.25
            assert args[6] == 0.5
            assert controller.get("soft_inpaint.transition_contrast_boost") == 1.5
            assert controller.get("soft_inpaint.mask_influence") == 0.25
            assert controller.get("soft_inpaint.difference_contrast") == 0.5
        finally:
            controller.close()

    def test_widget_reads_legacy_int_defaults_as_float(self, tmp_path):
        controller = _legacy_int_controller(tmp_path)
        try:
            widget = soft_inpaint_mod.SoftInpaintWidget(controller)
            for key in (
                "transition_contrast_boost",
                "mask_influence",
                "difference_contrast",
            ):
                assert type(widget.variables[key]) is float, key
        finally:
            controller.close()


# ---------------------------------------------------------------------------
# Schema-level audit guard
# ---------------------------------------------------------------------------

# key -> emission types of the producing widget (from the F3 audit) plus the
# producer. Declared type rule: a float-emitting key MUST be declared float
# (declaring int re-creates this crash); an int-only key is declared int.
# Every numeric leaf of default_settings.json must appear here -- adding a
# numeric setting without auditing its producer fails the coverage test.
_NUMERIC_AUDIT: dict[str, tuple[tuple[str, ...], str]] = {
    "defaults.sampling_steps": (("int",), "ModelsWidget QSpinBox.value()"),
    # slider at 0 -> int 0, otherwise value/100 -> float
    "defaults.refiner_start": (("int", "float"), "ModelsWidget slider/100"),
    "defaults.cfg_scale": (("float",), "CFGWidget round(value, 2)"),
    "defaults.denoise_strength": (("float",), "DenoiseWidget slider/100"),
    "defaults.min_size": (("int",), "QSpinBox / model_registry default_min_size"),
    "defaults.max_size": (("int",), "QSpinBox / model_registry default_max_size"),
    "hr_fix.auto_hrfix_min": (("int",), "HiResFixWidget QSpinBox.value()"),
    "hr_fix.sd_min": (("int",), "HiResFixWidget QSpinBox.value()"),
    "hr_fix.hrfix_steps": (("int",), "HiResFixWidget QSpinBox.value()"),
    "hr_fix.denoise_strength": (("float",), "HiResFixWidget slider/100"),
    "batch.count": (("int",), "BatchWidget QSpinBox.value()"),
    "batch.size": (("int",), "BatchWidget QSpinBox.value()"),
    "tiled.tile_size": (("int",), "TiledWidget int(currentText)"),
    "tiled.overlap": (("int",), "TiledWidget int(slider.value())"),
    "seed.seed": (("int",), "SeedWidget int(line edit)"),
    "seed.subseed": (("int",), "SeedWidget int(line edit)"),
    "seed.subseed_strength": (("float",), "SeedWidget slider/100"),
    "previews.refresh_seconds": (("float",), "SettingsPage float(text)"),
    "inpaint.mask_blur": (("int",), "MaskWidget QSpinBox.value()"),
    "inpaint.mask_mode": (("int",), "MaskWidget QComboBox.currentIndex()"),
    "inpaint.masked_content": (("int",), "MaskWidget QComboBox.currentIndex()"),
    "inpaint.inpaint_area": (("int",), "MaskWidget QComboBox.currentIndex()"),
    "inpaint.padding": (("int",), "MaskWidget QSpinBox.value()"),
    "soft_inpaint.schedule_bias": (("float",), "SoftInpaintWidget slider/multiplier"),
    "soft_inpaint.preservation_strength": (("float",), "SoftInpaintWidget slider/multiplier"),
    "soft_inpaint.transition_contrast_boost": (("float",), "SoftInpaintWidget slider/multiplier"),
    "soft_inpaint.mask_influence": (("float",), "SoftInpaintWidget slider/multiplier"),
    "soft_inpaint.difference_threshold": (("float",), "SoftInpaintWidget slider/multiplier"),
    "soft_inpaint.difference_contrast": (("float",), "SoftInpaintWidget slider/multiplier"),
    "upscale.tab": (("int",), "UpscalePage currentIndex()"),
    "upscale.resize": (("float",), "UpscalePage QDoubleSpinBox.value()"),
    "upscale.width": (("int",), "UpscalePage QSpinBox.value()"),
    "upscale.height": (("int",), "UpscalePage QSpinBox.value()"),
    "rembg.erode_size": (("int",), "RemBGPage slider/spinbox (int)"),
    "rembg.foreground_threshold": (("int",), "RemBGPage slider/spinbox (int)"),
    "rembg.background_threshold": (("int",), "RemBGPage slider/spinbox (int)"),
}


def _numeric_leaves(node, prefix=""):
    """Yield dotted paths of every non-bool int/float leaf in the schema."""
    for key, value in node.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            yield from _numeric_leaves(value, f"{path}.")
        elif isinstance(value, bool):
            continue
        elif isinstance(value, (int, float)):
            yield path


class TestNumericSchemaAudit:
    """Executable form of the settings-schema int/float audit."""

    def test_every_numeric_leaf_is_audited(self):
        leaves = set(_numeric_leaves(_real_schema()))
        assert leaves == set(_NUMERIC_AUDIT), (
            "numeric leaf keys and audit table disagree; audit every new "
            "numeric setting's producing widget and register it in "
            "_NUMERIC_AUDIT"
        )

    @pytest.mark.parametrize("key", sorted(_NUMERIC_AUDIT))
    def test_declared_type_matches_producer_emissions(self, key):
        emitted, producer = _NUMERIC_AUDIT[key]
        declared = _lookup(_real_schema(), key)
        # A float emission rejected by an int-declared key = the F3 crash.
        required = "float" if "float" in emitted else "int"
        assert type(declared).__name__ == required, (
            f"{key} (produced by {producer}) emits {emitted} but is declared "
            f"{type(declared).__name__}"
        )
        # And prove it against the real validator, not just by name.
        for kind in emitted:
            sample = 3 if kind == "int" else 0.5
            assert _value_matches_type(sample, declared), (
                f"{key}: validator rejects a {kind} emission"
            )
