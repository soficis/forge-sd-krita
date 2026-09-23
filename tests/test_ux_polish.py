"""Todo 33 (Phase 3 UX polish): extractable UX predicates and wiring.

Failing-first: none of the functions/classes under test exist before
todo 33 - ``history_empty_message``, ``models_status_message``,
``presets_status_message``, ``should_cancel_on_escape``,
``disabled_button_tooltip``, ``GenerateWidget.handle_escape``, and the
pages' Escape ``keyPressEvent`` all import/attribute-error until implemented.

Covers:
- Empty-state message selection: history (none vs filter-no-match),
  models (loading/disconnected/empty/ok), presets (empty).
- Escape-to-cancel predicate: fires only for an in-flight generation whose
  button shows Cancel AND is enabled (disabled = disconnected; interrupt
  would fail), plus GenerateWidget.handle_escape consuming the key.
- Disabled-button why-tooltip: reason (or fallback) while disconnected,
  cleared when connected; ForgeDocker._update_connection_state wires it
  onto Generate/Cancel/Remove Background only.
- Pages owning a Cancel button (txt2img/img2img/inpaint) declare their own
  keyPressEvent (class dict, not the mock base) so Escape from a focused
  prompt field propagates up to the page.

Widget modules load FRESH under stub-Qt real classes (pattern from
tests/test_controlnet_dict_guards.py / tests/test_ui_surface.py);
subclassing conftest's MagicMock Qt does NOT work.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


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
    "QPixmap", "QPointF", "qAlpha", "qRgb", "QMessageBox", "DockWidget",
]

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


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
        path = REPO_ROOT / relpath
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


# forge.forge needs the DockWidget-stub swap (same as test_connection_errors)
class _DockWidgetStub:
    def __init__(self, *args, **kwargs):
        pass

    def setWindowTitle(self, *args, **kwargs):
        pass

    def setWidget(self, *args, **kwargs):
        pass

    def closeEvent(self, event):
        pass


def _load_forge_module():
    mod_name = "forge.forge_task33"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    krita_mod = sys.modules.get("krita")
    old_dock = getattr(krita_mod, "DockWidget", None)
    krita_mod.DockWidget = _DockWidgetStub
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


history_mod = _load_real(
    "forge/widgets/history.py", "forge.widgets.history_task33", "forge.widgets",
)
models_mod = _load_real(
    "forge/widgets/models.py", "forge.widgets.models_task33", "forge.widgets",
)
presets_mod = _load_real(
    "forge/widgets/prompt_presets.py",
    "forge.widgets.prompt_presets_task33",
    "forge.widgets",
)
generate_mod = _load_real(
    "forge/widgets/generate.py", "forge.widgets.generate_task33", "forge.widgets",
)
forge_mod = _load_forge_module()


# ---------------------------------------------------------------------------
# 1. Empty-state message selection
# ---------------------------------------------------------------------------

class TestHistoryEmptyMessage:
    def test_no_history_at_all(self):
        msg = history_mod.history_empty_message(0, 0, "")
        assert "No generations yet" in msg
        assert msg.strip()

    def test_filter_no_match_mentions_query(self):
        msg = history_mod.history_empty_message(5, 0, "a cat")
        assert "a cat" in msg
        assert "No history entries" in msg

    def test_entries_present_returns_empty_string(self):
        assert history_mod.history_empty_message(5, 5, "") == ""
        assert history_mod.history_empty_message(5, 2, "cat") == ""

    def test_filtered_empty_without_query_is_still_nonempty(self):
        # Defensive branch: filtered==0 with history present but no query.
        msg = history_mod.history_empty_message(5, 0, "   ")
        assert msg.strip()


class TestModelsStatusMessage:
    def test_loading_wins_over_everything(self):
        assert models_mod.models_status_message(
            loading=True, connected=False, model_count=0,
        ) == models_mod.MODELS_LOADING_TEXT
        assert models_mod.models_status_message(
            loading=True, connected=True, model_count=9,
        ) == models_mod.MODELS_LOADING_TEXT

    def test_disconnected_placeholder(self):
        msg = models_mod.models_status_message(
            loading=False, connected=False, model_count=0,
        )
        assert msg == models_mod.MODELS_DISCONNECTED_TEXT
        assert "connect" in msg.lower()

    def test_connected_but_no_models(self):
        msg = models_mod.models_status_message(
            loading=False, connected=True, model_count=0,
        )
        assert msg == models_mod.MODELS_EMPTY_TEXT

    def test_connected_with_models_is_silent(self):
        assert models_mod.models_status_message(
            loading=False, connected=True, model_count=3,
        ) == ""

    @pytest.mark.parametrize("count", [-5, 0])
    def test_nonpositive_counts_treated_as_empty(self, count):
        msg = models_mod.models_status_message(
            loading=False, connected=True, model_count=count,
        )
        assert msg == models_mod.MODELS_EMPTY_TEXT


class TestPresetsStatusMessage:
    def test_empty_shows_placeholder(self):
        msg = presets_mod.presets_status_message(0)
        assert msg == presets_mod.PRESETS_EMPTY_TEXT
        assert msg.strip()

    def test_presets_present_is_silent(self):
        assert presets_mod.presets_status_message(1) == ""


# ---------------------------------------------------------------------------
# 2. Escape-to-cancel predicate + GenerateWidget.handle_escape
# ---------------------------------------------------------------------------

class TestShouldCancelOnEscape:
    def test_active_enabled_cancel_fires(self):
        assert generate_mod.should_cancel_on_escape(True, "Cancel", True) is True

    @pytest.mark.parametrize("is_generating,text,enabled,expected", [
        (False, "Cancel", True, False),   # idle - nothing to cancel
        (True, "Generate", True, False),  # button not in cancel state
        (True, "Cancel", False, False),   # disabled: disconnected, interrupt would fail
        (False, "Generate", False, False),
    ])
    def test_guard_cases(self, is_generating, text, enabled, expected):
        assert generate_mod.should_cancel_on_escape(
            is_generating, text, enabled,
        ) is expected


def _escape_self(generating, text, enabled):
    calls = {"cancel": 0}
    return SimpleNamespace(
        is_generating=generating,
        generate_btn=SimpleNamespace(
            text=lambda: text,
            isEnabled=lambda: enabled,
        ),
        cancel=lambda: calls.__setitem__("cancel", calls["cancel"] + 1),
    ), calls


class TestGenerateWidgetHandleEscape:
    def test_consumes_and_cancels_when_active(self):
        self, calls = _escape_self(True, "Cancel", True)
        handled = generate_mod.GenerateWidget.handle_escape(self)
        assert handled is True
        assert calls["cancel"] == 1

    @pytest.mark.parametrize("generating,text,enabled", [
        (False, "Cancel", True),
        (True, "Generate", True),
        (True, "Cancel", False),
    ])
    def test_ignored_cases_do_not_cancel(self, generating, text, enabled):
        self, calls = _escape_self(generating, text, enabled)
        handled = generate_mod.GenerateWidget.handle_escape(self)
        assert handled is False
        assert calls["cancel"] == 0


# ---------------------------------------------------------------------------
# 3. Disabled-button why-tooltip + ForgeDocker wiring
# ---------------------------------------------------------------------------

class TestDisabledButtonTooltip:
    def test_connected_returns_empty(self):
        assert forge_mod.disabled_button_tooltip(True, "boom") == ""

    def test_disconnected_reuses_banner_reason(self):
        reason = "Connection refused. Is Forge running with --api?"
        assert forge_mod.disabled_button_tooltip(False, reason) == reason

    def test_disconnected_with_blank_reason_falls_back(self):
        for blank in ("", "   ", None):
            tip = forge_mod.disabled_button_tooltip(False, blank)
            assert tip.strip()
            assert tip == forge_mod.DISCONNECTED_TOOLTIP_FALLBACK


class _FakeBanner:
    def __init__(self):
        self._text = "No Connection"
        self._hidden = True

    def setText(self, text):
        self._text = text

    def text(self):
        return self._text

    def setHidden(self, hidden):
        self._hidden = bool(hidden)

    def isHidden(self):
        return self._hidden


class _FakeButton:
    def __init__(self, label):
        self._label = label
        self._enabled = True
        self._tooltip = ""

    def text(self):
        return self._label

    def setEnabled(self, value):
        self._enabled = bool(value)

    def isEnabled(self):
        return self._enabled

    def setToolTip(self, tip):
        self._tooltip = tip

    def toolTip(self):
        return self._tooltip


class _FakeScroll:
    def __init__(self, buttons):
        self._buttons = buttons

    def widget(self):
        return self

    def findChildren(self, cls):
        return list(self._buttons)


def _make_docker(api, labels):
    docker = forge_mod.ForgeDocker.__new__(forge_mod.ForgeDocker)
    docker.api = api
    docker.connection_banner = _FakeBanner()
    docker.content_area = _FakeScroll([_FakeButton(label) for label in labels])
    return docker


_LABELS = ["Generate", "Cancel", "Remove Background", "Foo"]


class TestConnectionStateTooltips:
    def test_disabled_buttons_get_why_tooltip(self):
        reason = "Could not connect - connection refused."
        api = SimpleNamespace(connected=False, last_error_message=reason)
        docker = _make_docker(api, _LABELS)

        forge_mod.ForgeDocker._update_connection_state(docker)

        by_label = {b.text(): b for b in docker.content_area._buttons}
        for label in ("Generate", "Cancel", "Remove Background"):
            assert by_label[label].isEnabled() is False
            assert by_label[label].toolTip() == reason
        # Unaffected buttons keep no tooltip.
        assert by_label["Foo"].toolTip() == ""
        assert by_label["Foo"].isEnabled() is True

    def test_blank_reason_still_yields_nonempty_tooltip(self):
        api = SimpleNamespace(connected=False, last_error_message="")
        docker = _make_docker(api, _LABELS)

        forge_mod.ForgeDocker._update_connection_state(docker)

        by_label = {b.text(): b for b in docker.content_area._buttons}
        assert by_label["Generate"].toolTip().strip()

    def test_recovery_clears_tooltip(self):
        api = SimpleNamespace(connected=False, last_error_message="boom")
        docker = _make_docker(api, _LABELS)
        forge_mod.ForgeDocker._update_connection_state(docker)

        api.connected = True
        api.last_error_message = ""
        forge_mod.ForgeDocker._update_connection_state(docker)

        by_label = {b.text(): b for b in docker.content_area._buttons}
        for label in ("Generate", "Cancel", "Remove Background"):
            assert by_label[label].isEnabled() is True
            assert by_label[label].toolTip() == ""


# ---------------------------------------------------------------------------
# 4. Page Escape wiring (only where a Cancel button exists)
# ---------------------------------------------------------------------------

class TestPageEscapeWiring:
    def test_cancel_pages_declare_keypresshandler(self):
        from forge.pages import img2img, inpaint, txt2img

        for page_cls in (txt2img.Txt2ImgPage, img2img.Img2ImgPage,
                         inpaint.InpaintPage):
            assert "keyPressEvent" in vars(page_cls), (
                "%s must handle Escape for its Cancel button" % page_cls.__name__
            )
            assert "cleanup" in vars(page_cls)

    def test_pages_without_cancel_do_not_handle_escape(self):
        from forge.pages import rembg, upscale

        assert "keyPressEvent" not in vars(rembg.RemBGPage)
        assert "keyPressEvent" not in vars(upscale.UpscalePage)


# ---------------------------------------------------------------------------
# 5. Empty-state label rendering in the history list (widget-level)
# ---------------------------------------------------------------------------

class _FakeItem:
    def __init__(self, widget):
        self._widget = widget

    def widget(self):
        return self._widget


class _FakeScrollLayout:
    def __init__(self):
        self._items = []
        self.alignments = []

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def addWidget(self, widget):
        self._items.append(_FakeItem(widget))

    def setAlignment(self, widget, flags):
        self.alignments.append((widget, flags))

    def widgets(self):
        return [item.widget() for item in self._items]


def _history_self(all_history, filtered, query=""):
    return SimpleNamespace(
        current_page=0,
        _all_history=all_history,
        _filtered_history=filtered,
        _thumbnail_cache={},
        reuse_required=SimpleNamespace(emit=lambda *args: None),
        search_box=SimpleNamespace(text=lambda: query),
        scroll_layout=_FakeScrollLayout(),
        _update_pagination_controls=MagicMock(),
    )


class TestHistoryEmptyLabel:
    def test_empty_history_renders_message_label(self):
        self = _history_self([], [])
        history_mod.HistoryWidget._populate_page(self)
        widgets = self.scroll_layout.widgets()
        assert len(widgets) == 1
        assert isinstance(widgets[0], history_mod.QLabel)
        assert self.scroll_layout.alignments  # centered, not top-stuck

    def test_filtered_empty_renders_message_label(self):
        entry = {"prompt": "a cat", "model": "m", "seed": 1}
        self = _history_self([entry], [], query="dog")
        history_mod.HistoryWidget._populate_page(self)
        assert len(self.scroll_layout.widgets()) == 1
        assert isinstance(self.scroll_layout.widgets()[0], history_mod.QLabel)

    def test_entries_present_render_entry_widgets_not_label(self):
        entries = [{"prompt": "p%d" % i, "model": "m", "seed": i}
                   for i in range(3)]
        self = _history_self(entries, list(entries))
        history_mod.HistoryWidget._populate_page(self)
        widgets = self.scroll_layout.widgets()
        assert len(widgets) == 3
        assert all(isinstance(w, history_mod.HistoryEntryWidget)
                   for w in widgets)
