"""Task 13 (High #6): mask-layer visibility must be restored to its snapshot
after generation — on success AND failure/interrupt — never force-shown.

Failing-first: tests 2, 3, 4 fail on the pre-fix code (restore force-sets
visible True; generate early-return / exception / cancel paths never restore).
"""

from __future__ import annotations

import json
import types
from unittest.mock import MagicMock, patch

import pytest

from forge.settings_controller import SettingsController


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeLayer:
    """Minimal Krita node double tracking visibility."""

    def __init__(self, visible=True):
        self._visible = bool(visible)
        self.set_visible_calls: list[bool] = []

    def setVisible(self, value):
        self._visible = bool(value)
        self.set_visible_calls.append(bool(value))

    def visible(self):
        return self._visible


class _FakeMaskKC:
    """KritaAdapter double for MaskWidget tests."""

    def __init__(self, layer):
        self._layer = layer
        self.active_uuid = "mask-uuid-1"
        self.activated: list = []

    def get_layer_from_uuid(self, uuid):
        return self._layer

    @staticmethod
    def set_layer_visible(layer, visible=True):
        layer.setVisible(visible)

    def get_active_layer_uuid(self):
        return self.active_uuid

    def set_layer_uuid_as_active(self, uuid):
        self.activated.append(uuid)
        self.active_uuid = uuid

    def get_selection_bounds(self):
        return (0, 0, 0, 0)

    def qimage_to_b64_str(self, image):
        return "ZmFrZQ=="


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


def _make_mask_widget(tmp_path, layer):
    from forge.widgets.mask import MaskWidget

    widget = MaskWidget(_make_settings(tmp_path), MagicMock(), {"x": 0, "y": 0, "w": 0, "h": 0})
    widget.kc = _FakeMaskKC(layer)
    widget.mask_uuid = "mask-uuid-1"
    widget.selection_mode = "canvas"
    widget.image = object()  # non-None: skip mask re-fetch in get_generation_data
    widget.mask = None
    widget.variables["hide_mask_on_gen"] = True
    widget.variables["auto_update_mask"] = False
    widget.variables["reference_layer"] = ""
    return widget


# ---------------------------------------------------------------------------
# MaskWidget snapshot/restore
# ---------------------------------------------------------------------------


class TestMaskVisibilitySnapshot:
    def test_visible_true_fail_restored_via_finally(self, tmp_path):
        """Happy-path guard: visible mask hidden during gen, restored after fail."""
        layer = _FakeLayer(visible=True)
        widget = _make_mask_widget(tmp_path, layer)

        widget.get_generation_data()
        assert layer.visible() is False  # hidden while generating
        with pytest.raises(RuntimeError, match="backend exploded"):
            try:
                raise RuntimeError("backend exploded mid-generation")
            finally:
                widget.restore_hidden_layers()
        assert layer.visible() is True

    def test_hidden_stays_hidden_after_success(self, tmp_path):
        """Restore-to-snapshot: a mask the user already hid must stay hidden."""
        layer = _FakeLayer(visible=False)
        widget = _make_mask_widget(tmp_path, layer)

        widget.get_generation_data()
        assert layer.visible() is False
        widget.restore_hidden_layers()
        assert layer.visible() is False  # pre-fix: force-shown True -> FAIL

    def test_hidden_stays_hidden_after_failure(self, tmp_path):
        """Failure path must also restore the snapshot, not force-show."""
        layer = _FakeLayer(visible=False)
        widget = _make_mask_widget(tmp_path, layer)

        widget.get_generation_data()
        with pytest.raises(RuntimeError, match="backend exploded"):
            try:
                raise RuntimeError("backend exploded mid-generation")
            finally:
                widget.restore_hidden_layers()
        assert layer.visible() is False  # pre-fix: force-shown True -> FAIL

    def test_restore_is_idempotent(self, tmp_path):
        layer = _FakeLayer(visible=True)
        widget = _make_mask_widget(tmp_path, layer)

        widget.get_generation_data()
        widget.restore_hidden_layers()
        widget.restore_hidden_layers()  # second call: no-op, no crash
        assert layer.visible() is True


