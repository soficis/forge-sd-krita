"""Page tabs: horizontal top rail instead of a left vertical rail.

forge.py wrapped a bare QTabBar (shape RoundedWest) in a `sidebar` QWidget
inside a QHBoxLayout with no stretch on that column, so labels ran vertically
down the left edge and the squeezed column truncated them ("Simplify U").

Failing-first (structure, not pixels) - these fail on current code:
- tab bar shape is RoundedWest, not RoundedNorth
- main layout is a QHBoxLayout whose first widget is a sidebar wrapper, so
  the rail's parent is the wrapper, not the main widget
- tabs expand to fill the rail with no elide mode (setExpanding(True),
  no setElideMode/setUsesScrollButtons), so narrow dockers truncate labels

Guards that must pass before AND after the change:
- one tab per entry in docker.pages, label = icon + name
- change_page swaps the content widget for every page, persists pages.last,
  saves, and cleans up the outgoing page (cleanup + deleteLater); an invalid
  index leaves the content untouched
- startup restore of pages.last (connected only; unknown name falls back to
  the first page)
- connection banner stays above the content area inside the content panel

forge.forge is loaded FRESH under stub-Qt real classes (pattern from
tests/test_denoise_turbo_guard.py / tests/test_ux_polish.py); never
`import forge` directly (forge/__init__ imports krita), and Qt symbols come
only from the stubbed forge.qt_compat. Page classes are swapped for fakes so
construction exercises forge.py's layout/dispatch, not page bodies.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
from unittest.mock import MagicMock

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Behaviour-recording stub Qt (real classes, not mocks)
# ---------------------------------------------------------------------------

class _Signal:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def emit(self):
        # PyQt truncates args for slots that take none; change_page reads
        # currentIndex() itself, so no payload is needed here.
        for slot in list(self._slots):
            slot()


class _Widget:
    def __init__(self, *args, **kwargs):
        self._layout = None
        self._parent_widget = None
        self._object_name = ""
        self._style_sheet = ""
        self._hidden = False

    def setObjectName(self, name):
        self._object_name = name

    def objectName(self):
        return self._object_name

    def setStyleSheet(self, sheet):
        self._style_sheet = sheet

    def setLayout(self, layout):
        self._layout = layout
        for widget in layout.widgets():
            widget._parent_widget = self

    def layout(self):
        return self._layout

    def findChildren(self, cls):
        return []

    def installEventFilter(self, flt):
        pass

    def update(self):
        pass

    def setHidden(self, hidden):
        self._hidden = bool(hidden)

    def isHidden(self):
        return self._hidden


class _QLabel(_Widget):
    def __init__(self, text="", *args, **kwargs):
        super().__init__()
        self._text = text
        self._alignment = None

    def setText(self, text):
        self._text = text

    def text(self):
        return self._text

    def setAlignment(self, alignment):
        self._alignment = alignment


class _QPushButton(_Widget):
    def __init__(self, text="", *args, **kwargs):
        super().__init__()
        self._text = text
        self._enabled = True

    def text(self):
        return self._text


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


class _Layout:
    direction = ""

    def __init__(self, *args, **kwargs):
        self._widgets = []

    def setContentsMargins(self, *args):
        pass

    def addWidget(self, widget, stretch=0):
        self._widgets.append(widget)

    def widgets(self):
        return list(self._widgets)


class _QVBoxLayout(_Layout):
    direction = "vertical"


class _QHBoxLayout(_Layout):
    direction = "horizontal"


class _QTabBarMeta(type):
    def __getattr__(cls, name):
        # PyQt5 exposes Shape members unscoped on the class too
        # (QTabBar.RoundedWest); PyQt6 only has the scoped form.
        shape = getattr(cls, "Shape", None)
        if shape is not None and hasattr(shape, name):
            return getattr(shape, name)
        raise AttributeError(name)


class _QTabBar(metaclass=_QTabBarMeta):
    """QTabBar with the Qt contract these tests depend on: Shape enum with
    real values (scoped + PyQt5-style unscoped access), signal on index
    change honouring blockSignals, first addTab selects index 0, and Qt
    defaults for expanding/elide/scroll buttons."""

    class Shape:
        RoundedNorth = 0
        RoundedSouth = 1
        RoundedWest = 2
        RoundedEast = 3

    def __init__(self, *args, **kwargs):
        self._object_name = ""
        self._shape = None
        self._expanding = True  # Qt default: expanding tabs
        self._elide = _Qt.TextElideMode.ElideNone  # Qt default: no elide
        self._uses_scroll = True  # Qt default: scroll buttons on
        self._labels = []
        self._index = -1
        self._blocked = False
        self.currentChanged = _Signal()

    def setObjectName(self, name):
        self._object_name = name

    def objectName(self):
        return self._object_name

    def layout(self):  # every QWidget has layout(); None when unset (Qt)
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
        if self._index < 0:  # first tab becomes current (Qt behaviour)
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


class _Qt:
    class AlignmentFlag:
        AlignCenter = "AlignCenter"

    class TextElideMode:  # real Qt values (PyQt5: ElideRight == 1)
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
    """Fallback for every other qt_compat symbol (pages, widgets) so the
    forge.forge import succeeds without modelling the whole Qt surface."""

    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return MagicMock(name=name)


class _DockWidgetStub:
    """Real base class: subclassing a MagicMock instance yields mocks."""

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


def _build_stub_qt():
    stub = types.ModuleType("forge.qt_compat")
    stub.Qt = _Qt
    stub.QWidget = _Widget
    stub.QVBoxLayout = _QVBoxLayout
    stub.QHBoxLayout = _QHBoxLayout
    stub.QLabel = _QLabel
    stub.QPushButton = _QPushButton
    stub.QScrollArea = _QScrollArea
    stub.QTabBar = _QTabBar
    stub.__all__ = [
        "Qt", "QWidget", "QVBoxLayout", "QHBoxLayout", "QLabel",
        "QPushButton", "QScrollArea", "QTabBar",
    ]

    def __getattr__(name):
        if name.startswith("__"):
            raise AttributeError(name)
        cls = _Meta(name, (_StubBase,), {})
        setattr(stub, name, cls)
        return cls

    stub.__getattr__ = __getattr__
    return stub


def _load_forge_module():
    """Import forge.forge fresh with stub-Qt classes; return the module."""
    mod_name = "forge.forge_f3_tabs"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    stub = _build_stub_qt()
    krita_mod = sys.modules.get("krita")
    old_dock = getattr(krita_mod, "DockWidget", None)
    krita_mod.DockWidget = _DockWidgetStub
    pre_keys = set(sys.modules)
    old_qt = sys.modules.get("forge.qt_compat")
    sys.modules["forge.qt_compat"] = stub
    try:
        path = REPO_ROOT / "forge" / "forge.py"
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
        for key in [k for k in sys.modules if k not in pre_keys
                    and k != mod_name]:
            sys.modules.pop(key, None)


# ---------------------------------------------------------------------------
# Fakes for construction seams: settings, API, pages
# ---------------------------------------------------------------------------

class _FakeSettings:
    def __init__(self, values):
        self.values = dict(values)
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
    def __init__(self, connected, error):
        self.connected = connected
        self.last_error_message = error


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


_state = {"settings": {}, "connected": False, "error": ""}


def _settings_factory():
    return _FakeSettings(_state["settings"])


def _api_factory(host=None):
    return _FakeAPI(connected=_state["connected"], error=_state["error"])


forge_mod = _load_forge_module()
for _attr in (
    "SettingsPage", "SimplifyPage", "Txt2ImgPage", "Img2ImgPage",
    "InpaintPage", "InterrogatePage", "UpscalePage", "RemBGPage",
    "SegmentationMapPage",
):
    if hasattr(forge_mod, _attr):
        setattr(forge_mod, _attr, type("Fake" + _attr, (_FakePage,), {}))
forge_mod.SettingsController = _settings_factory
forge_mod.SDAPI = _api_factory


def _make_docker(last_page=None, connected=False):
    """Construct a real ForgeDocker under the stub Qt; returns
    (docker, fake_settings_controller)."""
    _state["settings"] = {} if last_page is None else {"pages.last": last_page}
    _state["connected"] = connected
    _state["error"] = ""
    docker = forge_mod.ForgeDocker()
    return docker, docker.settings_controller


def _content_holder(docker):
    """Widget in the main layout whose layout contains the content area."""
    main = docker.main_widget.layout()
    for widget in main.widgets():
        layout = widget.layout()
        if layout is not None and docker.content_area in layout.widgets():
            return widget
    return None


# ---------------------------------------------------------------------------
# 1-2. Tab rail orientation and label-degradation policy
# ---------------------------------------------------------------------------

class TestTabRailOrientation:
    def test_shape_is_north_not_west(self):
        docker, _ = _make_docker()
        shape = docker.page_tabs.shape()
        assert shape == _QTabBar.Shape.RoundedNorth
        assert shape != _QTabBar.Shape.RoundedWest

    def test_tabs_size_to_labels_with_elide_and_scroll_fallback(self):
        docker, _ = _make_docker()
        tabs = docker.page_tabs
        assert tabs.expanding() is False
        assert tabs.elideMode() == _Qt.TextElideMode.ElideRight
        assert tabs.usesScrollButtons() is True


# ---------------------------------------------------------------------------
# 3-4. Vertical layout, rail on top, no orphan sidebar wrapper
# ---------------------------------------------------------------------------

class TestVerticalLayout:
    def test_main_layout_is_vertical(self):
        docker, _ = _make_docker()
        main = docker.main_widget.layout()
        assert isinstance(main, _QVBoxLayout)
        assert not isinstance(main, _QHBoxLayout)
        assert main.direction == "vertical"

    def test_rail_is_first_widget_in_the_vertical_layout(self):
        docker, _ = _make_docker()
        widgets = docker.main_widget.layout().widgets()
        assert widgets, "main layout must contain widgets"
        assert widgets[0] is docker.page_tabs

    def test_rail_parent_is_the_main_widget_no_wrapper(self):
        docker, _ = _make_docker()
        assert docker.page_tabs._parent_widget is docker.main_widget

    def test_content_area_lives_under_the_rail_in_the_same_layout(self):
        docker, _ = _make_docker()
        holder = _content_holder(docker)
        assert holder is not None, (
            "content area must be reachable from the main layout"
        )
        assert holder in docker.main_widget.layout().widgets()
        assert holder.layout().direction == "vertical"

    def test_banner_stays_above_the_content_area(self):
        docker, _ = _make_docker()
        holder = _content_holder(docker)
        assert holder is not None
        widgets = holder.layout().widgets()
        assert docker.connection_banner in widgets
        assert (
            widgets.index(docker.connection_banner)
            < widgets.index(docker.content_area)
        )


# ---------------------------------------------------------------------------
# 5. Tab registry matches the page list
# ---------------------------------------------------------------------------

class TestTabRegistry:
    def test_tab_count_matches_page_list(self):
        docker, _ = _make_docker()
        assert docker.page_tabs.count() == len(docker.pages)

    def test_tab_labels_are_icon_plus_name(self):
        docker, _ = _make_docker()
        assert docker.page_tabs.count() >= 1
        for index, page in enumerate(docker.pages):
            assert (
                docker.page_tabs.tabText(index)
                == "%s %s" % (page["icon"], page["name"])
            )


# ---------------------------------------------------------------------------
# 6. change_page dispatch: swaps content, persists, cleans up
# ---------------------------------------------------------------------------

class TestChangePageDispatch:
    def test_switching_tabs_swaps_content_for_every_page(self):
        docker, settings = _make_docker()
        count = len(docker.pages)
        assert count >= 1
        assert docker.content_area.widget() is not None  # init dispatched
        prev = docker.content_area.widget()

        for index in range(count):
            # Invalid index: guard keeps the current content untouched.
            docker.page_tabs.setCurrentIndex(-1)
            assert docker.content_area.widget() is prev
            # Valid index: swaps in a fresh page widget.
            docker.page_tabs.setCurrentIndex(index)
            current = docker.content_area.widget()
            assert current is not None
            assert current is not prev
            assert prev.cleaned_up is True
            assert prev.deleted_later is True
            assert settings.values.get("pages.last") == docker.pages[index][
                "name"
            ]
            prev = current

        assert settings.save_count >= 1
        assert docker._updates >= 1  # change_page still calls self.update()


# ---------------------------------------------------------------------------
# 7. Startup restore of the last-used page
# ---------------------------------------------------------------------------

class TestStartupRestore:
    def test_restores_last_page_when_connected(self):
        probe, _ = _make_docker()
        names = [page["name"] for page in probe.pages]
        target = names[2] if len(names) > 2 else names[-1]

        docker, settings = _make_docker(last_page=target, connected=True)
        expected = [page["name"] for page in docker.pages].index(target)
        assert docker.page_tabs.currentIndex() == expected
        assert settings.values.get("pages.last") == target
        assert isinstance(docker.content_area.widget(), _FakePage)

    def test_no_restore_when_disconnected(self):
        probe, _ = _make_docker()
        name = probe.pages[2]["name"] if len(probe.pages) > 2 else probe.pages[0]["name"]

        docker, _ = _make_docker(last_page=name, connected=False)
        assert docker.page_tabs.currentIndex() == 0

    def test_unknown_last_page_falls_back_to_first(self):
        docker, _ = _make_docker(last_page="No Such Page", connected=True)
        assert docker.page_tabs.currentIndex() == 0
