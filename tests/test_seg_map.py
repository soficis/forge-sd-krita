"""Todo 17 (Medium #11): seg_map page renders the segment list with search.

Failing-first (pre-fix skeleton): forge/pages/seg_map.py had no
connect/QListWidget/QLineEdit/filter symbols (search box UNCONNECTED, no list
render), load_seg_map_json raised on a missing json (traceback escaped), and
forge/extras/seg_map_importer.py had no def/__main__/argv (hardcoded
cwd-relative paths, executed on import). Every test below fails against that
skeleton and passes after the fix.
"""

from __future__ import annotations

import csv
import importlib
import importlib.util
import json
import pathlib
import subprocess
import sys
import types
from unittest.mock import MagicMock

import pytest

# Page import under the conftest mock-Qt layer (proves the page imports
# without Krita when mocked).
import forge.pages.seg_map as seg_map_conftest


REAL_JSON = (
    pathlib.Path(__file__).resolve().parent.parent
    / "forge" / "extras" / "seg_map.json"
)
REAL_CSV = (
    pathlib.Path(__file__).resolve().parent.parent
    / "forge" / "extras" / "seg_map.csv"
)
IMPORTER_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "forge" / "extras" / "seg_map_importer.py"
)

from forge.extras.seg_map_importer import convert_csv_to_json  # noqa: E402
from forge.pages.seg_map import filter_segments, load_seg_map_data  # noqa: E402


def _csv_data_rows() -> int:
    with open(str(REAL_CSV), "r", newline="", encoding="utf-8") as fh:
        return sum(1 for _ in csv.reader(fh)) - 1


# ---------------------------------------------------------------------------
# Pure search-filter logic (no Qt)
# ---------------------------------------------------------------------------

SAMPLE = [
    {"rgb": [120, 120, 120], "hex": "#787878", "desc": ["wall"]},
    {"rgb": [180, 120, 120], "hex": "#B47878", "desc": ["building", "edifice"]},
    {"rgb": [6, 230, 230], "hex": "#06E6E6", "desc": ["sky"]},
]


class TestFilterSegments:
    def test_empty_query_returns_all_dict_entries(self):
        assert filter_segments(SAMPLE, "") == SAMPLE
        assert filter_segments(SAMPLE, "   ") == SAMPLE
        assert filter_segments(SAMPLE, None) == SAMPLE

    def test_name_match_case_insensitive(self):
        assert filter_segments(SAMPLE, "sky") == [SAMPLE[2]]
        assert filter_segments(SAMPLE, "SKY") == [SAMPLE[2]]
        assert filter_segments(SAMPLE, "  sky  ") == [SAMPLE[2]]

    def test_secondary_name_matches(self):
        assert filter_segments(SAMPLE, "edifice") == [SAMPLE[1]]

    def test_partial_name_matches(self):
        assert filter_segments(SAMPLE, "build") == [SAMPLE[1]]

    def test_hex_match_case_insensitive(self):
        assert filter_segments(SAMPLE, "#06e6e6") == [SAMPLE[2]]
        assert filter_segments(SAMPLE, "06E6E6") == [SAMPLE[2]]

    def test_no_match_returns_empty(self):
        assert filter_segments(SAMPLE, "zzz-no-such-segment") == []

    def test_skips_non_dict_entries(self):
        entries = [None, "junk", 42, SAMPLE[0]]
        assert filter_segments(entries, "") == [SAMPLE[0]]
        assert filter_segments(entries, "wall") == [SAMPLE[0]]

    def test_non_list_entries_returns_empty(self):
        assert filter_segments(None, "sky") == []
        assert filter_segments("sky", "sky") == []
        assert filter_segments({"key": SAMPLE}, "sky") == []

    def test_non_string_query_coerced(self):
        assert filter_segments(SAMPLE, 120) == [SAMPLE[0], SAMPLE[1]]

    def test_real_json_searchable(self):
        data = json.loads(REAL_JSON.read_text(encoding="utf-8"))
        entries = data["key"]
        assert len(entries) > 0
        assert len(filter_segments(entries, "")) == len(entries)
        skies = filter_segments(entries, "sky")
        assert len(skies) >= 1
        assert any("sky" in str(e.get("desc", "")).lower() for e in skies)


# ---------------------------------------------------------------------------
# Graceful json load (+ csv fallback). Never raises.
# ---------------------------------------------------------------------------

