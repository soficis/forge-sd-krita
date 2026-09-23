from ..qt_compat import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QSlider, QVBoxLayout,
    QWidget, Qt,
)
from ..adapters.sd_api import SDAPI
from ..domain.generation_plan import build_generation_plan
from ..settings_controller import SettingsController

TILE_SIZE_CHOICES = (512, 768, 1024)
DEFAULT_TILE_SIZE = 768
DEFAULT_OVERLAP = 64
MIN_OVERLAP = 0
MAX_OVERLAP = 128


def clamp_tile_size(tile_size: int, min_size: int, max_size: int) -> int:
    """Clamp a square tile edge through the existing generation-plan logic."""
    try:
        edge = int(tile_size)
    except (TypeError, ValueError):
        edge = DEFAULT_TILE_SIZE
    edge = max(edge, 1)
    plan = build_generation_plan(
        width=edge,
        height=edge,
        min_size=min_size,
        max_size=max_size,
        enable_max_size=True,
    )
    return plan.request_width


class TiledWidget(QWidget):
    """Tiled high-res generation controls (Txt2Img only).

    Emits ``tiled_*`` keys consumed by the shared generate path, which
    delegates to the existing ``SDAPI.tiled_generate`` helper.
    """

    def __init__(self, settings_controller:SettingsController, api:SDAPI, ignore_hidden=False):
        super().__init__()
        self.settings_controller = settings_controller
        self.api = api
        self.ignore_hidden = ignore_hidden
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0,0,0,0)
        self.variables = {
            'enabled': self.settings_controller.get('tiled.enabled'),
            'tile_size': self.settings_controller.get('tiled.tile_size'),
            'overlap': self.settings_controller.get('tiled.overlap'),
        }

        self.draw_ui()

    def draw_ui(self):
        enable_row = QWidget()
        enable_row.setLayout(QHBoxLayout())
        enable_row.layout().setContentsMargins(0,0,0,0)

        enable_cb = QCheckBox('Enable Tiled Generation')
        enable_cb.setToolTip('Generate large images tile-by-tile, then blend the seams')
        enable_cb.setChecked(self.variables['enabled'])
        enable_cb.toggled.connect(lambda: self._update_variables('enabled', enable_cb.isChecked()))
        enable_row.layout().addWidget(enable_cb)
        self.enable_cb = enable_cb

        size_row = QWidget()
        size_row.setLayout(QHBoxLayout())
        size_row.layout().setContentsMargins(0,0,0,0)

        size_row.layout().addWidget(QLabel('Tile Size'))
        size_row.setToolTip('Edge length of each square tile. Clamped to the model family min/max size.')

        self.tile_select = QComboBox()
        self.tile_select.addItems([str(size) for size in TILE_SIZE_CHOICES])
        stored = str(self.variables['tile_size'])
        if stored not in [str(size) for size in TILE_SIZE_CHOICES]:
            self.tile_select.addItems([stored])
        self.tile_select.setCurrentText(stored)
        self.tile_select.currentTextChanged.connect(lambda: self._update_tile_size(self.tile_select.currentText()))
        size_row.layout().addWidget(self.tile_select)

        enable_row.layout().addWidget(size_row)
        self.layout().addWidget(enable_row)

        overlap_row = QWidget()
        overlap_row.setLayout(QHBoxLayout())
        overlap_row.layout().setContentsMargins(0,0,0,0)

        overlap_row.layout().addWidget(QLabel('Overlap'))
        overlap_row.setToolTip('Overlap between adjacent tiles in pixels. Blended at the seams.')

        self.overlap_value = QLabel('%s px' % self.variables['overlap'])

        self.overlap_slider = QSlider(Qt.Orientation.Horizontal)
        self.overlap_slider.setTickInterval(16)
        self.overlap_slider.setTickPosition(QSlider.TickPosition.TicksAbove)
        self.overlap_slider.setMinimum(MIN_OVERLAP)
        self.overlap_slider.setMaximum(MAX_OVERLAP)
        self.overlap_slider.setValue(self.variables['overlap'])
        self.overlap_slider.valueChanged.connect(lambda: self._update_overlap(self.overlap_slider.value()))

        overlap_row.layout().addWidget(self.overlap_slider)
        overlap_row.layout().addWidget(self.overlap_value)
        self.layout().addWidget(overlap_row)

    def _update_variables(self, key, value):
        self.variables[key] = value

    def _update_tile_size(self, text):
        try:
            self.variables['tile_size'] = int(str(text).strip())
        except (TypeError, ValueError):
            pass

    def _update_overlap(self, value):
        try:
            clamped = max(MIN_OVERLAP, min(int(value), MAX_OVERLAP))
        except (TypeError, ValueError):
            return
        self.variables['overlap'] = clamped
        self.overlap_value.setText('%s px' % clamped)

    def _clamped_tile_size(self) -> int:
        min_size = self.settings_controller.get('defaults.min_size')
        max_size = self.settings_controller.get('defaults.max_size')
        return clamp_tile_size(self.variables['tile_size'], min_size, max_size)

    def save_settings(self):
        self.settings_controller.set('tiled.enabled', self.variables['enabled'])
        self.settings_controller.set('tiled.tile_size', self.variables['tile_size'])
        self.settings_controller.set('tiled.overlap', self.variables['overlap'])
        self.settings_controller.debounced_save()

    def get_generation_data(self):
        self.save_settings()
        if not self.variables['enabled']:
            return {"tiled_enabled": False}
        return {
            "tiled_enabled": True,
            "tiled_tile_size": self._clamped_tile_size(),
            "tiled_overlap": self.variables['overlap'],
        }

    def set_generation_data(self, data: dict):
        if not isinstance(data, dict):
            return
        if "tiled_enabled" in data:
            self.variables['enabled'] = bool(data["tiled_enabled"])
        if "tiled_tile_size" in data:
            try:
                self.variables['tile_size'] = int(data["tiled_tile_size"])
            except (TypeError, ValueError):
                pass
        if "tiled_overlap" in data:
            try:
                self.variables['overlap'] = max(MIN_OVERLAP, min(int(data["tiled_overlap"]), MAX_OVERLAP))
            except (TypeError, ValueError):
                pass
        try:
            self.enable_cb.setChecked(self.variables['enabled'])
            self.tile_select.setCurrentText(str(self.variables['tile_size']))
            self.overlap_slider.setValue(self.variables['overlap'])
        except RuntimeError:
            pass
