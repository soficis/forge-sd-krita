from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt
from ..adapters.sd_api import SDAPI
from ..adapters.krita_adapter import KritaAdapter
from ..settings_controller import SettingsController

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
        is_flux = 'flux' in model_name.lower() or 'nunchaku' in model_name.lower()
        if is_flux:
            self.label.setText('Distilled CFG')
            self.cfg_entry.setMinimum(1.0)
            self.cfg_entry.setMaximum(10.0)
            if self.variables['cfg'] > 10.0 or self.variables['cfg'] < 1.0:
                 self.cfg_entry.setValue(3.5) # Standard Flux distilled CFG
        else:
            self.label.setText('CFG Scale')
            self.cfg_entry.setMinimum(0.0)
            self.cfg_entry.setMaximum(30.0)

    def save_settings(self):
        self.settings_controller.set('defaults.cfg_scale', self.variables['cfg'])
        self.settings_controller.save()
    
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