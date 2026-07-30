"""Shared test infrastructure — mocks Krita and Qt dependencies so that
forge modules can be imported outside the Krita application environment.

This file is loaded by pytest before any test module is collected.
"""

from __future__ import annotations

import sys
import types
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
    for _name in (
        "Qt",
        "QComboBox",
        "QLabel",
        "QPushButton",
        "QScrollArea",
        "QVBoxLayout",
        "QWidget",
        "QColor",
        "QPainter",
        "QByteArray",
        "QBuffer",
        "QImage",
        "QIODevice",
    ):
        setattr(_qt_compat, _name, MagicMock())
    sys.modules["forge.qt_compat"] = _qt_compat
