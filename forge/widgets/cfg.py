from ..qt_compat import *
from ..adapters.sd_api import SDAPI
from ..adapters.krita_adapter import KritaAdapter
from ..settings_controller import SettingsController
from ..domain.model_registry import ModelFamily, detect_model_family, get_model_config

class CFGWidget(QWidget):
    def __init__(self, settings_controller:SettingsController, api:SDAPI):
        super().__init__()
        self.settings_controller = settings_controller
        self.kc = KritaAdapter()
        self.api = api
        self.setLayout(QHBoxLayout())
        self.layout().setContentsMargins(0,0,0,0)
        self.variables = {
            'cfg': self.settings_controller.get('defaults.cfg_scale'),
        }
        self.draw_ui()

    def draw_ui(self):
        self.label = QLabel('CFG Scale')
        self.layout().addWidget(self.label)

        self.cfg_entry = QDoubleSpinBox()
        self.cfg_entry.setMinimum(0.0)
        self.cfg_entry.setMaximum(30.0)
        self.cfg_entry.setValue(self.variables['cfg'])
        self.cfg_entry.setSingleStep(0.1)
        self.cfg_entry.valueChanged.connect(lambda: self._update_variable('cfg', self.cfg_entry.value()))
        self.layout().addWidget(self.cfg_entry)

    def _update_variable(self, key, value):
        self.variables[key] = round(value, 2)

    def update_for_model(self, model_name):
        """Adjust CFG label, range, and visibility based on model family."""
        family = detect_model_family(model_name)
        name_lower = model_name.lower()
        is_krea2_turbo = family == ModelFamily.KREA2 and 'turbo' in name_lower

        if family == ModelFamily.FLUX or family == ModelFamily.FLUX2:
            self.label.setText('Distilled CFG')
            self.cfg_entry.setMinimum(1.0)
            self.cfg_entry.setMaximum(10.0)
            self.cfg_entry.setEnabled(True)
            if self.variables['cfg'] > 10.0 or self.variables['cfg'] < 1.0:
                self.cfg_entry.setValue(3.5)
        elif family == ModelFamily.ZIMAGE:
            self.label.setText('CFG Scale (fixed)')
            self.cfg_entry.setMinimum(1.0)
            self.cfg_entry.setMaximum(1.0)
            self.cfg_entry.setValue(1.0)
            self.cfg_entry.setEnabled(False)
            self.variables['cfg'] = 1.0
        elif is_krea2_turbo:
            self.label.setText('CFG (fixed to 0)')
            self.cfg_entry.setMinimum(0.0)
            self.cfg_entry.setMaximum(0.0)
            self.cfg_entry.setValue(0.0)
            self.cfg_entry.setEnabled(False)
            self.variables['cfg'] = 0.0
        elif family == ModelFamily.KREA2:
            self.label.setText('Guidance Scale')
            self.cfg_entry.setMinimum(0.0)
            self.cfg_entry.setMaximum(10.0)
            self.cfg_entry.setEnabled(True)
            if self.variables['cfg'] > 10.0:
                self.cfg_entry.setValue(4.5)
        elif family == ModelFamily.ANIMA:
            self.label.setText('CFG Scale')
            self.cfg_entry.setMinimum(0.0)
            self.cfg_entry.setMaximum(20.0)
            self.cfg_entry.setEnabled(True)
        elif family == ModelFamily.QWEN_IMAGE:
            self.label.setText('Guidance Scale')
            self.cfg_entry.setMinimum(0.0)
            self.cfg_entry.setMaximum(10.0)
            self.cfg_entry.setEnabled(True)
            if self.variables['cfg'] > 10.0 or self.variables['cfg'] < 1.0:
                self.cfg_entry.setValue(4.0)
        else:
            self.label.setText('CFG Scale')
            self.cfg_entry.setMinimum(0.0)
            self.cfg_entry.setMaximum(30.0)
            self.cfg_entry.setEnabled(True)

    def save_settings(self):
        self.settings_controller.set('defaults.cfg_scale', self.variables['cfg'])
        self.settings_controller.debounced_save()
    
    def get_generation_data(self):
        data = {
            'cfg_scale': self.variables['cfg']
        }
        self.save_settings()
        return data

    def set_generation_data(self, data: dict) -> None:
        if "cfg_scale" in data:
            self.cfg_entry.setValue(data["cfg_scale"])
            self._update_variable("cfg", data["cfg_scale"])

__all__ = ["CFGWidget"]