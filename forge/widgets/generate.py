from __future__ import annotations

import base64
import json
import logging
import time
import uuid
from dataclasses import dataclass

from ..qt_compat import QProgressBar, QPushButton, QVBoxLayout, QWidget, QTextEdit, QLabel
from krita import QTimer


@dataclass
class GenerationJob:
    id: str
    data: dict
    x: int
    y: int
    width: int
    height: int
    processing_instructions: dict
    timestamp: float

from ..adapters.krita_adapter import KritaAdapter
from ..adapters.sd_api import SDAPI
from ..domain.generation_plan import (
    build_generation_plan,
    merge_generation_data,
    prune_generation_results,
)
from ..domain.generation_validation import validate_generation_data
from ..domain.history_manager import HistoryManager
from ..domain.model_registry import ModelFamily, ModelConfig, detect_model_family, get_model_config
from ..domain.progress_state import parse_progress_state
from ..settings_controller import SettingsController

logger = logging.getLogger(__name__)

# Kept out of the debug log: user text.
_UNLOGGED_KEYS = frozenset({"prompt", "negative_prompt"})


TILED_PAYLOAD_KEYS = ("tiled_enabled", "tiled_tile_size", "tiled_overlap")


def _strip_tiled_keys(data: dict) -> dict:
    """Return generation data without the ``tiled_*`` UI keys.

    Returns the original object when no tiled keys are present; otherwise a
    copy, so unknown UI keys never reach the API payload while the caller's
    dict stays intact for history/reuse.
    """
    if not isinstance(data, dict):
        return data
    if not any(key in data for key in TILED_PAYLOAD_KEYS):
        return data
    return {
        key: value for key, value in data.items()
        if key not in TILED_PAYLOAD_KEYS
    }


