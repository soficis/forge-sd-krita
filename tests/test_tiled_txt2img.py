"""Todo 25: wire tiled generation UI to existing sd_api helpers (Txt2Img only).

Covers:
- default_settings.json carries additive ``tiled.*`` keys (no version bump)
  and SettingsController round-trips them (strict-merge accepts them).
- TiledWidget (fresh stub-Qt real classes): defaults off/64, payload shape,
  below-family-min tile size clamped via existing generation_plan logic,
  set_generation_data reuse, save_settings persistence.
- Shared payload path: GenerateWidget.threadable_run with tiled flag
  delegates to api.tiled_generate (call side only, sd_api untouched);
  flag off -> normal txt2img POST; non-txt2img modes ignore the flag.
- Txt2Img page wires the widget into the generate flow behind a
  collapsible "Tiled (high-res)" section.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import shutil
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from forge.domain.generation_plan import build_generation_plan
from forge.settings_controller import SettingsController


# ---------------------------------------------------------------------------
# Fresh stub-Qt module loader (real classes, not mocks)
# ---------------------------------------------------------------------------

_QT_NAMES = [
    "Qt", "QWidget", "QVBoxLayout", "QHBoxLayout", "QFormLayout",
    "QGridLayout", "QLabel", "QComboBox", "QPushButton", "QCheckBox",
    "QTabWidget", "QGroupBox", "QSlider", "QSpinBox", "QDoubleSpinBox",
    "QPlainTextEdit", "QTextEdit", "QLineEdit", "QScrollArea", "QColor",
    "QPainter", "QByteArray", "QBuffer", "QImage", "QIODevice", "QObject",
    "QThread", "QTimer", "QProgressBar", "pyqtSignal", "QSize", "QIcon",
    "QPixmap", "QPointF", "qAlpha", "qRgb",
]


def _load_real(relpath: str, mod_name: str, package: str):
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
        path = (
            pathlib.Path(__file__).resolve().parent.parent / relpath
        )
        spec = importlib.util.spec_from_file_location(mod_name, str(path))
        mod = importlib.util.module_from_spec(spec)
        mod.__package__ = package
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


generate_mod = _load_real(
    "forge/widgets/generate.py", "forge.widgets.generate_task25",
    "forge.widgets",
)
tiled_mod = _load_real(
    "forge/widgets/tiled.py", "forge.widgets.tiled_task25",
    "forge.widgets",
)


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

def _fake_settings(store: dict):
    """Dict-backed settings_controller stand-in (dotted-path get/set)."""
    saved = {}

    def _walk(path, create=False):
        node = store
        keys = [p for p in path.split(".") if p]
        for key in keys[:-1]:
            if key not in node:
                if not create:
                    raise KeyError(path)
                node[key] = {}
            node = node[key]
        return node, keys[-1]

    def get(path, default=None):
        try:
            node, leaf = _walk(path)
            return node[leaf]
        except (KeyError, TypeError):
            if default is not None:
                return default
            raise

    def set_(path, value):
        node, leaf = _walk(path)
        if leaf not in node:
            raise KeyError(path)
        node[leaf] = value

    fake = SimpleNamespace(
        get=get,
        set=set_,
        debounced_save=lambda: saved.setdefault("calls", 0) or saved.update(calls=saved.get("calls", 0) + 1),
        _store=store,
        _saved=saved,
    )
    return fake


def _settings_store(**overrides):
    with open(REPO_ROOT / "forge" / "default_settings.json", encoding="utf-8") as fh:
        store = json.load(fh)
    for path, value in overrides.items():
        node = store
        keys = path.split(".")
        for key in keys[:-1]:
            node = node[key]
        node[keys[-1]] = value
    return store


def _gen_self(**overrides):
    stub = SimpleNamespace(
        api=SimpleNamespace(defaults={"model": "dreamshaper"}, samplers=[]),
        mode="txt2img",
        results=None,
    )
    stub.GENERATION_ENDPOINT_BY_MODE = (
        generate_mod.GenerateWidget.GENERATION_ENDPOINT_BY_MODE)
    for key, value in overrides.items():
        setattr(stub, key, value)
    return stub


# ---------------------------------------------------------------------------
# default_settings schema + round-trip
# ---------------------------------------------------------------------------

class TestTiledDefaults:
    def test_really_real_classes(self):
        assert isinstance(tiled_mod.TiledWidget, type)

    def test_default_settings_has_tiled_section(self):
        with open(REPO_ROOT / "forge" / "default_settings.json", encoding="utf-8") as fh:
            defaults = json.load(fh)
        tiled = defaults["tiled"]
        assert tiled["enabled"] is False
        assert tiled["tile_size"] in (512, 768, 1024)
        assert tiled["overlap"] == 64
        assert "_schema_version" not in defaults

    def test_settings_controller_round_trips_tiled_keys(self, tmp_path):
        shutil.copy(
            REPO_ROOT / "forge" / "default_settings.json",
            tmp_path / "default_settings.json",
        )
        controller = SettingsController(base_dir=tmp_path)
        assert controller.get("tiled.enabled") is False
        assert controller.get("tiled.overlap") == 64
        controller.set("tiled.enabled", True)
        controller.set("tiled.tile_size", 768)
        controller.set("tiled.overlap", 96)
        controller.save()
        reloaded = SettingsController(base_dir=tmp_path)
        assert reloaded.get("tiled.enabled") is True
        assert reloaded.get("tiled.tile_size") == 768
        assert reloaded.get("tiled.overlap") == 96


# ---------------------------------------------------------------------------
# TiledWidget payload shape + clamp
# ---------------------------------------------------------------------------

class TestTiledWidget:
    def _widget(self, **overrides):
        store = _settings_store(**overrides)
        fake = _fake_settings(store)
        widget = tiled_mod.TiledWidget.__new__(tiled_mod.TiledWidget)
        tiled_mod.TiledWidget.__init__(widget, fake, SimpleNamespace())
        return widget, fake

    def test_defaults_off(self):
        widget, _ = self._widget()
        assert widget.variables["enabled"] is False
        assert widget.variables["overlap"] == 64
        assert widget.variables["tile_size"] in (512, 768, 1024)

    def test_disabled_emits_flag_off(self):
        widget, _ = self._widget()
        data = widget.get_generation_data()
        assert data["tiled_enabled"] is False

    def test_enabled_emits_payload(self):
        widget, _ = self._widget()
        widget.variables["enabled"] = True
        widget.variables["tile_size"] = 768
        widget.variables["overlap"] = 64
        data = widget.get_generation_data()
        assert data == {
            "tiled_enabled": True,
            "tiled_tile_size": 768,
            "tiled_overlap": 64,
        }

    def test_tile_size_below_family_min_clamps(self):
        widget, _ = self._widget(**{"defaults.min_size": 768})
        widget.variables["enabled"] = True
        widget.variables["tile_size"] = 512
        data = widget.get_generation_data()
        assert data["tiled_tile_size"] == 768

    def test_set_generation_data_reuses(self):
        widget, _ = self._widget()
        widget.set_generation_data({
            "tiled_enabled": True,
            "tiled_tile_size": 1024,
            "tiled_overlap": 32,
        })
        assert widget.variables["enabled"] is True
        assert widget.variables["tile_size"] == 1024
        assert widget.variables["overlap"] == 32
        data = widget.get_generation_data()
        assert data["tiled_tile_size"] == 1024
        assert data["tiled_overlap"] == 32

    def test_save_settings_persists(self):
        widget, fake = self._widget()
        widget.variables["enabled"] = True
        widget.variables["tile_size"] = 1024
        widget.variables["overlap"] = 96
        widget.save_settings()
        assert fake.get("tiled.enabled") is True
        assert fake.get("tiled.tile_size") == 1024
        assert fake.get("tiled.overlap") == 96


# ---------------------------------------------------------------------------
# Shared payload path dispatch
# ---------------------------------------------------------------------------

class TestTiledDispatch:
    def test_tiled_flag_delegates_to_tiled_generate(self):
        api = SimpleNamespace(
            txt2img=MagicMock(return_value={"images": []}),
            tiled_generate=MagicMock(return_value={"images": ["x"]}),
        )
        stub = _gen_self(api=api)
        data = {
            "prompt": "cat",
            "tiled_enabled": True,
            "tiled_tile_size": 768,
            "tiled_overlap": 64,
        }
        generate_mod.GenerateWidget.threadable_run(stub, data)
        api.tiled_generate.assert_called_once()
        (payload,), kwargs = api.tiled_generate.call_args
        assert payload == {"prompt": "cat"}
        assert kwargs == {"tile_size": 768, "overlap": 64}
        api.txt2img.assert_not_called()
        # Original job data keeps tiled keys for history/reuse.
        assert data["tiled_enabled"] is True

    def test_flag_off_posts_normal_txt2img(self):
        api = SimpleNamespace(
            txt2img=MagicMock(return_value={"images": []}),
            tiled_generate=MagicMock(),
        )
        stub = _gen_self(api=api)
        data = {"prompt": "cat", "tiled_enabled": False}
        generate_mod.GenerateWidget.threadable_run(stub, data)
        api.txt2img.assert_called_once_with({"prompt": "cat"})
        api.tiled_generate.assert_not_called()

    def test_no_flag_posts_normal_txt2img(self):
        api = SimpleNamespace(
            txt2img=MagicMock(return_value={"images": []}),
            tiled_generate=MagicMock(),
        )
        stub = _gen_self(api=api)
        generate_mod.GenerateWidget.threadable_run(stub, {"prompt": "cat"})
        api.txt2img.assert_called_once_with({"prompt": "cat"})
        api.tiled_generate.assert_not_called()

    def test_non_txt2img_mode_ignores_tiled_flag(self):
        api = SimpleNamespace(
            img2img=MagicMock(return_value={"images": []}),
            tiled_generate=MagicMock(),
        )
        stub = _gen_self(api=api, mode="img2img")
        generate_mod.GenerateWidget.threadable_run(stub, {
            "prompt": "cat",
            "tiled_enabled": True,
            "tiled_tile_size": 768,
            "tiled_overlap": 64,
        })
        api.img2img.assert_called_once_with({"prompt": "cat"})
        api.tiled_generate.assert_not_called()


# ---------------------------------------------------------------------------
# Existing clamp logic still applies (regression guard)
# ---------------------------------------------------------------------------

class TestGenerationPlanClamp:
    def test_tile_size_below_family_min_clamps(self):
        plan = build_generation_plan(
            width=256,
            height=256,
            min_size=512,
            max_size=2048,
            enable_max_size=True,
        )
        assert (plan.request_width, plan.request_height) == (512, 512)

    def test_tile_size_above_max_clamps(self):
        plan = build_generation_plan(
            width=2048,
            height=2048,
            min_size=512,
            max_size=1024,
            enable_max_size=True,
        )
        assert (plan.request_width, plan.request_height) == (1024, 1024)


# ---------------------------------------------------------------------------
# Txt2Img page wiring
# ---------------------------------------------------------------------------

class TestTxt2ImgPageWiring:
    def test_page_source_has_tiled_collapsible(self):
        source = (
            REPO_ROOT / "forge" / "pages" / "txt2img.py"
        ).read_text(encoding="utf-8")
        assert "Tiled (high-res)" in source
        assert "tiled_widget" in source

    def test_tiled_widget_exported_from_widgets_package(self):
        import forge.widgets as widgets_pkg
        assert hasattr(widgets_pkg, "TiledWidget")
