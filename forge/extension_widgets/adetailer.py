from ..qt_compat import QCheckBox, QComboBox, QLabel, QVBoxLayout, QWidget
from enum import Enum
import logging
from ..adapters.sd_api import SDAPI
from ..settings_controller import SettingsController
from ..widgets import PromptWidget, CollapsibleWidget

logger = logging.getLogger(__name__)

class ADetailerExtension(QWidget):
    def __init__(self, settings_controller:SettingsController, api:SDAPI):
        super().__init__()
        self.settings_controller = settings_controller
        self.api = api
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0,0,0,0)
        self.units = []
        self.enabled = False

        server_supported = self.api.script_installed('adetailer')
        if not server_supported:
            error = QLabel('Host "%s" does not have ADetailer installed' % self.api.host)
            website = QLabel('Get it from https://github.com/Bing-su/adetailer')
            self.layout().addWidget(error)
            self.layout().addWidget(website)
            return

        # Checkbox to Enable
        self.enable_cb = QCheckBox('Enable')
        self.enable_cb.stateChanged.connect(lambda: self.set_enabled(self.enable_cb.isChecked()))
        self.layout().addWidget(self.enable_cb)

        # Model Select (fetched from API, cached 60s like other getters)
        models = []
        try:
            getter = getattr(self.api, 'get_adetailer_models', None)
            if callable(getter):
                models = getter() or []
        except Exception:
            logger.warning('ADetailer model list fetch failed')
            models = []
        if not isinstance(models, list):
            models = []
        models = [m for m in models if isinstance(m, str) and m]
        self.model_select = QComboBox()
        if models:
            self.model_select.addItems(models)
            self.model_select.setCurrentText(models[0])
        else:
            self.model_select.addItem('None')
            self.model_select.setCurrentText('None')
        # Inline styles removed for global QSS
        self.model_select.setMaxVisibleItems(5) # Suppose to limit the number of visible options
        self.model_select.setMinimumContentsLength(10) # Allows the box to be smaller than the longest item's char length
        self.layout().addWidget(self.model_select)


        # Prompts
        self.prompt_widget = PromptWidget(self.settings_controller, self.api, 'adetailer')
        self.layout().addWidget(self.prompt_widget)

        # ... a ton of settings I honestly never used.
        # Although there is a use steps option that might make it work as a post-processing...

    def set_enabled(self, value):
        self.enabled = value

    def get_generation_data(self):
        # https://github.com/Bing-su/adetailer/wiki/API
        if not self.enabled:
            return {}
        
        prompt_data = self.prompt_widget.get_generation_data()
        data = { # Whatever is requesting this data will have to add the `alwayson_scripts`, otherwise multiple extensions will delete each other
            'ADetailer': {
                'args': [
                    True, # Enabled... and technically optionall
                    {
                        'ad_model': self.model_select.currentText(),
                        'ad_prompt': prompt_data['prompt'],
                        'ad_negative_prompt': prompt_data['negative_prompt'],
                        # Many more args I'm skipping and using the defaults for
                    }
                    # Could add more tabs, just add their args down here in the same way
                ]
            }
        }
        self.prompt_widget.save_prompt()
        return data
