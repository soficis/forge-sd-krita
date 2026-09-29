"""QComboBox::wheelEvent steps currentIndex, QAbstractSpinBox::wheelEvent and
QSlider::wheelEvent step their value on each wheel tick, so scrolling a docker
page silently mutates the setting under the cursor. Block the wheel from
reaching those value widgets but leave it unaccepted so parents still scroll."""

from __future__ import annotations

from ..qt_compat import QAbstractSpinBox, QComboBox, QEvent, QObject, QSlider

_FILTER = None

# Widgets whose wheelEvent mutates a setting; scrolling must not touch them.
_WHEEL_STEPPERS = (
    QComboBox,  # steps currentIndex: model/sampler/VAE/style pickers
    QAbstractSpinBox,  # steps value: QSpinBox/QDoubleSpinBox (steps, CFG, batch)
    QSlider,  # steps value; NOT a QAbstractSpinBox subclass (QAbstractSlider)
)


class NoWheelFilter(QObject):
    def eventFilter(self, obj, event):
        etype = event.type()
        if etype == QEvent.Type.Wheel and isinstance(obj, _WHEEL_STEPPERS):
            event.ignore()
            return True
        if etype == QEvent.Type.ChildAdded:
            # Pages/dynamic units build value widgets after construction; cascade.
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
