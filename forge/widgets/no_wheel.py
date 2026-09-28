"""QComboBox::wheelEvent steps currentIndex on each wheel tick, so scrolling a
docker page silently mutates the setting under the cursor. Block the wheel
from reaching combos but leave it unaccepted so parents still scroll."""

from __future__ import annotations

from ..qt_compat import QComboBox, QEvent, QObject

_FILTER = None


class NoWheelFilter(QObject):
    def eventFilter(self, obj, event):
        etype = event.type()
        if etype == QEvent.Type.Wheel and isinstance(obj, QComboBox):
            event.ignore()
            return True
        if etype == QEvent.Type.ChildAdded:
            # Pages/dynamic units build combos after construction; cascade.
            _install(event.child(), self)
        return False


def _install(root, flt):
    root.installEventFilter(flt)
    for child in root.findChildren(QObject):
        child.installEventFilter(flt)


def install_no_wheel(root):
    """Install the wheel-blocking filter on root and every descendant."""
    global _FILTER
    if _FILTER is None:
        _FILTER = NoWheelFilter()
    _install(root, _FILTER)
    return _FILTER
