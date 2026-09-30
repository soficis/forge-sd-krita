"""Simplify UI folded into the Settings tab (8 -> 7 top-rail entries).

The standalone "Simplify UI" tab is gone; its hide_ui.* controls now live
inside the Settings page as a collapsible section. Locks:

- page list in forge/forge.py: exactly 7 entries, no "Simplify UI" entry,
  no SimplifyPage import, no show_simplify dispatcher
- change_page still dispatches every remaining page (fresh content widget,
  pages.last persisted, save called), the connection banner still tracks
  api state, and install_no_wheel still runs over the main widget
- EVERY hide_ui.* key declared by forge/default_settings.json - iterated
  from the real file so a future key cannot silently lose its checkbox -
  is toggleable through the constructed Settings page, and the toggle
  round-trips into the settings controller
- toggling hide_ui.model hides the model selector widget (ModelsWidget
  omits the row), with the visible-row control case proved alongside

Loading: never `import forge` directly (forge/__init__ imports krita,
registers a dock and starts an update thread), and Qt symbols come ONLY
from forge.qt_compat - fresh-loaded under behaviour-recording stub classes
(pattern from tests/test_denoise_turbo_guard.py /
tests/test_tabs_top_rail.py / tests/test_mask_layer_pixel_ops.py;
subclassing conftest's MagicMock Qt yields mocks, not classes).
"""

from __future__ import annotations

import ast
import contextlib
import copy
import importlib
import importlib.util
import inspect
import json
import pathlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
FORGE_DIR = REPO_ROOT / "forge"

EXPECTED_PAGE_NAMES = [
    "Settings",
    "Txt2Img",
    "Img2Img",
    "Inpaint",
    "Upscale",
    "Remove Background",
    "Segmentation Map",
]

# The 8 names forge.py imported before the merge; the lite package below
# exposes all of them so a pre-merge forge.py still loads (the AST import
# assertion, not a load crash, is what fails first on SimplifyPage).
_ALL_PAGE_ATTRS = [
    "SettingsPage", "SimplifyPage", "Txt2ImgPage", "Img2ImgPage",
    "InpaintPage", "UpscalePage", "RemBGPage", "SegmentationMapPage",
]

_SCHEMA = json.loads(
    (FORGE_DIR / "default_settings.json").read_text(encoding="utf-8")
)
HIDE_UI_KEYS = sorted(_SCHEMA["hide_ui"])

# Declared in default_settings.json since the rebrand but read by NO widget
# (the plugin has no clip-skip, face-restore or tiling control). Kept in the
# JSON, deliberately given no checkbox; see
# test_orphan_keys_are_kept_and_really_have_no_consumer.
ORPHAN_HIDE_UI_KEYS = {"clip_skip", "face_restore", "tiling"}


def _flatten(node: dict, prefix: str = "") -> dict:
    """Nested default_settings.json -> the dotted keys SettingsController uses."""
    out: dict = {}
    for key, value in node.items():
        path = "%s%s" % (prefix, key)
        if isinstance(value, dict):
            out.update(_flatten(value, path + "."))
        else:
            out[path] = value
    return out


# ---------------------------------------------------------------------------
# Behaviour-recording stub Qt (real classes, not mocks)
# ---------------------------------------------------------------------------


def _max_positional(slot) -> int:
    """How many positional args the slot can accept (PyQt truncates args)."""
    try:
        sig = inspect.signature(slot)
    except (TypeError, ValueError):
        return 0
    count = 0
    for param in sig.parameters.values():
        if param.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            count += 1
        elif param.kind is inspect.Parameter.VAR_POSITIONAL:
            return 3
    return count


class _Signal:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def emit(self, *args):
        for slot in list(self._slots):
            slot(*args[:_max_positional(slot)])


class _QObject:
    def __init__(self, *args, **kwargs):
        self._filters = []

    def installEventFilter(self, flt):
        self._filters.append(flt)


