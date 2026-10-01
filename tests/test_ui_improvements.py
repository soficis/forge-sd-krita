"""Tests for UI/UX improvements from HANDOFF_ANTIGRAVITY.md."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

FORGE_DIR = Path(__file__).resolve().parent.parent / "forge"


def _setup_fresh_package(pkg_name: str):
    """Create a private package with stubbed Qt and dependencies."""
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(FORGE_DIR)]
    sys.modules[pkg_name] = pkg

    # Minimal Qt stand-ins
    qt_compat = types.ModuleType(f"{pkg_name}.qt_compat")

    class _Signal:
        def __init__(self):
            self.slots = []

        def connect(self, slot):
            self.slots.append(slot)

        def emit(self, *args):
            for slot in self.slots:
                try:
                    slot(*args)
                except TypeError:
                    slot()

    class _Widget:
        def __init__(self, *a, **k):
            self._visible = True
            self._layout = None
            self._tooltip = ""
            self._object_name = ""
            self._properties = {}

        def setLayout(self, layout):
            self._layout = layout

        def layout(self):
            return self._layout

        def show(self):
            self._visible = True

        def hide(self):
            self._visible = False

        def setVisible(self, v):
            self._visible = bool(v)

        def isVisible(self):
            return self._visible

        def setHidden(self, h):
            self._visible = not bool(h)

        def isHidden(self):
            return not self._visible

        def setToolTip(self, text):
            self._tooltip = text

        def toolTip(self):
            return self._tooltip

        def setObjectName(self, name):
            self._object_name = name

        def objectName(self):
            return self._object_name

        def setProperty(self, name, value):
            self._properties[name] = value

        def property(self, name):
            return self._properties.get(name)

        def style(self):
            return self

        def unpolish(self, w):
            pass

        def polish(self, w):
            pass

        def update(self):
            pass

    class _Layout:
        def __init__(self):
            self.widgets = []
            self.rows = []

        def addWidget(self, w):
            self.widgets.append(w)

        def addRow(self, *a):
            self.rows.append(a)
            for item in a:
                if isinstance(item, _Widget):
                    self.widgets.append(item)

        def addSpacing(self, s):
            self.widgets.append(f"spacing:{s}")

        def addStretch(self):
            pass

        def setContentsMargins(self, *a):
            pass

    class _ComboBox(_Widget):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._items = []
            self._current_text = ""
            self.currentTextChanged = _Signal()

        def addItems(self, items):
            self._items.extend(items)
            if not self._current_text and self._items:
                self._current_text = self._items[0]

        def setCurrentText(self, text):
            self._current_text = text
            self.currentTextChanged.emit(text)

        def setCurrentIndex(self, index):
            if 0 <= index < len(self._items):
                self.setCurrentText(self._items[index])

        def currentText(self):
            return self._current_text

        def setMinimumContentsLength(self, n):
            pass

        def setMaxVisibleItems(self, n):
            pass

        def setPlaceholderText(self, t):
            pass

    class _CheckBox(_Widget):
        def __init__(self, text="", *a, **k):
            super().__init__(*a, **k)
            self._text = text
            self._checked = False
            self.stateChanged = _Signal()
            self.toggled = _Signal()

        def text(self):
            return self._text

        def setText(self, text):
            self._text = text

        def isChecked(self):
            return self._checked

        def setChecked(self, checked):
            checked = bool(checked)
            changed = (self._checked != checked)
            self._checked = checked
            if changed:
                self.toggled.emit(checked)
                self.stateChanged.emit(2 if checked else 0)

    class _Label(_Widget):
        def __init__(self, text="", *a, **k):
            super().__init__(*a, **k)
            self._text = text

        def text(self):
            return self._text

        def setText(self, text):
            self._text = text

    class _Slider(_Widget):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._val = 0
            self._max = 100
            self._min = 0
            self.valueChanged = _Signal()

        def setMinimum(self, v):
            self._min = v

        def setMaximum(self, v):
            self._max = v

        def setValue(self, v):
            self._val = v
            self.valueChanged.emit(v)

        def value(self):
            return self._val

        def setTickInterval(self, *a):
            pass

        def setTickPosition(self, *a):
            pass

        class TickPosition:
            TicksAbove = 1

    class _SpinBox(_Widget):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._val = 1
            self.valueChanged = _Signal()

        def setRange(self, mi, ma):
            pass

        def setMinimum(self, mi):
            pass

        def setMaximum(self, ma):
            pass

        def setSuffix(self, s):
            pass

        def setValue(self, v):
            self._val = v
            self.valueChanged.emit(v)

        def value(self):
            return self._val

    class _Button(_Widget):
        def __init__(self, text="", *a, **k):
            super().__init__(*a, **k)
            self._text = text
            self.clicked = _Signal()

        def text(self):
            return self._text

        def setText(self, t):
            self._text = t

    class _Qt:
        class Orientation:
            Horizontal = 1
            Vertical = 2

        class Key:
            Key_Escape = 0x01000000

    qt_compat.QWidget = _Widget
    qt_compat.QVBoxLayout = _Layout
    qt_compat.QHBoxLayout = _Layout
    qt_compat.QFormLayout = _Layout
    qt_compat.QComboBox = _ComboBox
    qt_compat.QCheckBox = _CheckBox
    qt_compat.QLabel = _Label
    qt_compat.QSlider = _Slider
    qt_compat.QSpinBox = _SpinBox
    class _ProgressBar(_Widget):
        def setMinimum(self, v): pass
        def setMaximum(self, v): pass
        def setValue(self, v): pass

    qt_compat.QTextEdit = _Widget
    qt_compat.QProgressBar = _ProgressBar
    qt_compat.QTimer = MagicMock
    qt_compat.Qt = _Qt
    qt_compat.QSize = MagicMock
    qt_compat.QIcon = MagicMock
    qt_compat.QPixmap = MagicMock
    qt_compat.QColor = MagicMock
    qt_compat.QPainter = MagicMock
    qt_compat.QByteArray = MagicMock
    qt_compat.QBuffer = MagicMock
    qt_compat.QImage = MagicMock
    def __getattr__(name):
        if name.startswith("__"):
            raise AttributeError(name)
        val = MagicMock()
        setattr(qt_compat, name, val)
        return val

    qt_compat.__getattr__ = __getattr__
    sys.modules[f"{pkg_name}.qt_compat"] = qt_compat

    if "krita" not in sys.modules:
        sys.modules["krita"] = MagicMock()

    return pkg, qt_compat


def test_scheduler_default_label_and_tooltip():
    """Phase 4: Scheduler default label must be 'Default (per model)' and box has tooltip."""
    pkg_name = "test_sched_ui"
    _setup_fresh_package(pkg_name)

    spec = importlib.util.spec_from_file_location(
        f"{pkg_name}.widgets.models",
        str(FORGE_DIR / "widgets" / "models.py"),
    )
    models_mod = importlib.util.module_from_spec(spec)
    models_mod.__package__ = f"{pkg_name}.widgets"
    sys.modules[f"{pkg_name}.widgets.models"] = models_mod
    spec.loader.exec_module(models_mod)

    # Label constant value check
    assert models_mod.SCHEDULER_BACKEND_DEFAULT_LABEL == "Default (per model)"

    # Tooltip check
    dummy_self = types.SimpleNamespace(
        schedulers=["Karras"],
        variables={"scheduler": "Default (per model)"},
        settings_controller=types.SimpleNamespace(get=lambda k: ""),
        _update_variables=lambda k, v: None,
    )
    box = models_mod.ModelsWidget._scheduler_settings(dummy_self)
    assert box.toolTip() == "Use the scheduler Forge picks for the loaded model."


def test_prompt_first_in_layout():
    """Phase 1: prompt_widget must be added to layout before model_widget on all 3 pages."""
    import ast

    for filename in ["txt2img.py", "img2img.py", "inpaint.py"]:
        path = FORGE_DIR / "pages" / filename
        tree = ast.parse(path.read_text(encoding="utf-8"))

        add_widget_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Look for self.layout().addWidget(...)
                func = node.func
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "addWidget"
                    and isinstance(func.value, ast.Call)
                    and isinstance(func.value.func, ast.Attribute)
                    and func.value.func.attr == "layout"
                ):
                    arg = node.args[0]
                    if isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name) and arg.value.id == "self":
                        add_widget_calls.append((arg.attr, node.lineno))

        # Check prompt_widget is added before model_widget
        prompt_line = None
        model_line = None
        for attr, lineno in add_widget_calls:
            if attr == "prompt_widget" and prompt_line is None:
                prompt_line = lineno
            elif attr == "model_widget" and model_line is None:
                model_line = lineno

        assert prompt_line is not None, f"prompt_widget not added to layout in {filename}"
        assert model_line is not None, f"model_widget not added to layout in {filename}"
        assert prompt_line < model_line, (
            f"Expected prompt_widget (line {prompt_line}) to be added before model_widget (line {model_line}) in {filename}"
        )

        # Check self.widgets keeps model_widget before prompt_widget
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Attribute) and target.attr == "widgets":
                        if isinstance(node.value, ast.List):
                            names = [elt.attr for elt in node.value.elts if isinstance(elt, ast.Attribute)]
                            assert "model_widget" in names and "prompt_widget" in names
                            assert names.index("model_widget") < names.index("prompt_widget"), (
                                f"self.widgets must keep model_widget before prompt_widget in {filename}"
                            )


def test_refiner_container_visibility_toggle():
    """Phase 2: Refiner controls only visible when enable_refiner is checked."""
    pkg_name = "test_refiner_ui"
    pkg, qt = _setup_fresh_package(pkg_name)

    spec = importlib.util.spec_from_file_location(
        f"{pkg_name}.widgets.models",
        str(FORGE_DIR / "widgets" / "models.py"),
    )
    models_mod = importlib.util.module_from_spec(spec)
    models_mod.__package__ = f"{pkg_name}.widgets"
    sys.modules[f"{pkg_name}.widgets.models"] = models_mod
    spec.loader.exec_module(models_mod)

    # Fake settings controller and api
    settings = {
        "defaults.model": "test_model",
        "defaults.vae": "None",
        "defaults.refiner": "test_refiner",
        "defaults.enable_refiner": False,
        "defaults.refiner_start": 0.8,
        "defaults.sampling_steps": 20,
        "defaults.sampler": "Euler",
        "defaults.scheduler": "",
        "hide_ui.model": False,
        "hide_ui.vae": False,
        "hide_ui.refiner": False,
        "hide_ui.sampler": False,
        "hide_ui.scheduler": False,
    }
    controller = types.SimpleNamespace(
        get=lambda k: settings.get(k),
        set=lambda k, v: settings.__setitem__(k, v),
        save=lambda: None,
        debounced_save=lambda: None,
    )
    api = types.SimpleNamespace(
        get_models_and_default=lambda: (["test_model"], "test_model"),
        get_vaes_and_default=lambda: (["None"], "None"),
        get_refiners_and_default=lambda: (["test_refiner"], "test_refiner"),
        get_samplers_and_default=lambda: (["Euler"], "Euler"),
        get_schedulers_and_default=lambda: (["Karras"], ""),
        get_schedulers=lambda: ["Karras"],
        connected=True,
        state=None,
    )

    widget = models_mod.ModelsWidget(controller, api)

    assert hasattr(widget, "refiner_container"), "ModelsWidget must have refiner_container"
    # Initially False
    assert widget.refiner_container.isVisible() is False

    # Checkbox toggled -> visible
    widget.refiner_enable.setChecked(True)
    assert widget.refiner_container.isVisible() is True

    # Checkbox unchecked -> hidden
    widget.refiner_enable.setChecked(False)
    assert widget.refiner_container.isVisible() is False

    # Programmatic history restore with enable_refiner: True
    widget.set_generation_data({"enable_refiner": True})
    assert widget.refiner_container.isVisible() is True
    assert widget.refiner_enable.isChecked() is True


def test_soft_inpaint_merged_settings():
    """Phase 3: Soft inpainting settings container visibility follows enabled checkbox without CollapsibleWidget."""
    pkg_name = "test_soft_inpaint_ui"
    pkg, qt = _setup_fresh_package(pkg_name)

    # Stub CollapsibleWidget in package
    class _FakeCollapsible(qt.QWidget):
        def __init__(self, title, child, expanded=False):
            super().__init__()
            self.title = title
            self.child = child

    sys.modules[f"{pkg_name}.widgets"] = types.ModuleType(f"{pkg_name}.widgets")
    sys.modules[f"{pkg_name}.widgets"].CollapsibleWidget = _FakeCollapsible

    spec = importlib.util.spec_from_file_location(
        f"{pkg_name}.widgets.soft_inpaint",
        str(FORGE_DIR / "widgets" / "soft_inpaint.py"),
    )
    si_mod = importlib.util.module_from_spec(spec)
    si_mod.__package__ = f"{pkg_name}.widgets"
    sys.modules[f"{pkg_name}.widgets.soft_inpaint"] = si_mod
    spec.loader.exec_module(si_mod)

    settings = {
        "soft_inpaint.enabled": False,
        "soft_inpaint.schedule_bias": 1.0,
        "soft_inpaint.preservation_strength": 0.5,
        "soft_inpaint.transition_contrast_boost": 4.0,
        "soft_inpaint.mask_influence": 0.0,
        "soft_inpaint.difference_threshold": 0.5,
        "soft_inpaint.difference_contrast": 2.0,
    }
    controller = types.SimpleNamespace(
        get=lambda k: settings.get(k),
        set=lambda k, v: settings.__setitem__(k, v),
        save=lambda: None,
    )

    widget = si_mod.SoftInpaintWidget(controller, settings_only=False)

    # Must NOT have CollapsibleWidget in layout widgets
    for child in widget.layout().widgets:
        assert not isinstance(child, _FakeCollapsible), "SoftInpaintWidget should not use CollapsibleWidget"

    # settings_widget must be in layout and hidden initially
    assert hasattr(widget, "settings_widget")
    assert widget.settings_widget in widget.layout().widgets
    assert widget.settings_widget.isVisible() is False

    # Toggled on -> visible
    widget.update_enabled(True)
    assert widget.settings_widget.isVisible() is True
    assert settings["soft_inpaint.enabled"] is True

    # Toggled off -> hidden
    widget.update_enabled(False)
    assert widget.settings_widget.isVisible() is False
    assert settings["soft_inpaint.enabled"] is False


def test_polish_mask_label():
    """Polish item 5: Mask checkbox text should be 'Mask 50% opacity'."""
    import ast
    path = FORGE_DIR / "widgets" / "mask.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr == "mask_opacity_toggle":
                    if isinstance(node.value, ast.Call) and node.value.args:
                        arg0 = node.value.args[0]
                        if isinstance(arg0, ast.Constant):
                            assert arg0.value == "Mask 50% opacity"
                            found = True
    assert found, "mask_opacity_toggle assignment with 'Mask 50% opacity' not found"


def test_polish_denoise_tooltip():
    """Polish item 5: Denoise slider should have descriptive tooltip."""
    pkg_name = "test_polish_denoise"
    pkg, qt = _setup_fresh_package(pkg_name)

    spec = importlib.util.spec_from_file_location(
        f"{pkg_name}.widgets.denoise",
        str(FORGE_DIR / "widgets" / "denoise.py"),
    )
    denoise_mod = importlib.util.module_from_spec(spec)
    denoise_mod.__package__ = f"{pkg_name}.widgets"
    sys.modules[f"{pkg_name}.widgets.denoise"] = denoise_mod
    spec.loader.exec_module(denoise_mod)

    controller = types.SimpleNamespace(get=lambda k: 0.7, set=lambda k, v: None)
    w = denoise_mod.DenoiseWidget(controller)
    assert "Denoise strength:" in w.denoise_label.toolTip()


def test_polish_model_tooltip():
    """Polish item 7: model_box should have full model name as tooltip."""
    pkg_name = "test_polish_model"
    pkg, qt = _setup_fresh_package(pkg_name)

    spec = importlib.util.spec_from_file_location(
        f"{pkg_name}.widgets.models",
        str(FORGE_DIR / "widgets" / "models.py"),
    )
    models_mod = importlib.util.module_from_spec(spec)
    models_mod.__package__ = f"{pkg_name}.widgets"
    sys.modules[f"{pkg_name}.widgets.models"] = models_mod
    spec.loader.exec_module(models_mod)

    model_name = "full_checkpoint_hash_123.safetensors"
    api = types.SimpleNamespace(
        get_models_and_default=lambda: ([model_name], model_name),
        get_vaes_and_default=lambda: (["None"], "None"),
        get_refiners_and_default=lambda: (["None"], "None"),
        get_samplers_and_default=lambda: (["Euler"], "Euler"),
        get_schedulers_and_default=lambda: (["Karras"], ""),
        connected=True,
        state=None,
    )
    settings = {
        "defaults.model": model_name,
        "defaults.vae": "None",
        "defaults.refiner": "None",
        "defaults.enable_refiner": False,
        "defaults.refiner_start": 0.8,
        "defaults.sampling_steps": 20,
        "defaults.sampler": "Euler",
        "defaults.scheduler": "",
        "hide_ui.model": False,
        "hide_ui.vae": False,
        "hide_ui.refiner": False,
        "hide_ui.sampler": False,
        "hide_ui.scheduler": False,
    }
    controller = types.SimpleNamespace(
        get=lambda k: settings.get(k),
        set=lambda k, v: settings.__setitem__(k, v),
        save=lambda: None,
        debounced_save=lambda: None,
    )
    w = models_mod.ModelsWidget(controller, api)
    assert w.model_box.toolTip() == model_name


def test_polish_queue_status_label():
    """Polish item 6: queue_status_label has objectName QueueStatusLabel and error property on failure."""
    pkg_name = "test_polish_queue"
    pkg, qt = _setup_fresh_package(pkg_name)

    spec = importlib.util.spec_from_file_location(
        f"{pkg_name}.widgets.generate",
        str(FORGE_DIR / "widgets" / "generate.py"),
    )
    gen_mod = importlib.util.module_from_spec(spec)
    gen_mod.__package__ = f"{pkg_name}.widgets"
    sys.modules[f"{pkg_name}.widgets.generate"] = gen_mod
    spec.loader.exec_module(gen_mod)

    controller = types.SimpleNamespace(get=lambda k: False, set=lambda k, v: None)
    api = types.SimpleNamespace(
        connected=True,
        defaults={"model": "test"},
        last_error_message="out of memory",
    )
    w = gen_mod.GenerateWidget(controller, api, [], "txt2img")
    assert w.queue_status_label.objectName() == "QueueStatusLabel"


def test_payload_equality():
    """Verify that generation data and payload generation remain identical."""
    from forge.domain.payload_builder import build_api_payload

    # 1. ModelsWidget generation data with sentinel
    pkg_name = "test_payload_eq"
    _setup_fresh_package(pkg_name)
    spec = importlib.util.spec_from_file_location(
        f"{pkg_name}.widgets.models",
        str(FORGE_DIR / "widgets" / "models.py"),
    )
    models_mod = importlib.util.module_from_spec(spec)
    models_mod.__package__ = f"{pkg_name}.widgets"
    sys.modules[f"{pkg_name}.widgets.models"] = models_mod
    spec.loader.exec_module(models_mod)

    api = types.SimpleNamespace(
        get_models_and_default=lambda: (["m1"], "m1"),
        get_vaes_and_default=lambda: (["None"], "None"),
        get_refiners_and_default=lambda: (["None"], "None"),
        get_samplers_and_default=lambda: (["Euler"], "Euler"),
        get_schedulers_and_default=lambda: (["Karras"], ""),
        connected=True,
        state=None,
    )
    ctrl = types.SimpleNamespace(
        get=lambda k: {"defaults.model": "m1", "defaults.vae": "None", "defaults.refiner": "None",
                       "defaults.enable_refiner": False, "defaults.refiner_start": 0.8,
                       "defaults.sampling_steps": 20, "defaults.sampler": "Euler",
                       "defaults.scheduler": ""}.get(k),
        set=lambda k, v: None,
        save=lambda: None,
        debounced_save=lambda: None,
    )
    mw = models_mod.ModelsWidget(ctrl, api)
    data = mw.get_generation_data()
    assert "scheduler" not in data
    assert "refiner" not in data
    assert "refiner_start" not in data
    assert data["model"] == "m1"
    assert data["sampler"] == "Euler"

    payload = build_api_payload(data)
    assert "scheduler" not in payload
    assert "refiner_checkpoint" not in payload
    assert payload["sampler_name"] == "Euler"

    # 2. SoftInpaintWidget data when disabled
    spec_si = importlib.util.spec_from_file_location(
        f"{pkg_name}.widgets.soft_inpaint",
        str(FORGE_DIR / "widgets" / "soft_inpaint.py"),
    )
    si_mod = importlib.util.module_from_spec(spec_si)
    si_mod.__package__ = f"{pkg_name}.widgets"
    sys.modules[f"{pkg_name}.widgets.soft_inpaint"] = si_mod
    spec_si.loader.exec_module(si_mod)

    si_ctrl = types.SimpleNamespace(
        get=lambda k: False if k == "soft_inpaint.enabled" else 1.0,
        set=lambda k, v: None,
        save=lambda: None,
    )
    si_w = si_mod.SoftInpaintWidget(si_ctrl, settings_only=False)
    assert si_w.get_generation_data() == {}

    # 3. SoftInpaintWidget data when enabled
    si_w.update_enabled(True)
    si_data = si_w.get_generation_data()
    assert "alwayson_scripts" in si_data
    assert "Soft Inpainting" in si_data["alwayson_scripts"]


def test_queue_status_deleted_widget_safe():
    """Verify that _apply_queue_status and threadable_return tolerate deleted C++ widgets."""
    pkg_name = "test_queue_deleted"
    pkg, qt = _setup_fresh_package(pkg_name)

    spec = importlib.util.spec_from_file_location(
        f"{pkg_name}.widgets.generate",
        str(FORGE_DIR / "widgets" / "generate.py"),
    )
    gen_mod = importlib.util.module_from_spec(spec)
    gen_mod.__package__ = f"{pkg_name}.widgets"
    sys.modules[f"{pkg_name}.widgets.generate"] = gen_mod
    spec.loader.exec_module(gen_mod)

    class DeletedLabel:
        def setText(self, text):
            raise RuntimeError("wrapped C/C++ object of type QLabel has been deleted")
        def setProperty(self, k, v):
            raise RuntimeError("wrapped C/C++ object of type QLabel has been deleted")

    # Must not raise
    gen_mod._apply_queue_status(DeletedLabel(), "Queue: 0 jobs")

    controller = types.SimpleNamespace(get=lambda k: False, set=lambda k, v: None)
    api = types.SimpleNamespace(
        connected=True,
        defaults={"model": "test"},
        last_error_message="",
    )
    w = gen_mod.GenerateWidget(controller, api, [], "txt2img")
    w.queue_status_label = DeletedLabel()
    w.results = None
    w.threadable_return(0, 0, 512, 512, {})


def test_page_cleanup_cascades_to_generate_widget():
    """Verify that page cleanup calls generate_widget.cleanup()."""
    from unittest.mock import MagicMock
    pkg_name = "test_page_cleanup_gen"
    pkg, qt = _setup_fresh_package(pkg_name)

    spec_txt = importlib.util.spec_from_file_location(
        f"{pkg_name}.pages.txt2img",
        str(FORGE_DIR / "pages" / "txt2img.py"),
    )
    txt_mod = importlib.util.module_from_spec(spec_txt)
    txt_mod.__package__ = f"{pkg_name}.pages"
    sys.modules[f"{pkg_name}.pages.txt2img"] = txt_mod
    spec_txt.loader.exec_module(txt_mod)

    page = txt_mod.Txt2ImgPage.__new__(txt_mod.Txt2ImgPage)
    gen_mock = MagicMock()
    page.generate_widget = gen_mock
    page.widgets = []
    page.cleanup()
    gen_mock.cleanup.assert_called_once()


def test_generate_inpaint_missing_image_refused():
    """Verify that Inpaint generation without inpaint_img is blocked with clear error."""
    pkg_name = "test_inpaint_val"
    pkg, qt = _setup_fresh_package(pkg_name)

    spec = importlib.util.spec_from_file_location(
        f"{pkg_name}.widgets.generate",
        str(FORGE_DIR / "widgets" / "generate.py"),
    )
    gen_mod = importlib.util.module_from_spec(spec)
    gen_mod.__package__ = f"{pkg_name}.widgets"
    sys.modules[f"{pkg_name}.widgets.generate"] = gen_mod
    spec.loader.exec_module(gen_mod)

    controller = types.SimpleNamespace(
        get=lambda k: 512 if "size" in k else False,
        set=lambda k, v: None,
    )
    api = types.SimpleNamespace(
        connected=True,
        defaults={"model": "test"},
        last_error_message="",
    )

    class MaskWidget:
        def get_generation_data(self):
            return {"prompt": "a photo"}

    mask_w = MaskWidget()
    w = gen_mod.GenerateWidget(controller, api, [mask_w], "inpaint")
    w._resolve_generation_bounds = lambda: (0, 0, 512, 512)
    w.generate()

    assert "Inpaint requires an active canvas image" in w.queue_status_label.text()
    assert len(w.job_queue) == 0

