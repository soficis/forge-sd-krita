from ..domain.model_registry import max_denoise_for_model
from ..qt_compat import QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget, Qt
from ..settings_controller import SettingsController

DEFAULT_DENOISE_TOOLTIP = (
    "Denoise strength: lower values preserve more of the original image, "
    "higher values generate more changes."
)


class DenoiseWidget(QWidget):
    def __init__(self, settings_controller:SettingsController, include_start=False, include_end=False):
        super().__init__()
        self.settings_controller = settings_controller
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0,0,0,0)

        denoise_row = QWidget()
        denoise_row.setLayout(QHBoxLayout())
        denoise_row.layout().setContentsMargins(0,0,0,0)
        self.denoise_label = QLabel('Denoise Strength')
        self.denoise_label.setToolTip(DEFAULT_DENOISE_TOOLTIP)
        denoise_row.layout().addWidget(self.denoise_label)

        # Denoise label
        default_noise = self.settings_controller.get('defaults.denoise_strength')
        self.denoise_percent = QLabel('%s%%' % int(default_noise * 100))

        # Denoise Strength
        self.denoise_slider = QSlider(Qt.Orientation.Horizontal)
        self.denoise_slider.setTickInterval(10)
        self.denoise_slider.setTickPosition(QSlider.TickPosition.TicksAbove)
        self.denoise_slider.setMinimum(0)
        self.denoise_slider.setMaximum(100)
        self.denoise_slider.setValue(int(default_noise * 100))
        self.denoise_slider.valueChanged.connect(lambda: self.denoise_percent.setText('%s%%' % self.denoise_slider.value()))

        denoise_row.layout().addWidget(self.denoise_slider)

        denoise_row.layout().addWidget(self.denoise_percent)
        self.layout().addWidget(denoise_row)

    def update_for_model(self, model_name: str) -> None:
        """Cap the slider for distilled/turbo checkpoints; 1.0 = no cap."""
        ceiling = max_denoise_for_model(model_name)
        self.denoise_slider.setMaximum(int(ceiling * 100))
        # setMaximum clamps the live value; re-read it so the label can't drift.
        self.denoise_percent.setText('%s%%' % self.denoise_slider.value())
        if ceiling < 1.0:
            self.denoise_slider.setToolTip(
                'Distilled/turbo models finish in very few steps and melt '
                'above %s%% denoise. Capped at %s%% for this model.'
                % (int(ceiling * 100), int(ceiling * 100)))
        else:
            self.denoise_slider.setToolTip('')

    def save_settings(self):
        denoise = self.denoise_slider.value() / 100
        self.settings_controller.set('defaults.denoise_strength', denoise)

    def get_generation_data(self):
        denoise = self.denoise_slider.value() / 100
        data = {
            'denoising_strength': denoise
        }
        self.save_settings()
        self.settings_controller.debounced_save()
        return data
    def set_generation_data(self, data: dict) -> None:
        if "denoising_strength" in data:
            self.denoise_slider.setValue(int(data["denoising_strength"] * 100))
            self.denoise_percent.setText("%s%%" % self.denoise_slider.value())