class _Widget(_QObject):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self._layout = None
        self._tooltip = ""
        self._hidden = False
        self._object_name = ""
        self._style_sheet = ""
        self._enabled = True

    def setObjectName(self, name):
        self._object_name = name

    def objectName(self):
        return self._object_name

    def setStyleSheet(self, sheet):
        self._style_sheet = sheet

    def setLayout(self, layout):
        self._layout = layout

    def layout(self):
        return self._layout

    def setToolTip(self, text):
        self._tooltip = text

    def toolTip(self):
        return self._tooltip

    def setHidden(self, hidden):
        self._hidden = bool(hidden)

    def isHidden(self):
        return self._hidden

    def show(self):
        self._hidden = False

    def hide(self):
        self._hidden = True

    def setEnabled(self, enabled):
        self._enabled = bool(enabled)

    def isEnabled(self):
        return self._enabled

    def update(self):
        pass

    def repaint(self):
        pass

    def children(self):
        return []

    def findChildren(self, cls):
        found = []
        for child in _layout_widgets(self):
            found.append(child)
            found.extend(child.findChildren(cls))
        return found


class _Stretch:
    pass


class _Item:
    def __init__(self, widget):
        self._widget = widget

    def widget(self):
        return self._widget


class _Layout:
    def __init__(self, *args, **kwargs):
        self._widgets = []

    def setContentsMargins(self, *args):
        pass

    def setSpacing(self, *args):
        pass

    def addWidget(self, widget, stretch=0):
        self._widgets.append(widget)

    def addStretch(self, stretch=0):
        self._widgets.append(_Stretch())

    def count(self):
        return len(self._widgets)

    def itemAt(self, index):
        if 0 <= index < len(self._widgets):
            item = self._widgets[index]
            if isinstance(item, _Widget):
                return _Item(item)
            return _Item(None)
        return None

    def widgets(self):
        return list(self._widgets)


class _QVBoxLayout(_Layout):
    pass


class _QHBoxLayout(_Layout):
    pass


class _QFormLayout(_Layout):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.rows = []

    def addRow(self, *args):
        self.rows.append(args)
        for arg in args:
            if isinstance(arg, _Widget):
                self._widgets.append(arg)


class _QLabel(_Widget):
    def __init__(self, text="", *args, **kwargs):
        super().__init__()
        self._text = text if isinstance(text, str) else ""
        self._word_wrap = False

    def setText(self, text):
        self._text = text

    def text(self):
        return self._text

    def setWordWrap(self, wrap):
        self._word_wrap = bool(wrap)

    def setAlignment(self, alignment):
        self._alignment = alignment


class _QPushButton(_Widget):
    def __init__(self, text="", *args, **kwargs):
        super().__init__()
        self._text = text if isinstance(text, str) else ""
        self._checked = False
        self._checkable = False
        self.clicked = _Signal()

    def text(self):
        return self._text

    def setText(self, text):
        self._text = text

    def setCheckable(self, checkable):
        self._checkable = bool(checkable)

    def setChecked(self, checked):
        self._checked = bool(checked)

    def isChecked(self):
        return self._checked


class _QCheckBox(_Widget):
    def __init__(self, text="", *args, **kwargs):
        super().__init__()
        self._text = text if isinstance(text, str) else ""
        self._checked = False
        self.stateChanged = _Signal()
        self.toggled = _Signal()

    def text(self):
        return self._text

    def setChecked(self, checked):
        checked = bool(checked)
        if checked != self._checked:
            self._checked = checked
            self.stateChanged.emit(1 if checked else 0)
            self.toggled.emit(checked)

    def isChecked(self):
        return self._checked


class _QComboBox(_Widget):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self._items = []
        self._index = -1
        self._blocked = False
        self._placeholder = ""
        self.currentTextChanged = _Signal()

    def addItem(self, text):
        self._items.append(text)

    def addItems(self, texts):
        self._items.extend(list(texts))

    def clear(self):
        self._items = []
        self._index = -1

    def setCurrentIndex(self, index):
        previous = self.currentText()
        self._index = index
        if not self._blocked and self.currentText() != previous:
            self.currentTextChanged.emit(self.currentText())

    def setCurrentText(self, text):
        if text in self._items:
            self.setCurrentIndex(self._items.index(text))

    def currentIndex(self):
        return self._index

    def currentText(self):
        if 0 <= self._index < len(self._items):
            return self._items[self._index]
        return ""

    def blockSignals(self, blocked):
        self._blocked = bool(blocked)

    def setPlaceholderText(self, text):
        self._placeholder = text

    def setMinimumContentsLength(self, length):
        pass

    def setMaxVisibleItems(self, items):
        pass


