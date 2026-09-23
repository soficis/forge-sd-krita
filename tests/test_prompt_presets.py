"""Todo 27 (artist tools, phase 2): Prompt Presets widget with settings-backed CRUD.

Failing-first: ``forge/widgets/prompt_presets.py`` does not exist,
``default_settings.json`` carries no ``presets`` object or
``hide_ui.prompt_presets`` key, and the txt2img/img2img pages do not compose
the widget, so every test below fails until todo 27 is implemented.

Covers:
- default_settings.json gains an additive ``presets`` object (name ->
  {prompt, negative}) plus ``hide_ui.prompt_presets``; no schema version bump.
- SettingsController round-trip for save/load/rename/delete, including a
  reload from disk (strict-merge must not drop open-map entries).
- 50-preset cap: the 51st *new* preset raises a typed error and leaves the
  stored count at 50; overwriting an existing name at the cap still works.
- Deleting/renaming a missing preset is a graceful no-op (no KeyError escape).
- PromptPresetsWidget (fresh stub-Qt real classes, same pattern as
  test_tiled_txt2img.py): get/set_generation_data expose the preset selection;
  save reads the prompt boxes via PromptWidget.get_generation_data, load merges
  back via PromptWidget.set_generation_data; cap errors surface in last_error.
- Page composition: txt2img/img2img sources wire PromptPresetsWidget behind
  hide_ui.prompt_presets; the widget is exported from forge.widgets; the page
  modules import cleanly under conftest-mocked Qt.
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

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load_real(relpath: str, mod_name: str, package: str):
    """Import a forge module fresh with stub-Qt classes; return it.

    Returns None when the file does not exist yet (failing-first runs).
    """
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

    path = REPO_ROOT / relpath
    if not path.is_file():
        return None

    pre_keys = set(sys.modules)
    old = sys.modules.get("forge.qt_compat")
    sys.modules["forge.qt_compat"] = stub
    try:
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


presets_mod = _load_real(
    "forge/widgets/prompt_presets.py",
    "forge.widgets.prompt_presets_task27",
    "forge.widgets",
)


def _mod():
    """Return the loaded module or fail loudly (red pre-implementation)."""
    assert presets_mod is not None, (
        "forge/widgets/prompt_presets.py is not implemented yet (todo 27)"
    )
    return presets_mod


def _load_defaults() -> dict:
    with open(REPO_ROOT / "forge" / "default_settings.json", encoding="utf-8") as fh:
        return json.load(fh)


def _controller(tmp_path) -> SettingsController:
    shutil.copy(
        REPO_ROOT / "forge" / "default_settings.json",
        tmp_path / "default_settings.json",
    )
    return SettingsController(base_dir=tmp_path)


# ---------------------------------------------------------------------------
# default_settings schema
# ---------------------------------------------------------------------------

class TestPresetsDefaults:
    def test_default_settings_has_presets_object(self):
        defaults = _load_defaults()
        assert isinstance(defaults["presets"], dict)
        assert defaults["presets"] == {}

    def test_default_settings_has_hide_ui_prompt_presets(self):
        defaults = _load_defaults()
        assert defaults["hide_ui"]["prompt_presets"] is False

    def test_no_schema_version_bump(self):
        defaults = _load_defaults()
        assert "_schema_version" not in defaults


# ---------------------------------------------------------------------------
# Settings-backed CRUD (real SettingsController over tmp dirs)
# ---------------------------------------------------------------------------

class TestPresetCrud:
    def test_save_and_get_round_trip(self, tmp_path):
        mod = _mod()
        controller = _controller(tmp_path)
        mod.save_preset(controller, "Anime", "1girl, solo", "lowres, blurry")
        entry = mod.get_preset(controller, "Anime")
        assert entry == {"prompt": "1girl, solo", "negative": "lowres, blurry"}
        assert controller.get("presets")["Anime"]["prompt"] == "1girl, solo"

    def test_reload_from_disk_preserves_presets(self, tmp_path):
        mod = _mod()
        controller = _controller(tmp_path)
        mod.save_preset(controller, "Landscape", "mountains", "")
        reloaded = SettingsController(base_dir=tmp_path)
        assert mod.get_preset(reloaded, "Landscape") == {
            "prompt": "mountains",
            "negative": "",
        }

    def test_rename_round_trip(self, tmp_path):
        mod = _mod()
        controller = _controller(tmp_path)
        mod.save_preset(controller, "Old", "p", "n")
        assert mod.rename_preset(controller, "Old", "New") is True
        assert mod.get_preset(controller, "Old") is None
        assert mod.get_preset(controller, "New") == {"prompt": "p", "negative": "n"}
        reloaded = SettingsController(base_dir=tmp_path)
        assert mod.get_preset(reloaded, "New") == {"prompt": "p", "negative": "n"}

    def test_delete_round_trip(self, tmp_path):
        mod = _mod()
        controller = _controller(tmp_path)
        mod.save_preset(controller, "Doomed", "p", "n")
        assert mod.delete_preset(controller, "Doomed") is True
        assert mod.get_preset(controller, "Doomed") is None
        reloaded = SettingsController(base_dir=tmp_path)
        assert mod.get_preset(reloaded, "Doomed") is None

    def test_delete_missing_is_graceful_noop(self, tmp_path):
        mod = _mod()
        controller = _controller(tmp_path)
        assert mod.delete_preset(controller, "ghost") is False

    def test_rename_missing_is_graceful_noop(self, tmp_path):
        mod = _mod()
        controller = _controller(tmp_path)
        assert mod.rename_preset(controller, "ghost", "other") is False

    def test_get_missing_returns_none(self, tmp_path):
        mod = _mod()
        controller = _controller(tmp_path)
        assert mod.get_preset(controller, "ghost") is None

    def test_empty_name_raises_value_error(self, tmp_path):
        mod = _mod()
        controller = _controller(tmp_path)
        with pytest.raises(ValueError):
            mod.save_preset(controller, "", "p", "")
        with pytest.raises(ValueError):
            mod.save_preset(controller, "   ", "p", "")

    def test_cap_50_new_presets_ok_51st_raises(self, tmp_path):
        mod = _mod()
        controller = _controller(tmp_path)
        for index in range(mod.MAX_PRESETS):
            mod.save_preset(controller, "p%02d" % index, "prompt", "")
        assert len(controller.get("presets")) == mod.MAX_PRESETS

        with pytest.raises(mod.PresetLimitError) as excinfo:
            mod.save_preset(controller, "p51", "one too many", "")
        assert str(mod.MAX_PRESETS) in str(excinfo.value)
        # Failed save must not corrupt or grow the stored map.
        assert len(controller.get("presets")) == mod.MAX_PRESETS
        assert mod.get_preset(controller, "p51") is None

    def test_overwrite_existing_at_cap_allowed(self, tmp_path):
        mod = _mod()
        controller = _controller(tmp_path)
        for index in range(mod.MAX_PRESETS):
            mod.save_preset(controller, "p%02d" % index, "prompt", "")
        mod.save_preset(controller, "p00", "updated prompt", "neg")
        assert len(controller.get("presets")) == mod.MAX_PRESETS
        assert mod.get_preset(controller, "p00") == {
            "prompt": "updated prompt",
            "negative": "neg",
        }

    def test_strict_merge_still_drops_unknown_keys(self, tmp_path):
        mod = _mod()
        _controller(tmp_path)
        user_path = tmp_path / "user_settings.json"
        payload = json.loads(user_path.read_text(encoding="utf-8")) if user_path.is_file() else {}
        payload["presets"] = {"Kept": {"prompt": "p", "negative": "n"}}
        payload["server"] = {"unknown_key": "value"}
        payload["extra_top_level"] = True
        user_path.write_text(json.dumps(payload), encoding="utf-8")

        controller = SettingsController(base_dir=tmp_path)
        assert mod.get_preset(controller, "Kept") == {"prompt": "p", "negative": "n"}
        assert controller.has("server.unknown_key") is False
        assert controller.has("extra_top_level") is False


# ---------------------------------------------------------------------------
# PromptPresetsWidget (fresh stub-Qt real classes)
# ---------------------------------------------------------------------------

class TestPromptPresetsWidget:
    def _widget(self, tmp_path, prompt_data=None):
        mod = _mod()
        controller = _controller(tmp_path)
        prompt_data = prompt_data or {
            "prompt": "a cat",
            "negative_prompt": "blurry",
        }
        prompt_widget = MagicMock()
        prompt_widget.get_generation_data.return_value = prompt_data
        widget = mod.PromptPresetsWidget.__new__(mod.PromptPresetsWidget)
        mod.PromptPresetsWidget.__init__(widget, controller, prompt_widget)
        return widget, controller, prompt_widget

    def test_really_real_class(self):
        mod = _mod()
        assert isinstance(mod.PromptPresetsWidget, type)

    def test_get_generation_data_default_is_empty_selection(self, tmp_path):
        widget, _, _ = self._widget(tmp_path)
        assert widget.get_generation_data() == {"preset": ""}

    def test_set_get_generation_data_round_trip(self, tmp_path):
        widget, _, _ = self._widget(tmp_path)
        widget.set_generation_data({"preset": "Anime"})
        assert widget.get_generation_data() == {"preset": "Anime"}

    def test_set_generation_data_nondict_ignored(self, tmp_path):
        widget, _, _ = self._widget(tmp_path)
        widget.set_generation_data(["junk"])
        widget.set_generation_data(None)
        assert widget.get_generation_data() == {"preset": ""}

    def test_on_save_stores_current_prompt(self, tmp_path):
        mod = _mod()
        widget, controller, _ = self._widget(tmp_path)
        assert widget.on_save("Mine") is True
        assert widget.last_error == ""
        assert mod.get_preset(controller, "Mine") == {
            "prompt": "a cat",
            "negative": "blurry",
        }

    def test_on_save_at_cap_surfaces_clear_error(self, tmp_path):
        mod = _mod()
        widget, controller, _ = self._widget(tmp_path)
        for index in range(mod.MAX_PRESETS):
            mod.save_preset(controller, "p%02d" % index, "prompt", "")
        assert widget.on_save("p51") is False
        assert str(mod.MAX_PRESETS) in widget.last_error
        assert len(controller.get("presets")) == mod.MAX_PRESETS

    def test_on_load_merges_into_prompt_widget(self, tmp_path):
        mod = _mod()
        widget, controller, prompt_widget = self._widget(tmp_path)
        mod.save_preset(controller, "Mine", "1girl", "lowres")
        assert widget.on_load("Mine") is True
        prompt_widget.set_generation_data.assert_called_once_with(
            {"prompt": "1girl", "negative_prompt": "lowres"}
        )
        assert widget.last_error == ""

    def test_on_load_missing_is_noop_with_error(self, tmp_path):
        widget, _, prompt_widget = self._widget(tmp_path)
        assert widget.on_load("ghost") is False
        prompt_widget.set_generation_data.assert_not_called()
        assert widget.last_error != ""

    def test_on_rename_and_delete_flows(self, tmp_path):
        mod = _mod()
        widget, controller, _ = self._widget(tmp_path)
        mod.save_preset(controller, "Old", "p", "n")
        assert widget.on_rename("New", "Old") is True
        assert mod.get_preset(controller, "New") == {"prompt": "p", "negative": "n"}
        assert widget.on_delete("New") is True
        assert mod.get_preset(controller, "New") is None
        assert widget.on_delete("New") is False  # second delete: graceful no-op
        assert widget.last_error != ""


# ---------------------------------------------------------------------------
# Page composition (conftest-mocked Qt)
# ---------------------------------------------------------------------------

class TestPageComposition:
    @pytest.mark.parametrize("pagename", ["txt2img", "img2img"])
    def test_page_source_wires_widget_behind_hide_ui(self, pagename):
        source = (REPO_ROOT / "forge" / "pages" / ("%s.py" % pagename)).read_text(
            encoding="utf-8"
        )
        assert "PromptPresetsWidget" in source
        assert "prompt_presets_widget" in source
        assert "hide_ui.prompt_presets" in source
        assert "Prompt Presets" in source

    def test_page_source_adds_widget_to_generation_list(self):
        for pagename in ("txt2img", "img2img"):
            source = (
                REPO_ROOT / "forge" / "pages" / ("%s.py" % pagename)
            ).read_text(encoding="utf-8")
            assert "self.prompt_presets_widget" in source
            # The widget participates in generation data / history reuse.
            assert source.count("self.widgets") >= 1

    def test_widget_exported_from_widgets_package(self):
        import forge.widgets as widgets_pkg
        assert hasattr(widgets_pkg, "PromptPresetsWidget")

    def test_txt2img_page_module_imports_cleanly(self):
        from forge.pages import txt2img as txt2img_page
        assert hasattr(txt2img_page, "Txt2ImgPage")

    def test_img2img_page_module_imports_cleanly(self):
        from forge.pages import img2img as img2img_page
        assert hasattr(img2img_page, "Img2ImgPage")
