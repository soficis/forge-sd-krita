from ..qt_compat import (
    QColor, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPixmap,
    QVBoxLayout, QWidget,
)
from ..settings_controller import SettingsController
from ..adapters.krita_adapter import KritaAdapter
from ..extras.seg_map_importer import convert_csv_to_json
import json
import os

# https://docs.google.com/spreadsheets/d/1se8YEtb2detS7OuPE86fXGyD269pMycAWe2mtKUj2W8/edit#gid=0

# NOTE (task 17 follow-up): there is no "apply selected segment to layer"
# action yet. KritaAdapter only exposes get_foreground_color_hex /
# get_background_color_hex (no setters), so painting a chosen segment color
# would need new adapter/backend protocol. This page ships list + search.


def filter_segments(entries, query):
    """Return the entries matching query (case-insensitive, names or hex).

    Pure function (no Qt) so the search logic is unit-testable. Never raises:
    non-dict entries are skipped, a missing/empty query returns every dict
    entry, and a non-list entries value returns [].
    """
    if not isinstance(entries, (list, tuple)):
        return []
    rows = [entry for entry in entries if isinstance(entry, dict)]
    if query is None:
        query = ""
    if not isinstance(query, str):
        query = str(query)
    needle = query.strip().lower()
    if not needle:
        return list(rows)
    matches = []
    for entry in rows:
        desc = entry.get("desc", [])
        if isinstance(desc, str):
            desc = [desc]
        if not isinstance(desc, (list, tuple)):
            desc = []
        rgb = entry.get("rgb", [])
        if not isinstance(rgb, (list, tuple)):
            rgb = []
        haystack = " ".join(
            [str(part) for part in list(desc)]
            + [str(entry.get("hex", "")), ",".join(str(c) for c in rgb)]
        ).lower()
        if needle in haystack:
            matches.append(entry)
    return matches


def load_seg_map_data(json_path, csv_path=None):
    """Load the seg-map JSON, regenerating it from CSV when missing. Never raises.

    Returns (data, error): data is a {"key": [...]} dict (possibly empty) and
    error is None on success or a human-readable message for the status label.
    """
    try:
        with open(json_path, 'r', encoding='utf-8') as file_in:
            data = json.load(file_in)
        if not isinstance(data, dict):
            return ({"key": []}, "Forge SD - Error loading segmap: unexpected JSON format")
        return (data, None)
    except FileNotFoundError:
        pass
    except Exception as e:
        return ({"key": []}, "Forge SD - Error loading segmap: %s" % e)
    if csv_path is not None and os.path.exists(csv_path):
        try:
            convert_csv_to_json(csv_path, json_path)
            with open(json_path, 'r', encoding='utf-8') as file_in:
                data = json.load(file_in)
            if not isinstance(data, dict):
                return ({"key": []}, "Forge SD - Error loading segmap: unexpected JSON format")
            return (data, None)
        except Exception as e:
            return ({"key": []}, "Forge SD - Error loading segmap: %s" % e)
    return ({"key": []}, "Forge SD - Segmentation map not found (expected %s)" % json_path)


class SegmentationMapPage(QWidget):
    def __init__(self, settings_controller:SettingsController):
        super().__init__()
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0,0,0,0)
        self.settings_controller = settings_controller
        self.kc = KritaAdapter()
        self.seg_map = {}
        self.load_error = None
        self.plugin_dir = os.path.dirname(os.path.realpath(__file__))
        self.map_path = os.path.join(self.plugin_dir, '..', 'extras', 'seg_map.json')
        self.csv_path = os.path.join(self.plugin_dir, '..', 'extras', 'seg_map.csv')
        self.icon_size = 24
        self.update_user_colors()
        self.load_seg_map_json()
        self.draw_ui()

    def load_seg_map_json(self):
        # Graceful path: regenerates a missing json from csv when possible and
        # records a status message instead of raising (missing json must never
        # crash the docker).
        self.seg_map, self.load_error = load_seg_map_data(self.map_path, self.csv_path)

    def draw_ui(self):
        description = QLabel("ControlNet's Segmentation Map uses different colors to represent different types of objects. Here's an easy way to access those colors.")
        description.setWordWrap(True)
        self.layout().addWidget(description)

        # Primary / Secondary colors, and their descriptions
        primary_pixmap = QPixmap(self.icon_size, self.icon_size)
        primary_pixmap.fill(QColor(self.foreground))
        # primary_icon = QIcon(primary_pixmap)
        primary_icon = QLabel()
        primary_icon.setPixmap(primary_pixmap)
        self.layout().addWidget(primary_icon)

        secondary_pixmap = QPixmap(self.icon_size, self.icon_size)
        secondary_pixmap.fill(QColor(self.background))
        # secondary_icon = QIcon(secondary_pixmap)
        secondary_icon = QLabel()
        secondary_icon.setPixmap(secondary_pixmap)
        self.layout().addWidget(secondary_icon)

        # Search box: filters the segment list below as you type
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search segments (name or hex)...")
        self.search_bar.textChanged.connect(self._on_search_text_changed)
        self.layout().addWidget(self.search_bar)

        # List of segments rendered from seg_map.json
        self.result_list = QListWidget()
        self.layout().addWidget(self.result_list)

        # Segment count, or the load error when the map is unavailable
        self.status_label = QLabel()
        self.layout().addWidget(self.status_label)

        self._refresh_list("")

        self.layout().addStretch() # Takes up the remaining space at the bottom, allowing everything to be pushed to the top

    def _on_search_text_changed(self, text):
        self._refresh_list(text)

    def _refresh_list(self, query):
        if isinstance(self.seg_map, dict):
            entries = self.seg_map.get("key", [])
        else:
            entries = []
        matches = filter_segments(entries, query)
        self.result_list.clear()
        for entry in matches:
            names = entry.get("desc", [])
            if isinstance(names, str):
                names = [names]
            label = "%s - %s" % (entry.get("hex", "?"), ", ".join(str(n) for n in names))
            self.result_list.addItem(QListWidgetItem(label))
        if self.load_error is not None:
            self.status_label.setText(self.load_error)
        else:
            total = len(filter_segments(entries, ""))
            self.status_label.setText("%d of %d segments" % (len(matches), total))

    def update(self):
        super().update()


    def update_user_colors(self):
        try:
            self.foreground = self.kc.get_foreground_color_hex()
            self.background = self.kc.get_background_color_hex()
        except Exception:
            self.foreground = "#000000"
            self.background = "#ffffff"