class _QLineEdit(_Widget):
    def __init__(self, text="", *args, **kwargs):
        super().__init__()
        self._text = text if isinstance(text, str) else ""
        self.textChanged = _Signal()

    def text(self):
        return self._text

    def setText(self, text):
        previous = self._text
        self._text = text
        if text != previous:
            self.textChanged.emit(text)

    def setPlaceholderText(self, text):
        self._placeholder = text

    def setValidator(self, validator):
        pass


class _QSpinBox(_Widget):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self._value = 0
        self._min = 0
        self._max = 99
        self._step = 1
        self.valueChanged = _Signal()

    def setRange(self, minimum, maximum):
        self._min, self._max = minimum, maximum

    def setMinimum(self, minimum):
        self._min = minimum

    def setMaximum(self, maximum):
        self._max = maximum

    def setSingleStep(self, step):
        self._step = step

    def setValue(self, value):
        previous = self._value
        self._value = value
        if value != previous:
            self.valueChanged.emit(value)

    def value(self):
        return self._value


class _QSlider(_QSpinBox):
    def setTickInterval(self, interval):
        pass

    def setTickPosition(self, position):
        pass

    class TickPosition:
        TicksAbove = 0
        TicksBelow = 1


class _QGroupBox(_Widget):
    def __init__(self, title="", *args, **kwargs):
        super().__init__()
        self._title = title if isinstance(title, str) else ""

    def setTitle(self, title):
        self._title = title

    def title(self):
        return self._title


class _QScrollArea(_Widget):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self._widget = None
        self._resizable = False

    def setWidgetResizable(self, resizable):
        self._resizable = bool(resizable)

    def setWidget(self, widget):
        self._widget = widget

    def widget(self):
        return self._widget


class _QTabBarMeta(type):
    def __getattr__(cls, name):
        shape = getattr(cls, "Shape", None)
        if shape is not None and hasattr(shape, name):
            return getattr(shape, name)
        raise AttributeError(name)


class _QTabBar(metaclass=_QTabBarMeta):
    class Shape:
        RoundedNorth = 0
        RoundedSouth = 1
        RoundedWest = 2
        RoundedEast = 3

    def __init__(self, *args, **kwargs):
        self._object_name = ""
        self._shape = None
        self._expanding = True
        self._elide = 0
        self._uses_scroll = True
        self._labels = []
        self._index = -1
        self._blocked = False
        self.currentChanged = _Signal()

    def setObjectName(self, name):
        self._object_name = name

    def objectName(self):
        return self._object_name

    def layout(self):
        return None

    def setShape(self, shape):
        self._shape = shape

    def shape(self):
        return self._shape

    def setExpanding(self, expanding):
        self._expanding = bool(expanding)

    def expanding(self):
        return self._expanding

    def setElideMode(self, mode):
        self._elide = mode

    def elideMode(self):
        return self._elide

    def setUsesScrollButtons(self, uses):
        self._uses_scroll = bool(uses)

    def usesScrollButtons(self):
        return self._uses_scroll

    def addTab(self, label):
        self._labels.append(label)
        if self._index < 0:
            self._index = 0
        return len(self._labels) - 1

    def count(self):
        return len(self._labels)

    def tabText(self, index):
        return self._labels[index]

    def currentIndex(self):
        return self._index

    def setCurrentIndex(self, index):
        if index == self._index:
            return
        self._index = index
        if not self._blocked:
            self.currentChanged.emit()

    def blockSignals(self, blocked):
        self._blocked = bool(blocked)


class _QThread(_QObject):
    def start(self):
        pass

    def wait(self, *args):
        pass


def _pyqt_signal(*types_, **kwargs):
    return _Signal()


