"""Todo 26 (Phase 2): Flux dynamic UI sizing.

Routes family behavior through architecture_changed + ModelConfig flags —
no hardcoded family checks scattered in widgets.

Covers:
- FLUX/FLUX2 family -> size constraints (step 16, min/max per ModelConfig)
- hide_hires_fix flag -> hires widget visibility/enabled predicate false
- SD family -> constraints unchanged (regression: step 8, no hides)
- Z family -> per docs/MODELS.md UI matrix (neg hidden, styles VISIBLE,
  CFG fixed, hires hidden)
- CFG label switches via cfg.py (verify only, no duplicate logic)
- prompts.py update_for_model routed through ModelConfig flags

Widget modules are loaded FRESH under stub-Qt real classes (pattern copied
from tests/test_controlnet_dict_guards.py): subclassing conftest's MagicMock
Qt does NOT work (produces mocks, not classes).
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from forge.domain.model_registry import (
    ModelFamily,
    detect_model_family,
    get_model_config,
)


# ---------------------------------------------------------------------------
# Fresh stub-Qt module loader (real classes, not mocks)
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


def _load_real(relpath: str, mod_name: str):
    """Import a forge module fresh with stub-Qt classes; return it."""
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
        path = pathlib.Path(__file__).resolve().parent.parent / relpath
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


prompts_mod = _load_real("forge/widgets/prompts.py", "forge.widgets.prompts_task26")
hires_mod = _load_real("forge/widgets/hires_fix.py", "forge.widgets.hires_task26")
cfg_mod = _load_real("forge/widgets/cfg.py", "forge.widgets.cfg_task26")


# ---------------------------------------------------------------------------
# Small fakes
# ---------------------------------------------------------------------------

def _settings_stub(get_map=None):
    get_map = get_map or {}

    def _get(key, default=None):
        return get_map.get(key, default)

    return SimpleNamespace(get=_get, set=MagicMock(), save=MagicMock(),
                           debounced_save=MagicMock())


def _prompt_stub():
    """Minimal self for PromptWidget.update_for_model (unbound call)."""
    neg = SimpleNamespace(visible=True,
                          setVisible=lambda v: setattr(neg, "visible", v))
    styles = SimpleNamespace(visible=True,
                             setVisible=lambda v: setattr(styles, "visible", v))
    return SimpleNamespace(negative_prompt_text_edit=neg,
                           style_collapsible=styles)


def _cfg_stub():
    label = SimpleNamespace(text="CFG Scale",
                            setText=lambda t: setattr(label, "text", t))
    entry = SimpleNamespace(minimum=0.0, maximum=30.0, enabled=True,
                            value=7.0)
    entry.setMinimum = lambda v: setattr(entry, "minimum", v)
    entry.setMaximum = lambda v: setattr(entry, "maximum", v)
    entry.setEnabled = lambda v: setattr(entry, "enabled", v)
    entry.setValue = lambda v: setattr(entry, "value", v)
    return SimpleNamespace(label=label, cfg_entry=entry,
                           variables={"cfg": 7.0})


# ---------------------------------------------------------------------------
# 1. ModelConfig size constraints per family
# ---------------------------------------------------------------------------

class TestFluxSizeConstraints:
    def test_flux_step_is_16(self):
        cfg = get_model_config(ModelFamily.FLUX)
        assert cfg.size_step == 16

    def test_flux2_step_is_16(self):
        cfg = get_model_config(ModelFamily.FLUX2)
        assert cfg.size_step == 16

    def test_zimage_step_is_16(self):
        cfg = get_model_config(ModelFamily.ZIMAGE)
        assert cfg.size_step == 16

    def test_flux_bounds(self):
        cfg = get_model_config(ModelFamily.FLUX)
        assert cfg.min_size == 512
        assert cfg.default_max_size == 2048

    def test_flux2_bounds(self):
        cfg = get_model_config(ModelFamily.FLUX2)
        assert cfg.min_size == 512
        assert cfg.default_max_size == 2048


class TestSdSizeRegression:
    """Non-Flux families must keep their existing sizing."""

    def test_sd_step_stays_8(self):
        cfg = get_model_config(ModelFamily.SD)
        assert cfg.size_step == 8

    def test_sdxl_step_stays_8(self):
        cfg = get_model_config(ModelFamily.SDXL)
        assert cfg.size_step == 8

    def test_sd_bounds_unchanged(self):
        cfg = get_model_config(ModelFamily.SD)
        assert cfg.min_size == 256
        assert cfg.default_min_size == 512
        assert cfg.default_max_size == 2048

    def test_wan_bounds_unchanged(self):
        cfg = get_model_config(ModelFamily.WAN)
        assert cfg.min_size == 256
        assert cfg.default_max_size == 1024


# ---------------------------------------------------------------------------
# 2. Size-constraint helpers (domain level, Qt-free)
# ---------------------------------------------------------------------------

class TestSizeHelpers:
    def test_get_size_constraints_flux(self):
        from forge.domain import model_registry as reg
        bounds = reg.get_size_constraints(ModelFamily.FLUX)
        assert bounds["step"] == 16
        assert bounds["min"] == 512
        assert bounds["max"] == 2048

    def test_get_size_constraints_sd(self):
        from forge.domain import model_registry as reg
        bounds = reg.get_size_constraints(ModelFamily.SD)
        assert bounds["step"] == 8
        assert bounds["min"] == 256
        assert bounds["max"] == 2048

    def test_snap_to_step_flux(self):
        from forge.domain import model_registry as reg
        assert reg.snap_to_step(1000, 16) == 992  # floor to multiple of 16
        assert reg.snap_to_step(1024, 16) == 1024

    def test_apply_constraints_clamps_and_snaps(self):
        from forge.domain import model_registry as reg
        w, h = reg.apply_size_constraints(ModelFamily.FLUX, 100, 5000)
        assert w % 16 == 0 and h % 16 == 0
        assert 512 <= w <= 2048 and 512 <= h <= 2048

    def test_apply_constraints_sd_unchanged_semantics(self):
        from forge.domain import model_registry as reg
        w, h = reg.apply_size_constraints(ModelFamily.SD, 512, 512)
        assert (w, h) == (512, 512)


# ---------------------------------------------------------------------------
# 3. Hires-fix visibility flags
# ---------------------------------------------------------------------------

class TestHiresFixFlags:
    def test_flux_hides_hires_fix(self):
        assert get_model_config(ModelFamily.FLUX).hide_hires_fix is True

    def test_flux2_hides_hires_fix(self):
        assert get_model_config(ModelFamily.FLUX2).hide_hires_fix is True

    def test_zimage_hides_hires_fix(self):
        assert get_model_config(ModelFamily.ZIMAGE).hide_hires_fix is True

    def test_sd_keeps_hires_fix(self):
        assert get_model_config(ModelFamily.SD).hide_hires_fix is False

    def test_sdxl_keeps_hires_fix(self):
        assert get_model_config(ModelFamily.SDXL).hide_hires_fix is False

    def test_predicate_flux_false(self):
        """hide flag set -> widget visibility predicate false."""
        from forge.domain import model_registry as reg
        assert reg.should_hide_hires_fix(ModelFamily.FLUX) is True
        assert reg.should_hide_hires_fix(ModelFamily.SD) is False

    def test_hires_widget_disables_for_flux(self):
        stub = SimpleNamespace(variables={})
        stub.setEnabled = lambda v: setattr(stub, "enabled", v)
        hires_mod.HiResFixWidget.update_for_family(stub, ModelFamily.FLUX)
        assert stub.enabled is False

    def test_hires_widget_enables_for_sd(self):
        stub = SimpleNamespace(variables={})
        stub.setEnabled = lambda v: setattr(stub, "enabled", v)
        hires_mod.HiResFixWidget.update_for_family(stub, ModelFamily.SD)
        assert stub.enabled is True


# ---------------------------------------------------------------------------
# 4. Prompt visibility routed through ModelConfig flags
# ---------------------------------------------------------------------------

class TestPromptVisibilityFlags:
    def test_flux_hides_negative_and_styles(self):
        assert get_model_config(ModelFamily.FLUX).hide_negative_prompt is True
        assert get_model_config(ModelFamily.FLUX).hide_styles is True

    def test_flux2_hides_negative_and_styles(self):
        assert get_model_config(ModelFamily.FLUX2).hide_negative_prompt is True
        assert get_model_config(ModelFamily.FLUX2).hide_styles is True

    def test_zimage_neg_hidden_styles_visible_per_models_md(self):
        """docs/MODELS.md UI matrix: Z neg hidden, styles VISIBLE."""
        cfg = get_model_config(ModelFamily.ZIMAGE)
        assert cfg.hide_negative_prompt is True
        assert cfg.hide_styles is False

    def test_sd_shows_both(self):
        cfg = get_model_config(ModelFamily.SD)
        assert cfg.hide_negative_prompt is False
        assert cfg.hide_styles is False

    def test_prompt_widget_flux_hides(self):
        stub = _prompt_stub()
        prompts_mod.PromptWidget.update_for_model(stub, "flux-dev-fp8")
        assert stub.negative_prompt_text_edit.visible is False
        assert stub.style_collapsible.visible is False

    def test_prompt_widget_sd_shows(self):
        stub = _prompt_stub()
        prompts_mod.PromptWidget.update_for_model(stub, "v1-5-pruned")
        assert stub.negative_prompt_text_edit.visible is True
        assert stub.style_collapsible.visible is True

    def test_prompt_widget_zimage_neg_hidden_styles_shown(self):
        stub = _prompt_stub()
        prompts_mod.PromptWidget.update_for_model(stub, "z-image-turbo")
        assert stub.negative_prompt_text_edit.visible is False
        assert stub.style_collapsible.visible is True


# ---------------------------------------------------------------------------
# 5. CFG label switching (verify via cfg.py, no duplicate logic)
# ---------------------------------------------------------------------------

class TestCfgLabels:
    def test_flux_distilled_cfg_label(self):
        stub = _cfg_stub()
        cfg_mod.CFGWidget.update_for_model(stub, "flux-dev-fp8")
        assert stub.label.text == "Distilled CFG"

    def test_flux2_distilled_cfg_label(self):
        stub = _cfg_stub()
        cfg_mod.CFGWidget.update_for_model(stub, "flux2-klein-4b")
        assert stub.label.text == "Distilled CFG"

    def test_zimage_cfg_fixed_label(self):
        stub = _cfg_stub()
        cfg_mod.CFGWidget.update_for_model(stub, "z-image-turbo")
        assert stub.label.text == "CFG Scale (fixed)"
        assert stub.cfg_entry.enabled is False

    def test_sd_cfg_label(self):
        stub = _cfg_stub()
        cfg_mod.CFGWidget.update_for_model(stub, "v1-5-pruned")
        assert stub.label.text == "CFG Scale"
        assert stub.cfg_entry.enabled is True


# ---------------------------------------------------------------------------
# 6. architecture_changed end-to-end (detection + flags, no page touch)
# ---------------------------------------------------------------------------

class TestArchitectureChangedWiring:
    def test_detect_flux_triggers_flag_lookup(self):
        family = detect_model_family("flux1-dev.safetensors")
        assert family == ModelFamily.FLUX
        assert get_model_config(family).hide_hires_fix is True
        assert get_model_config(family).size_step == 16

    def test_detect_sd_keeps_defaults(self):
        family = detect_model_family("v1-5-pruned.safetensors")
        assert family == ModelFamily.SD
        assert get_model_config(family).hide_hires_fix is False
        assert get_model_config(family).size_step == 8
