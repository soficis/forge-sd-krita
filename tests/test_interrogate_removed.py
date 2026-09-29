"""Interrogate feature removal guard (backend endpoint absent in Forge Neo).

The plugin's Interrogate tab, its two widgets, the SDAPI.interrogate() client
method, and the interrogate.* settings were removed because Forge Neo exposes
no /sdapi/v1/interrogate endpoint (404, no matching openapi path). This file
locks the removal: the source files are gone, the word appears nowhere in the
shipped forge/ package (test files under tests/ may still mention it), the
settings schema carries no interrogate keys, and forge/forge.py exposes
exactly 8 page tabs with no Interrogate entry or dispatcher.

Docker construction reuses the fresh-module-load pattern from
test_connection_errors.py (aliased module + DockWidget stub), with SDAPI
refresh and SettingsController save patched so the test touches neither the
network nor disk.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import json
import pathlib
import sys
from unittest.mock import patch

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
FORGE_DIR = REPO_ROOT / "forge"

EXPECTED_PAGE_NAMES = [
    "Settings",
    "Simplify UI",
    "Txt2Img",
    "Img2Img",
    "Inpaint",
    "Upscale",
    "Remove Background",
    "Segmentation Map",
]


def _forge_sources() -> list[pathlib.Path]:
    """All .py files under forge/, excluding __pycache__ and any test_*
    modules (the removal spec allows the word only inside a test file)."""
    return [
        p
        for p in sorted(FORGE_DIR.rglob("*.py"))
        if "__pycache__" not in p.parts and not p.name.startswith("test_")
    ]


def _sources_containing(word: str) -> list[str]:
    needle = word.lower()
    return [
        str(p.relative_to(REPO_ROOT))
        for p in _forge_sources()
        if needle in p.read_text(encoding="utf-8").lower()
    ]


def _forge_source() -> str:
    return (FORGE_DIR / "forge.py").read_text(encoding="utf-8")


def _pages_list_assignments(tree: ast.AST) -> list[ast.List]:
    found: list[ast.List] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.List)
            and any(
                isinstance(t, ast.Attribute) and t.attr == "pages"
                for t in node.targets
            )
        ):
            found.append(node.value)
    return found


def _dict_string_values(node: ast.Dict) -> list[str]:
    values = []
    for value in node.values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            values.append(value.value)
    return values


# ---------------------------------------------------------------------------
# 1. The source files are gone from disk
# ---------------------------------------------------------------------------


class TestRemovedSourceFiles:
    def test_pages_interrogate_module_absent(self):
        assert not (FORGE_DIR / "pages" / "interrogate.py").exists()

    def test_widgets_interrogate_module_absent(self):
        assert not (FORGE_DIR / "widgets" / "interrogate.py").exists()

    def test_widgets_interrogate_model_module_absent(self):
        assert not (FORGE_DIR / "widgets" / "interrogate_model.py").exists()

    def test_no_interrogate_named_modules_in_pages(self):
        assert list((FORGE_DIR / "pages").glob("interrogate*.py")) == []

    def test_no_interrogate_named_modules_in_widgets(self):
        assert list((FORGE_DIR / "widgets").glob("interrogate*.py")) == []


# ---------------------------------------------------------------------------
# 2. No reference survives anywhere in the shipped forge/ package
# ---------------------------------------------------------------------------


class TestNoInterrogateStringInForgePackage:
    def test_absent_from_every_forge_source(self):
        assert _sources_containing("interrogate") == []

    def test_absent_from_pages_package(self):
        pages_dir = FORGE_DIR / "pages"
        hits = [
            str(p.relative_to(REPO_ROOT))
            for p in sorted(pages_dir.glob("*.py"))
            if "interrogate" in p.read_text(encoding="utf-8").lower()
        ]
        assert hits == []

    def test_absent_from_widgets_package(self):
        widgets_dir = FORGE_DIR / "widgets"
        hits = [
            str(p.relative_to(REPO_ROOT))
            for p in sorted(widgets_dir.glob("*.py"))
            if "interrogate" in p.read_text(encoding="utf-8").lower()
        ]
        assert hits == []

    def test_absent_from_adapters_package(self):
        adapters_dir = FORGE_DIR / "adapters"
        hits = [
            str(p.relative_to(REPO_ROOT))
            for p in sorted(adapters_dir.glob("*.py"))
            if "interrogate" in p.read_text(encoding="utf-8").lower()
        ]
        assert hits == []

    def test_absent_from_forge_docker_module(self):
        assert "interrogate" not in _forge_source().lower()


# ---------------------------------------------------------------------------
# 3. Settings schema carries no interrogate keys
# ---------------------------------------------------------------------------


class TestDefaultSettingsSchema:
    @pytest.fixture()
    def schema(self) -> dict:
        path = FORGE_DIR / "default_settings.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_no_interrogate_top_level_section(self, schema):
        assert "interrogate" not in schema

    def test_no_interrogate_keys_under_hide_ui(self, schema):
        hide_ui = schema.get("hide_ui", {})
        assert [k for k in hide_ui if "interrogate" in k.lower()] == []

    def test_serialized_schema_never_mentions_interrogate(self, schema):
        assert "interrogate" not in json.dumps(schema).lower()


# ---------------------------------------------------------------------------
# 4. Page list in forge/forge.py: exactly 8 tabs, no Interrogate entry
# ---------------------------------------------------------------------------


class TestPageListInForgeSource:
    @pytest.fixture()
    def pages_list(self) -> ast.List:
        tree = ast.parse(_forge_source())
        assignments = _pages_list_assignments(tree)
        assert len(assignments) == 1, (
            "expected exactly one self.pages = [...] assignment in forge.py, "
            f"found {len(assignments)}"
        )
        return assignments[0]

    def test_page_list_has_exactly_eight_entries(self, pages_list):
        assert len(pages_list.elts) == 8

    def test_page_list_has_no_interrogate_entry(self, pages_list):
        for entry in pages_list.elts:
            if not isinstance(entry, ast.Dict):
                continue
            values = _dict_string_values(entry)
            assert not any("interrogate" in v.lower() for v in values), values

    def test_no_show_interrogate_dispatcher_in_source(self):
        assert "show_interrogate" not in _forge_source()


# ---------------------------------------------------------------------------
# 5. The module still imports and the full docker constructs (8 tabs)
# ---------------------------------------------------------------------------


class _DockWidgetStub:
    def __init__(self, *args, **kwargs):
        pass

    def setWindowTitle(self, *args, **kwargs):
        pass

    def setWidget(self, *args, **kwargs):
        pass

    def update(self, *args, **kwargs):
        pass

    def closeEvent(self, event):
        pass


def _load_forge_module():
    """Fresh-load forge/forge.py under an alias (pattern from
    test_connection_errors.py) without disturbing conftest's forge.forge stub."""
    mod_name = "forge.forge_interrogate_removed"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    krita_mod = sys.modules.get("krita")
    old_dock = getattr(krita_mod, "DockWidget", None)
    krita_mod.DockWidget = _DockWidgetStub
    try:
        spec = importlib.util.spec_from_file_location(mod_name, str(FORGE_DIR / "forge.py"))
        mod = importlib.util.module_from_spec(spec)
        mod.__package__ = "forge"
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        krita_mod.DockWidget = old_dock


