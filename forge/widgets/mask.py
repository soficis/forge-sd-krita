from __future__ import annotations

import logging
from ..qt_compat import QSize, Qt

logger = logging.getLogger(__name__)
from ..qt_compat import QIcon, QPixmap
from ..qt_compat import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTimer,
    QVBoxLayout,
    QWidget,
)

from ..adapters.krita_adapter import KritaAdapter
from ..adapters.sd_api import SDAPI
from ..settings_controller import SettingsController
from ..widgets import CollapsibleWidget


class MaskWidget(QWidget):
    MAX_HEIGHT = 100

    def __init__(
        self,
        settings_controller: SettingsController,
        api: SDAPI,
        size_dict: dict,
    ) -> None:
        super().__init__()
        self.settings_controller = settings_controller
        self.api = api
        self.size_dict = size_dict
        self.kc = KritaAdapter()

        self.variables = {
            "mask_blur": self.settings_controller.get("inpaint.mask_blur"),
            "mask_mode": self.settings_controller.get("inpaint.mask_mode"),
            "masked_content": self.settings_controller.get("inpaint.masked_content"),
            "inpaint_area": self.settings_controller.get("inpaint.inpaint_area"),
            "mask_padding": self.settings_controller.get("inpaint.padding"),
            "auto_update_mask": self.settings_controller.get(
                "inpaint.auto_update_mask"
            ),
            "results_below_mask": self.settings_controller.get(
                "inpaint.results_below_mask"
            ),
            "hide_mask_on_gen": self.settings_controller.get(
                "inpaint.hide_mask_on_gen"
            ),
            "reference_layer": self.settings_controller.get(
                "inpaint.reference_layer", ""
            ),
        }

        self.selection_mode = "canvas"
        self.mask_uuid = None
        self.mask = None
        self.image = None

        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.draw_ui()

    def draw_ui(self) -> None:
        self.preview_list = QListWidget()
        self.preview_list.setFixedHeight(self.MAX_HEIGHT)
        self.preview_list.setFlow(QListView.Flow.LeftToRight)
        self.preview_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_list.setResizeMode(QListView.ResizeMode.Adjust)
        self.preview_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.preview_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.preview_list.setIconSize(QSize(self.MAX_HEIGHT, self.MAX_HEIGHT))
        self.layout().addWidget(self.preview_list)

        button_row = QWidget()
        button_row.setLayout(QHBoxLayout())
        button_row.layout().setContentsMargins(0, 0, 0, 0)

        quick_mask = QPushButton("Quick Mask")
        quick_mask.setToolTip("Creates a new layer for masking and selects the brush tool.")
        quick_mask.clicked.connect(self.handle_quick_mask)
        button_row.layout().addWidget(quick_mask)

        use_selection = QPushButton("Use Selection")
        use_selection.clicked.connect(lambda: self.get_mask_and_img("selection"))
        button_row.layout().addWidget(use_selection)

        use_layer = QPushButton("Use Layer")
        use_layer.clicked.connect(lambda: self.get_mask_and_img("layer"))
        button_row.layout().addWidget(use_layer)

        use_canvas = QPushButton("Use Canvas")
        use_canvas.clicked.connect(lambda: self.get_mask_and_img("canvas"))
        button_row.layout().addWidget(use_canvas)

        self.layout().addWidget(button_row)

        mask_row = QWidget()
        mask_row.setLayout(QHBoxLayout())
        mask_row.layout().setContentsMargins(0, 0, 0, 0)

        brush_label = QLabel("Brush:")
        mask_row.layout().addWidget(brush_label)

        self.brush_size_box = QSpinBox()
        self.brush_size_box.setRange(1, 500)
        self.brush_size_box.setSuffix("px")
        self.brush_size_box.setToolTip("Current brush size (read from Krita).")
        mask_row.layout().addWidget(self.brush_size_box)

        self.mask_opacity_toggle = QCheckBox("50%")
        self.mask_opacity_toggle.setToolTip(
            "Toggle mask layer opacity between 50% and 100%."
        )
        self.mask_opacity_toggle.setChecked(False)
        self.mask_opacity_toggle.stateChanged.connect(self._toggle_mask_opacity)
        mask_row.layout().addWidget(self.mask_opacity_toggle)

        clear_mask = QPushButton("Clear")
        clear_mask.setToolTip("Clear the mask layer to fully transparent.")
        clear_mask.clicked.connect(self._clear_mask)
        mask_row.layout().addWidget(clear_mask)

        fill_mask = QPushButton("Fill")
        fill_mask.setToolTip("Fill the mask layer to fully opaque (white).")
        fill_mask.clicked.connect(self._fill_mask)
        mask_row.layout().addWidget(fill_mask)

        self.layout().addWidget(mask_row)

        self._brush_poll_timer = QTimer(self)
        self._brush_poll_timer.setInterval(500)
        self._brush_poll_timer.timeout.connect(self._poll_brush_size)
        self._brush_poll_timer.start()
        self._hidden_layer_uuids: list[str] = []

        self._build_mask_qol_settings()
        self._build_inpaint_settings()

    def _build_mask_qol_settings(self) -> None:
        mask_settings = QWidget()
        mask_settings.setLayout(QFormLayout())
        mask_settings.layout().setContentsMargins(0, 0, 0, 0)

        auto_update = QCheckBox("Update mask before generating")
        auto_update.setToolTip(
            "Uses the current state of the selected mask layer when Generate is clicked."
        )
        auto_update.setChecked(self.variables["auto_update_mask"])
        auto_update.stateChanged.connect(
            lambda: self._update_variable("auto_update_mask", auto_update.isChecked())
        )
        if not self.settings_controller.get("hide_ui.inpaint_auto_update"):
            mask_settings.layout().addWidget(auto_update)

        results_below = QCheckBox("Results below mask")
        results_below.setToolTip("Insert results as a new layer below the mask layer.")
        results_below.setChecked(self.variables["results_below_mask"])
        results_below.stateChanged.connect(
            lambda: self._update_variable(
                "results_below_mask", results_below.isChecked()
            )
        )
        if not self.settings_controller.get("hide_ui.inpaint_below_mask"):
            mask_settings.layout().addWidget(results_below)

        hide_mask = QCheckBox("Hide mask when generating")
        hide_mask.setToolTip(
            "Temporarily hide mask layer visibility during generation."
        )
        hide_mask.setChecked(self.variables["hide_mask_on_gen"])
        hide_mask.stateChanged.connect(
            lambda: self._update_variable("hide_mask_on_gen", hide_mask.isChecked())
        )
        if not self.settings_controller.get("hide_ui.inpaint_hide_mask"):
            mask_settings.layout().addWidget(hide_mask)

        visible_count = sum(
            [
                not self.settings_controller.get("hide_ui.inpaint_auto_update"),
                not self.settings_controller.get("hide_ui.inpaint_below_mask"),
                not self.settings_controller.get("hide_ui.inpaint_hide_mask"),
            ]
        )
        if visible_count == 1:
            self.layout().addWidget(mask_settings)
        elif visible_count > 1:
            self.layout().addWidget(CollapsibleWidget("Mask Settings", mask_settings))

    def _build_inpaint_settings(self) -> None:
        form = QWidget()
        form.setLayout(QFormLayout())
        form.layout().setContentsMargins(0, 0, 0, 0)

        blur_box = QSpinBox()
        blur_box.setRange(0, 64)
        blur_box.setValue(self.variables["mask_blur"])
        blur_box.valueChanged.connect(
            lambda: self._update_variable("mask_blur", blur_box.value())
        )
        form.layout().addRow("Mask Blur", blur_box)

        mask_mode = QComboBox()
        mask_mode.addItems(["Inpaint masked", "Inpaint not masked"])
        mask_mode.setMinimumContentsLength(10)
        mask_mode.setCurrentIndex(self.variables["mask_mode"])
        mask_mode.currentIndexChanged.connect(
            lambda: self._update_variable("mask_mode", mask_mode.currentIndex())
        )
        form.layout().addRow("Mask Mode", mask_mode)

        mask_content = QComboBox()
        mask_content.addItems(["Fill", "Original", "Latent Noise", "Latent Nothing"])
        mask_content.setMinimumContentsLength(10)
        mask_content.setCurrentIndex(self.variables["masked_content"])
        mask_content.currentIndexChanged.connect(
            lambda: self._update_variable("masked_content", mask_content.currentIndex())
        )
        form.layout().addRow("Masked Content", mask_content)

        inpaint_area = QComboBox()
        inpaint_area.addItems(["Whole Picture", "Only Masked"])
        inpaint_area.setMinimumContentsLength(10)
        inpaint_area.setCurrentIndex(self.variables["inpaint_area"])
        inpaint_area.currentIndexChanged.connect(
            lambda: self._update_variable("inpaint_area", inpaint_area.currentIndex())
        )
        form.layout().addRow("Inpaint Area", inpaint_area)

        padding_box = QSpinBox()
        padding_box.setRange(0, 64)
        padding_box.setValue(self.variables["mask_padding"])
        padding_box.valueChanged.connect(
            lambda: self._update_variable("mask_padding", padding_box.value())
        )
        form.layout().addRow("Only masked padding", padding_box)

        self.reference_layer_combo = QComboBox()
        self.reference_layer_combo.setMinimumContentsLength(10)
        self.reference_layer_combo.setToolTip(
            "Select a reference layer for IP-Adapter based inpainting."
        )
        self._populate_reference_layers()
        self.reference_layer_combo.currentTextChanged.connect(
            lambda: self._update_variable(
                "reference_layer", self.reference_layer_combo.currentText()
            )
        )
        form.layout().addRow("Reference Layer", self.reference_layer_combo)

        self.layout().addWidget(CollapsibleWidget("Inpaint Settings", form))

    def _populate_reference_layers(self) -> None:
        """Populate the reference layer combo box with available paint layers."""
        self.reference_layer_combo.blockSignals(True)
        self.reference_layer_combo.clear()
        self.reference_layer_combo.addItem("")
        try:
            names = self.kc.get_paintable_layer_names()
            for name in names:
                self.reference_layer_combo.addItem(name)
        except Exception:
            logger.warning("Could not populate reference layer names")
        saved = self.variables.get("reference_layer", "")
        idx = self.reference_layer_combo.findText(saved)
        if idx >= 0:
            self.reference_layer_combo.setCurrentIndex(idx)
        self.reference_layer_combo.blockSignals(False)

    def _update_variable(self, key: str, value) -> None:
        self.variables[key] = value

    def handle_quick_mask(self) -> None:
        self.kc.setup_mask_layer()
        self.kc.activate_brush()
        self.get_mask_and_img("layer")

    def _toggle_mask_opacity(self, state) -> None:
        if self.mask_uuid is None:
            return
        layer = self.kc.get_layer_from_uuid(self.mask_uuid)
        if layer is None:
            return
        checked = (state == Qt.CheckState.Checked)
        opacity = 0.5 if checked else 1.0
        self.kc.set_mask_opacity(opacity, layer)

    def _clear_mask(self) -> None:
        if self.mask_uuid is None:
            return
        layer = self.kc.get_layer_from_uuid(self.mask_uuid)
        if layer is None:
            return
        self.kc.clear_mask_layer(layer)

    def _fill_mask(self) -> None:
        if self.mask_uuid is None:
            return
        layer = self.kc.get_layer_from_uuid(self.mask_uuid)
        if layer is None:
            return
        self.kc.fill_mask_layer(layer)

    def _poll_brush_size(self) -> None:
        size = self.kc.get_active_brush_size()
        if size > 0:
            self.brush_size_box.blockSignals(True)
            self.brush_size_box.setValue(size)
            self.brush_size_box.blockSignals(False)

    def update_size_dict(self, mode: str = "canvas") -> None:
        if mode == "selection":
            (
                self.size_dict["x"],
                self.size_dict["y"],
                self.size_dict["w"],
                self.size_dict["h"],
            ) = self.kc.get_selection_bounds()
        elif mode == "layer":
            (
                self.size_dict["x"],
                self.size_dict["y"],
                self.size_dict["w"],
                self.size_dict["h"],
            ) = self.kc.get_layer_bounds()
        else:
            (
                self.size_dict["x"],
                self.size_dict["y"],
                self.size_dict["w"],
                self.size_dict["h"],
            ) = self.kc.get_canvas_bounds()

    def update_preview_icons(self) -> None:
        self.preview_list.clear()
        if self.image is not None:
            self.preview_list.addItem(
                QListWidgetItem(QIcon(QPixmap.fromImage(self.image)), "Image")
            )
        if self.mask is not None:
            self.preview_list.addItem(
                QListWidgetItem(QIcon(QPixmap.fromImage(self.mask)), "Mask")
            )

    def update_mask_only(self, mode: str = "canvas") -> None:
        self.update_size_dict(mode)
        self.mask, _ = self.kc.get_mask_and_image(mode)
        self.update_preview_icons()

    def get_mask_and_img(self, mode: str = "canvas") -> None:
        self.selection_mode = mode
        self.update_size_dict(mode)

        self.mask_uuid = self.kc.get_active_layer_uuid()
        self.mask, self.image = self.kc.get_mask_and_image(mode)
        self.update_preview_icons()

    def save_settings(self) -> None:
        self.settings_controller.set("inpaint.mask_blur", self.variables["mask_blur"])
        self.settings_controller.set("inpaint.mask_mode", self.variables["mask_mode"])
        self.settings_controller.set(
            "inpaint.masked_content", self.variables["masked_content"]
        )
        self.settings_controller.set(
            "inpaint.inpaint_area", self.variables["inpaint_area"]
        )
        self.settings_controller.set("inpaint.padding", self.variables["mask_padding"])
        self.settings_controller.set(
            "inpaint.auto_update_mask", self.variables["auto_update_mask"]
        )
        self.settings_controller.set(
            "inpaint.results_below_mask", self.variables["results_below_mask"]
        )
        self.settings_controller.set(
            "inpaint.hide_mask_on_gen", self.variables["hide_mask_on_gen"]
        )
        self.settings_controller.set(
            "inpaint.reference_layer", self.variables["reference_layer"]
        )
        self.settings_controller.save()

    def get_generation_data(self) -> dict:
        self.save_settings()

        if self.variables["auto_update_mask"] and self.mask_uuid is not None:
            self.kc.set_layer_uuid_as_active(self.mask_uuid)
            if self.selection_mode == "selection":
                _, _, selected_w, selected_h = self.kc.get_selection_bounds()
                if selected_w == 0 and selected_h == 0:
                    self.selection_mode = "canvas"
            self.update_mask_only(mode=self.selection_mode)

        if self.image is None:
            _, _, selection_w, selection_h = self.kc.get_selection_bounds()
            self.get_mask_and_img(
                "selection" if selection_w > 0 and selection_h > 0 else "canvas"
            )

        data = {
            "mask_blur": self.variables["mask_blur"],
            "inpainting_mask_invert": self.variables["mask_mode"],
            "inpainting_fill": self.variables["masked_content"],
            "inpaint_full_res": self.variables["inpaint_area"],
            "inpaint_full_res_padding": self.variables["mask_padding"],
        }

        if self.image is not None:
            data["inpaint_img"] = self.kc.qimage_to_b64_str(self.image)
        if self.mask is not None:
            data["mask_img"] = self.kc.qimage_to_b64_str(self.mask)

        ref_layer_name = self.variables.get("reference_layer", "")
        if ref_layer_name:
            ref_node = self.kc.get_layer_by_name(ref_layer_name)
            if ref_node is not None:
                ref_image = self.kc.get_layer_projection_image(ref_node)
                if not ref_image.isNull():
                    data["reference_image"] = self.kc.qimage_to_b64_str(ref_image)

        if self.variables["results_below_mask"] and self.mask_uuid is not None:
            data["FORGE"] = {"results_below_layer_uuid": self.mask_uuid}

        if self.variables["hide_mask_on_gen"] and self.mask_uuid is not None:
            layer = self.kc.get_layer_from_uuid(self.mask_uuid)
            if layer is not None:
                self._hidden_layer_uuids.append(self.mask_uuid)
                self.kc.set_layer_visible(layer, False)

        return data

    def restore_hidden_layers(self) -> None:
        for uuid_str in self._hidden_layer_uuids:
            layer = self.kc.get_layer_from_uuid(uuid_str)
            if layer is not None:
                self.kc.set_layer_visible(layer, True)
        self._hidden_layer_uuids.clear()
