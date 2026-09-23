"""Todo 20 (Low #13): qt_compat explicit-import codemod guard.

Every UI module under forge/widgets, forge/pages and
forge/extension_widgets must import only explicitly-named symbols from
forge.qt_compat (no ``from ..qt_compat import *``). This test loads each
module fresh from source under a strict stub-Qt layer built from REAL
classes (pattern copied from tests/test_controlnet_dict_guards.py), so a
missing symbol fails loudly:

- star import still present  -> assertion failure listing the file
- explicit name absent from stub -> ImportError on exec
- body uses a name that was not explicitly imported -> NameError on exec
- stub classes not subclassable / mocked -> real-class guard failure

Subclassing conftest's MagicMock Qt does NOT work, hence the dedicated
stub layer below with true ``type`` classes.
"""

from __future__ import annotations

import ast
import importlib.util
import pathlib
import re
import sys
import types
from abc import ABCMeta
from unittest.mock import MagicMock

import pytest

# Pre-import every non-UI forge dependency under conftest's mock-Qt layer so
# fresh UI module loads below reuse them instead of re-executing under the
# strict stub (same reason test_controlnet_dict_guards imports sd_api first).
# ORDER MATTERS: forge.widgets first — importing forge.extension_widgets
# before forge.widgets would bind a partially-initialized extension_widgets
# package into forge.widgets.extensions (missing ControlNetExtension).
import forge.widgets  # noqa: F401
import forge.adapters.krita_adapter  # noqa: F401
import forge.adapters.sd_api  # noqa: F401
import forge.extension_widgets  # noqa: F401
import forge.extras.seg_map_importer  # noqa: F401
import forge.pages  # noqa: F401
import forge.settings_controller  # noqa: F401

_FORGE_ROOT = pathlib.Path(__file__).resolve().parent.parent / "forge"

TARGETS = sorted(
    [p for p in (_FORGE_ROOT / "widgets").glob("*.py") if p.name != "__init__.py"]
    + [p for p in (_FORGE_ROOT / "pages").glob("*.py") if p.name != "__init__.py"]
    + [
        p
        for p in (_FORGE_ROOT / "extension_widgets").glob("*.py")
        if p.name != "__init__.py"
    ]
)
TARGET_IDS = [p.relative_to(_FORGE_ROOT).as_posix() for p in TARGETS]
assert len(TARGETS) >= 24, f"expected at least 24 UI modules, found {len(TARGETS)}"


def _qt_compat_imported_names(path: pathlib.Path) -> list[str]:
    """Names a module explicitly imports from qt_compat (any depth)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").endswith(
            "qt_compat"
        ):
            for alias in node.names:
                assert alias.name != "*", f"star import remains in {path}"
                names.append(alias.asname or alias.name)
    assert names, f"no qt_compat import found in {path}"
    return names


def _module_level_classes(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [n.name for n in tree.body if isinstance(n, ast.ClassDef)]


def _body_without_qt_imports(path: pathlib.Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(
        ln for ln in lines if "qt_compat import" not in ln
    )


def _build_strict_stub(names: list[str]) -> types.ModuleType:
    """Strict stub-Qt module of REAL classes with NO __getattr__ fallback.

    Any name missing from the stub raises ImportError on explicit import,
    and any body use of a non-imported name raises NameError on exec.
    """
    _dummy = MagicMock()

    class _Meta(ABCMeta):
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
    for _name in names:
        setattr(stub, _name, _Meta(_name, (_StubBase,), {}))
    stub.__all__ = list(names)
    # NOTE: deliberately no PEP-562 module __getattr__ here.
    return stub


def _load_fresh(path: pathlib.Path, stub: types.ModuleType) -> types.ModuleType:
    """Exec a forge UI module fresh from file under ``stub`` qt_compat."""
    package = "forge." + path.parent.name
    mod_name = f"{package}.{path.stem}_task20"
    pre_keys = set(sys.modules)
    old = sys.modules.get("forge.qt_compat")
    sys.modules["forge.qt_compat"] = stub
    try:
        spec = importlib.util.spec_from_file_location(mod_name, str(path))
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        if old is not None:
            sys.modules["forge.qt_compat"] = old
        else:
            sys.modules.pop("forge.qt_compat", None)
        for _key in [k for k in sys.modules if k not in pre_keys]:
            sys.modules.pop(_key, None)


_QT_USE_RE = re.compile(r"^(?:Q[A-Z]|Qt$|pyqt[A-Z]|q[A-Z])")


def _qt_names_used(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    used = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }
    return {name for name in used if _QT_USE_RE.match(name)}


def _names_imported_from_elsewhere(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if (node.module or "").endswith("qt_compat"):
                continue
            for alias in node.names:
                if alias.name == "*":
                    continue
                names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
    return names


def _union_names() -> list[str]:
    union: list[str] = []
    for path in TARGETS:
        for name in _qt_compat_imported_names(path):
            if name not in union:
                union.append(name)
    return union


_STUB = _build_strict_stub(_union_names())


class TestQtCompatExplicitImports:
    def test_no_star_imports_remain(self):
        for path in TARGETS:
            _qt_compat_imported_names(path)  # asserts no "*" per file

    def test_every_imported_name_is_used(self):
        for path in TARGETS:
            body = _body_without_qt_imports(path)
            for name in _qt_compat_imported_names(path):
                assert re.search(r"\b%s\b" % re.escape(name), body), (
                    f"{path.name}: explicitly imports {name} "
                    "but never uses it"
                )

    def test_every_used_qt_name_is_imported(self):
        for path in TARGETS:
            used = _qt_names_used(path) - _names_imported_from_elsewhere(path)
            imported = set(_qt_compat_imported_names(path))
            assert used <= imported, (
                f"{path.name}: uses {sorted(used - imported)} "
                "without importing from qt_compat"
            )

    @pytest.mark.parametrize("path", TARGETS, ids=TARGET_IDS)
    def test_module_loads_under_strict_stub(self, path):
        mod = _load_fresh(path, _STUB)
        assert mod.__name__.endswith(f"{path.stem}_task20")

    @pytest.mark.parametrize("path", TARGETS, ids=TARGET_IDS)
    def test_module_classes_are_real(self, path):
        """Guard proving stub-Qt classes are real types, not mocks."""
        mod = _load_fresh(path, _STUB)
        classes = _module_level_classes(path)
        assert classes, f"{path.name} defines no classes"
        for cls_name in classes:
            cls = getattr(mod, cls_name)
            assert isinstance(cls, type), (
                f"{path.name}.{cls_name} is not a real class "
                f"(got {type(cls).__name__})"
            )