def _safe_int(value: object, fallback: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback


def should_cancel_on_escape(
    is_generating: bool, button_text: str, button_enabled: bool
) -> bool:
    """True when Escape should fire the Cancel action.

    Requires an in-flight generation whose button currently reads Cancel
    and is enabled - a disabled button means the backend is unreachable
    and ``interrupt()`` would fail.
    """
    return bool(is_generating) and button_text == "Cancel" and bool(button_enabled)


def _extract_tiled_request(data: dict) -> tuple[dict, int, int] | None:
    """Split tiled-generation params out of merged generation data.

    Returns ``(clean_data, tile_size, overlap)`` when ``tiled_enabled`` is
    truthy, else ``None``. ``clean_data`` never carries ``tiled_*`` keys.
    """
    clean_data = _strip_tiled_keys(data)
    if not isinstance(data, dict) or not data.get("tiled_enabled"):
        return None
    tile_size = _safe_int(data.get("tiled_tile_size", 1024), 1024)
    overlap = _safe_int(data.get("tiled_overlap", 64), 64)
    return clean_data, tile_size, overlap


def _apply_queue_status(label, text: str, status: str = "", active: bool = False) -> None:
    if label is None:
        return
    try:
        label.setText(text)
        if hasattr(label, "setProperty"):
            label.setProperty("status", status)
            label.setProperty("active", "true" if active else "false")
        if hasattr(label, "style"):
            style = label.style()
            if style is not None and hasattr(style, "unpolish") and hasattr(style, "polish"):
                style.unpolish(label)
                style.polish(label)
    except (RuntimeError, Exception):
        return


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
        # Set by cleanup(): the page was switched away or the docker closed,
        # so Qt may already have deleted this widget's children. A generation
        # still in flight then finishes into a dead UI and must not touch it.
        self._disposed = False
        self._run_error = None
        self._progress_timer_start = 0.0
        self._last_progress_change_time = 0.0
        self._last_progress_value = -1

        self.job_queue: list[GenerationJob] = []
        self.current_job: GenerationJob | None = None

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

        self.queue_status_label = QLabel("Queue: 0 jobs")
        self.queue_status_label.setObjectName("QueueStatusLabel")
        self.layout().addWidget(self.queue_status_label)

        self.clear_queue_btn = QPushButton("Clear Queue")
        self.clear_queue_btn.clicked.connect(self._clear_queue)
        self.clear_queue_btn.setHidden(True)
        self.layout().addWidget(self.clear_queue_btn)

        if self.debug:
            self.debug_data = QTextEdit()
            self.debug_data.setPlaceholderText(
                "JSON payload used to generate the image"
            )
            self.layout().addWidget(self.debug_data)

    def handle_generate_btn_click(self) -> None:
        logger.info("generate click: mode=%s is_generating=%s", self.mode, self.is_generating)
        if self.is_generating:
            self.cancel()
        else:
            self.generate()
        self.update()

    def generate(self) -> None:
        """Build a generation job from current widget state and enqueue it."""
        x, y, width, height = self._resolve_generation_bounds()

        family = detect_model_family(self.api.defaults.get("model", ""))
        config = get_model_config(family)

        user_min = self.settings_controller.get("defaults.min_size")
        user_max = self.settings_controller.get("defaults.max_size")
        min_size = user_min if user_min else config.default_min_size
        max_size = user_max if user_max else config.default_max_size

        generation_plan = build_generation_plan(
            width=width,
            height=height,
            min_size=min_size,
            max_size=max_size,
            enable_max_size=self.settings_controller.get("defaults.enable_max_size"),
        )

        base_data = {
            "width": generation_plan.request_width,
            "height": generation_plan.request_height,
        }
        if self.settings_controller.get("server.save_imgs"):
            base_data["save_images"] = True

        try:
            widget_payloads = [
                widget.get_generation_data() for widget in self.list_of_widgets
            ]
            generation_data, processing_instructions = merge_generation_data(
                base_data=base_data,
                widget_payloads=widget_payloads,
            )
            raw_prompt = generation_data.get("prompt", "")
            prompt = raw_prompt.strip() if isinstance(raw_prompt, str) else ""
            validation_errors = validate_generation_data(generation_data)
            if self.mode == "inpaint" and any(type(w).__name__ == "MaskWidget" for w in self.list_of_widgets):
                if not generation_data.get("inpaint_img"):
                    validation_errors.append("Inpaint requires an active canvas image.")
            if validation_errors or not prompt:
                logger.info("generate refused: %s", validation_errors or "empty prompt")
                _apply_queue_status(
                    getattr(self, "queue_status_label", None),
                    "Cannot generate: %s" % (validation_errors[0] if validation_errors else "Prompt is empty."),
                    status="error",
                    active=False,
                )
                self._restore_hidden_layers()
                return
            self._apply_flux_adjustments(generation_data)

            if generation_plan.resize is not None:
                processing_instructions["resize"] = {
                    "width": generation_plan.resize.width,
                    "height": generation_plan.resize.height,
                }

            job = GenerationJob(
                id=uuid.uuid4().hex,
                data=generation_data,
                x=x,
                y=y,
                width=width,
                height=height,
                processing_instructions=processing_instructions,
                timestamp=time.time(),
            )
        except Exception:
            self._restore_hidden_layers()
            raise
        self.job_queue.append(job)
        self._update_queue_status()

        if not self.is_generating:
            self._start_next_job()

    def handle_escape(self) -> bool:
        """Cancel active generation on Escape; True when the key was consumed."""
        if should_cancel_on_escape(
            self.is_generating,
            self.generate_btn.text(),
            self.generate_btn.isEnabled(),
        ):
            self.cancel()
            return True
        return False

    def _start_next_job(self) -> None:
        """Dequeue the next job and begin generation."""
        if not self.job_queue:
            return

        job = self.job_queue.pop(0)
        self.current_job = job
        self.abort = False
        self.finished = False
        # A failed run must not inherit the previous run's image or error.
        self.results = None
        self._run_error = None
        self.is_generating = True
        self.generate_btn.setText("Cancel")
        self.progress_bar.setHidden(False)
        self.update_progress_bar(0)
        self._update_queue_status()

        self.current_generation_data = job.data

        if self.debug:
            self.debug_data.setPlainText(
                json.dumps(self.api.build_payload(job.data), indent=2)
            )

        try:
            self.kc.refresh_doc()
            if self.kc.doc is None:
                self.kc.create_new_doc()

            logger.info(
                "starting job: mode=%s size=%sx%s settings=%s",
                self.mode, job.data.get("width"), job.data.get("height"),
                {k: v for k, v in sorted(job.data.items())
                 if k not in _UNLOGGED_KEYS
                 and not isinstance(v, (dict, list))
                 and not (isinstance(v, str) and len(v) > 200)},
            )
            started = self.kc.run_as_thread(
                lambda: self.threadable_run(job.data),
                lambda: self.threadable_return(
                    job.x,
                    job.y,
                    job.width,
                    job.height,
                    job.processing_instructions,
                ),
            )

            if started is False:
                logger.warning("run_as_thread refused to start (worker busy); job dropped")

            refresh_seconds = self.settings_controller.get("previews.refresh_seconds")
            refresh_ms = max(int(1000 * refresh_seconds), 100)
            if self.progress_timer is not None:
                self.progress_timer.stop()
            self.progress_timer = QTimer(self)
            self.progress_timer.timeout.connect(
                lambda: self.progress_check(
                    job.x,
                    job.y,
                    job.width,
                    job.height,
                    job.processing_instructions,
                )
            )
            self._progress_timer_start = time.time()
            self._last_progress_change_time = time.time()
            self._last_progress_value = -1
            self.progress_timer.start(refresh_ms)

        except Exception as error:
            self._restore_hidden_layers()
            self.is_generating = False
            self.current_job = None
            self.generate_btn.setText("Generate")
            self.progress_bar.setHidden(True)
            if self.progress_timer is not None:
                self.progress_timer.stop()
            self._update_queue_status()
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

        elapsed = time.time() - self._progress_timer_start
        if elapsed > 300:
            self._stop_generation_loop()
            return

        current_percent = progress_state.percent
        if current_percent != self._last_progress_value:
            self._last_progress_change_time = time.time()
            self._last_progress_value = current_percent
        elif time.time() - self._last_progress_change_time > 300:
            self._stop_generation_loop()
            return

        self.update_progress_bar(progress_state.percent)

        if not self.settings_controller.get("previews.enabled"):
            return

        if progress_state.current_image is None:
            return

        try:
            preview_bytes = base64.b64decode(progress_state.current_image)
        except ValueError:
            # binascii.Error (malformed base64) is a ValueError subclass;
            # skip the frame rather than raising out of the Qt timer slot.
            return
        if not preview_bytes:
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
        # The worker's error signal has no listener, so an exception here
        # would vanish without a trace; record it for threadable_return.
        try:
            endpoint_name = self.GENERATION_ENDPOINT_BY_MODE.get(self.mode)
            if endpoint_name is None:
                raise RuntimeError(f"Unsupported generation mode: {self.mode}")

            tiled_request = _extract_tiled_request(data)
            if self.mode == "txt2img" and tiled_request is not None:
                clean_data, tile_size, overlap = tiled_request
                self.results = self.api.tiled_generate(
                    clean_data, tile_size=tile_size, overlap=overlap
                )
                return

            run_generation = getattr(self.api, endpoint_name)
            self.results = run_generation(_strip_tiled_keys(data))
            logger.info(
                "request finished: endpoint=%s result=%s api_error=%r",
                endpoint_name, type(self.results).__name__,
                getattr(self.api, "last_error_message", ""),
            )
        except Exception as error:
            logger.exception("Forge SD - generation request failed")
            self._run_error = error

    def threadable_return(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        processing_instructions: dict,
    ) -> None:
        logger.info("threadable_return: has_results=%s run_error=%r abort=%s",
                    self.results is not None, self._run_error, self.abort)
        try:
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

                # Save to history (async thumbnail write, non-blocking)
                if "images" in self.results and len(self.results["images"]) > 0:
                    self.history_manager.save_generation_async(
                        data=self.current_generation_data,
                        image_data_b64=self.results["images"][0],
                    )

            elif self.debug:
                try:
                    self.debug_data.setPlainText(
                        f"{self.debug_data.toPlainText()}\nThreadable return had no results"
                    )
                except RuntimeError:
                    pass
        finally:
            self._restore_hidden_layers()
            self.current_job = None
            self._stop_generation_loop()
            if not getattr(self, "_disposed", False):
                try:
                    self.update()

                    if self.job_queue and not self.abort:
                        self._start_next_job()
                    else:
                        try:
                            self.generate_btn.setText("Generate")
                        except RuntimeError:
                            pass
                        try:
                            self.progress_bar.setHidden(True)
                        except RuntimeError:
                            pass
                        self.update_progress_bar(0)
                        self._update_queue_status()
                        try:
                            self.update()
                        except RuntimeError:
                            pass
                        if self.results is None and not self.abort:
                            _apply_queue_status(getattr(self, "queue_status_label", None), self._failure_message(), status="error", active=False)
                except RuntimeError:
                    pass

    def _failure_message(self) -> str:
        """Why a finished job produced no image, for the status line."""
        if self._run_error is not None:
            reason = "%s: %s" % (type(self._run_error).__name__, self._run_error)
        else:
            reason = getattr(self.api, "last_error_message", "") or "no result returned"
        return "Generation failed: %s" % reason

    def _stop_generation_loop(self) -> None:
        try:
            self.kc.delete_preview_layer()
        except Exception:
            pass
        self.is_generating = False
        if getattr(self, "_disposed", False):
            return
        self.update_progress_bar(0)
        if self.progress_timer is not None:
            try:
                self.progress_timer.stop()
            except RuntimeError:
                # C++ timer already deleted with its parent widget.
                self.progress_timer = None
        self._update_queue_status()

    def cleanup(self) -> None:
        """Stop the progress timer; safe on page switch or docker close."""
        self._disposed = True
        timer = getattr(self, "progress_timer", None)
        if timer is not None:
            try:
                timer.stop()
            except RuntimeError:
                pass

    def cancel(self) -> None:
        try:
            self.api.interrupt()
            self.abort = True
            self.current_job = None
            self.job_queue.clear()
            try:
                self.generate_btn.setText("Generate")
                self.progress_bar.setHidden(True)
            except RuntimeError:
                pass
            self._stop_generation_loop()
            self._restore_hidden_layers()
            self._update_queue_status()
            try:
                self.update()
            except RuntimeError:
                pass
        except Exception as error:
            raise RuntimeError(
                f"Forge SD - Exception trying to interrupt: {error}"
            ) from error

    def _set_queue_status_text(self, text: str, status: str = "", active: bool = False) -> None:
        _apply_queue_status(getattr(self, "queue_status_label", None), text, status, active)

    def _update_queue_status(self) -> None:
        """Update the queue status label and clear button visibility."""
        if getattr(self, "_disposed", False):
            return
        try:
            queued = len(getattr(self, "job_queue", []))
            label = getattr(self, "queue_status_label", None)
            if getattr(self, "is_generating", False):
                if queued > 0:
                    _apply_queue_status(label, f"Generating... Queue: {queued} jobs", status="", active=True)
                else:
                    _apply_queue_status(label, "Generating...", status="", active=True)
            else:
                _apply_queue_status(label, f"Queue: {queued} jobs", status="", active=False)
            clear_btn = getattr(self, "clear_queue_btn", None)
            if clear_btn is not None and hasattr(clear_btn, "setHidden"):
                clear_btn.setHidden(queued == 0)
        except RuntimeError:
            pass

    def _clear_queue(self) -> None:
        """Remove all queued jobs without cancelling the current one."""
        self.job_queue.clear()
        self._update_queue_status()

    def _restore_hidden_layers(self) -> None:
        for widget in self.list_of_widgets:
            try:
                restore = getattr(widget, 'restore_hidden_layers', None)
                if callable(restore):
                    restore()
            except RuntimeError as e:
                logger.debug("Failed to restore hidden layers for %s: %s", widget, e)
                pass

    def _is_flux_model(self) -> bool:
        """Check if the current model is a Flux model."""
        model_name = self.api.defaults.get("model", "")
        return detect_model_family(model_name) in (ModelFamily.FLUX, ModelFamily.FLUX2)

    def _is_flux_distilled(self) -> bool:
        """Check if the current model is a distilled Flux model (e.g., nunchaku)."""
        model_name = self.api.defaults.get("model", "")
        model_lower = model_name.lower()
        return "nunchaku" in model_lower or "distilled" in model_lower

    def _detect_turbo_lora(self, prompt: str) -> bool:
        """Detect if a turbo distill LoRA is loaded in the prompt."""
        prompt_lower = prompt.lower()
        turbo_keywords = ["turbo", "hyper-sd", "hyper_sd", "lcm", "alimama"]
        for kw in turbo_keywords:
            if f"<lora:{kw}" in prompt_lower:
                return True
        return False

    def _apply_flux_adjustments(self, data: dict) -> None:
        """Apply model-family-specific adjustments to generation data.

        Most adjustments are now handled by payload_builder via model_registry.
        This function handles pre-build adjustments that need widget state.
        """
        model_name = self.api.defaults.get("model", "")
        family = detect_model_family(model_name)

        # Handle [Forge] sampler prefix for Flux models
        if family == ModelFamily.FLUX:
            sampler = data.get("sampler", "")
            if sampler and not sampler.startswith("[Forge]"):
                forge_sampler = f"[Forge] {sampler}"
                available = [s.get("name", "") for s in self.api.samplers]
                if forge_sampler in available:
                    data["sampler"] = forge_sampler

        # Handle turbo LoRA adjustments
        prompt = data.get("prompt", "")
        if self._detect_turbo_lora(prompt):
            data["steps"] = min(data.get("steps", 20), 8)
            # Keep CFG as set by user or model config
