"""CollapsibleWidget starts collapsed, marks its state, and toggles.

forge.widgets.collapsible is loaded fresh with minimal Qt stand-ins (importing
``forge`` needs krita); the real PyQt6 behaviour was checked separately.
"""

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class _Signal:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)

    def emit(self, *args):
        for slot in self.slots:
            try:
                slot(*args)
            except TypeError:
                slot()  # Qt drops 'checked' for slots that don't take it


class _Widget:
    def __init__(self, *a, **k):
        self._visible = True
        self._layout = None

    def setLayout(self, layout):
        self._layout = layout

    def layout(self):
        return self._layout

    def show(self):
        self._visible = True

    def hide(self):
        self._visible = False

    def isHidden(self):
        return not self._visible

    def update(self):
        pass


class _Layout:
    def __init__(self):
        self.items = []

    def setContentsMargins(self, *a):
        pass

    def addWidget(self, w):
        self.items.append(w)


class _Button(_Widget):
    def __init__(self, text=""):
        super().__init__()
        self._text, self._checked = text, False
        self.clicked = _Signal()

    def setObjectName(self, n):
        pass

    def setCheckable(self, c):
        pass

    def setChecked(self, c):
        self._checked = bool(c)

    def isChecked(self):
        return self._checked

    def setText(self, t):
        self._text = t

    def text(self):
        return self._text

    def click(self):
        self._checked = not self._checked
        self.clicked.emit(self._checked)


def _load():
    qt = types.ModuleType("fp_col.qt_compat")
    qt.QPushButton, qt.QVBoxLayout, qt.QWidget = _Button, _Layout, _Widget
    pkg = types.ModuleType("fp_col")
    pkg.__path__ = []
    widgets = types.ModuleType("fp_col.widgets")
    widgets.__path__ = []
    sys.modules.update({"fp_col": pkg, "fp_col.qt_compat": qt, "fp_col.widgets": widgets})
    spec = importlib.util.spec_from_file_location(
        "fp_col.widgets.collapsible", ROOT / "forge/widgets/collapsible.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod.CollapsibleWidget


Collapsible = _load()


def test_starts_collapsed_by_default():
    section = Collapsible("Seed Details", _Widget())
    assert section.child.isHidden()
    assert not section.toggle_label.isChecked()


def test_expanded_true_keeps_the_section_open():
    section = Collapsible("Model", _Widget(), expanded=True)
    assert not section.child.isHidden()


def test_click_toggles_and_the_header_mark_follows():
    section = Collapsible("Seed Details", _Widget())
    closed = section.toggle_label.text()
    section.toggle_label.click()
    assert not section.child.isHidden()
    assert section.toggle_label.text() != closed
    section.toggle_label.click()
    assert section.child.isHidden()
    assert section.toggle_label.text() == closed


def test_header_keeps_the_section_title():
    section = Collapsible("Generation History", _Widget())
    assert section.toggle_label.text().endswith("Generation History")
    assert section.title == "Generation History"