class _Qt:
    class AlignmentFlag:
        AlignCenter = "AlignCenter"

    class Orientation:
        Horizontal = 1
        Vertical = 2

    class TextElideMode:
        ElideLeft = 0
        ElideRight = 1
        ElideMiddle = 2
        ElideNone = 3


class _Meta(type):
    def __getattr__(cls, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return MagicMock(name="%s.%s" % (cls.__name__, name))


class _StubBase(metaclass=_Meta):
    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return MagicMock(name=name)


def _layout_widgets(widget):
    layout = widget.layout()
    if layout is None:
        return []
    return [w for w in layout.widgets() if isinstance(w, _Widget)]


def _all_widgets(root):
    """Every _Widget reachable through layouts from root (root excluded)."""
    found = []
    stack = list(_layout_widgets(root))
    while stack:
        widget = stack.pop(0)
        found.append(widget)
        stack.extend(_layout_widgets(widget))
    return found


def _build_stub_qt():
    stub = types.ModuleType("forge.qt_compat")
    stub.Qt = _Qt
    stub.QObject = _QObject
    stub.QWidget = _Widget
    stub.QVBoxLayout = _QVBoxLayout
    stub.QHBoxLayout = _QHBoxLayout
    stub.QFormLayout = _QFormLayout
    stub.QLabel = _QLabel
    stub.QPushButton = _QPushButton
    stub.QCheckBox = _QCheckBox
    stub.QComboBox = _QComboBox
    stub.QLineEdit = _QLineEdit
    stub.QSpinBox = _QSpinBox
    stub.QSlider = _QSlider
    stub.QGroupBox = _QGroupBox
    stub.QScrollArea = _QScrollArea
    stub.QTabBar = _QTabBar
    stub.QThread = _QThread
    stub.pyqtSignal = _pyqt_signal
    stub.__all__ = [
        "Qt", "QObject", "QWidget", "QVBoxLayout", "QHBoxLayout",
        "QFormLayout", "QLabel", "QPushButton", "QCheckBox", "QComboBox",
        "QLineEdit", "QSpinBox", "QSlider", "QGroupBox", "QScrollArea",
        "QTabBar", "QThread", "pyqtSignal",
    ]

    def __getattr__(name):
        if name.startswith("__"):
            raise AttributeError(name)
        cls = _Meta(name, (_StubBase,), {})
        setattr(stub, name, cls)
        return cls

    stub.__getattr__ = __getattr__
    return stub


class _DockWidgetStub:
    def __init__(self, *args, **kwargs):
        self._updates = 0

    def setWindowTitle(self, *args, **kwargs):
        pass

    def setWidget(self, widget):
        self._dock_widget = widget

    def update(self):
        self._updates += 1

    def closeEvent(self, event):
        pass


# ---------------------------------------------------------------------------
# Fresh forge.forge load with faked pages (Part 1)
# ---------------------------------------------------------------------------


class _FakePage:
    def __init__(self, *args, **kwargs):
        self.cleaned_up = False
        self.deleted_later = False

    def cleanup(self):
        self.cleaned_up = True

    def deleteLater(self):
        self.deleted_later = True

    def findChildren(self, cls):
        return []


def _lite_package(name: str, path: pathlib.Path, attrs: list[str]) -> dict:
    """Temporarily stand a package in for forge.pages/forge.widgets so a
    fresh module load resolves its relative imports without executing the
    real package __init__ (or, for forge.py, importing real page bodies)."""
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    for attr in attrs:
        setattr(module, attr, type(attr, (_FakePage,), {}))
    return module


_MISSING = object()
_FORGE_CHILD_ATTRS = ("pages", "widgets", "qt_compat")


def _snapshot_forge_attrs() -> dict:
    """Importing forge.pages/forge.widgets fresh rebinds them as ATTRIBUTES
    of the real `forge` package, and restoring sys.modules does not undo
    that - a later `import forge.widgets.generate as m` would then resolve
    through the stale stub-Qt package (this broke test_timer_cleanup)."""
    pkg = sys.modules.get("forge")
    return {name: getattr(pkg, name, _MISSING) for name in _FORGE_CHILD_ATTRS}


def _restore_forge_attrs(snapshot: dict) -> None:
    pkg = sys.modules.get("forge")
    if pkg is None:
        return
    for name, value in snapshot.items():
        if value is _MISSING:
            if hasattr(pkg, name):
                delattr(pkg, name)
        else:
            setattr(pkg, name, value)


def _load_forge_module():
    """Import forge/forge.py fresh under stub-Qt; returns the module."""
    mod_name = "forge.forge_f3_simplify_into_settings"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    stub = _build_stub_qt()
    krita_mod = sys.modules.get("krita")
    old_dock = getattr(krita_mod, "DockWidget", None)
    krita_mod.DockWidget = _DockWidgetStub
    pre_keys = set(sys.modules)
    forge_attrs = _snapshot_forge_attrs()
    old_qt = sys.modules.get("forge.qt_compat")
    saved = {}
    for key in list(sys.modules):
        if key == "forge.pages" or key == "forge.widgets":
            saved[key] = sys.modules.pop(key)
    sys.modules["forge.qt_compat"] = stub
    sys.modules["forge.pages"] = _lite_package(
        "forge.pages", FORGE_DIR / "pages", _ALL_PAGE_ATTRS
    )
    sys.modules["forge.widgets"] = _lite_package(
        "forge.widgets", FORGE_DIR / "widgets", []
    )
    try:
        path = FORGE_DIR / "forge.py"
        spec = importlib.util.spec_from_file_location(mod_name, str(path))
        mod = importlib.util.module_from_spec(spec)
        mod.__package__ = "forge"
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        krita_mod.DockWidget = old_dock
        if old_qt is not None:
            sys.modules["forge.qt_compat"] = old_qt
        else:
            sys.modules.pop("forge.qt_compat", None)
        for key in [k for k in list(sys.modules) if k not in pre_keys]:
            sys.modules.pop(key, None)
        sys.modules.update(saved)
        _restore_forge_attrs(forge_attrs)


class _FakeSettings:
    def __init__(self, values=None):
        self.values = dict(values or {})
        self.save_count = 0

    def has(self, key):
        return key in self.values

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value

    def save(self):
        self.save_count += 1

    def close(self):
        pass


class _FakeAPI:
    def __init__(self, connected=False, error=""):
        self.connected = connected
        self.last_error_message = error


_state = {"settings": {}, "connected": False, "error": ""}

forge_mod = _load_forge_module()
for _attr in _ALL_PAGE_ATTRS:
    if hasattr(forge_mod, _attr):
        setattr(forge_mod, _attr, type("Fake" + _attr, (_FakePage,), {}))
forge_mod.SettingsController = lambda: _FakeSettings(_state["settings"])
forge_mod.SDAPI = lambda host=None: _FakeAPI(
    connected=_state["connected"], error=_state["error"]
)


def _make_docker(last_page=None, connected=False, error=""):
    """Construct a real ForgeDocker under the stub Qt; returns
    (docker, fake_settings_controller)."""
    _state["settings"] = {} if last_page is None else {"pages.last": last_page}
    _state["connected"] = connected
    _state["error"] = error
    docker = forge_mod.ForgeDocker()
    return docker, docker.settings_controller


# ---------------------------------------------------------------------------
# Part 2: real Settings page + embedded simplify section under stub Qt
# ---------------------------------------------------------------------------


class _RecordingSettings:
    """SettingsController stand-in: dotted-key store that records every set
    (mirrors the real controller's unknown-key KeyError)."""

    def __init__(self, values):
        self.values = {k: (list(v) if isinstance(v, list) else v)
                       for k, v in values.items()}
        self.sets = []
        self.save_count = 0

    def get(self, path, default=None):
        if path in self.values:
            return self.values[path]
        if default is not None:
            return default
        raise KeyError(path)

    def has(self, path):
        return path in self.values

    def set(self, path, value):
        if path not in self.values:
            raise KeyError("Unknown settings key: %s" % path)
        self.values[path] = list(value) if isinstance(value, list) else value
        self.sets.append((path, self.values[path]))

    def toggle(self, path, value=None):
        target = self.get(path)
        if isinstance(target, bool):
            self.set(path, not target)
            return
        if value in target:
            target.remove(value)
        else:
            target.append(value)
        self.set(path, target)

    def save(self):
        self.save_count += 1

    def debounced_save(self):
        pass

    def close(self):
        pass


class _SettingsAPI:
    """Enough SDAPI for SettingsPage + the simplify preview widgets."""

    DEFAULT_HOST = "http://127.0.0.1:7860"

    def __init__(self, connected=True):
        self.connected = connected
        self.last_error_message = ""

    def script_installed(self, name):
        return True

    def get_models_and_default(self):
        return ["model-a.safetensors"], "model-a.safetensors"

    def get_vaes_and_default(self):
        return [], "None"

    def get_refiners_and_default(self):
        return ["None"], "None"

    def get_samplers_and_default(self):
        return ["Euler"], "Euler"

    def get_schedulers_and_default(self):
        # "" default = the backend owns the per-preset scheduler (the
        # adapter's contract; harmless on pre-scheduler widget code).
        return ["Automatic", "Karras"], ""

    def get_upscaler_names(self):
        return ["Latent", "4x-UltraSharp"]

    def get_status(self):
        return {"ok": True} if self.connected else None

    def change_host(self, host):
        pass


@contextlib.contextmanager
def _settings_env():
    """Fresh-load forge.pages.settings (+ simplify + widgets) under stub Qt,
    then restore the previous sys.modules state."""
    stub = _build_stub_qt()
    pre_keys = set(sys.modules)
    forge_attrs = _snapshot_forge_attrs()
    old_qt = sys.modules.get("forge.qt_compat")
    saved = {}
    for key in list(sys.modules):
        if (
            key == "forge.pages"
            or key.startswith("forge.pages.")
            or key == "forge.widgets"
            or key.startswith("forge.widgets.")
        ):
            saved[key] = sys.modules.pop(key)
    sys.modules["forge.qt_compat"] = stub
    try:
        lite_pages = types.ModuleType("forge.pages")
        lite_pages.__path__ = [str(FORGE_DIR / "pages")]
        sys.modules["forge.pages"] = lite_pages
        settings_mod = importlib.import_module("forge.pages.settings")
        models_mod = importlib.import_module("forge.widgets.models")
        yield SimpleNamespace(settings=settings_mod, models=models_mod)
    finally:
        if old_qt is not None:
            sys.modules["forge.qt_compat"] = old_qt
        else:
            sys.modules.pop("forge.qt_compat", None)
        for key in [k for k in list(sys.modules) if k not in pre_keys]:
            sys.modules.pop(key, None)
        sys.modules.update(saved)
        _restore_forge_attrs(forge_attrs)


def _hide_settings() -> _RecordingSettings:
    values = _flatten(_SCHEMA)
    # The section writes its hidden dict to the controller whenever the
    # autosave box is on (the JSON default); pin it so a future default
    # flip cannot silently disable the live round-trip this test asserts.
    values["hide_ui.auto_save"] = True
    return _RecordingSettings(values)


def _hide_checkboxes(page):
    return [w for w in _all_widgets(page) if isinstance(w, _QCheckBox)]


def _toggle_and_diff(settings, checkbox) -> set:
    """Flip the checkbox; return the hide_ui.* keys whose controller value
    changed as a result (the key the checkbox is bound to).

    Deep-copied snapshot: hide_ui.hidden_extensions is a list the section
    toggles IN PLACE, so a shallow copy would alias it and hide the change.
    If the flip turned autosave off, it is flipped straight back on (the
    diff is still reported) - otherwise every later checkbox in the probe
    would silently stop writing and look unbound."""
    before = copy.deepcopy(settings.values)
    checkbox.setChecked(not checkbox.isChecked())
    changed = {
        key
        for key, value in settings.values.items()
        if key.startswith("hide_ui.") and before.get(key) != value
    }
    if settings.values.get("hide_ui.auto_save") is False:
        checkbox.setChecked(not checkbox.isChecked())
        assert settings.values.get("hide_ui.auto_save") is True
    return changed


# ---------------------------------------------------------------------------
# 1. Page list: exactly 7 entries, no Simplify UI, no dangling dispatch
# ---------------------------------------------------------------------------


def _forge_source() -> str:
    return (FORGE_DIR / "forge.py").read_text(encoding="utf-8")


def _pages_list(tree: ast.AST) -> ast.List:
    found = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.List)
            and any(
                isinstance(target, ast.Attribute) and target.attr == "pages"
                for target in node.targets
            )
        ):
            found.append(node.value)
    assert len(found) == 1, "expected exactly one self.pages = [...] assignment"
    return found[0]


