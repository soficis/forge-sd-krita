"""Task 29 (Phase 2): Quick Mask polish on the Inpaint page.

One action that (a) reuses an existing ``Forge Mask`` paint layer or creates
one via ``KritaAdapter.setup_mask_layer``, (b) enters paint mode through
documented pykrita APIs (``Krita.action`` + ``View.setEraserMode`` /
``erase_action`` — ``View.setPaintingMode`` does not exist publicly; toast
fallback when unreachable), and (c) leaves the white/black mask read path
(``get_mask_and_image``) untouched.

Failing-first (pre-change ``handle_quick_mask``): always creates a new layer
(never reuses), has no eraser/paint normalization, and lets adapter
exceptions escape into the Qt slot instead of showing a dialog — tests 1-6
are red until the polish lands; test 7 is the green round-trip guard.

Widget module is loaded fresh under stub-Qt real classes (pattern:
tests/test_controlnet_dict_guards.py) because subclassing conftest's
MagicMock Qt does not work.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# Pin real modules into sys.modules BEFORE the fresh loader runs so its
# cleanup pass cannot pop krita_adapter / the widgets package out from
# under later imports (stale qt_compat bindings).
from forge.settings_controller import SettingsController  # noqa: E402
import forge.adapters.krita_adapter  # noqa: F401,E402
import forge.widgets  # noqa: F401,E402


# ---------------------------------------------------------------------------
# Real-stub-Qt loader for forge/widgets/mask.py
# ---------------------------------------------------------------------------

_QT_NAMES = [
    "Qt", "QWidget", "QVBoxLayout", "QHBoxLayout", "QFormLayout",
    "QLabel", "QComboBox", "QPushButton", "QCheckBox", "QTabWidget",
    "QGroupBox", "QSlider", "QSpinBox", "QDoubleSpinBox", "QPlainTextEdit",
    "QScrollArea", "QColor", "QPainter", "QByteArray", "QBuffer", "QImage",
    "QIODevice", "QObject", "QThread", "QTimer", "pyqtSignal", "QSize",
    "QIcon", "QPixmap", "QPointF", "qAlpha", "qRgb",
    "QSizePolicy", "QListView", "QListWidget", "QListWidgetItem",
    "QMessageBox",
]


def _load_mask_real():
    """Import mask.py fresh with stub-Qt classes; return the module."""
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
            # Plain-value getters mirroring tests/conftest.py: real widget
            # code compares these against ints/uses them as strings.
            if name in ("findText", "findData"):
                return lambda *args, **kwargs: -1
            if name in ("isChecked", "isVisible", "isNull"):
                return lambda *args, **kwargs: False
            if name in ("text", "currentText"):
                return lambda *args, **kwargs: ""
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
            pathlib.Path(__file__).resolve().parent.parent
            / "forge" / "widgets" / "mask.py"
        )
        mod_name = "forge.widgets.mask_task29"
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
                     and k != "forge.widgets.mask_task29"]:
            sys.modules.pop(_key, None)


mask_mod = _load_mask_real()
MaskWidget = mask_mod.MaskWidget


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeLayerNode:
    def __init__(self, uuid: str):
        self._uuid = uuid

    def uniqueId(self):
        return self._uuid


class _FakeMaskKC:
    """KritaAdapter double covering the quick-mask call surface."""

    def __init__(self, existing=None, create_error: Exception | None = None):
        self.existing = existing
        self.create_error = create_error
        self.queried: str | None = None
        self.setup_calls: list[str] = []
        self.activated: list = []
        self.brush_calls = 0
        self.active_uuid = "bg-uuid"
        self.mask_reads: list[str] = []
        self.selection_bounds = (0, 0, 0, 0)
        self.layer_bounds = (0, 0, 4, 4)

    def get_layer_by_name(self, name: str):
        self.queried = name
        return self.existing

    def setup_mask_layer(self, name: str = "Forge Mask"):
        if self.create_error is not None:
            raise self.create_error
        self.setup_calls.append(name)
        self.active_uuid = "new-mask-uuid"

    def set_layer_uuid_as_active(self, uuid):
        self.activated.append(uuid)
        self.active_uuid = uuid

    def activate_brush(self):
        self.brush_calls += 1

    def get_active_layer_uuid(self):
        return self.active_uuid

    def get_layer_bounds(self):
        return self.layer_bounds

    def get_selection_bounds(self):
        return self.selection_bounds

    def get_mask_and_image(self, mode: str = "canvas"):
        self.mask_reads.append(mode)
        return "mask-b64", "image-b64"

    def get_paintable_layer_names(self):
        return []


def _make_settings(tmp_path):
    defaults = {
        "inpaint": {
            "mask_blur": 0,
            "mask_mode": 0,
            "masked_content": 0,
            "inpaint_area": 0,
            "padding": 0,
            "auto_update_mask": False,
            "results_below_mask": False,
            "hide_mask_on_gen": True,
            "reference_layer": "",
        },
        "hide_ui": {
            "inpaint_auto_update": False,
            "inpaint_below_mask": False,
            "inpaint_hide_mask": False,
        },
    }
    (tmp_path / "default_settings.json").write_text(
        json.dumps(defaults), encoding="utf-8"
    )
    return SettingsController(base_dir=tmp_path)


def _make_widget(tmp_path, kc):
    widget = MaskWidget(
        _make_settings(tmp_path),
        MagicMock(),
        {"x": 0, "y": 0, "w": 0, "h": 0},
    )
    widget.kc = kc
    return widget


def _fake_action(checked: bool = True):
    return SimpleNamespace(
        trigger=MagicMock(),
        isChecked=MagicMock(return_value=checked),
    )


def _fake_krita(view, actions=None):
    """Patchable stand-in for mask.py's ``Krita`` symbol."""
    krita = MagicMock()
    instance = krita.instance.return_value
    actions = actions or {}
    instance.action.side_effect = lambda name: actions.get(name, 0)
    window = MagicMock()
    window.activeView.return_value = view
    instance.activeWindow.return_value = window
    return krita


