"""Shared test infrastructure — mocks Krita and Qt dependencies so that
forge modules can be imported outside the Krita application environment.

This file is loaded by pytest before any test module is collected.
"""

from __future__ import annotations

import sys
import types
from abc import ABCMeta
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Mock the Krita application runtime
# ---------------------------------------------------------------------------

_krita_mock = MagicMock()
sys.modules.setdefault("krita", _krita_mock)

# ---------------------------------------------------------------------------
# Mock PyQt5 (and PyQt6) so qt_compat can be imported
# ---------------------------------------------------------------------------

for _mod in (
    "PyQt5",
    "PyQt5.QtCore",
    "PyQt5.QtGui",
    "PyQt5.QtWidgets",
    "PyQt6",
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
):
    sys.modules.setdefault(_mod, MagicMock())

# ---------------------------------------------------------------------------
# Mock the forge.forge module so forge.__init__'s "from .forge import ForgeDocker"
# doesn't execute real Qt code.
# ---------------------------------------------------------------------------

if "forge.forge" not in sys.modules:
    _forge_module = types.ModuleType("forge.forge")
    _forge_module.ForgeDocker = MagicMock()
    sys.modules["forge.forge"] = _forge_module

# ---------------------------------------------------------------------------
# Ensure forge.qt_compat exposes expected Qt symbols as mock objects
# ---------------------------------------------------------------------------

if "forge.qt_compat" not in sys.modules:
    _qt_compat = types.ModuleType("forge.qt_compat")

    class _QtMeta(ABCMeta):
        def __getattr__(cls, name):
            if name.startswith("__") and name.endswith("__"):
                raise AttributeError(name)
            mock = MagicMock(name="%s.%s" % (cls.__name__, name))
            setattr(cls, name, mock)
            return mock

    class _QtBase(MagicMock, metaclass=_QtMeta):
        def __new__(cls, *args, **kwargs):
            return object.__new__(cls)

        def __init__(self, *args, **kwargs):
            MagicMock.__init__(self)

        def __getattr__(self, name):
            if name in ("findText", "findData"):
                return lambda *args, **kwargs: -1
            if name in ("currentIndex", "count", "value", "exec"):
                return lambda *args, **kwargs: 0
            if name in (
                "currentText",
                "text",
                "toPlainText",
                "placeholderText",
                "windowTitle",
            ):
                return lambda *args, **kwargs: ""
            if name in (
                "isChecked",
                "isHidden",
                "isVisible",
                "isActive",
                "isNull",
                "isRunning",
            ):
                return lambda *args, **kwargs: False
            return super().__getattr__(name)

    def _make_qt_class(name):
        return _QtMeta(name, (_QtBase,), {})

    # Broad Qt surface: every symbol forge imports from qt_compat (explicitly
    # or via `import *`), so widget/page/adapter modules import under mocks.
    _qt_names = (
        "Qt",
        "QObject",
        "QThread",
        "QThreadPool",
        "QRunnable",
        "QTimer",
        "QEventLoop",
        "QSize",
        "QSizePolicy",
        "QPoint",
        "QPointF",
        "QRect",
        "QUrl",
        "QDateTime",
        "QBuffer",
        "QByteArray",
        "QIODevice",
        "QImage",
        "QImageReader",
        "QPixmap",
        "QIcon",
        "QColor",
        "QBrush",
        "QPen",
        "QPalette",
        "QFont",
        "QCursor",
        "QPainter",
        "QWidget",
        "QDialog",
        "QDialogButtonBox",
        "QMessageBox",
        "QFileDialog",
        "QLabel",
        "QPushButton",
        "QCheckBox",
        "QComboBox",
        "QSpinBox",
        "QDoubleSpinBox",
        "QSlider",
        "QLineEdit",
        "QTextEdit",
        "QPlainTextEdit",
        "QListView",
        "QListWidget",
        "QListWidgetItem",
        "QTableWidget",
        "QTabWidget",
        "QTreeWidget",
        "QScrollArea",
        "QGroupBox",
        "QSplitter",
        "QFrame",
        "QProgressBar",
        "QMenu",
        "QAction",
        "QApplication",
        "QVBoxLayout",
        "QHBoxLayout",
        "QFormLayout",
        "QGridLayout",
        "QLayout",
        "QSpacerItem",
        "QAbstractItemView",
        "QHeaderView",
        "QStyledItemDelegate",
        "QDoubleValidator",
        "QIntValidator",
        "QDesktopServices",
        "pyqtSignal",
        "pyqtSlot",
        "qAlpha",
        "qRgb",
        "qRgba",
    )
    for _name in _qt_names:
        setattr(_qt_compat, _name, _make_qt_class(_name))
    _qt_compat.__all__ = list(_qt_names)

    def _qt_compat_getattr(name):
        cls = _make_qt_class(name)
        setattr(_qt_compat, name, cls)
        return cls

    _qt_compat.__getattr__ = _qt_compat_getattr
    sys.modules["forge.qt_compat"] = _qt_compat