def _page_entry_names(pages_list: ast.List) -> list:
    names = []
    for entry in pages_list.elts:
        assert isinstance(entry, ast.Dict), "page entries must be dicts"
        for key, value in zip(entry.keys, entry.values):
            if (
                isinstance(key, ast.Constant)
                and key.value == "name"
                and isinstance(value, ast.Constant)
            ):
                names.append(value.value)
    return names


class TestPageListIsSeven:
    def test_source_page_list_has_exactly_seven_entries_no_simplify_ui(self):
        tree = ast.parse(_forge_source())
        names = _page_entry_names(_pages_list(tree))
        assert names == EXPECTED_PAGE_NAMES
        assert len(names) == 7
        assert "Simplify UI" not in names

    def test_source_has_no_simplify_import_and_no_show_simplify(self):
        tree = ast.parse(_forge_source())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "pages":
                imported.update(alias.name for alias in node.names)
            if isinstance(node, ast.FunctionDef) and node.name == "show_simplify":
                raise AssertionError("show_simplify dispatcher still defined")
        assert "SimplifyPage" not in imported
        source = _forge_source()
        assert "show_simplify" not in source
        assert "Simplify UI" not in source

    def test_docker_builds_seven_named_tabs(self):
        docker, _ = _make_docker()
        names = [page["name"] for page in docker.pages]
        assert names == EXPECTED_PAGE_NAMES
        assert docker.page_tabs.count() == 7

    def test_docker_has_no_show_simplify_dispatcher(self):
        docker, _ = _make_docker()
        assert not hasattr(type(docker), "show_simplify")


