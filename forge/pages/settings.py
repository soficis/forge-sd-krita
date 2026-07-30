from __future__ import annotations

from ..qt_compat import (
    QComboBox, QCheckBox, QDoubleValidator, QFormLayout,
    QGroupBox, QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout,
    QWidget, QThread, pyqtSignal,
)

from ..adapters.sd_api import SDAPI
from ..settings_controller import SettingsController
from ..version import __version__

_MAX_RECENT_HOSTS = 5


class _TestWorker(QThread):

    finished = pyqtSignal(str, bool, str)

    def __init__(self, host: str) -> None:
        super().__init__()
        self.host = host

    def run(self) -> None:
        try:
            test_api = SDAPI(self.host)
            if test_api.get_status() is None:
                self.finished.emit(self.host, False, "Connection Failed")
            else:
                self.finished.emit(self.host, True, f"Connected to {self.host}")
        except Exception:
            self.finished.emit(self.host, False, "Connection Failed")


class _UpdateCheckWorker(QThread):

    finished = pyqtSignal(bool, str)

    def run(self) -> None:
        try:
            from urllib.request import Request, urlopen
            import json
            from ..version import GITHUB_REPO

            url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            req = Request(
                url,
                headers={
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "forge-sd-krita-plugin",
                },
            )

            with urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))

            tag_name = data.get("tag_name", "")
            latest_version = tag_name.lstrip("v")

            if not latest_version:
                self.finished.emit(False, "Could not determine latest version")
                return

            current_parts = tuple(int(x) for x in __version__.split("."))
            latest_parts = tuple(int(x) for x in latest_version.split("."))

            if latest_parts > current_parts:
                release_url = data.get("html_url", "")
                self.finished.emit(
                    True,
                    f"Update available: v{latest_version} (current: v{__version__})\n"
                    f"Download: {release_url}"
                )
            else:
                self.finished.emit(True, f"You are up to date (v{__version__})")

        except Exception as e:
            self.finished.emit(False, f"Update check failed: {e}")