# ---------------------------------------------------------------------------
# KritaAdapter.get_mask_and_image snapshot/restore
# ---------------------------------------------------------------------------


class _FakeNode:
    def __init__(self, visible):
        self._visible = visible

    def channels(self):
        return [object()]

    def projectionPixelData(self, x, y, w, h):
        return b"\x00" * 16

    def setVisible(self, value):
        self._visible = bool(value)

    def visible(self):
        return self._visible


class _FakeBounds:
    def __init__(self, x, y, w, h):
        self._v = (x, y, w, h)

    def x(self):
        return self._v[0]

    def y(self):
        return self._v[1]

    def width(self):
        return self._v[2]

    def height(self):
        return self._v[3]


class _FakeDoc:
    def __init__(self, node):
        self._node = node

    def activeNode(self):
        return self._node

    def refreshProjection(self):
        return None

    def projection(self, x, y, w, h):
        return "source-sentinel"

    def bounds(self):
        return _FakeBounds(0, 0, 2, 2)


class TestGetMaskAndImageRestore:
    def _run(self, was_visible):
        from forge.adapters import krita_adapter as adapter_mod

        node = _FakeNode(was_visible)
        doc = _FakeDoc(node)
        krita = MagicMock()
        krita.instance.return_value.activeDocument.return_value = doc
        with patch.object(adapter_mod, "Krita", krita):
            adapter = adapter_mod.KritaAdapter()
            mask, source = adapter.get_mask_and_image("canvas")
        return node, mask, source

    def test_restores_prior_hidden(self):
        """A mask layer that started hidden must still be hidden afterwards."""
        node, _mask, source = self._run(False)
        assert source == "source-sentinel"
        assert node.visible() is False  # pre-fix: force-shown True -> FAIL

    def test_restores_prior_visible(self):
        node, _mask, _source = self._run(True)
        assert node.visible() is True


# ---------------------------------------------------------------------------
# GenerateWidget failure/interrupt paths must restore too
# ---------------------------------------------------------------------------


def _make_generate_widget(mask_double, kc):
    from forge.widgets.generate import GenerateWidget

    settings = MagicMock()
    settings.get.return_value = None
    api = MagicMock()
    api.defaults = {"model": "test-sdxl-ckpt"}
    widget = GenerateWidget(
        settings, api, [mask_double], "inpaint", {"x": 0, "y": 0, "w": 0, "h": 0}
    )
    widget.kc = kc
    return widget


def _mask_double(payload):
    return types.SimpleNamespace(
        get_generation_data=MagicMock(return_value=payload),
        restore_hidden_layers=MagicMock(),
    )


class TestGenerateRestorePaths:
    def test_empty_prompt_return_restores(self):
        """Empty prompt bails out AFTER MaskWidget hid the layer -> must restore."""
        mask = _mask_double({})
        kc = MagicMock()
        kc.get_selection_bounds.return_value = (0, 0, 0, 0)
        kc.get_canvas_size.return_value = (512, 512)
        gen = _make_generate_widget(mask, kc)

        gen.generate()  # no prompt -> early return, no job queued
        assert gen.job_queue == []
        mask.restore_hidden_layers.assert_called_once_with()  # pre-fix: never -> FAIL

    def test_start_next_job_exception_restores(self):
        """Failure between hide and thread start must not leak a hidden mask."""
        mask = _mask_double({"prompt": "a cat"})
        kc = MagicMock()
        kc.get_selection_bounds.return_value = (0, 0, 0, 0)
        kc.get_canvas_size.return_value = (512, 512)
        kc.refresh_doc.side_effect = RuntimeError("krita doc gone")
        gen = _make_generate_widget(mask, kc)

        with pytest.raises(RuntimeError):
            gen.generate()
        mask.restore_hidden_layers.assert_called()  # pre-fix: never -> FAIL

    def test_cancel_restores(self):
        """User interrupt must restore the snapshot (threadable_return may never run)."""
        mask = _mask_double({"prompt": "a cat"})
        kc = MagicMock()
        gen = _make_generate_widget(mask, kc)

        gen.cancel()
        mask.restore_hidden_layers.assert_called_once_with()  # pre-fix: never -> FAIL