# ---------------------------------------------------------------------------
# 2. change_page / connection banner / install_no_wheel keep working
# ---------------------------------------------------------------------------


class TestChangePageStillWorks:
    def test_every_page_dispatches_and_persists_pages_last(self):
        docker, settings = _make_docker()
        assert docker.content_area.widget() is not None  # init dispatched
        prev = docker.content_area.widget()
        for index, page in enumerate(docker.pages):
            name = page["name"]
            # Invalid index: guard keeps the current content untouched.
            docker.page_tabs.setCurrentIndex(-1)
            assert docker.content_area.widget() is prev
            # Valid index: swaps in a fresh page widget.
            docker.page_tabs.setCurrentIndex(index)
            current = docker.content_area.widget()
            assert current is not None
            assert current is not prev, name
            assert prev.cleaned_up is True
            assert prev.deleted_later is True
            assert settings.values.get("pages.last") == name
            prev = current
        # One init dispatch + one per tab (the -1 guards dispatch nothing).
        assert settings.save_count >= len(docker.pages)
        assert docker._updates >= len(docker.pages)

    def test_invalid_index_leaves_content_untouched(self):
        docker, _ = _make_docker()
        current = docker.content_area.widget()
        docker.page_tabs.setCurrentIndex(-1)
        assert docker.content_area.widget() is current

    def test_banner_shows_when_disconnected_and_hides_when_connected(self):
        docker, _ = _make_docker(connected=False, error="")
        assert docker.connection_banner.isHidden() is False
        assert docker.connection_banner.text() == "No Connection"

        docker, _ = _make_docker(connected=True)
        assert docker.connection_banner.isHidden() is True

    def test_install_no_wheel_runs_over_the_main_widget(self):
        docker, _ = _make_docker()
        assert docker.main_widget._filters, "install_no_wheel never ran"
        assert type(docker.main_widget._filters[0]).__name__ == "NoWheelFilter"


