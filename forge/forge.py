from __future__ import annotations

from PyQt5.QtWidgets import QComboBox, QScrollArea, QVBoxLayout, QWidget
from krita import DockWidget
import os

from .adapters.sd_api import SDAPI
from .pages import (
    Img2ImgPage,
    InpaintPage,
    InterrogatePage,
    RemBGPage,
    SettingsPage,
    SimplifyPage,
    Txt2ImgPage,
    UpscalePage,
)
from .settings_controller import SettingsController

DEFAULT_HOST = "http://127.0.0.1:7860"


class ForgeDocker(DockWidget):
    def __init__(self) -> None:
        super().__init__()

        self.settings_controller = SettingsController()
        host = (
            self.settings_controller.get("server.host")
            if self.settings_controller.has("server.host")
            else DEFAULT_HOST
        )
        self.api = SDAPI(host)

        self.setWindowTitle("Forge SD")
        self.main_widget = QWidget(self)
        
        style_path = os.path.join(os.path.dirname(__file__), "style.qss")
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                self.main_widget.setStyleSheet(f.read())

        self.main_widget.setLayout(QVBoxLayout())
        self.setWidget(self.main_widget)

        self.page_combobox = QComboBox()
        self.page_combobox.setObjectName("NavigationBox")
        self.pages = [
            {"name": "Settings", "content": self.show_settings},
            {"name": "Simplify UI", "content": self.show_simplify},
            {"name": "Txt2Img", "content": self.show_txt2img},
            {"name": "Img2Img", "content": self.show_img2img},
            {"name": "Inpaint", "content": self.show_inpaint},
            {"name": "Interrogate", "content": self.show_interrogate},
            {"name": "Upscale", "content": self.show_upscale},
            {"name": "Remove Background", "content": self.show_rembg},
        ]
        for page in self.pages:
            self.page_combobox.addItem(page["name"])
        self.page_combobox.activated.connect(self.change_page)
        self.main_widget.layout().addWidget(self.page_combobox)

        if self.api.connected and self.settings_controller.has("pages.last"):
            last_page = self.settings_controller.get("pages.last")
            page_names = [page["name"] for page in self.pages]
            if last_page in page_names:
                self.page_combobox.setCurrentText(last_page)

        self.content_area = QScrollArea()
        self.content_area.setWidgetResizable(True)
        self.main_widget.layout().addWidget(self.content_area)

        self.change_page()

    def canvasChanged(self, canvas) -> None:
        return

    def change_page(self) -> None:
        selected_page = self.page_combobox.currentText()
        for page in self.pages:
            if page["name"] != selected_page:
                continue
            self.settings_controller.set("pages.last", page["name"])
            self.settings_controller.save()
            page["content"]()
            break
        self.update()

    def show_settings(self) -> None:
        self.content_area.setWidget(SettingsPage(self.settings_controller, self.api))

    def show_simplify(self) -> None:
        self.content_area.setWidget(SimplifyPage(self.settings_controller, self.api))

    def show_txt2img(self) -> None:
        self.content_area.setWidget(Txt2ImgPage(self.settings_controller, self.api))

    def show_img2img(self) -> None:
        self.content_area.setWidget(Img2ImgPage(self.settings_controller, self.api))

    def show_inpaint(self) -> None:
        self.content_area.setWidget(InpaintPage(self.settings_controller, self.api))

    def show_interrogate(self) -> None:
        self.content_area.setWidget(InterrogatePage(self.settings_controller, self.api))

    def show_upscale(self) -> None:
        self.content_area.setWidget(UpscalePage(self.settings_controller, self.api))

    def show_rembg(self) -> None:
        self.content_area.setWidget(RemBGPage(self.settings_controller, self.api))

