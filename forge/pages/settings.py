from __future__ import annotations

from PyQt5.QtGui import QDoubleValidator
from PyQt5.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..adapters.sd_api import SDAPI
from ..settings_controller import SettingsController


class SettingsPage(QWidget):
    def __init__(self, settings_controller: SettingsController, api: SDAPI) -> None:
        super().__init__()
        self.settings_controller = settings_controller
        self.api = api

        self.setLayout(QVBoxLayout())
        self._server_settings_group()
        self._size_group()
        self._previews_group()
        self._prompt_group()
        self.layout().addStretch()

    def _server_settings_group(self) -> None:
        host_form = QGroupBox("Server Settings")
        host_form.setLayout(QFormLayout())

        host_addr = QLineEdit(self.settings_controller.get("server.host"))
        host_addr.setPlaceholderText(self.api.DEFAULT_HOST)
        host_form.layout().addRow("Host", host_addr)

        connect_btn = QPushButton("Connect")
        connect_btn.clicked.connect(lambda: self.test_new_host(host_addr.text()))
        host_form.layout().addWidget(connect_btn)

        self.connection_label = QLabel()
        host_form.layout().addWidget(self.connection_label)

        host_form.layout().addRow(
            "Save images on host",
            self.create_checkbox("server.save_imgs"),
        )
        self.add_tooltip(
            host_form,
            "Enable to have the host save generated images the same way as the WebUI.",
        )

        self.layout().addWidget(host_form)

    def _size_group(self) -> None:
        size_form = QGroupBox("Size")
        size_form.setLayout(QFormLayout())

        min_size_entry = QSpinBox()
        min_size_entry.setRange(256, 2048)
        min_size_entry.setValue(self.settings_controller.get("defaults.min_size"))
        min_size_entry.valueChanged.connect(
            lambda: self.settings_controller.set(
                "defaults.min_size", min_size_entry.value()
            )
        )
        size_form.layout().addRow("Minimum Size", min_size_entry)
        self.add_tooltip(
            size_form,
            "Small selections are generated at least this size, then resized to fit.",
        )

        size_form.layout().addRow(
            "Enable max size",
            self.create_checkbox("defaults.enable_max_size"),
        )
        self.add_tooltip(
            size_form,
            "Scale generation down for large selections/canvases, then resize back up.",
        )

        max_size_entry = QSpinBox()
        max_size_entry.setRange(256, 5 * 2048)
        max_size_entry.setValue(self.settings_controller.get("defaults.max_size"))
        max_size_entry.valueChanged.connect(
            lambda: self.settings_controller.set(
                "defaults.max_size", max_size_entry.value()
            )
        )
        size_form.layout().addRow("Maximum Size", max_size_entry)
        self.add_tooltip(
            size_form,
            "Largest size sent to Stable Diffusion before output is resized.",
        )

        self.layout().addWidget(size_form)

    def _previews_group(self) -> None:
        previews_form = QGroupBox("Previews")
        previews_form.setLayout(QFormLayout())

        previews_form.layout().addRow(
            "Show Previews",
            self.create_checkbox("previews.enabled"),
        )
        self.add_tooltip(previews_form, "Enable live preview images on the canvas.")

        refresh_time = QLineEdit(
            str(self.settings_controller.get("previews.refresh_seconds"))
        )
        refresh_time.setPlaceholderText("1.0")
        refresh_time.setValidator(QDoubleValidator(0.5, 10.0, 1))
        refresh_time.textChanged.connect(
            lambda: self.settings_controller.set(
                "previews.refresh_seconds",
                float(refresh_time.text()) if refresh_time.text() else 1.0,
            )
        )
        previews_form.layout().addRow("Refresh Time (seconds)", refresh_time)
        self.add_tooltip(
            previews_form,
            "How often Krita polls Stable Diffusion for progress and preview updates.",
        )

        self.layout().addWidget(previews_form)

    def _prompt_group(self) -> None:
        prompt_form = QGroupBox("Prompts")
        prompt_form.setLayout(QFormLayout())

        prompt_form.layout().addRow(
            "Share Prompts",
            self.create_checkbox("prompts.share_prompts"),
        )
        self.add_tooltip(
            prompt_form,
            "Share prompt/negative prompt text between Txt2Img, Img2Img, and Inpaint.",
        )

        exclude_form = QWidget()
        exclude_form.setLayout(QVBoxLayout())

        for page_name, label in [
            ("txt2img", "Txt2Img"),
            ("img2img", "Img2Img"),
            ("inpaint", "Inpaint"),
        ]:
            checkbox = QCheckBox(label)
            checkbox.setChecked(
                page_name in self.settings_controller.get("prompts.exclude_sharing")
            )
            checkbox.toggled.connect(
                lambda _, value=page_name: self._toggle_and_save(
                    "prompts.exclude_sharing", value
                )
            )
            exclude_form.layout().addWidget(checkbox)

        if self.api.script_installed("adetailer"):
            adetailer = QCheckBox("ADetailer")
            adetailer.setChecked(
                "adetailer" in self.settings_controller.get("prompts.exclude_sharing")
            )
            adetailer.toggled.connect(
                lambda: self._toggle_and_save("prompts.exclude_sharing", "adetailer")
            )
            exclude_form.layout().addWidget(adetailer)

        prompt_form.layout().addRow("Exclude from sharing", exclude_form)
        self.add_tooltip(
            prompt_form,
            "Checked modes keep their own prompts instead of shared prompts.",
        )

        prompt_form.layout().addRow(
            "Save Prompts",
            self.create_checkbox("prompts.save_prompts"),
        )
        self.add_tooltip(prompt_form, "Save prompts in Krita settings for next launch.")

        self.layout().addWidget(prompt_form)

    def _toggle_and_save(self, key: str, value: str) -> None:
        self.settings_controller.toggle(key, value)
        self.settings_controller.save()

    def update(self) -> None:
        super().update()
        self.repaint()

    @staticmethod
    def add_tooltip(form: QWidget, text: str) -> None:
        index = len(form.children()) - 2
        form.layout().itemAt(index).widget().setToolTip(text)
        form.layout().itemAt(index - 1).widget().setToolTip(text)

    def create_checkbox(self, settings_key: str) -> QCheckBox:
        checkbox = QCheckBox()
        checkbox.setChecked(self.settings_controller.get(settings_key))
        checkbox.toggled.connect(
            lambda: self.update_setting(settings_key, checkbox.isChecked())
        )
        return checkbox

    def test_new_host(self, host: str = "") -> None:
        if not host:
            is_connected = self.api.get_status() is not None
            self.connection_label.setText(
                "Connected" if is_connected else "No Connection"
            )
            return

        test_api = SDAPI(host)
        if test_api.get_status() is None:
            self.connection_label.setText("No Connection")
            return

        self.connection_label.setText("Connected")
        self.api.change_host(host)
        self.settings_controller.set("server.host", host)
        self.settings_controller.save()

    def update_setting(self, key: str, value) -> None:
        self.settings_controller.set(key, value)