# ---------------------------------------------------------------------------
# 3. Every hide_ui.* key from the real JSON is toggleable via Settings
# ---------------------------------------------------------------------------


class TestSettingsExposesEveryHideUiKey:
    def test_json_declares_hide_ui_keys(self):
        # Guards the vacuous-pass trap: if the parse found nothing, the
        # coverage test below would be meaningless.
        assert len(HIDE_UI_KEYS) >= 30

    def test_every_hide_ui_key_has_a_toggle_in_the_settings_page(self):
        with _settings_env() as env:
            settings = _hide_settings()
            page = env.settings.SettingsPage(settings, _SettingsAPI())

            covered = set()
            bound_controls = 0
            for checkbox in _hide_checkboxes(page):
                changed = _toggle_and_diff(settings, checkbox)
                if changed:
                    bound_controls += 1
                    # probe reports dotted controller keys; JSON keys are bare
                    covered |= {key[len("hide_ui."):] for key in changed}

            expected = set(HIDE_UI_KEYS) - ORPHAN_HIDE_UI_KEYS
            missing = expected - covered
            assert not missing, (
                "hide_ui keys declared in default_settings.json but not "
                "toggleable through the Settings page: %s" % sorted(missing)
            )
            assert covered <= expected, (
                "orphan keys (no consumer) must not get a no-op checkbox: %s"
                % sorted(covered & ORPHAN_HIDE_UI_KEYS)
            )
            # Non-vacuity: the probe must actually have driven a control per
            # exposed key (hidden_extensions has two checkboxes, so >= keys).
            assert bound_controls >= len(expected), (
                "expected at least one hide control per key, found %d"
                % bound_controls
            )

    def test_orphan_keys_are_kept_and_really_have_no_consumer(self):
        # Kept in the JSON (no key dropped - old user_settings.json files
        # still merge cleanly) but deliberately NOT given a checkbox: no
        # widget reads them, so a checkbox would be a silent no-op. If a
        # consumer is ever added, this fails and forces a real checkbox.
        assert ORPHAN_HIDE_UI_KEYS <= set(HIDE_UI_KEYS)
        sources = [
            p.read_text(encoding="utf-8")
            for p in sorted(FORGE_DIR.rglob("*.py"))
            if "__pycache__" not in p.parts
        ]
        for key in ORPHAN_HIDE_UI_KEYS:
            needle = "hide_ui.%s" % key
            users = [s for s in sources if needle in s]
            assert not users, "%s now has a consumer; expose it" % needle

    def test_settings_page_embeds_the_simplify_section(self):
        with _settings_env() as env:
            settings = _hide_settings()
            page = env.settings.SettingsPage(settings, _SettingsAPI())
            labels = [cb.text() for cb in _hide_checkboxes(page)]
            assert any(
                label.startswith("Hide ") for label in labels
            ), "no hide_ui checkboxes embedded in SettingsPage"
            assert "Hide Model" in labels


