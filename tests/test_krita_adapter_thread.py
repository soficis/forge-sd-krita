"""Critical #3: KritaAdapter.run_as_thread skip-if-busy contract.

Contract under test (documented in KritaAdapter.run_as_thread docstring):
- run_as_thread() returns True when the worker starts, False when a previous
  worker is still running (the new function is DROPPED, never queued and
  never overwriting the live thread/worker).
- An exception inside the worker body is forwarded via _Worker.error and
  ALWAYS clears the running flag (try/finally chain), so a failed run never
  wedges the adapter: the next run_as_thread() call starts normally.

Qt is unavailable outside Krita, so this module installs minimal QObject /
pyqtSignal / QThread stand-ins into the conftest forge.qt_compat mock BEFORE
(real) krita_adapter classes are bound. The install is unconditional plus an
importlib.reload: sibling test modules may import krita_adapter first (with
conftest's auto-mocks), and collection order must not decide which _Worker /
KritaAdapter the tests see. Original mock attributes are restored afterwards
(krita_adapter keeps its own references), so sibling suites are unaffected.
"""

from __future__ import annotations

import sys

# ---------------------------------------------------------------------------
# Qt fakes (installed into the conftest mock before krita_adapter is imported)
# ---------------------------------------------------------------------------

_qt_compat = sys.modules["forge.qt_compat"]


class _FakeBoundSignal:
    """Per-instance signal: connect()/emit() a slot list."""

    def __init__(self) -> None:
        self._slots: list = []

    def connect(self, slot):
        self._slots.append(slot)
        return slot

    def disconnect(self, slot=None) -> None:
        if slot is None:
            self._slots.clear()
        else:
            self._slots = [s for s in self._slots if s != slot]

    def emit(self, *args, **kwargs) -> None:
        for slot in list(self._slots):
            slot(*args, **kwargs)


class _FakeSignalDescriptor:
    """pyqtSignal stand-in as a descriptor so each _Worker instance gets its
    own bound signal (mirrors real Qt bound-signal semantics)."""

    def __init__(self, *types) -> None:
        self._types = types
        self._attr = ""

    def __set_name__(self, owner, name: str) -> None:
        self._attr = "_bound_" + name

    def __get__(self, obj, owner=None):
        if obj is None:
            return self
        bound = getattr(obj, self._attr, None)
        if bound is None:
            bound = _FakeBoundSignal()
            setattr(obj, self._attr, bound)
        return bound


def _fake_pyqtSignal(*types):
    return _FakeSignalDescriptor(*types)


class _FakeQObject:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def moveToThread(self, thread) -> None:
        self._thread = thread

    def deleteLater(self) -> None:
        pass


class FakeQThread:
    """Synchronous QThread stand-in.

    start() marks the thread running and (by default) delivers the `started`
    signal inline, so the worker body runs deterministically without an event
    loop. With auto_emit=False the thread stays "running" until the test
    manually fires `thread.started.emit()`, simulating a busy worker.
    """

    def __init__(self, auto_emit: bool = True) -> None:
        self._running = False
        self._auto_emit = auto_emit
        self.started = _FakeBoundSignal()
        self.start_calls = 0

    def isRunning(self) -> bool:
        return self._running

    def start(self) -> None:
        self.start_calls += 1
        self._running = True
        if self._auto_emit:
            self.started.emit()

    def quit(self) -> None:
        self._running = False

    def wait(self, *args, **kwargs) -> bool:
        return True

    def deleteLater(self) -> None:
        pass


class _ExplodingThread(FakeQThread):
    """Simulates QThread.start() itself failing (e.g. OS thread limit)."""

    def start(self) -> None:
        self.start_calls += 1
        raise RuntimeError("boom: cannot start thread")


_MISSING = object()
_fakes = {
    "QObject": _FakeQObject,
    "QPointF": object,
    "QThread": FakeQThread,
    "pyqtSignal": _fake_pyqtSignal,
    "qAlpha": lambda pixel: 0,
    "qRgb": lambda r, g, b: 0,
}
_saved_qt_attrs = {}
for _name, _obj in _fakes.items():
    _saved_qt_attrs[_name] = getattr(_qt_compat, _name, _MISSING)
    setattr(_qt_compat, _name, _obj)

# ---------------------------------------------------------------------------
# Imports under test (fakes installed above; reload rebinds _Worker /
# KritaAdapter to the fakes even if a sibling module imported krita_adapter
# first with conftest auto-mocks)
# ---------------------------------------------------------------------------

