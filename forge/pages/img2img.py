from ..qt_compat import Qt, QVBoxLayout, QWidget
from ..adapters.sd_api import SDAPI
from ..domain.model_registry import ModelFamily, get_model_config
from ..settings_controller import SettingsController
from ..adapters.krita_adapter import KritaAdapter
from ..widgets import *

class Img2ImgPage(QWidget):
    def __init__(self, settings_controller:SettingsController, api:SDAPI):
        super().__init__()
        self.settings_controller = settings_controller
        self.api = api
        self.kc = KritaAdapter()
        self.size_dict = {"x":0,"y":0,"w":0,"h":0}
        self.setLayout(QVBoxLayout())

        self.img_in = ImageInWidget(self.settings_controller, self.api, 'img2img_img', self.size_dict)
        self.layout().addWidget(self.img_in)

        self.color_correction = ColorCorrectionWidget(self.settings_controller, self.api)
        if not self.settings_controller.get('hide_ui.color_correction'):
            self.layout().addWidget(self.color_correction)

        self.denoise_widget = DenoiseWidget(self.settings_controller)
        if not self.settings_controller.get('hide_ui.denoise_strength'):
            self.layout().addWidget(self.denoise_widget)

        self.model_widget = ModelsWidget(self.settings_controller, self.api)
        self.layout().addWidget(self.model_widget)

        self.prompt_widget = PromptWidget(self.settings_controller, self.api, 'img2img')
        self.layout().addWidget(self.prompt_widget)

        self.prompt_presets_widget = PromptPresetsWidget(self.settings_controller, self.prompt_widget)
        prompt_presets_collapsed = CollapsibleWidget('Prompt Presets', self.prompt_presets_widget)
        if not self.settings_controller.get('hide_ui.prompt_presets'):
            self.layout().addWidget(prompt_presets_collapsed)

        self.batch_widget = BatchWidget(self.settings_controller, self.api)
        if not self.settings_controller.get('hide_ui.batch'):
            self.layout().addWidget(self.batch_widget)

        self.smart_size_widget = SmartSizeWidget(self.settings_controller, self.api, self.size_dict)
        if not self.settings_controller.get('hide_ui.batch'):
            self.layout().addWidget(self.smart_size_widget)

        self.cfg_widget = CFGWidget(self.settings_controller, self.api)
        self.model_widget.register_model_changed_signal(self.prompt_widget.update_for_model)
        self.model_widget.register_model_changed_signal(self.cfg_widget.update_for_model)
        self.model_widget.register_model_changed_signal(self.denoise_widget.update_for_model)
        self.model_widget.register_architecture_changed_signal(self._on_architecture_changed)

        if not self.settings_controller.get('hide_ui.cfg'):
            self.layout().addWidget(self.cfg_widget)


        self.seed_widget = SeedWidget(self.settings_controller)
        seed_collapsed = CollapsibleWidget('Seed Details', self.seed_widget)
        if not self.settings_controller.get('hide_ui.seed'):
            self.layout().addWidget(seed_collapsed)

        self.extension_widget = ExtensionWidget(self.settings_controller, self.api)
        extension_collapsed = CollapsibleWidget('Extensions', self.extension_widget)
        if not self.settings_controller.get('hide_ui.extensions'):
            self.layout().addWidget(extension_collapsed)

        self.widgets = [self.img_in, self.color_correction, self.denoise_widget, self.model_widget, self.prompt_widget, self.prompt_presets_widget, self.batch_widget, self.cfg_widget, self.seed_widget, self.extension_widget]
        self.generate_widget = GenerateWidget(self.settings_controller, self.api, self.widgets, 'img2img', self.size_dict)
        self.layout().addWidget(self.generate_widget)

        # History Panel
        self.history_widget = HistoryWidget(self.settings_controller, self.api)
        self.history_widget.reuse_required.connect(self.reuse_parameters)
        history_collapsed = CollapsibleWidget('Generation History', self.history_widget)
        self.layout().addWidget(history_collapsed)

        self.layout().addStretch()

    def reuse_parameters(self, data: dict):
        for widget in self.widgets:
            if hasattr(widget, "set_generation_data"):
                widget.set_generation_data(data)

    def keyPressEvent(self, event):
        # Escape from a focused child (prompt field etc.) propagates here;
        # consumed only while this page's Cancel button is active.
        if event.key() == Qt.Key.Key_Escape and self.generate_widget.handle_escape():
            event.accept()
            return
        super().keyPressEvent(event)

    def cleanup(self) -> None:
        """Stop timer-owning children; safe on page switch or docker close."""
        for child in list(getattr(self, "widgets", []) or []):
            candidate = getattr(child, "cleanup", None)
            if callable(candidate):
                try:
                    candidate()
                except RuntimeError:
                    pass

    def _on_architecture_changed(self, family: ModelFamily) -> None:
        config = get_model_config(family)
        self.settings_controller.set("defaults.min_size", config.default_min_size)
        self.settings_controller.set("defaults.max_size", config.default_max_size)
        self.settings_controller.debounced_save()

    def update(self):
        super().update()
