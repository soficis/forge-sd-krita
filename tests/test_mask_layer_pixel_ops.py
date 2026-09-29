"""Mask-layer pixel ops: clear/fill buffer content + 0-255 opacity contract.

Confirmed live in Krita 5.3.2.1 (real error dialogs):
  AttributeError: 'Node' object has no attribute 'clear'
    mask.py:375 _clear_mask -> krita_adapter.clear_mask_layer -> node.clear()
  TypeError: setOpacity(self, value: int): argument 1 has unexpected type 'float'
    mask.py:367 _toggle_mask_opacity -> krita_adapter.set_mask_opacity -> node.setOpacity(0.5)

pykrita's Node exposes no clear() - setPixelData(QByteArray, x, y, w, h) is
the only pixel-write path - and setOpacity takes an int 0-255 while the
adapter documents 0.0-1.0 (mask.py passes 0.5 / 1.0).

krita_adapter.py is loaded FRESH under stub-Qt classes with a real,
inspectable QByteArray (pattern from tests/test_denoise_turbo_guard.py):
conftest's MagicMock Qt yields mocks, not classes, and forge/__init__
imports krita.
"""

from __future__ import annotations

import importlib.util
import inspect
import pathlib
import sys
import types
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Behaviour-recording stub Qt (real classes, not mocks)
# ---------------------------------------------------------------------------

class _FakeQByteArray:
    """QByteArray stand-in that keeps the payload byte-inspectable."""

    def __init__(self, data=b""):
        if isinstance(data, _FakeQByteArray):
            data = data._data
        self._data = bytes(data)

    def data(self) -> bytes:
        return self._data

    def length(self) -> int:
        return len(self._data)

    def __bytes__(self) -> bytes:
        return self._data

    def __len__(self) -> int:
        return len(self._data)


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


_QT_NAMES = [
    "QBuffer", "QIODevice", "QObject", "QPointF", "QThread", "Qt",
    "pyqtSignal", "QImage", "qAlpha", "qRgb",
]


def _load_krita_adapter_real():
    """Import krita_adapter.py fresh with stub-Qt classes; return the module."""
    stub = types.ModuleType("forge.qt_compat")
    for _name in _QT_NAMES:
        setattr(stub, _name, _Meta(_name, (_StubBase,), {}))
    stub.QByteArray = _FakeQByteArray
    stub.__all__ = _QT_NAMES + ["QByteArray"]

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
            / "forge" / "adapters" / "krita_adapter.py"
        )
        mod_name = "forge.adapters.krita_adapter_mask_pixel_ops"
        spec = importlib.util.spec_from_file_location(mod_name, str(path))
        mod = importlib.util.module_from_spec(spec)
        mod.__package__ = "forge.adapters"
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        if old is not None:
            sys.modules["forge.qt_compat"] = old
        else:
            sys.modules.pop("forge.qt_compat", None)
        for _key in [k for k in sys.modules if k not in pre_keys
                     and k != "forge.adapters.krita_adapter_mask_pixel_ops"]:
            sys.modules.pop(_key, None)


krita_mod = _load_krita_adapter_real()


# ---------------------------------------------------------------------------
# Fake Krita runtime (real classes with pykrita's actual API surface)
# ---------------------------------------------------------------------------

class _FakeRect:
    def __init__(self, x, y, w, h):
        self._x, self._y, self._w, self._h = x, y, w, h

    def x(self):
        return self._x

    def y(self):
        return self._y

    def width(self):
        return self._w

    def height(self):
        return self._h


class _FakeNode:
    """pykrita Node surface: setPixelData + int setOpacity; NO clear()."""

    def __init__(self, x=0, y=0, w=0, h=0):
        self._rect = _FakeRect(x, y, w, h)
        self.pixel_calls = []
        self._opacity = 255

    def bounds(self):
        return self._rect

    def setPixelData(self, data, x, y, w, h):
        self.pixel_calls.append((data, x, y, w, h))

    def setOpacity(self, value):
        # Mirrors the real binding: setOpacity(self, value: int)
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(
                "setOpacity(self, value: int): argument 1 has unexpected type '%s'"
                % type(value).__name__
            )
        self._opacity = value

    def opacity(self):
        return self._opacity


class _FakeDocument:
    def __init__(self, node):
        self._node = node
        self.refresh_count = 0

    def activeNode(self):
        return self._node

    def refreshProjection(self):
        self.refresh_count += 1


class _FakeKrita:
    def __init__(self, document):
        self._document = document

    def instance(self):
        return self

    def activeDocument(self):
        return self._document


def _adapter(monkeypatch, node):
    doc = _FakeDocument(node)
    monkeypatch.setattr(krita_mod, "Krita", _FakeKrita(doc))
    return krita_mod.KritaAdapter(), doc


# ---------------------------------------------------------------------------
# 1-2. clear_mask_layer: all-zero buffer at the node's bounds
# ---------------------------------------------------------------------------

