from ..qt_compat import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QSlider,
    QSpinBox, QVBoxLayout, QWidget, Qt,
)
import copy
from ..adapters.sd_api import ConnectionState, SDAPI
from ..settings_controller import SettingsController
from ..domain.model_registry import ModelFamily, detect_model_family, get_model_config

MODELS_LOADING_TEXT = "Loading models..."
MODELS_DISCONNECTED_TEXT = "Not connected - open Settings to connect"
MODELS_EMPTY_TEXT = "No models found on the backend"

SCHEDULER_BACKEND_DEFAULT_LABEL = "Automatic (backend default)"


def is_selectable_scheduler(value, schedulers) -> bool:
    """True only for a label the backend advertised.

    The sentinel text, '', absent and garbage values all mean "let Forge Neo
    apply its own per-preset default" and must never reach the payload.
    """
    return isinstance(value, str) and bool(value) and value in schedulers


def models_status_message(loading: bool, connected: bool, model_count: int) -> str:
    """Placeholder text for the model dropdown; '' once models are listed."""
    if loading:
        return MODELS_LOADING_TEXT
    if not connected:
        return MODELS_DISCONNECTED_TEXT
    if model_count <= 0:
        return MODELS_EMPTY_TEXT
    return ""

# Select model, VAE, sampler, steps for generation
# Yes, a better name would've been nice. No, I couldn't think of one
class ModelsWidget(QWidget):
    def __init__(self, settings_controller:SettingsController, api:SDAPI, ignore_hidden=False):
        super().__init__()
        self.settings_controller = settings_controller
        self.api = api
        self.ignore_hidden = ignore_hidden
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0,0,0,0)
        self.variables = {
            'model': '',
            'vae': '',
            'enable_refiner': self.settings_controller.get('defaults.enable_refiner'),
            'refiner': '',
            'refiner_start': self.settings_controller.get('defaults.refiner_start'),
            'sampler': '',
            'sampling_steps': self.settings_controller.get('defaults.sampling_steps'),
            'scheduler': '',
        }
        self.models = []
        self.vaes = []
        self.refiners = []
        self.samplers = []
        self.schedulers = []
        self.model_changed_signals = []
        self.architecture_changed_signals = []
        self.architecture = ModelFamily.SD  # default architecture

        self.init_variables()
        self.architecture = self.detect_architecture(self.variables['model'])
        self.draw_ui()
    
    def init_variables(self):
        # Model
        self.models, self.variables['model'] = self.api.get_models_and_default()
        settings_model = self.settings_controller.get('defaults.model')
        if settings_model is not None and len(settings_model) > 0 and settings_model in self.models:
            self.variables['model'] = settings_model

        # VAE
        self.vaes, default_vae = self.api.get_vaes_and_default()
        if default_vae in self.vaes:
            self.variables['vae'] = default_vae
        else:
            # Backend default (e.g. the "Automatic" sentinel) is not a
            # selectable item; hold the combo's no-VAE state instead so the
            # widget and the payload cannot disagree.
            self.variables['vae'] = 'None'
        settings_vae = self.settings_controller.get('defaults.vae')
        if settings_vae is not None and len(settings_vae) > 0 and settings_vae in self.vaes:
            self.variables['vae'] = settings_vae

        # Refiner
        self.refiners, self.variables['refiner'] = self.api.get_refiners_and_default() # Refiners are treated the same as models right now, but could change in the future
        settings_refiner = self.settings_controller.get('defaults.refiner')
        if settings_refiner is not None and len(settings_refiner) > 0 and settings_refiner in self.refiners:
            self.variables['refiner'] = settings_refiner

        # Sampler
        self.samplers, self.variables['sampler'] = self.api.get_samplers_and_default()
        settings_sampler = self.settings_controller.get('defaults.sampler')
        if settings_sampler is not None and len(settings_sampler) > 0 and settings_sampler in self.samplers:
            self.variables['sampler'] = settings_sampler

        # Scheduler: only a backend-advertised label is selectable; '' from
        # the adapter means the backend owns the default, so the widget holds
        # the sentinel label and the payload carries no scheduler key.
        schedulers_result = self.api.get_schedulers_and_default()
        if isinstance(schedulers_result, tuple) and len(schedulers_result) == 2:
            self.schedulers, scheduler_default = schedulers_result
        else:
            self.schedulers, scheduler_default = [], ""
        self.variables['scheduler'] = (
            scheduler_default
            if is_selectable_scheduler(scheduler_default, self.schedulers)
            else SCHEDULER_BACKEND_DEFAULT_LABEL
        )
        settings_scheduler = self.settings_controller.get('defaults.scheduler')
        if settings_scheduler is not None and len(settings_scheduler) > 0 and settings_scheduler in self.schedulers:
            self.variables['scheduler'] = settings_scheduler

        # Steps
        self.variables['sampling_steps'] = self.settings_controller.get('defaults.sampling_steps')


    def draw_ui(self):
        select_form = QWidget()
        select_form.setLayout(QFormLayout())
        select_form.layout().setContentsMargins(0,0,0,0)

        # Model Select
        self.model_box = QComboBox()
        status = models_status_message(
            loading=getattr(self.api, "state", None) is ConnectionState.CONNECTING,
            connected=bool(getattr(self.api, "connected", False)),
            model_count=len(self.models),
        )
        if status:
            # QComboBox renders placeholderText only while the item list is empty.
            self.model_box.setPlaceholderText(status)
        # models, server_default_model = self.api.get_models_and_default()
        self.model_box.addItems(self.models)
        # self.model_box.setCurrentText(server_default_model)
        self.model_box.setCurrentText(self.variables['model'])
        self.model_box.setMinimumContentsLength(10) # Allows the box to be smaller than the longest item's char length
        # Inline styles removed for global QSS
        self.model_box.setMaxVisibleItems(10) # Suppose to limit the number of visible options

        # Send the changed model to settings. It'll get saved when the generate button is clicked
        self.model_box.currentTextChanged.connect(lambda: self._update_variables('model', self.model_box.currentText()))
        self.model_box.setToolTip('SD Model')

        if self.ignore_hidden or not self.settings_controller.get('hide_ui.model'):
            select_form.layout().addRow('Model', self.model_box)

        # VAE Select
        self.vae_box = QComboBox()
        # vaes, server_default_vae = self.api.get_vaes_and_default()
        if not 'None' in self.vaes:
            new_vaes = ['None']
            for vae in self.vaes:
                new_vaes.append(vae)
            self.vaes = new_vaes
        self.vae_box.addItems(self.vaes)
        self.vae_box.setCurrentText(self.variables['vae'])
        self.vae_box.setMinimumContentsLength(10) # Allows the box to be smaller than the longest item's char length
        # Inline styles removed for global QSS
        self.vae_box.setMaxVisibleItems(10) # Suppose to limit the number of visible options
        settings_vae = self.settings_controller.get('defaults.vae')
        if len(settings_vae) > 0 and settings_vae in self.vaes:
            self.vae_box.setCurrentText(settings_vae)
        else:
            self.settings_controller.set('defaults.vae', self.variables['vae'])
        # Send the changed model to settings. It'll get saved when the generate button is clicked
        self.vae_box.currentTextChanged.connect(lambda: self._update_variables('vae', self.vae_box.currentText()))
        self.vae_box.setToolTip('VAE')

        if self.ignore_hidden or not self.settings_controller.get('hide_ui.vae'):
            select_form.layout().addRow('VAE', self.vae_box)
        
        
        # Refiner enable
        self.refiner_enable = QCheckBox()
        self.refiner_enable.setChecked(self.variables['enable_refiner'])
        self.refiner_enable.stateChanged.connect(lambda: self._update_variables('enable_refiner', self.refiner_enable.isChecked()))

        # Refiner select
        self.refiner_box = QComboBox()
        # refiners, server_default_refiner = self.api.get_models_and_default()
        self.refiner_box.addItems(self.refiners)
        self.refiner_box.setCurrentText(self.variables['refiner'])
        self.refiner_box.setMinimumContentsLength(10) # Allows the box to be smaller than the longest item's char length
        # Inline styles removed for global QSS
        self.refiner_box.setMaxVisibleItems(10) # Suppose to limit the number of visible options
        self.refiner_box.currentTextChanged.connect(lambda: self._update_variables('refiner', self.refiner_box.currentText()))
        self.refiner_box.setToolTip('Refiner model')

        # Refiner start at
        refiner_start = QWidget()
        refiner_start.setLayout(QHBoxLayout())
        refiner_start.layout().setContentsMargins(0,0,0,0)
        self.refiner_start_slider = QSlider(Qt.Orientation.Horizontal)
        self.refiner_start_slider.setTickInterval(10)
        self.refiner_start_slider.setTickPosition(QSlider.TickPosition.TicksAbove)
        self.refiner_start_slider.setMinimum(0)
        self.refiner_start_slider.setMaximum(100)
        self.refiner_start_slider.setValue(int(self.variables['refiner_start'] * 100))
        self.refiner_start_slider.valueChanged.connect(lambda: self.update_slider(self.refiner_start_slider.value()))
        refiner_start.layout().addWidget(self.refiner_start_slider)
        self.refiner_start_label = QLabel()
        self.refiner_start_label.setText('%s%%' % int(self.variables['refiner_start'] * 100))
        refiner_start.layout().addWidget(self.refiner_start_label)

        if self.ignore_hidden or not self.settings_controller.get('hide_ui.refiner'):
            select_form.layout().addRow('Enable Refiner', self.refiner_enable)
            select_form.layout().addRow('Refiner', self.refiner_box)
            select_form.layout().addRow('Refiner start %', refiner_start)
        
        # Sampler and Steps
        if self.ignore_hidden or not self.settings_controller.get('hide_ui.sampler'):
            select_form.layout().addRow('Sampler', self._sampler_settings())

        # Scheduler
        if self.ignore_hidden or not self.settings_controller.get('hide_ui.scheduler'):
            select_form.layout().addRow('Scheduler', self._scheduler_settings())

        self.layout().addWidget(select_form)

    def update_slider(self, value):
        if value == 0:
            self._update_variables('refiner_start', value)
        else:
            self._update_variables('refiner_start', value / 100)
        self.refiner_start_label.setText('%s%%' % int(self.variables['refiner_start'] * 100))

    def _sampler_settings(self):
        sampler_row = QWidget()
        sampler_row.setLayout(QHBoxLayout())
        sampler_row.layout().setContentsMargins(0,0,0,0)

        self.sampler_box = QComboBox()
        # samplers, server_default_sampler = self.api.get_samplers_and_default()
        self.sampler_box.addItems(self.samplers)
        self.sampler_box.setCurrentText(self.variables['sampler'])
        self.sampler_box.setMinimumContentsLength(10) # Allows the box to be smaller than the longest item's char length
        # Inline styles removed for global QSS
        self.sampler_box.setMaxVisibleItems(10) # Suppose to limit the number of visible options
        settings_sampler = self.settings_controller.get('defaults.sampler')
        if len(settings_sampler) > 0 and settings_sampler in self.samplers:
            self.sampler_box.setCurrentIndex(self.samplers.index(settings_sampler))
        else:
            self.settings_controller.set('defaults.sampler', self.variables['sampler'])
        # Send the changed sampler to the settings. It'll get saved when the generate button is clicked
        self.sampler_box.currentTextChanged.connect(lambda: self._update_variables('sampler', self.sampler_box.currentText()))
        self.sampler_box.setToolTip('Sampling method')
        sampler_row.layout().addWidget(self.sampler_box)

        self.sampling_steps = QSpinBox()
        self.sampling_steps.setMinimum(1)
        # self.sampling_steps.setValue(self.settings_controller.get('defaults.sampling_steps'))
        self.sampling_steps.setValue(self.variables['sampling_steps'])
        self.sampling_steps.setMaximum(100)
        self.sampling_steps.valueChanged.connect(lambda: self._update_variables('sampling_steps', self.sampling_steps.value()))
        self.sampling_steps.setToolTip('Sampling steps')
        sampler_row.layout().addWidget(self.sampling_steps)

        return sampler_row

    def _scheduler_settings(self):
        self.scheduler_box = QComboBox()
        # First entry is the sentinel: selecting it sends NO scheduler key.
        self.scheduler_box.addItems([SCHEDULER_BACKEND_DEFAULT_LABEL, *self.schedulers])
        self.scheduler_box.setCurrentText(self.variables['scheduler'])
        self.scheduler_box.setMinimumContentsLength(10) # Allows the box to be smaller than the longest item's char length
        # Inline styles removed for global QSS
        self.scheduler_box.setMaxVisibleItems(10) # Suppose to limit the number of visible options
        settings_scheduler = self.settings_controller.get('defaults.scheduler')
        if settings_scheduler is not None and len(settings_scheduler) > 0 and settings_scheduler in self.schedulers:
            self.scheduler_box.setCurrentText(settings_scheduler)
        else:
            self.settings_controller.set('defaults.scheduler', self.variables['scheduler'])
        # Send the changed scheduler to the settings. It'll get saved when the generate button is clicked
        self.scheduler_box.currentTextChanged.connect(lambda: self._update_variables('scheduler', self.scheduler_box.currentText()))
        self.scheduler_box.setToolTip('Schedule type')
        return self.scheduler_box
    
    def _update_variables(self, key, value):
        self.variables[key] = value
        if key == 'model':
            for signal in self.model_changed_signals:
                signal(value)
            new_arch = self.detect_architecture(value)
            if new_arch != self.architecture:
                self.architecture = new_arch
                for signal in self.architecture_changed_signals:
                    signal(self.architecture)

    def register_model_changed_signal(self, signal):
        self.model_changed_signals.append(signal)

    def register_architecture_changed_signal(self, signal):
        self.architecture_changed_signals.append(signal)

    def detect_architecture(self, model_name):
        """Detect model architecture from model name using centralized registry.
        Returns ModelFamily enum value.
        """
        return detect_model_family(model_name)

    def set_generation_data(self, data: dict) -> None:
        # History reuse: restore every field the generate flow reads via
        # get_generation_data(). Values are deep-copied so later mutation of
        # the source history entry cannot corrupt live widget state.
        # Never triggers a generation as a side effect.
        if not isinstance(data, dict):
            return
        model_name = data.get("model") or data.get("sd_model_checkpoint")
        if model_name and isinstance(model_name, str):
            self._update_variables('model', copy.deepcopy(model_name))
            box = getattr(self, 'model_box', None)
            if box is not None:
                try:
                    index = box.findText(model_name)
                except AttributeError:
                    index = -1
                if index is not None and index >= 0:
                    box.setCurrentIndex(index)
        vae_name = data.get("vae") or data.get("sd_vae")
        if vae_name and isinstance(vae_name, str):
            self._update_variables('vae', copy.deepcopy(vae_name))
            box = getattr(self, 'vae_box', None)
            if box is not None:
                try:
                    if vae_name in getattr(self, 'vaes', [vae_name]):
                        box.setCurrentText(vae_name)
                except AttributeError:
                    pass
        sampler_name = data.get("sampler") or data.get("sampler_name")
        if sampler_name and isinstance(sampler_name, str):
            self._update_variables('sampler', copy.deepcopy(sampler_name))
            box = getattr(self, 'sampler_box', None)
            if box is not None:
                try:
                    if sampler_name in getattr(self, 'samplers', [sampler_name]):
                        box.setCurrentText(sampler_name)
                except AttributeError:
                    pass
        scheduler_value = data.get("scheduler")
        if is_selectable_scheduler(scheduler_value, getattr(self, 'schedulers', [])):
            restored_scheduler = copy.deepcopy(scheduler_value)
        else:
            # Absent/empty = that generation used the backend default;
            # unknown values must never be replayed - degrade to the sentinel.
            restored_scheduler = SCHEDULER_BACKEND_DEFAULT_LABEL
        self._update_variables('scheduler', restored_scheduler)
        box = getattr(self, 'scheduler_box', None)
        if box is not None:
            try:
                box.setCurrentText(restored_scheduler)
            except AttributeError:
                pass
        steps = data.get("sampling_steps", data.get("steps"))
        if steps is not None:
            try:
                steps = int(steps)
            except (TypeError, ValueError):
                steps = None
            if steps is not None:
                self._update_variables('sampling_steps', steps)
                spin = getattr(self, 'sampling_steps', None)
                if spin is not None and not isinstance(spin, int):
                    try:
                        spin.setValue(steps)
                    except AttributeError:
                        pass
        if "enable_refiner" in data:
            enable_refiner = bool(copy.deepcopy(data["enable_refiner"]))
            self._update_variables('enable_refiner', enable_refiner)
            check = getattr(self, 'refiner_enable', None)
            if check is not None:
                try:
                    check.setChecked(enable_refiner)
                except AttributeError:
                    pass
        refiner_name = data.get("refiner")
        if refiner_name and isinstance(refiner_name, str):
            self._update_variables('refiner', copy.deepcopy(refiner_name))
            box = getattr(self, 'refiner_box', None)
            if box is not None:
                try:
                    if refiner_name in getattr(self, 'refiners', [refiner_name]):
                        box.setCurrentText(refiner_name)
                except AttributeError:
                    pass
        refiner_start = data.get("refiner_start")
        if refiner_start is not None:
            try:
                refiner_start = float(refiner_start)
            except (TypeError, ValueError):
                refiner_start = None
            if refiner_start is not None:
                self._update_variables('refiner_start', refiner_start)
                slider = getattr(self, 'refiner_start_slider', None)
                if slider is not None:
                    try:
                        slider.setValue(int(refiner_start * 100))
                    except AttributeError:
                        pass
                label = getattr(self, 'refiner_start_label', None)
                if label is not None:
                    try:
                        label.setText('%s%%' % int(refiner_start * 100))
                    except AttributeError:
                        pass

    def save_settings(self):
        self.settings_controller.set('defaults.model', self.variables['model'])
        self.settings_controller.set('defaults.vae', self.variables['vae'])
        self.settings_controller.set('defaults.sampler', self.variables['sampler'])
        self.settings_controller.set('defaults.scheduler', self.variables.get('scheduler', ''))
        self.settings_controller.set('defaults.sampling_steps', self.variables['sampling_steps'])
        self.settings_controller.set('defaults.enable_refiner', self.variables['enable_refiner'])
        self.settings_controller.set('defaults.refiner', self.variables['refiner'])
        self.settings_controller.set('defaults.refiner_start', self.variables['refiner_start'])
        self.settings_controller.save()
    
    def get_generation_data(self):
        self.save_settings()
        self.settings_controller.save()
        data = {**self.variables}
        if not is_selectable_scheduler(data.get('scheduler'), getattr(self, 'schedulers', [])):
            # No scheduler key at all is what lets Forge Neo apply its own
            # per-preset default (sd/xl=Automatic, flux=Beta, krea=Simple).
            data.pop('scheduler', None)
        if not data['enable_refiner']:
            # Remove the refiner stuff if it's not enabled
            # data['refiner'] = 'none'
            # data['refiner_start'] = 1.0
            data.pop('refiner')
            data.pop('refiner_start')
        data.pop('enable_refiner')
        return data