class SettingsPage(QWidget):
    def __init__(self, settings_controller: SettingsController, api: SDAPI) -> None:
        super().__init__()
        self.settings_controller = settings_controller
        self.api = api
        self._worker: _TestWorker | None = None

        self.setLayout(QVBoxLayout())
        self._server_settings_group()
        self._size_group()
        self._previews_group()
        self._prompt_group()
        self._version_group()
        self.layout().addStretch()

    def _server_settings_group(self) -> None:
        host_form = QGroupBox("Server Settings")
        host_form.setLayout(QFormLayout())

        self.recent_hosts_combo = QComboBox()
        self.recent_hosts_combo.setPlaceholderText("Recent hosts...")
        self.recent_hosts_combo.currentTextChanged.connect(
            self._on_recent_host_selected
        )
        host_form.layout().addRow("Recent Hosts", self.recent_hosts_combo)
        self._populate_recent_hosts()

        host_addr = QLineEdit(self.settings_controller.get("server.host"))
        host_addr.setPlaceholderText(self.api.DEFAULT_HOST)
        self._host_input = host_addr
        host_form.layout().addRow("Host", host_addr)

        connect_btn = QPushButton("Connect")
        connect_btn.clicked.connect(lambda: self.test_new_host(host_addr.text()))
        self._connect_btn = connect_btn
        host_form.layout().addWidget(connect_btn)

        self.connection_label = QLabel()
        host_form.layout().addWidget(self.connection_label)

        current_host = self.settings_controller.get("server.host")
        if current_host and self.api.connected:
            self._update_connection_status(f"Connected to {current_host}", True)
        elif current_host:
            self._update_connection_status("Not connected", False)

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

    def _version_group(self) -> None:
        version_group = QGroupBox("Plugin Info")
        version_group.setLayout(QFormLayout())

        version_label = QLabel(f"v{__version__}")
        version_group.layout().addRow("Version", version_label)

        update_btn = QPushButton("Check for Updates")
        update_btn.clicked.connect(self._check_updates)
        self._update_btn = update_btn
        version_group.layout().addWidget(update_btn)

        self._update_status = QLabel()
        version_group.layout().addWidget(self._update_status)

        self.layout().addWidget(version_group)

    def _check_updates(self) -> None:
        self._update_btn.setEnabled(False)
        self._update_status.setText("Checking...")
        self._update_status.setStyleSheet("")

        self._update_worker = _UpdateCheckWorker()
        self._update_worker.finished.connect(self._on_update_check_finished)
        self._update_worker.start()

    def _on_update_check_finished(self, success: bool, message: str) -> None:
        self._update_btn.setEnabled(True)
        self._update_status.setText(message)
        if success:
            self._update_status.setStyleSheet("color: green;")
        else:
            self._update_status.setStyleSheet("color: red;")

    def _toggle_and_save(self, key: str, value: str) -> None:
        self.settings_controller.toggle(key, value)
        self.settings_controller.save()

    def _populate_recent_hosts(self) -> None:
        self.recent_hosts_combo.blockSignals(True)
        self.recent_hosts_combo.clear()
        for host in self._get_recent_hosts():
            self.recent_hosts_combo.addItem(host)
        self.recent_hosts_combo.setCurrentIndex(-1)
        self.recent_hosts_combo.blockSignals(False)

    def _get_recent_hosts(self) -> list[str]:
        if not self.settings_controller.has("server.recent_hosts"):
            return []
        hosts = self.settings_controller.get("server.recent_hosts")
        return hosts if isinstance(hosts, list) else []

    def _save_recent_host(self, host: str) -> None:
        recent = self._get_recent_hosts()
        if host in recent:
            recent.remove(host)
        recent.insert(0, host)
        recent = recent[:_MAX_RECENT_HOSTS]
        self.settings_controller.set("server.recent_hosts", recent)
        self.settings_controller.save()
        self._populate_recent_hosts()

    def _on_recent_host_selected(self, text: str) -> None:
        if not text:
            return
        self._host_input.setText(text)
        self.test_new_host(text)

    def _update_connection_status(self, text: str, success: bool | None) -> None:
        self.connection_label.setText(text)
        if success is True:
            self.connection_label.setStyleSheet("color: green; font-weight: bold;")
        elif success is False:
            self.connection_label.setStyleSheet("color: red;")
        else:
            self.connection_label.setStyleSheet("")

    def update(self) -> None:
        super().update()
        self.repaint()

    @staticmethod
    def add_tooltip(form: QWidget, text: str) -> None:
        layout = form.layout()
        count = layout.count()
        if count >= 2:
            layout.itemAt(count - 1).widget().setToolTip(text)
            layout.itemAt(count - 2).widget().setToolTip(text)

    def create_checkbox(self, settings_key: str) -> QCheckBox:
        checkbox = QCheckBox()
        checkbox.setChecked(self.settings_controller.get(settings_key))
        checkbox.toggled.connect(
            lambda: self.update_setting(settings_key, checkbox.isChecked())
        )
        return checkbox

    def test_new_host(self, host: str = "") -> None:
        if self._worker is not None:
            return

        if not host:
            is_connected = self.api.get_status() is not None
            self._update_connection_status(
                "Connected" if is_connected else "No Connection",
                is_connected,
            )
            return

        self._update_connection_status("Testing...", None)
        self._connect_btn.setEnabled(False)

        self._worker = _TestWorker(host)
        self._worker.finished.connect(self._on_test_finished)
        self._worker.start()

    def _on_test_finished(self, host: str, success: bool, message: str) -> None:
        self._connect_btn.setEnabled(True)
        self._update_connection_status(message, success)

        if success:
            self._save_recent_host(host)
            self.api.change_host(host)
            self.settings_controller.set("server.host", host)
            self.settings_controller.save()

        self._worker = None

    def update_setting(self, key: str, value) -> None:
        self.settings_controller.set(key, value)
