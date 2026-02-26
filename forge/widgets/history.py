from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap, QIcon
import json
import os
from ..domain.history_manager import HistoryManager
from ..adapters.sd_api import SDAPI
from ..settings_controller import SettingsController

class HistoryWidget(QWidget):
    reuse_required = pyqtSignal(dict)

    def __init__(self, settings_controller: SettingsController, api: SDAPI):
        super().__init__()
        self.settings_controller = settings_controller
        self.api = api
        self.history_manager = HistoryManager()
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.draw_ui()

    def draw_ui(self):
        # Controls
        controls = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.load_history)
        controls.addWidget(refresh_btn)
        
        clear_btn = QPushButton("Clear History")
        clear_btn.clicked.connect(self.clear_history)
        controls.addWidget(clear_btn)
        
        self.layout().addLayout(controls)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.scroll_content)
        self.layout().addWidget(self.scroll)

        self.load_history()

    def clear_history(self):
        confirm = QMessageBox.question(self, "Clear History", "Are you sure you want to delete all generation history?", QMessageBox.Yes | QMessageBox.No)
        if confirm == QMessageBox.Yes:
            self.history_manager.clear_all()
            self.load_history()

    def load_history(self):
        # Clear existing
        for i in reversed(range(self.scroll_layout.count())):
            self.scroll_layout.itemAt(i).widget().setParent(None)

        history = self.history_manager.get_history()
        for entry in history:
            item = HistoryEntryWidget(entry)
            item.reuse_clicked.connect(self.reuse_required.emit)
            self.scroll_layout.addWidget(item)

class HistoryEntryWidget(QWidget):
    reuse_clicked = pyqtSignal(dict)

    def __init__(self, entry_data):
        super().__init__()
        self.entry_data = entry_data
        self.setLayout(QHBoxLayout())
        
        # Thumbnail
        self.thumb = QLabel()
        self.thumb.setFixedSize(64, 64)
        if entry_data.get('thumbnail') and os.path.exists(entry_data['thumbnail']):
            pixmap = QPixmap(entry_data['thumbnail'])
            self.thumb.setPixmap(pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.thumb.setText("No Image")
        self.layout().addWidget(self.thumb)

        # Info
        info = QVBoxLayout()
        prompt = entry_data.get('prompt', 'No Prompt')
        if len(prompt) > 50:
            prompt = prompt[:47] + "..."
        info.addWidget(QLabel(prompt))
        
        details = f"Model: {entry_data.get('model', 'Unknown')} | Seed: {entry_data.get('seed', 'N/A')}"
        info.addWidget(QLabel(details))
        self.layout().addLayout(info)

        # Reuse button
        reuse_btn = QPushButton("Reuse")
        reuse_btn.clicked.connect(lambda: self.reuse_clicked.emit(self.entry_data))
        self.layout().addWidget(reuse_btn)

__all__ = ["HistoryWidget"]
