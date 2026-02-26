from __future__ import annotations

import base64
import os
import random

from krita import Krita, QUuid, Selection
from PyQt5.QtCore import (
    QByteArray,
    QBuffer,
    QIODevice,
    QObject,
    QPointF,
    QThread,
    QTimer,
    pyqtSignal,
)
from PyQt5.QtGui import QImage, qAlpha, qRgb


class _Worker(QObject):
    finished = pyqtSignal()

    def __init__(self, task):
        super().__init__()
        self._task = task

    def run(self) -> None:
        try:
            self._task()
        finally:
            self.finished.emit()


class KritaAdapter:
    def __init__(self) -> None:
        self.doc = Krita.instance().activeDocument()
        self.preview_layer_uid = None
        self.thread = None
        self.worker = None

    def version_gte(self, target_version: str) -> bool:
        current_parts = Krita.instance().version().split(".")
        target_parts = target_version.split(".")

        for index, target_part in enumerate(target_parts):
            current_part = current_parts[index]
            if int(target_part) > int(current_part):
                return False
        return True

    def run_as_thread(self, function, after_function) -> None:
        self.thread = QThread()
        self.worker = _Worker(function)
        self.worker.moveToThread(self.thread)
        self.worker.finished.connect(after_function)
        self.worker.finished.connect(self.thread.quit)
        self.thread.started.connect(self.worker.run)
        self.thread.start()

    def create_new_doc(self, width: int = 512, height: int = 512) -> None:
        self.doc = Krita.instance().createDocument(
            width,
            height,
            "Forge SD Output",
            "RGBA",
            "U8",
            "",
            72.0,
        )
        Krita.instance().activeWindow().addView(self.doc)

    def refresh_doc(self) -> None:
        self.doc = Krita.instance().activeDocument()

    def get_selection_bounds(self) -> tuple[int, int, int, int]:
        document = self._ensure_document()
        selection = document.selection()
        if selection:
            return selection.x(), selection.y(), selection.width(), selection.height()
        return 0, 0, 0, 0

    def set_selection(self, x: int, y: int, w: int, h: int) -> None:
        document = self._ensure_document()
        selection = Selection()
        selection.select(x, y, w, h, 255)
        document.setSelection(selection)

    def get_canvas_bounds(self) -> tuple[int, int, int, int]:
        document = self._ensure_document()
        bounds = document.bounds()
        return bounds.x(), bounds.y(), bounds.width(), bounds.height()

    def resize_canvas(self, width: int, height: int) -> None:
        x, y, _, _ = self.get_canvas_bounds()
        self.doc.resizeImage(x, y, width - x, height - y)

    def get_layer_bounds(self) -> tuple[int, int, int, int]:
        document = self._ensure_document()
        bounds = document.activeNode().bounds()
        return bounds.x(), bounds.y(), bounds.width(), bounds.height()

    @staticmethod
    def set_layer_visible(layer, visible: bool = True) -> None:
        layer.setVisible(visible)

    def get_active_layer_name(self) -> str:
        document = self._ensure_document()
        return document.activeNode().name()

    def get_canvas_size(self) -> tuple[int, int]:
        document = self._ensure_document()
        return document.width(), document.height()

    @staticmethod
    def base64_to_pixeldata(
        base64str: str,
        width: int = -1,
        height: int = -1,
    ) -> tuple[QByteArray, int, int]:
        image_data = base64.b64decode(base64str)
        image_format = "PNG" if base64str.startswith("iVBORw0KGgo") else "JPEG"
        image = QImage.fromData(image_data, image_format)

        if image.isGrayscale():
            image = image.convertToFormat(QImage.Format_RGBA8888)

        if width > -1:
            image = image.scaledToWidth(width)
        if height > -1:
            image = image.scaledToHeight(height)

        image_bits = image.bits()
        if image_bits is None:
            return QByteArray(), 0, 0

        image_bits.setsize(image.byteCount())
        return QByteArray(image_bits.asstring()), image.width(), image.height()

    @staticmethod
    def qimage_to_b64_str(image: QImage) -> str:
        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        return byte_array.toBase64().data().decode()

    def find_below(self, below_layer=None):
        target_node = below_layer or self.doc.activeNode()
        target_index = target_node.index()
        siblings = target_node.parentNode().childNodes()
        if target_index == len(siblings) - 1:
            return target_node
        return siblings[target_index - 1]

    def find_parent_node(self, layer=None):
        child_node = layer or self.doc.activeNode()
        return child_node.parentNode()

    def results_to_layers(
        self,
        results,
        x: int = 0,
        y: int = 0,
        w: int = -1,
        h: int = -1,
        layer_name: str = "",
        below_active: bool = False,
        below_layer=None,
    ) -> None:
        document = self._ensure_document()

        if w < 0 or h < 0:
            w, h = self._resolve_result_dimensions(results)

        parent = document.rootNode()
        if below_active or below_layer is not None:
            parent = self.find_parent_node(below_layer)

        if isinstance(results, dict) and "images" in results:
            self._add_images_results(
                results,
                parent,
                x,
                y,
                w,
                h,
                layer_name,
                below_active,
                below_layer,
            )

        if isinstance(results, dict) and "image" in results:
            self._add_single_image_result(
                results,
                parent,
                x,
                y,
                w,
                h,
                layer_name,
                below_active,
                below_layer,
            )

        document.refreshProjection()

    def result_to_transparency_mask(
        self,
        results,
        x: int = 0,
        y: int = 0,
        w: int = -1,
        h: int = -1,
    ) -> None:
        delay_ms = 500
        document = self._ensure_document()

        previous_active = document.activeNode()
        was_group = previous_active.type() == "grouplayer"
        parent_node = previous_active.parentNode()

        unique_name = f"forge_sd_transparent-{random.randint(10000, 99999)}"
        self.results_to_layers(results, x, y, w, h, unique_name, below_active=True)

        transparency_layer = document.nodeByName(unique_name)
        QTimer.singleShot(delay_ms, lambda: document.setActiveNode(transparency_layer))
        document.refreshProjection()
        document.waitForDone()
        QTimer.singleShot(
            delay_ms,
            lambda: Krita.instance().action("convert_to_transparency_mask").trigger(),
        )

        if parent_node.type() == "grouplayer" and not was_group:
            QTimer.singleShot(
                delay_ms,
                lambda: previous_active.addChildNode(document.activeNode(), None),
            )

    def get_active_layer_uuid(self):
        document = self._ensure_document()
        if len(document.activeNode().channels()) == 0:
            document.setActiveNode(document.activeNode().parentNode())
        return document.activeNode().uniqueId()

    def get_layer_from_uuid(self, uuid):
        document = self._ensure_document()
        if isinstance(uuid, str):
            uuid = QUuid(uuid)

        if self.version_gte("5.2"):
            return document.nodeByUniqueID(uuid)
        return self._find_node_by_uuid(document.rootNode(), uuid)

    def _find_node_by_uuid(self, start_node, uuid):
        if start_node.uniqueId() == uuid:
            return start_node
        for child in start_node.childNodes():
            result = self._find_node_by_uuid(child, uuid)
            if result is not None:
                return result
        return None

    def set_layer_uuid_as_active(self, uuid) -> None:
        node = self.get_layer_from_uuid(uuid)
        try:
            self.doc.setActiveNode(node)
        except Exception:
            return

    def get_selected_layer_img(self) -> QImage:
        x, y, width, height = self.get_layer_bounds()
        return self._ensure_document().projection(x, y, width, height)

    def get_canvas_img(self) -> QImage:
        x, y, width, height = self.get_canvas_bounds()
        return self._ensure_document().projection(x, y, width, height)

    def get_selection_img(self) -> QImage:
        x, y, width, height = self.get_selection_bounds()
        return self._ensure_document().projection(x, y, width, height)

    def get_transparent_selection(self) -> QImage:
        x, y, width, height = self.get_selection_bounds()
        pixels = self.doc.activeNode().projectionPixelData(x, y, width, height)
        return self.projection_to_qimage(pixels, width, height)

    def get_transparent_layer(self) -> QImage:
        x, y, width, height = self.get_layer_bounds()
        pixels = self.doc.activeNode().projectionPixelData(x, y, width, height)
        return self.projection_to_qimage(pixels, width, height)

    def get_transparent_canvas(self) -> QImage:
        x, y, width, height = self.get_canvas_bounds()
        pixels = self.doc.activeNode().projectionPixelData(x, y, width, height)
        return self.projection_to_qimage(pixels, width, height)

    @staticmethod
    def alpha_to_mask(image: QImage, width: int, height: int) -> QImage:
        for pixel_x in range(width):
            for pixel_y in range(height):
                pixel = image.pixel(pixel_x, pixel_y)
                alpha = qAlpha(pixel)
                image.setPixel(pixel_x, pixel_y, qRgb(alpha, alpha, alpha))
        return image

    def get_mask_and_image(self, mode: str = "canvas"):
        document = self._ensure_document()
        mask_layer = document.activeNode()

        if len(mask_layer.channels()) == 0:
            mask_layer = mask_layer.parentNode()
            document.setActiveNode(mask_layer)

        x, y, width, height = self._bounds_for_mode(mode)

        mask_pixels = mask_layer.projectionPixelData(x, y, width, height)
        mask_image = self.projection_to_qimage(mask_pixels, width, height)
        mask_image_bw = self.alpha_to_mask(mask_image, width, height)

        mask_layer.setVisible(False)
        document.refreshProjection()
        source_image = document.projection(x, y, width, height)
        mask_layer.setVisible(True)
        document.refreshProjection()

        return mask_image_bw, source_image

    @staticmethod
    def projection_to_qimage(pixel_data: QByteArray, width: int, height: int) -> QImage:
        bytes_per_pixel = 4
        return QImage(
            pixel_data,
            width,
            height,
            width * bytes_per_pixel,
            QImage.Format.Format_ARGB32,
        )

    def _get_layer_with_uid(self, uid, node=None):
        if node is None:
            node = self.doc.rootNode()
        if node.uniqueId() == uid:
            return node
        for child in node.childNodes():
            result = self._get_layer_with_uid(uid, child)
            if result:
                return result
        return None

    def transform_to_width_height(
        self, layer, x: int, y: int, width: int, height: int
    ) -> None:
        try:
            if self.version_gte("5.2"):
                self.use_transform_mask(layer, x, y, width, height)
            else:
                self.scale_layer(layer, x, y, width, height)
        except Exception:
            self.scale_layer(layer, x, y, width, height)

    @staticmethod
    def scale_layer(
        layer, x: int, y: int, width: int, height: int, strategy: str = "Bilinear"
    ) -> None:
        layer.scaleNode(QPointF(x, y), width, height, strategy)

    def use_transform_mask(
        self, layer, x: int, y: int, width: int, height: int
    ) -> None:
        document = self._ensure_document()
        mask = document.createTransformMask("Transform")
        layer.addChildNode(mask, None)

        bounds = layer.bounds()
        if bounds.width() == 0 or bounds.height() == 0:
            bounds = document.bounds()

        scale_x = width / bounds.width()
        scale_y = height / bounds.height()

        plugin_dir = os.path.dirname(os.path.realpath(__file__))
        xml_path = os.path.join(plugin_dir, "..", "resources", "transform_params.xml")
        xml_path = os.path.normpath(xml_path)

        with open(xml_path, "r", encoding="utf-8") as handle:
            xml_template = handle.read()

        mask.fromXML(xml_template.format(x=x, y=y, scale_x=scale_x, scale_y=scale_y))

    def delete_preview_layer(self) -> None:
        if self.preview_layer_uid is None:
            return

        layer = self._get_layer_with_uid(self.preview_layer_uid)
        if layer:
            layer.setLocked(False)
            layer.remove()

        self.preview_layer_uid = None

    def update_preview_layer(
        self, base64str: str, x: int, y: int, w: int, h: int
    ) -> None:
        document = self._ensure_document()
        byte_array, img_w, img_h = self.base64_to_pixeldata(base64str, w, h)

        if self.preview_layer_uid is None:
            layer = document.createNode("Preview", "paintLayer")
            document.rootNode().addChildNode(layer, None)
            self.preview_layer_uid = layer.uniqueId()
        else:
            layer = self._get_layer_with_uid(self.preview_layer_uid)

        layer.setLocked(False)
        layer.setPixelData(byte_array, x, y, img_w, img_h)
        layer.setLocked(True)
        document.refreshProjection()

    @staticmethod
    def get_foreground_color_hex() -> str:
        view = Krita.instance().activeWindow().activeView()
        canvas = view.canvas()
        return view.foregroundColor().colorForCanvas(canvas).name()

    @staticmethod
    def get_background_color_hex() -> str:
        view = Krita.instance().activeWindow().activeView()
        canvas = view.canvas()
        return view.backgroundColor().colorForCanvas(canvas).name()

    def setup_mask_layer(self, name: str = "Forge Mask") -> None:
        document = self._ensure_document()
        layer = document.createNode(name, "paintLayer")
        document.rootNode().addChildNode(layer, None)
        document.setActiveNode(layer)
        document.refreshProjection()

    def activate_brush(self) -> None:
        Krita.instance().action("KritaShapeDrawingToolBrush").trigger()

    def _ensure_document(self):
        self.doc = Krita.instance().activeDocument()
        if self.doc is None:
            self.create_new_doc()
        return self.doc

    def _bounds_for_mode(self, mode: str) -> tuple[int, int, int, int]:
        mode = mode.lower()
        if mode == "selection":
            return self.get_selection_bounds()
        if mode == "layer":
            return self.get_layer_bounds()
        return self.get_canvas_bounds()

    def _resolve_result_dimensions(self, results) -> tuple[int, int]:
        if isinstance(results, dict):
            info = results.get("info")
            if isinstance(info, dict):
                width = info.get("width")
                height = info.get("height")
                if isinstance(width, int) and isinstance(height, int):
                    return width, height

            poses = results.get("poses")
            if isinstance(poses, list) and poses:
                first_pose = poses[0]
                if isinstance(first_pose, dict):
                    width = first_pose.get("canvas_width")
                    height = first_pose.get("canvas_height")
                    if isinstance(width, int) and isinstance(height, int):
                        return width, height

        _, _, selection_w, selection_h = self.get_selection_bounds()
        if selection_w > 0 and selection_h > 0:
            return selection_w, selection_h

        _, _, canvas_w, canvas_h = self.get_canvas_bounds()
        return canvas_w, canvas_h

    def _add_images_results(
        self,
        results,
        parent,
        x: int,
        y: int,
        w: int,
        h: int,
        layer_name: str,
        below_active: bool,
        below_layer,
    ) -> None:
        images = results.get("images")
        if not isinstance(images, list):
            return

        document = self._ensure_document()
        image_parent = parent
        group = None

        if len(images) > 1:
            group = document.createGroupLayer("Results")
            image_parent = group

        for index, image_data in enumerate(images):
            if not image_data:
                continue

            if layer_name:
                name = layer_name
            else:
                name = self._seed_layer_name(results, index)

            layer = document.createNode(name, "paintLayer")
            byte_array, img_w, img_h = self.base64_to_pixeldata(image_data)
            layer.setPixelData(byte_array, x, y, img_w, img_h)

            destination = None
            if len(images) == 1 and (below_active or below_layer is not None):
                destination = self.find_below(below_layer)

            image_parent.addChildNode(layer, destination)
            if img_w != w or img_h != h:
                self.transform_to_width_height(layer, x, y, w, h)

            document.refreshProjection()

        if group is not None:
            if below_active or below_layer is not None:
                group_parent = self.find_parent_node(below_layer)
                group_parent.addChildNode(group, self.find_below(below_layer))
            else:
                document.rootNode().addChildNode(group, None)

    def _add_single_image_result(
        self,
        results,
        parent,
        x: int,
        y: int,
        w: int,
        h: int,
        layer_name: str,
        below_active: bool,
        below_layer,
    ) -> None:
        image_data = results.get("image")
        if not isinstance(image_data, str) or not image_data:
            return

        document = self._ensure_document()
        layer = document.createNode(layer_name or "Image", "paintLayer")
        byte_array, img_w, img_h = self.base64_to_pixeldata(image_data, w, h)
        layer.setPixelData(byte_array, x, y, img_w, img_h)

        destination = (
            self.find_below(below_layer)
            if (below_active or below_layer is not None)
            else None
        )
        parent.addChildNode(layer, destination)

        if img_w != w or img_h != h:
            self.transform_to_width_height(layer, x, y, w, h)

        document.refreshProjection()

    @staticmethod
    def _seed_layer_name(results, index: int) -> str:
        info = results.get("info")
        if isinstance(info, dict):
            all_seeds = info.get("all_seeds")
            if isinstance(all_seeds, list) and len(all_seeds) > index:
                return f"Seed: {all_seeds[index]}"
        return "Image"


__all__ = ["KritaAdapter"]
