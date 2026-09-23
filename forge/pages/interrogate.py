from ..qt_compat import QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from ..adapters.sd_api import SDAPI
from ..settings_controller import SettingsController
from ..adapters.krita_adapter import KritaAdapter
from ..widgets import (
    InterrogateWidget,
    InterrogateModelWidget,
    ImageInWidget,
    PromptWidget,
)


class InterrogatePage(QWidget):
    def __init__(self, settings_controller: SettingsController, api: SDAPI):
        super().__init__()
        self.settings_controller = settings_controller
        self.api = api
        self.kc = KritaAdapter()
        self.size_dict = {"x": 0, "y": 0, "w": 0, "h": 0}
        self.setLayout(QVBoxLayout())

        self.img_in = ImageInWidget(
            self.settings_controller, self.api, "img2img_img", self.size_dict
        )
        self.layout().addWidget(self.img_in)

        prompt_mode = self.settings_controller.get("interrogate.prompt_mode")

        # Default for fresh installs lacking the key; get_prompt_mode() must never be None.
        if not prompt_mode:
            prompt_mode = "img2img"
            self.settings_controller.set("interrogate.prompt_mode", prompt_mode)

        self.prompt_widget = PromptWidget(
            self.settings_controller,
            self.api,
            prompt_mode,
        )
        self.layout().addWidget(self.prompt_widget)

        self.interrogate_model_widget = InterrogateModelWidget(
            self.settings_controller, self.api, self.size_dict
        )
        self.layout().addWidget(self.interrogate_model_widget)

        self.interrogate_widget = InterrogateWidget(
            self.settings_controller,
            self.api,
            self.interrogate_model_widget,
            self.prompt_widget,
            self.img_in,
        )
        self.layout().addWidget(self.interrogate_widget)

        caption_mode_row = QWidget()
        caption_mode_row.setLayout(QHBoxLayout())
        caption_mode_row.layout().setContentsMargins(0, 0, 0, 0)
        caption_mode_row.layout().addWidget(QLabel("Caption inserts:"))
        self.caption_mode_box = QComboBox()
        self.caption_mode_box.addItems(["replace", "append", "prepend"])
        self.caption_mode_box.setCurrentText(
            self.settings_controller.get("interrogate.caption_mode", "replace")
        )
        self.caption_mode_box.setToolTip(
            "How the interrogated caption combines with the current prompt"
        )
        self.caption_mode_box.currentTextChanged.connect(
            lambda: self._update_caption_mode(self.caption_mode_box.currentText())
        )
        caption_mode_row.layout().addWidget(self.caption_mode_box)
        self.layout().addWidget(caption_mode_row)

        self.layout().addStretch()  # Takes up the remaining space at the bottom, allowing everything to be pushed to the top

    def _update_caption_mode(self, mode):
        if mode not in ("replace", "append", "prepend"):
            return
        self.settings_controller.set("interrogate.caption_mode", mode)
        self.settings_controller.save()

    def update(self):
        super().update()
