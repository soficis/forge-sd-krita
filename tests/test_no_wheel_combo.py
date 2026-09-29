"""Failing-first: mousewheel over a value widget must NOT change its value.

User-reported bugs: scrolling the docker wheel-steps the combo under the
cursor (QComboBox::wheelEvent mutates currentIndex), and after the combo
fix still wheel-steps sliders and spin boxes (QSlider and QAbstractSpinBox
wheel handlers step the value) - silently changing sampler steps, CFG
scale, refiner start, denoise strength and soft-inpainting settings while
the page scrolls.

conftest's Qt layer is MagicMock-based (subclassing it yields mocks, not
classes), so this file loads forge/widgets/no_wheel.py fresh under its own
stub-Qt layer of REAL classes (pattern: tests/test_controlnet_dict_guards.py).
The stubs model Qt's wheel handling - a delivered wheel steps the value and
is accepted - so "value unchanged" proves the filter really blocked delivery
rather than the stub quietly ignoring wheel events.

Assertions are behavioural: after the filter is installed, a wheel delivered
to a combo/slider/spin box leaves the value unchanged AND the event
unaccepted (Qt's wheel loop only hops to the parent scroll area while the
event stays unaccepted); programmatic setters keep working; non-wheel
events are not swallowed.
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


class QAbstractSpinBox(QObject):
    """Stub spin-box base whose event() mirrors QAbstractSpinBox::wheelEvent
    (steps the value and accepts) - the bug behind QSpinBox/QDoubleSpinBox
    (steps, CFG scale, batch count, mask blur, ...)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0
        self.handled = []  # event types that actually reached event()

    def value(self):
        return self._value

    def setValue(self, value):
        self._value = value

    def event(self, event):
        etype = event.type()
        self.handled.append(etype)
        if etype == QEvent.Type.Wheel:
            self._value += 1  # singleStep=1, as QSpinBox does per notch
            event.accept()
            return True
        if etype in (QEvent.Type.KeyPress, QEvent.Type.MouseButtonPress):
            event.accept()
            return True
        return False


class QSpinBox(QAbstractSpinBox):
    """Integer spin box - a QAbstractSpinBox subclass in Qt too."""


class QDoubleSpinBox(QAbstractSpinBox):
    """Float spin box - a QAbstractSpinBox subclass in Qt too."""


class QSlider(QObject):
    """Stub slider whose event() mirrors QSlider::wheelEvent: the wheel steps
    the position and is accepted. QSlider derives from QAbstractSlider, NOT
    QAbstractSpinBox (verified against real Qt6), so it needs its own entry."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0
        self.handled = []  # event types that actually reached event()

    def value(self):
        return self._value

    def setValue(self, value):
        self._value = value

    def event(self, event):
        etype = event.type()
        self.handled.append(etype)
        if etype == QEvent.Type.Wheel:
            self._value += 1  # singleStep per notch, as QSlider does
            event.accept()
            return True
        if etype in (QEvent.Type.KeyPress, QEvent.Type.MouseButtonPress):
            event.accept()
            return True
        return False


class QScrollArea(QObject):
    """Stub scroll area whose event() consumes the wheel (models the docker's
    QScrollArea actually scrolling when an unaccepted wheel bubbles up)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.wheels_scrolled = 0

    def event(self, event):
        if event.type() == QEvent.Type.Wheel:
            self.wheels_scrolled += 1
            event.accept()
            return True
        return False


# ---------------------------------------------------------------------------
# Load the module under test fresh (real classes, not conftest's mocks)
# ---------------------------------------------------------------------------

_STUB_NAMES = ("QComboBox", "QEvent", "QObject", "QAbstractSpinBox", "QSlider")


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


def _filtered(widget):
    nw_mod.install_no_wheel(widget)
    return widget


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

    def test_unfiltered_wheel_steps_spin_box_value_and_is_consumed(self):
        """Honesty check for spin boxes: QAbstractSpinBox::wheelEvent steps
        value per notch, so an unfiltered stub must reproduce that or the
        spin-box assertions below would pass on a no-op filter."""
        for box in (QSpinBox(), QDoubleSpinBox()):
            box.setValue(50)
            wheel = QEvent(QEvent.Type.Wheel)

            consumed = box.deliver(wheel)

            assert box.value() == 51, type(box).__name__
            assert consumed is True, type(box).__name__

    def test_unfiltered_wheel_steps_slider_value_and_is_consumed(self):
        """Honesty check for sliders: QSlider::wheelEvent steps the value per
        notch (real Qt6 verified: 50 -> 53), so an unfiltered stub must
        reproduce that or the slider assertions would pass on a no-op filter."""
        slider = QSlider()
        slider.setValue(50)
        wheel = QEvent(QEvent.Type.Wheel)

        consumed = slider.deliver(wheel)

        assert slider.value() == 51
        assert consumed is True


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