import importlib

import forge.adapters.krita_adapter as krita_adapter_mod

krita_adapter_mod = importlib.reload(krita_adapter_mod)
from forge.adapters.krita_adapter import KritaAdapter, _Worker

for _name, _orig in _saved_qt_attrs.items():
    if _orig is _MISSING:
        try:
            delattr(_qt_compat, _name)
        except AttributeError:
            pass
    else:
        setattr(_qt_compat, _name, _orig)
del _name, _obj, _orig, _saved_qt_attrs, _fakes, _MISSING


def _make_adapter():
    return KritaAdapter()


def test_second_run_while_active_is_refused_not_overwritten(monkeypatch):
    """A run_as_thread() call while a worker is active returns False and must
    neither overwrite the live thread/worker nor invoke the dropped fn."""
    monkeypatch.setattr(
        krita_adapter_mod, "QThread", lambda: FakeQThread(auto_emit=False)
    )
    adapter = _make_adapter()

    calls1, afters1 = [], []
    calls2, afters2 = [], []
    assert adapter.run_as_thread(lambda: calls1.append(1), lambda: afters1.append(1)) is True
    assert adapter.is_running() is True

    live_thread, live_worker = adapter.thread, adapter.worker

    # Second run while the first is still active: refused, dropped cleanly.
    assert adapter.run_as_thread(lambda: calls2.append(1), lambda: afters2.append(1)) is False
    assert calls2 == [] and afters2 == []
    assert adapter.thread is live_thread
    assert adapter.worker is live_worker

    # Completing the first run clears the flag; a third run starts normally.
    adapter.thread.started.emit()
    assert calls1 == [1] and afters1 == [1]
    assert adapter.is_running() is False

    calls3, afters3 = [], []
    assert adapter.run_as_thread(lambda: calls3.append(1), lambda: afters3.append(1)) is True
    adapter.thread.started.emit()  # manual thread: deliver `started` explicitly
    assert calls3 == [1] and afters3 == [1]
    assert adapter.is_running() is False


def test_worker_exception_clears_flag_and_next_run_starts():
    """A raising worker body forwards via error, still fires after_function,
    clears the running flag, and the next run starts (no permanent wedge)."""
    adapter = _make_adapter()

    def _boom():
        raise RuntimeError("worker exploded")

    errors, afters = [], []
    assert adapter.run_as_thread(_boom, lambda: afters.append(1)) is True
    # _Worker.run() catches the raise internally and emits finished, so the
    # completion callback fires and the adapter is idle again.
    assert afters == [1]
    assert adapter.is_running() is False

    calls, afters2 = [], []
    assert adapter.run_as_thread(lambda: calls.append(1), lambda: afters2.append(1)) is True
    assert calls == [1] and afters2 == [1]
    assert errors == []  # error signal asserted directly below, not here
    assert adapter.is_running() is False


def test_worker_error_signal_forwards_exception():
    """_Worker.run() emits the caught exception via error, then finished."""
    errors, dones = [], []

    def _boom():
        raise ValueError("bad pixels")

    worker = _Worker(_boom)
    worker.error.connect(errors.append)
    worker.finished.connect(lambda: dones.append(True))
    worker.run()

    assert len(errors) == 1 and isinstance(errors[0], ValueError)
    assert dones == [True]


def test_successful_run_clears_flag_and_quits_thread():
    """Happy path: True returned, after_function fires once, thread stopped."""
    adapter = _make_adapter()
    calls, afters = [], []
    assert adapter.run_as_thread(lambda: calls.append(1), lambda: afters.append(1)) is True
    assert calls == [1] and afters == [1]
    assert adapter.is_running() is False
    assert adapter.thread.isRunning() is False


def test_thread_start_failure_clears_flag(monkeypatch):
    """If QThread.start() itself raises, run_as_thread() refuses cleanly
    (False) instead of wedging the adapter with a stuck running flag."""
    monkeypatch.setattr(krita_adapter_mod, "QThread", _ExplodingThread)
    adapter = _make_adapter()
    calls, afters = [], []
    assert adapter.run_as_thread(lambda: calls.append(1), lambda: afters.append(1)) is False
    assert calls == [] and afters == []
    assert adapter.is_running() is False
    # Adapter recovered: a later run with a working thread starts.
    monkeypatch.setattr(krita_adapter_mod, "QThread", FakeQThread)
    assert adapter.run_as_thread(lambda: calls.append(1), lambda: afters.append(1)) is True
    assert calls == [1] and afters == [1]
