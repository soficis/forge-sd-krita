from __future__ import annotations

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QIcon, QImage, QPixmap
from PyQt5.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..adapters.krita_adapter import KritaAdapter
from ..adapters.sd_api import SDAPI
from ..settings_controller import SettingsController


class ImageInWidget(QWidget):
    MAX_HEIGHT = 100

    def __init__(
        self,
        settings_controller: SettingsController,
        api: SDAPI,
        key: str,
        size_dict: dict | None = None,
        hide_refresh: bool = True,
    ) -> None:
        super().__init__()
        self.settings_controller = settings_controller
        self.api = api
        self.key = key
        self.size_dict = size_dict or {"x": 0, "y": 0, "w": 0, "h": 0}
        self.hide_refresh = hide_refresh
        self.selection_mode = "canvas"
        self.kc = KritaAdapter()
        self.image: QImage | None = None

        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.draw_ui()

    def draw_ui(self) -> None:
        self.preview_list = QListWidget()
        self.preview_list.setFixedHeight(self.MAX_HEIGHT)
        self.preview_list.setFlow(QListView.Flow.LeftToRight)
        self.preview_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview_list.setResizeMode(QListView.ResizeMode.Adjust)
        self.preview_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.preview_list.setViewMode(QListWidget.IconMode)
        self.preview_list.setIconSize(QSize(self.MAX_HEIGHT, self.MAX_HEIGHT))
        self.clear_previews()
        self.layout().addWidget(self.preview_list)

        button_row = QWidget()
        button_row.setLayout(QHBoxLayout())
        button_row.layout().setContentsMargins(0, 0, 0, 0)

        use_selection = QPushButton("Use Selection")
        use_selection.clicked.connect(self.get_selection_img)
        button_row.layout().addWidget(use_selection)

        use_layer = QPushButton("Use Layer")
        use_layer.clicked.connect(self.get_layer_img)
        button_row.layout().addWidget(use_layer)

        use_canvas = QPushButton("Use Canvas")
        use_canvas.clicked.connect(self.get_canvas_img)
        button_row.layout().addWidget(use_canvas)

        self.layout().addWidget(button_row)

        self.refresh_before_gen_cb = QCheckBox("Refresh image before generating")
        self.refresh_before_gen_cb.setToolTip(
            "If checked, the current selection source is re-captured right before generate."
        )
        if not self.hide_refresh:
            self.layout().addWidget(self.refresh_before_gen_cb)

    def clear_previews(self) -> None:
        self.preview_list.clear()
        self.preview_list.addItem(QListWidgetItem(QIcon(), "No Image Selected"))
        self.image = None

    def get_selection_img(self) -> None:
        self.selection_mode = "selection"
        (
            self.size_dict["x"],
            self.size_dict["y"],
            self.size_dict["w"],
            self.size_dict["h"],
        ) = self.kc.get_selection_bounds()
        self.get_img()

    def get_layer_img(self) -> None:
        self.selection_mode = "layer"
        (
            self.size_dict["x"],
            self.size_dict["y"],
            self.size_dict["w"],
            self.size_dict["h"],
        ) = self.kc.get_layer_bounds()
        self.get_img()

    def get_canvas_img(self) -> None:
        self.selection_mode = "canvas"
        (
            self.size_dict["x"],
            self.size_dict["y"],
            self.size_dict["w"],
            self.size_dict["h"],
        ) = self.kc.get_canvas_bounds()
        self.get_img()

    def get_img(self, selection_mode: str | None = None) -> None:
        selection_mode = selection_mode or self.selection_mode

        if selection_mode == "selection":
            self.image = self.kc.get_selection_img()
        elif selection_mode == "layer":
            self.image = self.kc.get_selected_layer_img()
        else:
            self.image = self.kc.get_canvas_img()

        self.preview_list.clear()
        self.preview_list.addItem(
            QListWidgetItem(QIcon(QPixmap.fromImage(self.image)), "")
        )

    def get_generation_data(self) -> dict:
        if self.refresh_before_gen_cb.isChecked():
            self._refresh_image_before_generation()

        if self.image is None:
            _, _, selection_width, selection_height = self.kc.get_selection_bounds()
            if selection_width > 0 and selection_height > 0:
                self.get_selection_img()
            else:
                self.get_canvas_img()

        return {self.key: self.kc.qimage_to_b64_str(self.image) if self.image else None}

    def _refresh_image_before_generation(self) -> None:
        clear_selection = False

        if self.selection_mode == "selection":
            _, _, width, height = self.kc.get_selection_bounds()
            if width == 0 and height == 0:
                clear_selection = True
                self.kc.set_selection(
                    self.size_dict["x"],
                    self.size_dict["y"],
                    self.size_dict["w"],
                    self.size_dict["h"],
                )

        self.get_img()

        if clear_selection:
            self.kc.set_selection(0, 0, 0, 0)