class TestLoadSegMapData:
    def test_real_json_loads(self):
        data, error = load_seg_map_data(str(REAL_JSON), str(REAL_CSV))
        assert error is None
        assert len(data["key"]) == _csv_data_rows()

    def test_missing_json_and_csv_graceful(self, tmp_path):
        data, error = load_seg_map_data(
            str(tmp_path / "missing.json"), str(tmp_path / "missing.csv")
        )
        assert data == {"key": []}
        assert isinstance(error, str) and error

    def test_missing_json_regenerates_from_csv(self, tmp_path):
        out = tmp_path / "regen.json"
        assert not out.exists()
        data, error = load_seg_map_data(str(out), str(REAL_CSV))
        assert error is None
        assert out.exists()
        assert len(data["key"]) == _csv_data_rows()

    def test_corrupt_json_graceful(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        data, error = load_seg_map_data(str(bad), str(REAL_CSV))
        assert data == {"key": []}
        assert isinstance(error, str) and error

    def test_non_dict_json_graceful(self, tmp_path):
        bad = tmp_path / "list.json"
        bad.write_text('["junk"]', encoding="utf-8")
        data, error = load_seg_map_data(str(bad), str(REAL_CSV))
        assert data == {"key": []}
        assert isinstance(error, str) and error


# ---------------------------------------------------------------------------
# Importer: path args + import side-effect free + CLI preserved
# ---------------------------------------------------------------------------

class TestSegMapImporter:
    def test_convert_explicit_paths(self, tmp_path):
        out = tmp_path / "out.json"
        assert convert_csv_to_json(str(REAL_CSV), str(out)) == str(out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert len(data["key"]) == _csv_data_rows()
        assert data["key"][0] == {
            "rgb": [120, 120, 120], "hex": "#787878", "desc": ["wall"],
        }

    def test_import_has_no_side_effects(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        mod = sys.modules.get("forge.extras.seg_map_importer")
        assert mod is not None
        importlib.reload(mod)
        assert list(tmp_path.iterdir()) == []

    def test_cli_defaults_cwd_relative(self, tmp_path):
        (tmp_path / "seg_map.csv").write_bytes(REAL_CSV.read_bytes())
        proc = subprocess.run(
            [sys.executable, str(IMPORTER_PATH)],
            cwd=str(tmp_path), capture_output=True, timeout=120,
        )
        assert proc.returncode == 0, proc.stderr.decode()
        data = json.loads((tmp_path / "seg_map.json").read_text(encoding="utf-8"))
        assert len(data["key"]) == _csv_data_rows()

    def test_cli_explicit_args(self, tmp_path):
        out = tmp_path / "custom.json"
        proc = subprocess.run(
            [sys.executable, str(IMPORTER_PATH), str(REAL_CSV), str(out)],
            capture_output=True, timeout=120,
        )
        assert proc.returncode == 0, proc.stderr.decode()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert len(data["key"]) == _csv_data_rows()


# ---------------------------------------------------------------------------
# Page under stub-Qt real classes (cf. test_controlnet_dict_guards pattern)
# ---------------------------------------------------------------------------

class _Signal:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def emit(self, *args):
        for slot in list(self._slots):
            slot(*args)


class _Layout:
    def __init__(self, *args):
        self.widgets = []

    def setContentsMargins(self, *args):
        pass

    def addWidget(self, widget):
        self.widgets.append(widget)

    def addStretch(self, *args):
        pass


class _QWidget:
    def __init__(self, *args, **kwargs):
        self._layout = None

    def setLayout(self, layout):
        self._layout = layout

    def layout(self):
        return self._layout

    def update(self):
        pass


class _QLabel(_QWidget):
    def __init__(self, text=""):
        super().__init__()
        self._text = text

    def setWordWrap(self, value):
        pass

    def setPixmap(self, pixmap):
        self._pixmap = pixmap

    def setText(self, text):
        self._text = text

    def text(self):
        return self._text


class _QPixmap:
    def __init__(self, *args):
        self.color = None

    def fill(self, color):
        self.color = color


class _QColor:
    def __init__(self, name=""):
        self.name = name


class _QLineEdit(_QWidget):
    def __init__(self, *args):
        super().__init__()
        self._text = ""
        self._placeholder = ""
        self.textChanged = _Signal()

    def setPlaceholderText(self, text):
        self._placeholder = text

    def text(self):
        return self._text

    def setText(self, text):
        self._text = text
        self.textChanged.emit(text)


class _QListWidgetItem:
    def __init__(self, text=""):
        self._text = text

    def text(self):
        return self._text


class _QListWidget(_QWidget):
    def __init__(self, *args):
        super().__init__()
        self._items = []

    def clear(self):
        self._items = []

    def addItem(self, item):
        if isinstance(item, str):
            item = _QListWidgetItem(item)
        self._items.append(item)

    def count(self):
        return len(self._items)

    def item(self, index):
        return self._items[index]


_QT_NAMES = {
    "QWidget": _QWidget,
    "QVBoxLayout": _Layout,
    "QLabel": _QLabel,
    "QPixmap": _QPixmap,
    "QColor": _QColor,
    "QLineEdit": _QLineEdit,
    "QListWidget": _QListWidget,
    "QListWidgetItem": _QListWidgetItem,
}


def _load_seg_map_real():
    """Import seg_map.py fresh with stub-Qt real classes; return the module."""
    stub = types.ModuleType("forge.qt_compat")
    for _name, _cls in _QT_NAMES.items():
        setattr(stub, _name, _cls)
    stub.__all__ = list(_QT_NAMES)

    def __getattr__(name):
        if name.startswith("__"):
            raise AttributeError(name)
        raise AttributeError(name)

    stub.__getattr__ = __getattr__

    pre_keys = set(sys.modules)
    old = sys.modules.get("forge.qt_compat")
    sys.modules["forge.qt_compat"] = stub
    try:
        path = (
            pathlib.Path(__file__).resolve().parent.parent
            / "forge" / "pages" / "seg_map.py"
        )
        mod_name = "forge.pages.seg_map_task17"
        spec = importlib.util.spec_from_file_location(mod_name, str(path))
        mod = importlib.util.module_from_spec(spec)
        mod.__package__ = "forge.pages"
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        if old is not None:
            sys.modules["forge.qt_compat"] = old
        else:
            sys.modules.pop("forge.qt_compat", None)
        for _key in [k for k in sys.modules if k not in pre_keys
                     and k != "forge.pages.seg_map_task17"]:
            sys.modules.pop(_key, None)


seg_mod = _load_seg_map_real()


def _make_page(monkeypatch=None):
    fake_kc = MagicMock()
    fake_kc.get_foreground_color_hex.return_value = "#112233"
    fake_kc.get_background_color_hex.return_value = "#445566"
    if monkeypatch is not None:
        monkeypatch.setattr(seg_mod, "KritaAdapter", MagicMock(return_value=fake_kc))
    else:
        seg_mod.KritaAdapter = MagicMock(return_value=fake_kc)
    return seg_mod.SegmentationMapPage(MagicMock())


class TestSegMapPage:
    def test_really_real_classes(self):
        assert isinstance(seg_mod.SegmentationMapPage, type)

    def test_renders_full_list_on_init(self):
        page = _make_page()
        total = len(filter_segments(
            json.loads(REAL_JSON.read_text(encoding="utf-8"))["key"], ""))
        assert page.result_list.count() == total > 0
        assert page.load_error is None
        assert "segments" in page.status_label.text()

    def test_search_filters_list(self):
        page = _make_page()
        page.search_bar.setText("sky")
        expected = filter_segments(
            json.loads(REAL_JSON.read_text(encoding="utf-8"))["key"], "sky")
        assert page.result_list.count() == len(expected) > 0
        assert "sky" in page.result_list.item(0).text().lower()

    def test_search_case_insensitive_and_clearable(self):
        page = _make_page()
        total = page.result_list.count()
        page.search_bar.setText("SKY")
        filtered = page.result_list.count()
        assert 0 < filtered < total
        page.search_bar.setText("")
        assert page.result_list.count() == total

    def test_no_match_shows_zero(self):
        page = _make_page()
        page.search_bar.setText("zzz-no-such-segment")
        assert page.result_list.count() == 0
        assert page.status_label.text().startswith("0 of ")

    def test_search_signal_connected(self):
        page = _make_page()
        assert len(page.search_bar.textChanged._slots) >= 1

    def test_missing_json_graceful_no_traceback(self, tmp_path):
        page = _make_page()
        page.map_path = str(tmp_path / "missing.json")
        page.csv_path = str(tmp_path / "missing.csv")
        page.load_seg_map_json()  # must not raise
        assert isinstance(page.load_error, str) and page.load_error
        page._refresh_list("")
        assert page.result_list.count() == 0
        assert page.status_label.text() == page.load_error

    def test_missing_json_regenerates_from_csv(self, tmp_path):
        page = _make_page()
        page.map_path = str(tmp_path / "regen.json")
        page.csv_path = str(REAL_CSV)
        page.load_seg_map_json()  # must not raise
        assert page.load_error is None
        page._refresh_list("")
        assert page.result_list.count() == _csv_data_rows()


class TestConftestPatternImport:
    """The page imports without Krita under the conftest mock layer."""

    def test_pure_helpers_exposed(self):
        assert callable(seg_map_conftest.filter_segments)
        assert callable(seg_map_conftest.load_seg_map_data)
        assert isinstance(seg_map_conftest.SegmentationMapPage, type)