def _view_krita6():
    """View exposing Krita 6.0+ setEraserMode."""
    return SimpleNamespace(
        setEraserMode=MagicMock(),
        showFloatingMessage=MagicMock(),
    )


def _view_legacy():
    """View WITHOUT setEraserMode (Krita 5.x) but with the toast API."""
    return SimpleNamespace(showFloatingMessage=MagicMock())


# ---------------------------------------------------------------------------
# (a) create / reuse + read path
# ---------------------------------------------------------------------------


class TestQuickMaskLayerBootstrap:
    def test_creates_layer_when_absent_and_reads_mask(self, tmp_path):
        kc = _FakeMaskKC(existing=None)
        widget = _make_widget(tmp_path, kc)

        widget.handle_quick_mask()  # must not raise

        assert kc.queried == "Forge Mask"
        assert kc.setup_calls == ["Forge Mask"]
        assert kc.active_uuid == "new-mask-uuid"  # layer active set
        assert kc.brush_calls == 1
        assert kc.mask_reads == ["layer"]
        assert widget.mask_uuid == "new-mask-uuid"

    def test_reuses_existing_mask_layer(self, tmp_path):
        node = _FakeLayerNode("mask-uuid-1")
        kc = _FakeMaskKC(existing=node)
        widget = _make_widget(tmp_path, kc)

        widget.handle_quick_mask()  # must not raise

        assert kc.queried == "Forge Mask"
        assert kc.setup_calls == []  # no duplicate layer
        assert kc.activated == ["mask-uuid-1"]
        assert widget.mask_uuid == "mask-uuid-1"
        assert kc.mask_reads == ["layer"]

    def test_roundtrip_read_path_unchanged(self, tmp_path):
        """Regression guard: white/black read path + size dict untouched."""
        kc = _FakeMaskKC()
        widget = _make_widget(tmp_path, kc)

        widget.handle_quick_mask()

        assert widget.selection_mode == "layer"
        assert widget.mask == "mask-b64"
        assert widget.image == "image-b64"
        assert widget.size_dict == {"x": 0, "y": 0, "w": 4, "h": 4}


# ---------------------------------------------------------------------------
# (b) paint-mode entry via documented pykrita APIs
# ---------------------------------------------------------------------------


class TestQuickMaskPaintMode:
    def test_enters_paint_mode_via_set_eraser_mode(self, tmp_path):
        kc = _FakeMaskKC()
        widget = _make_widget(tmp_path, kc)
        view = _view_krita6()
        krita = _fake_krita(view)

        with patch.object(mask_mod, "Krita", krita, create=True):
            widget.handle_quick_mask()

        view.setEraserMode.assert_called_once_with(False)
        view.showFloatingMessage.assert_not_called()  # API reachable: no toast
        assert kc.brush_calls == 1

    def test_legacy_view_toggles_off_active_eraser_action(self, tmp_path):
        kc = _FakeMaskKC()
        widget = _make_widget(tmp_path, kc)
        view = _view_legacy()
        erase = _fake_action(checked=True)
        krita = _fake_krita(view, actions={"erase_action": erase})

        with patch.object(mask_mod, "Krita", krita, create=True):
            widget.handle_quick_mask()

        assert krita.instance.called  # paint-mode entry went through Krita
        erase.trigger.assert_called_once_with()  # eraser ON -> toggled to paint
        view.showFloatingMessage.assert_not_called()

    def test_legacy_view_leaves_inactive_eraser_action_untouched(self, tmp_path):
        kc = _FakeMaskKC()
        widget = _make_widget(tmp_path, kc)
        view = _view_legacy()
        erase = _fake_action(checked=False)
        krita = _fake_krita(view, actions={"erase_action": erase})

        with patch.object(mask_mod, "Krita", krita, create=True):
            widget.handle_quick_mask()

        assert krita.instance.called
        erase.trigger.assert_not_called()  # never force eraser ON
        view.showFloatingMessage.assert_not_called()

    def test_toasts_paint_fallback_when_tool_api_unreachable(self, tmp_path):
        """No setEraserMode, no erase_action -> create/select layer + toast."""
        kc = _FakeMaskKC()
        widget = _make_widget(tmp_path, kc)
        view = _view_legacy()
        krita = _fake_krita(view, actions={})  # every action lookup -> 0

        with patch.object(mask_mod, "Krita", krita, create=True):
            widget.handle_quick_mask()  # must not raise

        view.showFloatingMessage.assert_called_once()
        assert "paint" in view.showFloatingMessage.call_args[0][0].lower()
        assert kc.setup_calls == ["Forge Mask"]  # layer still created+active
        assert kc.mask_reads == ["layer"]  # read path unaffected by fallback


# ---------------------------------------------------------------------------
# adapter failure -> user-visible error, no crash
# ---------------------------------------------------------------------------


class TestQuickMaskErrorSurface:
    def test_adapter_create_error_shows_dialog_without_crash(self, tmp_path):
        kc = _FakeMaskKC(
            existing=None, create_error=RuntimeError("disk full on createNode")
        )
        widget = _make_widget(tmp_path, kc)

        with patch.object(mask_mod, "QMessageBox", create=True) as mb:
            widget.handle_quick_mask()  # must NOT raise

        mb.warning.assert_called_once()
        args = mb.warning.call_args[0]
        assert args[1] == "Quick Mask"
        assert "disk full on createNode" in args[2]