class TestClearMaskLayer:
    def test_clear_writes_all_zero_buffer_at_node_bounds(self, monkeypatch):
        """The reported crash: Node has no clear(); clear must go through
        setPixelData with a fully transparent (all-0x00) buffer."""
        node = _FakeNode(x=3, y=4, w=5, h=6)
        adapter, doc = _adapter(monkeypatch, node)

        adapter.clear_mask_layer(node)

        assert len(node.pixel_calls) == 1
        data, x, y, w, h = node.pixel_calls[0]
        assert (x, y, w, h) == (3, 4, 5, 6)
        raw = data.data()
        assert len(raw) == 5 * 6 * 4  # 4 bytes per pixel
        assert raw == bytes(len(raw))  # all zero = fully transparent
        assert doc.refresh_count == 1

    def test_clear_on_zero_area_node_is_noop_not_crash(self, monkeypatch):
        node = _FakeNode(w=0, h=0)
        adapter, doc = _adapter(monkeypatch, node)

        adapter.clear_mask_layer(node)

        assert node.pixel_calls == []
        assert doc.refresh_count == 1


# ---------------------------------------------------------------------------
# 3-4. fill_mask_layer: regression guard (all-0xFF opaque white)
# ---------------------------------------------------------------------------

class TestFillMaskLayer:
    def test_fill_writes_all_ff_buffer_at_node_bounds(self, monkeypatch):
        node = _FakeNode(x=7, y=9, w=4, h=3)
        adapter, doc = _adapter(monkeypatch, node)

        adapter.fill_mask_layer(node)

        assert len(node.pixel_calls) == 1
        data, x, y, w, h = node.pixel_calls[0]
        assert (x, y, w, h) == (7, 9, 4, 3)
        raw = data.data()
        assert len(raw) == 4 * 3 * 4
        assert raw == bytes([255]) * (4 * 3 * 4)  # all-0xFF = opaque white
        assert doc.refresh_count == 1

    def test_fill_on_zero_area_node_is_noop_not_crash(self, monkeypatch):
        node = _FakeNode(w=10, h=0)
        adapter, doc = _adapter(monkeypatch, node)

        adapter.fill_mask_layer(node)

        assert node.pixel_calls == []
        assert doc.refresh_count == 1


# ---------------------------------------------------------------------------
# 5-6. set_mask_opacity: documented 0.0-1.0 float -> Krita int 0-255
# ---------------------------------------------------------------------------

class TestSetMaskOpacity:
    def test_half_opacity_maps_to_128(self, monkeypatch):
        """Reported crash: setOpacity takes int 0-255, mask.py passes 0.5."""
        node = _FakeNode()
        adapter, doc = _adapter(monkeypatch, node)

        adapter.set_mask_opacity(0.5, node)

        assert node.opacity() == 128
        assert doc.refresh_count == 1

    def test_full_opacity_maps_to_255(self, monkeypatch):
        node = _FakeNode()
        adapter, doc = _adapter(monkeypatch, node)

        adapter.set_mask_opacity(1.0, node)

        assert node.opacity() == 255
        assert doc.refresh_count == 1


# ---------------------------------------------------------------------------
# 7-8. get_mask_opacity: documented 0.0-1.0 contract + round trip
# ---------------------------------------------------------------------------

class TestGetMaskOpacity:
    def test_get_returns_documented_float_range(self, monkeypatch):
        node = _FakeNode()
        node.setOpacity(128)
        adapter, _ = _adapter(monkeypatch, node)

        value = adapter.get_mask_opacity(node)

        assert isinstance(value, float)
        assert abs(value - 128 / 255) < 1e-9

    def test_get_and_set_are_inverse_within_rounding(self, monkeypatch):
        node = _FakeNode()
        adapter, _ = _adapter(monkeypatch, node)

        expected_int = {0.0: 0, 0.5: 128, 1.0: 255}
        for target in (0.0, 0.5, 1.0):
            adapter.set_mask_opacity(target, node)
            assert node.opacity() == expected_int[target]
            read_back = adapter.get_mask_opacity(node)
            assert isinstance(read_back, float)
            assert abs(read_back - target) <= 0.5 / 255 + 1e-12
            # Re-setting the read-back value must be stable (no drift).
            adapter.set_mask_opacity(read_back, node)
            assert node.opacity() == expected_int[target]


# ---------------------------------------------------------------------------
# 9. Public signatures stay byte-identical for existing callers (mask.py)
# ---------------------------------------------------------------------------

def test_public_signatures_unchanged_for_mask_widget_callers():
    expected = {
        "clear_mask_layer": ["self", "layer"],
        "fill_mask_layer": ["self", "layer"],
        "set_mask_opacity": ["self", "opacity", "layer"],
        "get_mask_opacity": ["self", "layer"],
    }
    for name, params in expected.items():
        sig = inspect.signature(getattr(krita_mod.KritaAdapter, name))
        assert list(sig.parameters) == params, name
        assert sig.parameters["layer"].default is None, name
