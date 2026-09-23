"""Task 30: live preview overlay for img2img/inpaint generation.

Failing-first anchors (red pre-change):
- invalid/empty preview b64 must be skipped without raising
  (pre-change: binascii.Error escapes the Qt timer slot through the real
  adapter decode path).
- the live preview path must cap the preview at 512 max dimension
  (pre-change: update_preview_layer scales the frame to the full target
  size, violating the plan's "512 cap stays" requirement).

Plan-premise correction encoded here: progress_check has NO mode gating —
the shared GenerateWidget already drives preview updates for txt2img,
img2img and inpaint alike. Wiring lives entirely in generate.py +
krita_adapter.py; forge/pages/img2img.py and forge/pages/inpaint.py need
no changes.
"""

from __future__ import annotations

import base64
import importlib.util
import pathlib
import sys
import time
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from forge.adapters import krita_adapter as ka_mod


# ---------------------------------------------------------------------------
# Fresh stub-Qt module loader (pattern from tests/test_controlnet_dict_guards.py)
# ---------------------------------------------------------------------------

_QT_NAMES = [
    "Qt", "QWidget", "QVBoxLayout", "QHBoxLayout", "QFormLayout",
    "QLabel", "QComboBox", "QPushButton", "QCheckBox", "QTabWidget",
    "QGroupBox", "QSlider", "QSpinBox", "QDoubleSpinBox", "QPlainTextEdit",
    "QTextEdit", "QScrollArea", "QColor", "QPainter", "QByteArray",
    "QBuffer", "QImage", "QIODevice", "QObject", "QThread", "QTimer",
    "QProgressBar", "pyqtSignal", "QSize", "QIcon", "QPixmap", "QPointF",
    "qAlpha", "qRgb",
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


generate_mod = _load_real(
    "forge/widgets/generate.py", "forge.widgets.generate_task30"
)
GenerateWidget = generate_mod.GenerateWidget


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class _PreviewKC:
    """KritaAdapter stand-in whose update_preview_layer decodes base64 the
    same way the real adapter does (base64.b64decode first), so malformed
    frames raise exactly as they would through the real pixel path."""

    def __init__(self):
        self.preview_calls: list[tuple] = []
        self.delete_calls = 0

    def update_preview_layer(self, b64str, x, y, w, h):
        base64.b64decode(b64str)
        self.preview_calls.append((b64str, x, y, w, h))

    def delete_preview_layer(self):
        self.delete_calls += 1


def _progress_response(image, percent=0.5):
    return {"progress": percent, "current_image": image, "state": {}}


def _stub_self(**overrides):
    """SimpleNamespace self for unbound GenerateWidget methods."""
    stub = SimpleNamespace(
        api=MagicMock(),
        kc=_PreviewKC(),
        settings_controller=SimpleNamespace(
            get=MagicMock(return_value=True)
        ),
        mode="img2img",
        abort=False,
        finished=False,
        is_generating=True,
        debug=False,
        results=None,
        current_job=None,
        current_generation_data={},
        history_manager=MagicMock(),
        job_queue=[],
        progress_timer=None,
        generate_btn=MagicMock(),
        progress_bar=MagicMock(),
        list_of_widgets=[],
        update=MagicMock(),
        update_progress_bar=MagicMock(),
        _update_queue_status=MagicMock(),
        _restore_hidden_layers=MagicMock(),
        _stop_generation_loop=MagicMock(),
        _progress_timer_start=time.time(),
        _last_progress_change_time=time.time(),
        _last_progress_value=-1,
    )
    for key, value in overrides.items():
        setattr(stub, key, value)
    return stub


def _bind_real(stub, name):
    """Rebind a GenerateWidget method so the stub runs the real logic."""
    setattr(
        stub, name,
        lambda *args, **kwargs: getattr(GenerateWidget, name)(stub, *args, **kwargs),
    )
    return stub


# ---------------------------------------------------------------------------
# 1. Progress callback with b64 image -> preview update with the image data
# ---------------------------------------------------------------------------

class TestProgressPreviewUpdate:
    def test_img2img_progress_b64_updates_preview_layer(self):
        image = base64.b64encode(b"fake-png-bytes").decode()
        stub = _stub_self()
        stub.api.get_progress.return_value = _progress_response(image)

        GenerateWidget.progress_check(stub, 10, 20, 512, 512, {})

        assert stub.kc.preview_calls == [(image, 10, 20, 512, 512)]

    def test_preview_disabled_skips_update(self):
        stub = _stub_self(
            settings_controller=SimpleNamespace(
                get=MagicMock(return_value=False)
            )
        )
        stub.api.get_progress.return_value = _progress_response(
            base64.b64encode(b"x").decode()
        )

        GenerateWidget.progress_check(stub, 0, 0, 64, 64, {})

        assert stub.kc.preview_calls == []


# ---------------------------------------------------------------------------
# 2 & 3. Preview layer removed on completion AND interrupt (regression guards)
# ---------------------------------------------------------------------------

class TestPreviewLayerRemoval:
    def test_completion_removes_preview_layer(self):
        stub = _bind_real(_stub_self(results=None), "_stop_generation_loop")

        GenerateWidget.threadable_return(stub, 0, 0, 64, 64, {})

        assert stub.kc.delete_calls == 1

    def test_failure_in_results_path_still_removes_preview_layer(self):
        stub = _bind_real(_stub_self(), "_stop_generation_loop")
        stub.results = {"images": []}
        stub.history_manager.save_generation_async.side_effect = RuntimeError(
            "boom"
        )
        # results_to_layers on a MagicMock adapter is fine; force the finally
        # path by making prune raise instead.
        with patch.object(
            generate_mod, "prune_generation_results", side_effect=RuntimeError("x")
        ):
            with pytest.raises(RuntimeError):
                GenerateWidget.threadable_return(stub, 0, 0, 64, 64, {})

        assert stub.kc.delete_calls == 1

    def test_cancel_interrupt_removes_preview_layer(self):
        stub = _bind_real(_stub_self(), "_stop_generation_loop")

        GenerateWidget.cancel(stub)

        stub.api.interrupt.assert_called_once_with()
        assert stub.kc.delete_calls == 1
        assert stub.abort is True


# ---------------------------------------------------------------------------
# 4. Empty/invalid preview b64 -> skip update, no exception (FAILING-FIRST)
# ---------------------------------------------------------------------------

class TestInvalidPreviewFrame:
    @pytest.mark.parametrize("bad", ["!!!!", "not valid base64!!", "@@"])
    def test_invalid_b64_skips_update_without_exception(self, bad):
        stub = _stub_self()
        stub.api.get_progress.return_value = _progress_response(bad)

        GenerateWidget.progress_check(stub, 0, 0, 512, 512, {})

        assert stub.kc.preview_calls == []


# ---------------------------------------------------------------------------
# 5. No second QTimer instantiated
# ---------------------------------------------------------------------------

def test_no_second_qtimer_instantiated():
    path = (
        pathlib.Path(__file__).resolve().parent.parent
        / "forge" / "widgets" / "generate.py"
    )
    source = path.read_text(encoding="utf-8")
    # Exactly two occurrences: the `from krita import QTimer` import and the
    # single parented `QTimer(self)` construction in _start_next_job.
    assert source.count("QTimer") == 2


# ---------------------------------------------------------------------------
# 6. 512 max-dim cap on the live preview path (FAILING-FIRST)
# ---------------------------------------------------------------------------

class TestPreviewResolutionCap:
    def test_large_target_capped_to_512_max_dim(self):
        adapter = ka_mod.KritaAdapter.__new__(ka_mod.KritaAdapter)
        with patch.object(
            ka_mod.KritaAdapter, "base64_to_pixeldata",
            return_value=(b"", 4, 3),
        ) as m_pixel, patch.object(
            ka_mod.KritaAdapter, "_ensure_document",
            return_value=MagicMock(),
        ), patch.object(
            ka_mod.KritaAdapter, "_apply_preview_pixels"
        ) as m_apply:
            ka_mod.KritaAdapter.update_preview_layer(
                adapter, "Zm9v", 10, 20, 1024, 768
            )

        _b64, w, h = m_pixel.call_args.args
        assert max(w, h) <= 512
        assert (w, h) == (512, 384)  # target aspect preserved
        m_apply.assert_called_once()

    def test_target_already_within_cap_unchanged(self):
        adapter = ka_mod.KritaAdapter.__new__(ka_mod.KritaAdapter)
        with patch.object(
            ka_mod.KritaAdapter, "base64_to_pixeldata",
            return_value=(b"", 4, 3),
        ) as m_pixel, patch.object(
            ka_mod.KritaAdapter, "_ensure_document",
            return_value=MagicMock(),
        ), patch.object(
            ka_mod.KritaAdapter, "_apply_preview_pixels"
        ):
            ka_mod.KritaAdapter.update_preview_layer(
                adapter, "Zm9v", 0, 0, 400, 300
            )

        assert m_pixel.call_args.args[1:] == (400, 300)

    def test_progress_check_forwards_full_target_to_adapter(self):
        """The cap lives inside update_preview_layer (its only caller is the
        timer path), so progress_check still forwards the raw target size."""
        image = base64.b64encode(b"frame").decode()
        stub = _stub_self()
        stub.api.get_progress.return_value = _progress_response(image)

        GenerateWidget.progress_check(stub, 0, 0, 1024, 768, {})

        assert stub.kc.preview_calls == [(image, 0, 0, 1024, 768)]
