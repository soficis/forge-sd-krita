from __future__ import annotations

import json

from PyQt5.QtWidgets import QProgressBar, QPushButton, QVBoxLayout, QWidget, QTextEdit
from krita import QTimer

from ..adapters.krita_adapter import KritaAdapter
from ..adapters.sd_api import SDAPI
from ..domain.generation_plan import (
    build_generation_plan,
    merge_generation_data,
    prune_generation_results,
)
from ..domain.history_manager import HistoryManager
from ..domain.progress_state import parse_progress_state
from ..settings_controller import SettingsController


class GenerateWidget(QWidget):
    GENERATION_ENDPOINT_BY_MODE = {
        "txt2img": "txt2img",
        "img2img": "img2img",
        "inpaint": "img2img",
    }

    def __init__(
        self,
        settings_controller: SettingsController,
        api: SDAPI,
        list_of_widgets: list,
        mode: str,
        size_dict: dict | None = None,
    ) -> None:
        super().__init__()
        self.settings_controller = settings_controller
        self.api = api
        self.list_of_widgets = list_of_widgets
        self.mode = mode
        self.size_dict = size_dict or {"x": 0, "y": 0, "w": 0, "h": 0}

        self.kc = KritaAdapter()
        self.history_manager = HistoryManager()
        self.results = None
        self.is_generating = False
        self.abort = False
        self.finished = False
        self.debug = False
        self.progress_timer = None

        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setHidden(True)
        self.layout().addWidget(self.progress_bar)

        self.generate_btn = QPushButton("Generate")
        self.generate_btn.setObjectName("GenerateButton")
        self.generate_btn.clicked.connect(self.handle_generate_btn_click)
        self.layout().addWidget(self.generate_btn)

        if self.debug:
            self.debug_data = QTextEdit()
            self.debug_data.setPlaceholderText(
                "JSON payload used to generate the image"
            )
            self.layout().addWidget(self.debug_data)

    def handle_generate_btn_click(self) -> None:
        if self.is_generating:
            self.cancel()
        else:
            self.generate()
        self.update()

    def generate(self) -> None:
        self.abort = False
        self.finished = False
        self.is_generating = True
        self.generate_btn.setText("Cancel")
        self.progress_bar.setHidden(False)
        self.update_progress_bar(0)

        x, y, width, height = self._resolve_generation_bounds()

        generation_plan = build_generation_plan(
            width=width,
            height=height,
            min_size=self.settings_controller.get("defaults.min_size"),
            max_size=self.settings_controller.get("defaults.max_size"),
            enable_max_size=self.settings_controller.get("defaults.enable_max_size"),
        )

        base_data = {
            "width": generation_plan.request_width,
            "height": generation_plan.request_height,
        }
        if self.settings_controller.get("server.save_imgs"):
            base_data["save_images"] = True

        widget_payloads = [
            widget.get_generation_data() for widget in self.list_of_widgets
        ]
        generation_data, processing_instructions = merge_generation_data(
            base_data=base_data,
            widget_payloads=widget_payloads,
        )
        self.current_generation_data = generation_data

        if generation_plan.resize is not None:
            processing_instructions["resize"] = {
                "width": generation_plan.resize.width,
                "height": generation_plan.resize.height,
            }

        if self.debug:
            self.debug_data.setPlainText(
                json.dumps(self.api.build_payload(generation_data), indent=2)
            )

        try:
            self.kc.refresh_doc()
            if self.kc.doc is None:
                self.kc.create_new_doc()

            self.kc.run_as_thread(
                lambda: self.threadable_run(generation_data),
                lambda: self.threadable_return(
                    x,
                    y,
                    width,
                    height,
                    processing_instructions,
                ),
            )

            refresh_seconds = self.settings_controller.get("previews.refresh_seconds")
            refresh_ms = max(int(1000 * refresh_seconds), 100)
            self.progress_timer = QTimer()
            self.progress_timer.timeout.connect(
                lambda: self.progress_check(
                    x,
                    y,
                    width,
                    height,
                    processing_instructions,
                )
            )
            self.progress_timer.start(refresh_ms)

        except Exception as error:
            self.is_generating = False
            self.generate_btn.setText("Generate")
            self.progress_bar.setHidden(True)
            raise RuntimeError(
                f"Forge SD - Error generating {self.mode}: {error}"
            ) from error

    def _resolve_generation_bounds(self) -> tuple[int, int, int, int]:
        x = self.size_dict["x"]
        y = self.size_dict["y"]
        width = self.size_dict["w"]
        height = self.size_dict["h"]

        if width == 0 or height == 0:
            x, y, width, height = self.kc.get_selection_bounds()
            if width == 0 or height == 0:
                x, y = 0, 0
                width, height = self.kc.get_canvas_size()

        return x, y, width, height

    def update_progress_bar(self, value: int) -> None:
        try:
            self.progress_bar.setValue(value)
        except Exception:
            return

    def progress_check(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        processing_instructions: dict,
    ) -> None:
        progress_state = parse_progress_state(self.api.get_progress())

        if self.abort or self.finished or not progress_state.is_active:
            self.abort = False
            self.finished = False
            self._stop_generation_loop()
            return

        self.update_progress_bar(progress_state.percent)

        if not self.settings_controller.get("previews.enabled"):
            return

        if progress_state.current_image is None:
            return

        preview_width = width
        preview_height = height
        resize = processing_instructions.get("resize")
        if isinstance(resize, dict):
            preview_width = resize.get("width", preview_width)
            preview_height = resize.get("height", preview_height)

        self.kc.update_preview_layer(
            progress_state.current_image,
            x,
            y,
            preview_width,
            preview_height,
        )

    def threadable_run(self, data: dict) -> None:
        endpoint_name = self.GENERATION_ENDPOINT_BY_MODE.get(self.mode)
        if endpoint_name is None:
            raise RuntimeError(f"Unsupported generation mode: {self.mode}")

        run_generation = getattr(self.api, endpoint_name)
        self.results = run_generation(data)

    def threadable_return(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        processing_instructions: dict,
    ) -> None:
        layer_adapter = KritaAdapter()
        if self.results is not None:
            self.finished = True
            self.results = prune_generation_results(self.results)

            below_layer_uuid = processing_instructions.get("results_below_layer_uuid")
            if below_layer_uuid:
                below_layer = layer_adapter.get_layer_from_uuid(below_layer_uuid)
                layer_adapter.results_to_layers(
                    self.results,
                    x,
                    y,
                    width,
                    height,
                    below_layer=below_layer,
                )
            else:
                layer_adapter.results_to_layers(self.results, x, y, width, height)

            # Save to history
            if "images" in self.results and len(self.results["images"]) > 0:
                self.history_manager.save_entry(
                    data=self.current_generation_data,
                    thumbnail_base64=self.results["images"][0],
                )

        elif self.debug:
            self.debug_data.setPlainText(
                f"{self.debug_data.toPlainText()}\nThreadable return had no results"
            )

        self.generate_btn.setText("Generate")
        self.progress_bar.setHidden(True)
        self.update_progress_bar(0)
        self._stop_generation_loop()
        self.update()

    def _stop_generation_loop(self) -> None:
        self.update_progress_bar(0)
        self.kc.delete_preview_layer()
        if self.progress_timer is not None:
            self.progress_timer.stop()
        self.is_generating = False

    def cancel(self) -> None:
        try:
            self.api.interrupt()
            self.abort = True
            self.generate_btn.setText("Generate")
            self.progress_bar.setHidden(True)
            self._stop_generation_loop()
            self.update()
        except Exception as error:
            raise RuntimeError(
                f"Forge SD - Exception trying to interrupt: {error}"
            ) from error