# ---------------------------------------------------------------------------
# 4. Toggle round-trip: controller write + the widget actually hides
# ---------------------------------------------------------------------------


class TestHideModelRoundTrip:
    def test_toggling_hide_model_persists_and_hides_model_row(self):
        with _settings_env() as env:
            settings = _hide_settings()
            page = env.settings.SettingsPage(settings, _SettingsAPI())
            assert settings.values["hide_ui.model"] is False

            toggled = False
            for checkbox in _hide_checkboxes(page):
                if _toggle_and_diff(settings, checkbox) == {"hide_ui.model"}:
                    toggled = True
                    break
            assert toggled, "no Settings checkbox is bound to hide_ui.model"
            assert settings.values["hide_ui.model"] is True
            assert ("hide_ui.model", True) in settings.sets

            # The hidden flag now reaches the widget that owns the row.
            hidden_widget = env.models.ModelsWidget(settings, _SettingsAPI())
            hidden_children = _all_widgets(hidden_widget)
            assert hidden_widget.model_box not in hidden_children, (
                "hide_ui.model=True but the model selector is still laid out"
            )

            # Control case: with the flag off the row must come back, so the
            # assertion above cannot pass just because the walk is broken.
            settings.set("hide_ui.model", False)
            shown_widget = env.models.ModelsWidget(settings, _SettingsAPI())
            assert shown_widget.model_box in _all_widgets(shown_widget)
