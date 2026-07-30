from ..qt_compat import *
import os
from ..domain.history_manager import HistoryManager
from ..adapters.sd_api import SDAPI
from ..settings_controller import SettingsController

PAGE_SIZE = 20


class HistoryWidget(QWidget):
    reuse_required = pyqtSignal(dict)

    def __init__(self, settings_controller: SettingsController, api: SDAPI):
        super().__init__()
        self.settings_controller = settings_controller
        self.api = api
        self.history_manager = HistoryManager()
        self.current_page = 0
        self._all_history: list[dict] = []
        self._filtered_history: list[dict] = []
        self._thumbnail_cache: dict[int, QPixmap] = {}
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.draw_ui()

    def draw_ui(self):
        # Search / filter row
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Filter:"))
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search by prompt text...")
        self.search_box.textChanged.connect(self._on_search_changed)
        search_row.addWidget(self.search_box)
        self.layout().addLayout(search_row)

        # Controls row
        controls = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.load_history)
        controls.addWidget(refresh_btn)

        clear_btn = QPushButton("Clear History")
        clear_btn.clicked.connect(self.clear_history)
        controls.addWidget(clear_btn)

        controls.addStretch()

        self.prev_btn = QPushButton("\u25c0 Prev")
        self.prev_btn.clicked.connect(self._prev_page)
        self.prev_btn.setEnabled(False)
        controls.addWidget(self.prev_btn)

        self.page_label = QLabel("Page 1 / 1")
        controls.addWidget(self.page_label)

        self.next_btn = QPushButton("Next \u25b6")
        self.next_btn.clicked.connect(self._next_page)
        self.next_btn.setEnabled(False)
        controls.addWidget(self.next_btn)

        self.layout().addLayout(controls)

        # Scroll area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.scroll_content)
        self.layout().addWidget(self.scroll)

        self.load_history()

    # ── History loading & pagination ────────────────────────────────

    def load_history(self):
        self._all_history = self.history_manager.get_history()
        self._thumbnail_cache.clear()
        self._apply_filter()

    def _apply_filter(self):
        query = self.search_box.text().strip().lower() if hasattr(self, "search_box") else ""
        if query:
            self._filtered_history = [
                e for e in self._all_history
                if query in e.get("prompt", "").lower()
            ]
        else:
            self._filtered_history = list(self._all_history)

        # Clamp page
        total_pages = max(1, -(-len(self._filtered_history) // PAGE_SIZE))  # ceil div
        if self.current_page >= total_pages:
            self.current_page = total_pages - 1
        if self.current_page < 0:
            self.current_page = 0

        self._populate_page()

    def _populate_page(self):
        # Clear existing widgets
        for i in reversed(range(self.scroll_layout.count())):
            item = self.scroll_layout.itemAt(i)
            if item is not None and item.widget() is not None:
                item.widget().setParent(None)

        start = self.current_page * PAGE_SIZE
        end = start + PAGE_SIZE
        page_entries = self._filtered_history[start:end]

        for idx, entry in enumerate(page_entries):
            global_idx = start + idx
            item = HistoryEntryWidget(entry, thumbnail_cache=self._thumbnail_cache, cache_key=global_idx)
            item.reuse_clicked.connect(self.reuse_required.emit)
            self.scroll_layout.addWidget(item)

        self._update_pagination_controls()

    def _update_pagination_controls(self):
        total = len(self._filtered_history)
        total_pages = max(1, -(-total // PAGE_SIZE))
        self.page_label.setText(f"Page {self.current_page + 1} / {total_pages}  ({total} entries)")
        self.prev_btn.setEnabled(self.current_page > 0)
        self.next_btn.setEnabled(self.current_page < total_pages - 1)

    def _prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self._populate_page()

    def _next_page(self):
        total_pages = max(1, -(-len(self._filtered_history) // PAGE_SIZE))
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self._populate_page()

    # ── Search / filter ─────────────────────────────────────────────

    def _on_search_changed(self, _text: str):
        self.current_page = 0
        self._apply_filter()

    # ── Clear ───────────────────────────────────────────────────────

    def clear_history(self):
        confirm = QMessageBox.question(
            self,
            "Clear History",
            "Are you sure you want to delete all generation history?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.history_manager.clear_all()
            self.load_history()


class HistoryEntryWidget(QWidget):
    reuse_clicked = pyqtSignal(dict)

    def __init__(self, entry_data: dict, thumbnail_cache: dict | None = None, cache_key: int | None = None):
        super().__init__()
        self.entry_data = entry_data
        self.setLayout(QHBoxLayout())

        # Thumbnail (with caching)
        self.thumb = QLabel()
        self.thumb.setFixedSize(64, 64)
        thumb_path = entry_data.get("thumbnail")
        if thumb_path and os.path.exists(thumb_path):
            cached_pixmap = None
            if thumbnail_cache is not None and cache_key is not None and cache_key in thumbnail_cache:
                cached_pixmap = thumbnail_cache[cache_key]
            else:
                cached_pixmap = QPixmap(thumb_path)
                if thumbnail_cache is not None and cache_key is not None:
                    thumbnail_cache[cache_key] = cached_pixmap
            self.thumb.setPixmap(
                cached_pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            )
        else:
            self.thumb.setText("No Image")
        self.layout().addWidget(self.thumb)

        # Info
        info = QVBoxLayout()
        prompt = entry_data.get("prompt", "No Prompt")
        if len(prompt) > 50:
            prompt = prompt[:47] + "..."
        info.addWidget(QLabel(prompt))

        model = entry_data.get("model", "Unknown")
        seed = entry_data.get("seed", "N/A")
        sampler = entry_data.get("sampler", "")
        steps = entry_data.get("steps", "")
        cfg = entry_data.get("cfg_scale", "")
        parts = [f"Model: {model}", f"Seed: {seed}"]
        if sampler:
            parts.append(f"Sampler: {sampler}")
        if steps:
            parts.append(f"Steps: {steps}")
        if cfg:
            parts.append(f"CFG: {cfg}")
        info.addWidget(QLabel(" | ".join(parts)))
        self.layout().addLayout(info)

        # Reuse button — emits the full entry_data dict with ALL fields
        reuse_btn = QPushButton("Reuse")
        reuse_btn.clicked.connect(lambda: self.reuse_clicked.emit(self.entry_data))
        self.layout().addWidget(reuse_btn)


__all__ = ["HistoryWidget"]
