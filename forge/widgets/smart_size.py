from __future__ import annotations

from ..qt_compat import QHBoxLayout, QLabel, QPushButton, QWidget
from ..adapters.sd_api import SDAPI
from ..domain.model_registry import detect_model_family
from ..domain.smart_resolution import suggest_resolution
from ..settings_controller import SettingsController


class SmartSizeWidget(QWidget):
    """Shared 'Smart size' row: suggest a step-aligned resolution locally.

    Reads the current model family (no backend calls), derives the
    aspect/budget from the shared ``size_dict`` (selection/canvas bounds),
    and writes the suggestion back into ``size_dict`` only when the button
    is pressed — manual sizes are never overridden otherwise.
    """

    def __init__(
        self,
        settings_controller: SettingsController,
        api: SDAPI,
        size_dict: dict | None = None,
    ) -> None:
        super().__init__()
        self.settings_controller = settings_controller
        self.api = api
        self.size_dict = size_dict if size_dict is not None else {"x": 0, "y": 0, "w": 0, "h": 0}
        self.setLayout(QHBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)

        self.smart_btn = QPushButton("Smart size")
        self.smart_btn.setToolTip(
            "Suggest a resolution snapped to the model family step "
            "that best fills the current megapixel budget."
        )
        self.smart_btn.clicked.connect(self.apply_smart_size)
        self.layout().addWidget(self.smart_btn)

        self.suggestion_label = QLabel("")
        self.layout().addWidget(self.suggestion_label)

    def _current_bounds(self) -> tuple[int, int]:
        width = self.size_dict.get("w", 0)
        height = self.size_dict.get("h", 0)
        if isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0:
            return width, height
        try:
            from ..adapters.krita_adapter import KritaAdapter

            x, y, width, height = KritaAdapter().get_selection_bounds()
            if width > 0 and height > 0:
                return width, height
            _x, _y, width, height = KritaAdapter().get_canvas_bounds()
            if width > 0 and height > 0:
                return width, height
        except Exception:
            pass
        return 512, 512

    def apply_smart_size(self) -> None:
        """Compute the suggestion and store it in ``size_dict``."""
        model_name = ""
        try:
            model_name = self.api.defaults.get("model", "")
        except AttributeError:
            model_name = ""
        family = detect_model_family(model_name or "")
        width, height = self._current_bounds()
        try:
            suggested_w, suggested_h = suggest_resolution(
                family, width / height, width, height
            )
        except ValueError:
            return
        self.size_dict["w"] = suggested_w
        self.size_dict["h"] = suggested_h
        self.suggestion_label.setText("%dx%d" % (suggested_w, suggested_h))

    def get_generation_data(self) -> dict:
        return {}
