"""Failing-first: mousewheel over a QComboBox must NOT change its value.

User-reported bug: scrolling the docker wheel-steps the combo under the
cursor (QComboBox::wheelEvent mutates currentIndex), silently changing
model/sampler/VAE/upscaler/style settings while the page scrolls.

conftest's Qt layer is MagicMock-based (subclassing it yields mocks, not
classes), so this file loads forge/widgets/no_wheel.py fresh under its own
stub-Qt layer of REAL classes (pattern: tests/test_controlnet_dict_guards.py).
The stub QComboBox models Qt's wheel handling - a delivered wheel steps
currentIndex and is accepted - so "value unchanged" proves the filter really
blocked delivery rather than the stub quietly ignoring wheel events.

Assertions are behavioural: after the filter is installed, a wheel delivered
to the combo leaves the value unchanged AND the event unaccepted (Qt's wheel
loop only hops to the parent scroll area while the event stays unaccepted);
programmatic setters keep working; non-wheel events are not swallowed.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types


# ---------------------------------------------------------------------------
# Stub-Qt layer: real classes modelling Qt delivery rules
# ---------------------------------------------------------------------------

class QObject:
    """Minimal QObject: parent/child tree + event-filter bookkeeping."""

    def __init__(self, parent=None):
        self._parent = parent
        self._children = []
        self._filters = []
        if parent is not None:
            parent._children.append(self)

    def parent(self):
        return self._parent

    def children(self):
        return list(self._children)

    def findChildren(self, cls):
        found = []
        for child in self._children:
            if isinstance(child, cls):
                found.append(child)
            found.extend(child.findChildren(cls))
        return found

    def installEventFilter(self, flt):
        # Qt re-installs an existing filter rather than duplicating it.
        if flt in self._filters:
            self._filters.remove(flt)
        self._filters.insert(0, flt)

    def eventFilter(self, watched, event):
        return False

    def event(self, event):
        return False

    def deliver(self, event):
        """Model QCoreApplicationPrivate::notify_helper: object event filters
        run first; only an unfiltered event reaches the target's event()."""
        for flt in list(self._filters):
            if flt.eventFilter(self, event):
                return event.isAccepted()  # filtered: target never sees it
        self.event(event)
        return event.isAccepted()


class QEvent:
    class Type:
        Wheel = 1
        KeyPress = 2
        MouseButtonPress = 3
        ChildAdded = 4

    def __init__(self, type_):
        self._type = type_
        self._accepted = True  # QEvent starts accepted, as in Qt

    def type(self):
        return self._type

    def accept(self):
        self._accepted = True

    def ignore(self):
        self._accepted = False

    def isAccepted(self):
        return self._accepted


class QChildEvent(QEvent):
    def __init__(self, type_, child):
        super().__init__(type_)
        self._child = child

    def child(self):
        return self._child


class QComboBox(QObject):
    """Stub combo whose event() mirrors QComboBox::wheelEvent (steps the
    index and accepts) - i.e. the bug as shipped when SH_ComboBox_
    AllowWheelScrolling is true (Krita on Windows)."""

    def __init__(self, items, parent=None):
        super().__init__(parent)
        self._items = list(items)
        self._index = 0
        self.handled = []  # event types that actually reached event()

    def count(self):
        return len(self._items)

    def currentIndex(self):
        return self._index

    def setCurrentIndex(self, index):
        self._index = index

    def currentText(self):
        if 0 <= self._index < len(self._items):
            return self._items[self._index]
        return ""

    def setCurrentText(self, text):
        if text in self._items:
            self._index = self._items.index(text)
            return True
        return False

    def event(self, event):
        etype = event.type()
        self.handled.append(etype)
        if etype == QEvent.Type.Wheel:
            if self._index + 1 < len(self._items):
                self._index += 1
            event.accept()
            return True
        if etype in (QEvent.Type.KeyPress, QEvent.Type.MouseButtonPress):
            event.accept()
            return True
        return False


# ---------------------------------------------------------------------------
# Load the module under test fresh (real classes, not conftest's mocks)
# ---------------------------------------------------------------------------

_STUB_NAMES = ("QComboBox", "QEvent", "QObject")


def _load_no_wheel():
    """Import forge/widgets/no_wheel.py under the stub-Qt layer above."""
    stub = types.ModuleType("forge.qt_compat")
    for name in _STUB_NAMES:
        setattr(stub, name, globals()[name])
    stub.__all__ = list(_STUB_NAMES)

    pre_keys = set(sys.modules)
    old = sys.modules.get("forge.qt_compat")
    sys.modules["forge.qt_compat"] = stub
    mod_name = "forge.widgets.no_wheel_nw_test"
    try:
        path = (
            pathlib.Path(__file__).resolve().parent.parent
            / "forge" / "widgets" / "no_wheel.py"
        )
        spec = importlib.util.spec_from_file_location(mod_name, str(path))
        assert spec is not None and spec.loader is not None, (
            f"cannot load {path} (missing module?)"
        )
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
        for key in [k for k in sys.modules if k not in pre_keys
                    and k != mod_name]:
            sys.modules.pop(key, None)


