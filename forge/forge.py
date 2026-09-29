from __future__ import annotations

import logging

from .qt_compat import (
    Qt,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTabBar,
    QVBoxLayout,
    QWidget,
)
from krita import DockWidget
import os

from .adapters.sd_api import SDAPI
from .pages import (
    Img2ImgPage,
    InpaintPage,
    RemBGPage,
    SegmentationMapPage,
    SettingsPage,
    SimplifyPage,
    Txt2ImgPage,
    UpscalePage,
)
from .settings_controller import SettingsController
from .widgets.no_wheel import install_no_wheel

logger = logging.getLogger(__name__)

DEFAULT_HOST = "http://127.0.0.1:7860"

DISCONNECTED_TOOLTIP_FALLBACK = (
    "Not connected to the Forge backend - check Settings > Server"
)


def disabled_button_tooltip(is_connected: bool, reason: str) -> str:
    """Why-tooltip for disabled Generate/Cancel/RemoveBG; '' when connected."""
    if is_connected:
        return ""
    text = (reason or "").strip()
    return text or DISCONNECTED_TOOLTIP_FALLBACK


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

        self.setWidget(self.main_widget)

        self.pages = [
            {"name": "Settings", "icon": "⚙️", "content": self.show_settings},
            {"name": "Simplify UI", "icon": "🔧", "content": self.show_simplify},
            {"name": "Txt2Img", "icon": "✨", "content": self.show_txt2img},
            {"name": "Img2Img", "icon": "🖼️", "content": self.show_img2img},
            {"name": "Inpaint", "icon": "🎨", "content": self.show_inpaint},
            {"name": "Upscale", "icon": "🔍", "content": self.show_upscale},
            {"name": "Remove Background", "icon": "🗑️", "content": self.show_rembg},
            {"name": "Segmentation Map", "icon": "🗺️", "content": self.show_segmap},
        ]

        self.page_tabs = QTabBar()
        self.page_tabs.setObjectName("PageTabs")
        self.page_tabs.setShape(QTabBar.RoundedWest)
        self.page_tabs.setExpanding(True)
        for page in self.pages:
            self.page_tabs.addTab(f"{page['icon']} {page['name']}")
        self.page_tabs.currentChanged.connect(self.change_page)

        if self.api.connected and self.settings_controller.has("pages.last"):
            last_page = self.settings_controller.get("pages.last")
            page_names = [page["name"] for page in self.pages]
            if last_page in page_names:
                self.page_tabs.blockSignals(True)
                self.page_tabs.setCurrentIndex(page_names.index(last_page))
                self.page_tabs.blockSignals(False)

        self.connection_banner = QLabel("No Connection")
        self.connection_banner.setObjectName("ConnectionBanner")
        self.connection_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.connection_banner.setHidden(True)

        self.content_area = QScrollArea()
        self.content_area.setWidgetResizable(True)

        sidebar = QWidget()
        sidebar_layout = QVBoxLayout()
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.addWidget(self.page_tabs)
        sidebar.setLayout(sidebar_layout)

        content_panel = QWidget()
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(self.connection_banner)
        content_layout.addWidget(self.content_area)
        content_panel.setLayout(content_layout)

        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(sidebar)
        main_layout.addWidget(content_panel, 1)
        self.main_widget.setLayout(main_layout)

        self.change_page()

        # Wheel over a combo must scroll the docker, not change the setting.
        install_no_wheel(self.main_widget)

    def canvasChanged(self, canvas) -> None:
        return

    def change_page(self) -> None:
        index = self.page_tabs.currentIndex()
        if index < 0 or index >= len(self.pages):
            return
        self._cleanup_current_page()
        page = self.pages[index]
        self.settings_controller.set("pages.last", page["name"])
        self.settings_controller.save()
        page["content"]()
        self.update()
        self._update_connection_state()

    def closeEvent(self, event) -> None:
        self._cleanup_current_page()
        try:
            self.settings_controller.close()
        except Exception:
            logger.exception("Forge SD - Error cancelling pending settings save")
        super().closeEvent(event)

    def _cleanup_current_page(self) -> None:
        try:
            old_widget = self.content_area.widget()
        except Exception:
            logger.exception("Forge SD - Error fetching current page for cleanup")
            return
        if old_widget is None:
            return
        cleanup = getattr(old_widget, "cleanup", None)
        if callable(cleanup):
            try:
                cleanup()
            except Exception:
                logger.exception("Forge SD - Error cleaning up page widget")
        delete_later = getattr(old_widget, "deleteLater", None)
        if callable(delete_later):
            try:
                delete_later()
            except Exception:
                logger.exception("Forge SD - Error deleting old page widget")

    def _update_connection_state(self) -> None:
        is_connected = self.api.connected
        if is_connected:
            self.connection_banner.setHidden(True)
        else:
            reason = getattr(self.api, "last_error_message", "") or "No Connection"
            self.connection_banner.setText(reason)
            self.connection_banner.setHidden(False)

        content_widget = self.content_area.widget()
        if content_widget is None:
            return
        tooltip = disabled_button_tooltip(
            is_connected, getattr(self.api, "last_error_message", "")
        )
        for btn in content_widget.findChildren(QPushButton):
            btn_text = btn.text()
            if btn_text in ("Generate", "Cancel", "Remove Background"):
                btn.setEnabled(is_connected)
                btn.setToolTip(tooltip)

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

    def show_upscale(self) -> None:
        self.content_area.setWidget(UpscalePage(self.settings_controller, self.api))

    def show_rembg(self) -> None:
        self.content_area.setWidget(RemBGPage(self.settings_controller, self.api))

    def show_segmap(self) -> None:
        self.content_area.setWidget(SegmentationMapPage(self.settings_controller))

