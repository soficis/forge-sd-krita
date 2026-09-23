from ..qt_compat import QLabel, QVBoxLayout, QWidget
from ..widgets import CollapsibleWidget
from ..adapters.sd_api import SDAPI
from ..settings_controller import SettingsController
from ..extension_widgets import *

KNOWN_EXTENSIONS = ('controlnet', 'adetailer')


def visible_extensions(server_supported, hidden_extensions):
    """Return installed + visible extension names, preserving known order."""
    hidden = set(hidden_extensions or [])
    return [
        name for name in KNOWN_EXTENSIONS
        if server_supported.get(name) and name not in hidden
    ]


class ExtensionWidget(QWidget):
    def __init__(self, settings_controller:SettingsController, api:SDAPI):
        super().__init__()
        self.settings_controller = settings_controller
        self.api = api
        self.setLayout(QVBoxLayout())
        # self.layout().setContentsMargins(0,0,0,0)
        self.server_supported = {
            'controlnet': self.api.script_installed('controlnet'),
            'adetailer': self.api.script_installed('adetailer'),
        }
        hidden_extensions = self.settings_controller.get('hide_ui.hidden_extensions')

        self.controlnet_widget = ControlNetExtension(self.settings_controller, self.api)
        controlnet_collapse = CollapsibleWidget('ControlNet', self.controlnet_widget)
        if 'controlnet' in visible_extensions(self.server_supported, hidden_extensions):
            self.layout().addWidget(controlnet_collapse)

        self.adetailer_widget = ADetailerExtension(self.settings_controller, self.api)
        adetailer_collapse = CollapsibleWidget('ADetailer', self.adetailer_widget)
        if 'adetailer' in visible_extensions(self.server_supported, hidden_extensions):
            self.layout().addWidget(adetailer_collapse)

        self.no_extensions_message = ''
        if not visible_extensions(self.server_supported, hidden_extensions):
            self.no_extensions_message = (
                'No extensions to show: ControlNet and ADetailer are either '
                'not installed on the backend or hidden via the Simplify page.'
            )
            notice = QLabel(self.no_extensions_message)
            notice.setWordWrap(True)
            self.layout().addWidget(notice)

    def get_generation_data(self):
        data = {}
        # Go through each widget get their data
        if self.server_supported['controlnet']:
            if not 'alwayson_scripts' in data.keys():
                data['alwayson_scripts'] = {}
            data['alwayson_scripts'].update(self.controlnet_widget.get_generation_data())

        if self.server_supported['adetailer']:
            if not 'alwayson_scripts' in data.keys():
                data['alwayson_scripts'] = {}
            data['alwayson_scripts'].update(self.adetailer_widget.get_generation_data())
        return data