nw_mod = _load_no_wheel()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ITEMS = ("alpha", "beta", "gamma")


def _combo_with_filter():
    combo = QComboBox(ITEMS)
    flt = nw_mod.install_no_wheel(combo)
    return combo, flt


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHarnessModelsTheBug:
    def test_unfiltered_wheel_steps_index_and_is_consumed(self):
        """Honesty check: without the filter the stub reproduces the bug, so
        the value-unchanged assertions below would fail on a no-op filter."""
        combo = QComboBox(ITEMS)
        wheel = QEvent(QEvent.Type.Wheel)

        consumed = combo.deliver(wheel)

        assert combo.currentIndex() == 1  # wheel stepped the value...
        assert consumed is True  # ...and the combo ate the event


class TestNoWheelFilter:
    def test_wheel_over_combo_leaves_value_unchanged_and_event_unconsumed(self):
        combo, _ = _combo_with_filter()
        wheel = QEvent(QEvent.Type.Wheel)

        consumed = combo.deliver(wheel)

        assert combo.currentIndex() == 0
        assert consumed is False, (
            "event must stay unaccepted so the wheel propagates to the "
            "parent scroll area"
        )
        assert QEvent.Type.Wheel not in combo.handled, (
            "the combo itself must never receive the wheel event"
        )

    def test_repeated_wheel_does_not_walk_the_selection(self):
        combo, _ = _combo_with_filter()
        for _ in range(5):
            combo.deliver(QEvent(QEvent.Type.Wheel))
        assert combo.currentIndex() == 0
        assert combo.currentText() == "alpha"

    def test_programmatic_setters_still_work_after_install(self):
        combo, _ = _combo_with_filter()

        assert combo.setCurrentText("gamma") is True
        assert combo.currentIndex() == 2
        assert combo.currentText() == "gamma"

        combo.setCurrentIndex(0)
        assert combo.currentText() == "alpha"

    def test_key_events_reach_the_combo(self):
        combo, flt = _combo_with_filter()
        key = QEvent(QEvent.Type.KeyPress)

        assert flt.eventFilter(combo, key) is False
        consumed = combo.deliver(key)
        assert QEvent.Type.KeyPress in combo.handled
        assert consumed is True

    def test_mouse_events_reach_the_combo(self):
        combo, flt = _combo_with_filter()
        press = QEvent(QEvent.Type.MouseButtonPress)

        assert flt.eventFilter(combo, press) is False
        combo.deliver(press)
        assert QEvent.Type.MouseButtonPress in combo.handled

    def test_wheel_over_non_combo_widget_is_not_swallowed(self):
        """The filter may sit on non-combo widgets (ChildAdded cascade);
        wheel events there must pass through so only combos are blocked."""
        widget = QObject()
        flt = nw_mod.install_no_wheel(widget)
        wheel = QEvent(QEvent.Type.Wheel)

        assert flt.eventFilter(widget, wheel) is False
        assert wheel.isAccepted() is True  # untouched: still default-accepted

    def test_install_walks_the_whole_subtree(self):
        root = QObject()
        mid = QObject(root)
        deep_combo = QComboBox(ITEMS, mid)
        top_combo = QComboBox(ITEMS, root)
        outside = QComboBox(ITEMS)

        flt = nw_mod.install_no_wheel(root)

        assert flt in root._filters
        assert flt in mid._filters
        assert flt in deep_combo._filters
        assert flt in top_combo._filters
        assert flt not in outside._filters

        outside_wheel = QEvent(QEvent.Type.Wheel)
        outside.deliver(outside_wheel)
        assert outside.currentIndex() == 1  # untouched widgets behave as Qt does

    def test_widgets_created_after_install_get_the_filter(self):
        """Pages and dynamic units (ControlNet rows, presets) build combos
        after construction: a ChildAdded event must extend coverage."""
        root = QObject()
        flt = nw_mod.install_no_wheel(root)

        # New subtree built AFTER install, then attached to the tree.
        panel = QObject()
        late_combo = QComboBox(ITEMS, panel)
        added = QChildEvent(QEvent.Type.ChildAdded, panel)
        assert flt.eventFilter(root, added) is False, (
            "ChildAdded must not be swallowed (Qt needs it for layouts)"
        )
        panel._parent = root
        root._children.append(panel)

        wheel = QEvent(QEvent.Type.Wheel)
        consumed = late_combo.deliver(wheel)

        assert late_combo.currentIndex() == 0
        assert consumed is False
        assert QEvent.Type.Wheel not in late_combo.handled