class TestForgeDockerSurface:
    def test_forge_module_imports_cleanly(self):
        mod = _load_forge_module()
        assert isinstance(mod.ForgeDocker, type)

    def _construct_docker(self):
        mod = _load_forge_module()
        from forge.pages import settings as settings_page_mod
        from forge.settings_controller import SettingsController

        # Nested stub-Qt layouts hand back plain MagicMocks whose .count()
        # is not int-comparable (conftest special-cases only top-level stub
        # instances), so add_tooltip's `count >= 2` cannot run under stubs.
        with patch.object(mod.SDAPI, "refresh"), patch.object(
            SettingsController, "save"
        ), patch.object(
            settings_page_mod.SettingsPage,
            "add_tooltip",
            staticmethod(lambda *args, **kwargs: None),
        ):
            return mod.ForgeDocker()

    def test_docker_constructs_under_stub_qt(self):
        docker = self._construct_docker()
        assert isinstance(docker.pages, list)

    def test_docker_page_list_is_eight_tabs_without_interrogate(self):
        docker = self._construct_docker()
        names = [page["name"] for page in docker.pages]
        assert names == EXPECTED_PAGE_NAMES
        assert "Interrogate" not in names

    def test_docker_has_no_show_interrogate_dispatcher(self):
        docker = self._construct_docker()
        assert not hasattr(type(docker), "show_interrogate")

    def test_page_tabs_added_for_every_page(self):
        docker = self._construct_docker()
        assert docker.page_tabs.addTab.call_count == len(docker.pages)


# ---------------------------------------------------------------------------
# 6. Package exports and the API client surface
# ---------------------------------------------------------------------------


class TestPackageExports:
    def test_pages_package_has_no_interrogate_export(self):
        pages_pkg = importlib.import_module("forge.pages")
        assert not hasattr(pages_pkg, "InterrogatePage")

    def test_widgets_package_has_no_interrogate_widget_exports(self):
        widgets_pkg = importlib.import_module("forge.widgets")
        assert not hasattr(widgets_pkg, "InterrogateWidget")
        assert not hasattr(widgets_pkg, "InterrogateModelWidget")

    def test_sdapi_client_has_no_interrogate_method(self):
        sd_api = importlib.import_module("forge.adapters.sd_api")
        assert not hasattr(sd_api.SDAPI, "interrogate")