class TestNoWheelFilterSpinAndSlider:
    @staticmethod
    def _assert_blocked(widget, value_of):
        wheel = QEvent(QEvent.Type.Wheel)

        consumed = widget.deliver(wheel)

        assert value_of() == 0, "wheel must not have stepped the value"
        assert consumed is False, (
            "event must stay unaccepted so the wheel propagates to the "
            "parent scroll area"
        )
        assert QEvent.Type.Wheel not in widget.handled, (
            f"{type(widget).__name__} itself must never receive the wheel"
        )

    def test_wheel_over_spin_box_leaves_value_unchanged_and_unconsumed(self):
        box = _filtered(QSpinBox())
        self._assert_blocked(box, box.value)

    def test_wheel_over_double_spin_box_leaves_value_unchanged_and_unconsumed(
        self,
    ):
        box = _filtered(QDoubleSpinBox())
        box.setValue(5.0)

        wheel = QEvent(QEvent.Type.Wheel)
        consumed = box.deliver(wheel)

        assert box.value() == 5.0
        assert consumed is False
        assert QEvent.Type.Wheel not in box.handled

    def test_wheel_over_slider_leaves_value_unchanged_and_unconsumed(self):
        slider = _filtered(QSlider())
        slider.setValue(70)

        wheel = QEvent(QEvent.Type.Wheel)
        consumed = slider.deliver(wheel)

        assert slider.value() == 70
        assert consumed is False
        assert QEvent.Type.Wheel not in slider.handled

    def test_repeated_wheel_does_not_walk_spin_box_or_slider_values(self):
        for widget, initial in ((_filtered(QSpinBox()), 0),
                                (_filtered(QSlider()), 0)):
            for _ in range(5):
                widget.deliver(QEvent(QEvent.Type.Wheel))
            assert widget.value() == initial, type(widget).__name__

    def test_programmatic_setters_still_work_after_install(self):
        box = _filtered(QSpinBox())
        assert box.value() == 0
        box.setValue(42)
        assert box.value() == 42

        slider = _filtered(QSlider())
        slider.setValue(70)
        assert slider.value() == 70

    def test_key_events_reach_the_spin_box(self):
        box = _filtered(QSpinBox())
        flt = box._filters[0]
        key = QEvent(QEvent.Type.KeyPress)

        assert flt.eventFilter(box, key) is False
        box.deliver(key)
        assert QEvent.Type.KeyPress in box.handled

    def test_enclosing_scroll_area_still_receives_the_wheel(self):
        """The guard must not swallow scrolling: a blocked (unaccepted) wheel
        bubbles to the parent QScrollArea, which scrolls the docker page."""
        scroll = QScrollArea()
        box = QSpinBox(scroll)
        _filtered(scroll)

        consumed = box.deliver(QEvent(QEvent.Type.Wheel))

        assert box.value() == 0
        assert consumed is False, "unaccepted wheel must bubble to the parent"
        # Qt's notify loop hops to the parent while unaccepted: model that.
        if not consumed:
            scroll.deliver(QEvent(QEvent.Type.Wheel))
        assert scroll.wheels_scrolled == 1, "the scroll area must still scroll"

    def test_text_edit_wheels_are_not_filtered(self):
        """Prompt/QPlainTextEdit wheels must keep scrolling content - only
        value widgets are guarded. A plain QObject stands in: the filter's
        isinstance check must not match non-value widgets."""
        widget = QObject()
        flt = nw_mod.install_no_wheel(widget)
        wheel = QEvent(QEvent.Type.Wheel)

        assert flt.eventFilter(widget, wheel) is False

    def test_spin_boxes_and_sliders_created_after_install_are_covered(self):
        """Dynamic pages/units build value widgets after construction: the
        ChildAdded cascade must extend coverage to them too."""
        root = QObject()
        flt = nw_mod.install_no_wheel(root)

        panel = QObject()
        late_box = QSpinBox(panel)
        late_slider = QSlider(panel)
        added = QChildEvent(QEvent.Type.ChildAdded, panel)
        assert flt.eventFilter(root, added) is False
        panel._parent = root
        root._children.append(panel)

        for widget in (late_box, late_slider):
            consumed = widget.deliver(QEvent(QEvent.Type.Wheel))
            assert widget.value() == 0, type(widget).__name__
            assert consumed is False, type(widget).__name__
            assert QEvent.Type.Wheel not in widget.handled, type(widget).__name__

    def test_install_walks_subtree_covering_spin_boxes_and_sliders(self):
        root = QObject()
        mid = QObject(root)
        deep_box = QSpinBox(mid)
        top_slider = QSlider(root)
        outside_box = QSpinBox()

        flt = nw_mod.install_no_wheel(root)

        assert flt in deep_box._filters
        assert flt in top_slider._filters
        assert flt not in outside_box._filters

        outside_box.deliver(QEvent(QEvent.Type.Wheel))
        assert outside_box.value() == 1
