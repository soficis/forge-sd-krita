from ..qt_compat import QComboBox, QFormLayout, QLabel, QVBoxLayout, QWidget
from ..adapters.sd_api import SDAPI
from ..settings_controller import SettingsController
from ..adapters.krita_adapter import KritaAdapter


CLIP_DOWNLOAD_HINT = (
    "If interrogation returns nothing, the CLIP model download may have "
    "failed on the backend - check the backend console and retry."
)

DEEPDANBOORU_INFO = (
    "DeepDanbooru is not installed on the backend, so only CLIP is offered. "
    "Install DeepDanbooru on the backend to enable anime-style tagging."
)


def deepdanbooru_available(api: SDAPI) -> bool:
    """Return True when the backend exposes DeepDanbooru options."""
    default_settings = getattr(api, "default_settings", None) or {}
    return bool(default_settings.get("deepbooru_sort_alpha"))


class InterrogateModelWidget(QWidget):
    def __init__(
        self,
        settings_controller: SettingsController,
        api: SDAPI,
        size_dict: dict,
        hide_prompt_mode: bool = False,
    ):
        super().__init__()
        self.settings_controller = settings_controller
        self.api = api
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.kc = KritaAdapter()
        self.size_dict = size_dict

        self.hide_prompt_mode = hide_prompt_mode

        self.variables = {
            "model": "",
            "prompt_mode": self.settings_controller.get(
                "interrogate.prompt_mode"
            ),  # txt2img / img2img / inpaint / adetailer
        }

        self.models = ["clip"]
        self.clip_hint_text = CLIP_DOWNLOAD_HINT

        # check if deepdanbooru is installed
        self.deepdanbooru_available = deepdanbooru_available(self.api)
        if self.deepdanbooru_available:
            self.models.append("deepdanbooru")
            self.model_status_text = ""
        else:
            self.model_status_text = DEEPDANBOORU_INFO

        self.init_variables()

        self.draw_ui()

    def init_variables(self):
        if self.settings_controller.get("interrogate.model"):
            self.variables["model"] = self.settings_controller.get("interrogate.model")

    def draw_ui(self):
        select_form = QWidget()
        select_form.setLayout(QFormLayout())
        select_form.layout().setContentsMargins(0, 0, 0, 0)

        if not self.settings_controller.get("hide_ui.interrogate_model"):
            self.model_box = QComboBox()
            self.model_box.addItems(self.models)
            self.model_box.setCurrentText(self.variables["model"])
            # Inline styles removed for global QSS
            self.model_box.setMaxVisibleItems(10)
            self.model_box.currentTextChanged.connect(
                lambda: self._update_variables("model", self.model_box.currentText())
            )
            self.model_box.setToolTip("Interrogate Model")

            select_form.layout().addRow("Model", self.model_box)

        if self.model_status_text:
            self.model_status_label = QLabel(self.model_status_text)
            self.model_status_label.setWordWrap(True)
            self.layout().addWidget(self.model_status_label)

        self.clip_hint_label = QLabel(self.clip_hint_text)
        self.clip_hint_label.setWordWrap(True)
        self.layout().addWidget(self.clip_hint_label)

        if not self.hide_prompt_mode:
            self.prompt_mode_box = QComboBox()
            self.prompt_mode_box.addItems(
                ["txt2img", "img2img", "inpaint", "adetailer"]
            )
            self.prompt_mode_box.setCurrentText(self.variables["prompt_mode"])
            # Inline styles removed for global QSS
            self.prompt_mode_box.setMaxVisibleItems(10)
            self.prompt_mode_box.currentTextChanged.connect(
                lambda: self._update_variables(
                    "prompt_mode", self.prompt_mode_box.currentText()
                )
            )
            self.prompt_mode_box.setToolTip(
                "Interrogate Prompt Mode (sync prompt with txt2img / img2img / inpaint / adetailer)"
            )

            select_form.layout().addRow("Prompt Mode", self.prompt_mode_box)

        self.layout().addWidget(select_form)

    def get_model(self):
        return self.variables["model"]

    def get_prompt_mode(self):
        return self.variables["prompt_mode"]

    def _update_variables(self, key, value):
        self.variables[key] = value
        # Save-on-change matches the app-wide pattern.
        self.save_settings()

    def save_settings(self):
        self.settings_controller.set("interrogate.model", self.variables["model"])
        self.settings_controller.set(
            "interrogate.prompt_mode", self.variables["prompt_mode"]
        )
        self.settings_controller.save()
