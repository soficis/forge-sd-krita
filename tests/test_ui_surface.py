"""Todo 23: tests-after for pre-existing critical UI surface.

Covers (in todo 7 priority order):
1. forge/widgets/models.py — model_changed/architecture_changed signal fan-out
2. forge/widgets/generate.py — turbo-LoRA detect + queue sequential logic
3. forge/domain/payload_builder.py — gaps not already covered
4. forge/widgets/history.py — pagination/search pure logic
5. forge/adapters/krita_adapter.py — pure helpers (bounds math, base64)

Widget modules are loaded FRESH under stub-Qt real classes (pattern copied
from tests/test_controlnet_dict_guards.py): subclassing conftest's MagicMock
Qt does NOT work (produces mocks, not classes). Unbound methods are then
driven with __new__ instances / SimpleNamespace selves so the tests assert
real logic, not mocks.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from forge.domain.model_registry import ModelFamily
from forge.domain.payload_builder import build_api_payload


# ---------------------------------------------------------------------------
# Fresh stub-Qt module loader (real classes, not mocks)
# ---------------------------------------------------------------------------

_QT_NAMES = [
    "Qt", "QWidget", "QVBoxLayout", "QHBoxLayout", "QFormLayout",
    "QGridLayout", "QLabel", "QComboBox", "QPushButton", "QCheckBox",
    "QTabWidget", "QGroupBox", "QSlider", "QSpinBox", "QDoubleSpinBox",
    "QPlainTextEdit", "QTextEdit", "QLineEdit", "QScrollArea", "QColor",
    "QPainter", "QByteArray", "QBuffer", "QImage", "QIODevice", "QObject",
    "QThread", "QTimer", "QProgressBar", "pyqtSignal", "QSize", "QIcon",
    "QPixmap", "QPointF", "qAlpha", "qRgb",
]


def _load_real(relpath: str, mod_name: str):
    """Import a forge module fresh with stub-Qt classes; return it."""
    _dummy = MagicMock()

    class _Meta(type):
        def __getattr__(cls, name):
            if name.startswith("__"):
                raise AttributeError(name)
            return _dummy

    class _StubBase(metaclass=_Meta):
        def __init__(self, *args, **kwargs):
            pass

        def __getattr__(self, name):
            if name.startswith("__"):
                raise AttributeError(name)
            return _dummy

    stub = types.ModuleType("forge.qt_compat")
    for _name in _QT_NAMES:
        setattr(stub, _name, _Meta(_name, (_StubBase,), {}))
    stub.__all__ = list(_QT_NAMES)

    def __getattr__(name):
        if name.startswith("__"):
            raise AttributeError(name)
        cls = _Meta(name, (_StubBase,), {})
        setattr(stub, name, cls)
        return cls

    stub.__getattr__ = __getattr__

    pre_keys = set(sys.modules)
    old = sys.modules.get("forge.qt_compat")
    sys.modules["forge.qt_compat"] = stub
    try:
        path = pathlib.Path(__file__).resolve().parent.parent / relpath
        spec = importlib.util.spec_from_file_location(mod_name, str(path))
        mod = importlib.util.module_from_spec(spec)
        mod.__package__ = "forge.widgets"
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        if old is not None:
            sys.modules["forge.qt_compat"] = old
        else:
            sys.modules.pop("forge.qt_compat", None)
        for _key in [k for k in sys.modules if k not in pre_keys
                     and k != mod_name]:
            sys.modules.pop(_key, None)


models_mod = _load_real("forge/widgets/models.py", "forge.widgets.models_task23")
generate_mod = _load_real("forge/widgets/generate.py", "forge.widgets.generate_task23")
history_mod = _load_real("forge/widgets/history.py", "forge.widgets.history_task23")

from forge.adapters import krita_adapter as ka_mod


# ---------------------------------------------------------------------------
# Small fakes
# ---------------------------------------------------------------------------

class _Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))

    def __len__(self):
        return len(self.calls)


class _FakeLabel:
    def __init__(self):
        self.text = ""

    def setText(self, text):
        self.text = text


class _FakeButton:
    def __init__(self):
        self.hidden = False
        self.enabled = True
        self.text = ""

    def setHidden(self, hidden):
        self.hidden = hidden

    def setEnabled(self, enabled):
        self.enabled = enabled

    def setText(self, text):
        self.text = text


class _FakeBar:
    def __init__(self):
        self.value = -1
        self.hidden = False

    def setValue(self, value):
        self.value = value

    def setHidden(self, hidden):
        self.hidden = hidden


# ---------------------------------------------------------------------------
# 1. models.py — signal fan-out
# ---------------------------------------------------------------------------

def _models_stub(**overrides):
    stub = models_mod.ModelsWidget.__new__(models_mod.ModelsWidget)
    stub.variables = {"model": "dreamshaper", "vae": "", "sampler": "",
                      "sampling_steps": 20}
    stub.model_changed_signals = []
    stub.architecture_changed_signals = []
    stub.architecture = ModelFamily.SD
    for key, value in overrides.items():
        setattr(stub, key, value)
    return stub


class TestModelsSignals:
    def test_really_real_classes(self):
        assert isinstance(models_mod.ModelsWidget, type)

    def test_model_signal_fires_with_value(self):
        stub = _models_stub()
        rec = _Recorder()
        stub.model_changed_signals.append(rec)
        models_mod.ModelsWidget._update_variables(stub, "model", "dreamshaper")
        assert rec.calls == [(("dreamshaper",), {})]
        assert stub.variables["model"] == "dreamshaper"

    def test_multiple_model_signals_all_fire(self):
        stub = _models_stub()
        rec1, rec2 = _Recorder(), _Recorder()
        stub.model_changed_signals.extend([rec1, rec2])
        models_mod.ModelsWidget._update_variables(stub, "model", "dreamshaper")
        assert len(rec1) == 1 and len(rec2) == 1

    def test_architecture_signal_on_family_change(self):
        stub = _models_stub()
        arch_rec = _Recorder()
        stub.architecture_changed_signals.append(arch_rec)
        models_mod.ModelsWidget._update_variables(stub, "model", "flux-dev")
        assert stub.architecture == ModelFamily.FLUX
        assert arch_rec.calls == [((ModelFamily.FLUX,), {})]

    def test_no_architecture_signal_on_same_family(self):
        stub = _models_stub()
        arch_rec = _Recorder()
        model_rec = _Recorder()
        stub.architecture_changed_signals.append(arch_rec)
        stub.model_changed_signals.append(model_rec)
        models_mod.ModelsWidget._update_variables(stub, "model", "dreamshaper-xl")
        assert len(model_rec) == 1
        assert len(arch_rec) == 0
        assert stub.architecture == ModelFamily.SD

    def test_non_model_key_fires_no_signals(self):
        stub = _models_stub()
        model_rec, arch_rec = _Recorder(), _Recorder()
        stub.model_changed_signals.append(model_rec)
        stub.architecture_changed_signals.append(arch_rec)
        models_mod.ModelsWidget._update_variables(stub, "sampling_steps", 30)
        assert stub.variables["sampling_steps"] == 30
        assert len(model_rec) == 0 and len(arch_rec) == 0

    def test_register_helpers_append(self):
        stub = _models_stub()
        cb1, cb2 = _Recorder(), _Recorder()
        models_mod.ModelsWidget.register_model_changed_signal(stub, cb1)
        models_mod.ModelsWidget.register_architecture_changed_signal(stub, cb2)
        assert stub.model_changed_signals == [cb1]
        assert stub.architecture_changed_signals == [cb2]

    def test_detect_architecture_known_families(self):
        stub = _models_stub()
        detect = models_mod.ModelsWidget.detect_architecture
        assert detect(stub, "flux-dev") == ModelFamily.FLUX
        assert detect(stub, "something-sdxl") == ModelFamily.SDXL
        assert detect(stub, "dreamshaper") == ModelFamily.SD

    def test_set_generation_data_ignores_nondict(self):
        stub = _models_stub()
        models_mod.ModelsWidget.set_generation_data(stub, None)
        models_mod.ModelsWidget.set_generation_data(stub, "junk")
        assert stub.variables["model"] == "dreamshaper"

    def test_set_generation_data_restores_fields(self):
        stub = _models_stub()
        stub.vaes = ["vaeA"]
        stub.samplers = ["Euler a"]
        stub.model_box = SimpleNamespace(findText=lambda t: 2,
                                         setCurrentIndex=_Recorder())
        stub.vae_box = SimpleNamespace(setCurrentText=_Recorder())
        stub.sampler_box = SimpleNamespace(setCurrentText=_Recorder())
        models_mod.ModelsWidget.set_generation_data(stub, {
            "model": "flux-dev",
            "vae": "vaeA",
            "sampler": "Euler a",
            "sampling_steps": "25",
        })
        assert stub.variables["model"] == "flux-dev"
        assert stub.variables["vae"] == "vaeA"
        assert stub.variables["sampler"] == "Euler a"
        assert stub.variables["sampling_steps"] == 25
        assert stub.architecture == ModelFamily.FLUX

    def test_set_generation_data_bad_steps_ignored(self):
        stub = _models_stub()
        models_mod.ModelsWidget.set_generation_data(stub, {"sampling_steps": "junk"})
        assert stub.variables["sampling_steps"] == 20

    def test_get_generation_data_drops_disabled_refiner(self):
        stub = _models_stub()
        stub.variables.update({"enable_refiner": False, "refiner": "r",
                               "refiner_start": 0.5})
        stub.settings_controller = SimpleNamespace(set=_Recorder(), save=_Recorder())
        data = models_mod.ModelsWidget.get_generation_data(stub)
        assert "refiner" not in data and "refiner_start" not in data
        assert "enable_refiner" not in data
        assert data["model"] == "dreamshaper"

    def test_update_slider_zero_vs_scaled(self):
        stub = _models_stub()
        stub.variables["refiner_start"] = 0.5
        stub.refiner_start_label = _FakeLabel()
        models_mod.ModelsWidget.update_slider(stub, 0)
        assert stub.variables["refiner_start"] == 0
        assert stub.refiner_start_label.text == "0%"
        models_mod.ModelsWidget.update_slider(stub, 80)
        assert stub.variables["refiner_start"] == pytest.approx(0.8)
        assert stub.refiner_start_label.text == "80%"


# ---------------------------------------------------------------------------
# 2. generate.py — turbo-LoRA detect + queue sequential logic
# ---------------------------------------------------------------------------

def _gen_self(**overrides):
    stub = SimpleNamespace(
        api=SimpleNamespace(defaults={"model": "dreamshaper"}, samplers=[]),
    )
    # Bind real helpers so unbound-method calls that delegate via self.*
    # exercise production code instead of raising AttributeError.
    stub._detect_turbo_lora = generate_mod.GenerateWidget._detect_turbo_lora.__get__(stub)
    stub.GENERATION_ENDPOINT_BY_MODE = (
        generate_mod.GenerateWidget.GENERATION_ENDPOINT_BY_MODE)
    for key, value in overrides.items():
        setattr(stub, key, value)
    return stub


class TestTurboLoraDetect:
    def test_really_real_classes(self):
        assert isinstance(generate_mod.GenerateWidget, type)

    @pytest.mark.parametrize("prompt", [
        "a cat <lora:turbo_v1:0.8>",
        "a cat <lora:TurboMix:1.0>",
        "photo <lora:hyper-sd_v1:0.7>",
        "photo <lora:hyper_sd_v1:0.7>",
        "art <lora:lcm_lora:0.9>",
        "art <lora:alimama_lightning:1.0>",
    ])
    def test_turbo_patterns_detected(self, prompt):
        stub = _gen_self()
        assert generate_mod.GenerateWidget._detect_turbo_lora(stub, prompt) is True

    @pytest.mark.parametrize("prompt", [
        "",
        "a cat, masterpiece",
        "turbo charged car",  # keyword without <lora: tag must NOT match
        "hyper-sd is great",
        "<lora:detail_tweaker:0.8>",
        "<embedding:turbo:1.0>",  # wrong tag type must NOT match
    ])
    def test_non_turbo_not_detected(self, prompt):
        stub = _gen_self()
        assert generate_mod.GenerateWidget._detect_turbo_lora(stub, prompt) is False


class TestFluxAdjustments:
    def test_flux_sampler_gets_forge_prefix(self):
        stub = _gen_self(api=SimpleNamespace(
            defaults={"model": "flux-dev"},
            samplers=[{"name": "[Forge] Euler"}, {"name": "Euler"}]))
        data = {"sampler": "Euler", "steps": 20, "prompt": "cat"}
        generate_mod.GenerateWidget._apply_flux_adjustments(stub, data)
        assert data["sampler"] == "[Forge] Euler"

    def test_flux_sampler_already_prefixed_untouched(self):
        stub = _gen_self(api=SimpleNamespace(
            defaults={"model": "flux-dev"},
            samplers=[{"name": "[Forge] Euler"}]))
        data = {"sampler": "[Forge] Euler", "steps": 20, "prompt": "cat"}
        generate_mod.GenerateWidget._apply_flux_adjustments(stub, data)
        assert data["sampler"] == "[Forge] Euler"

    def test_non_flux_sampler_untouched(self):
        stub = _gen_self()
        data = {"sampler": "Euler a", "steps": 20, "prompt": "cat"}
        generate_mod.GenerateWidget._apply_flux_adjustments(stub, data)
        assert data["sampler"] == "Euler a"
        assert data["steps"] == 20

    def test_turbo_lora_clamps_steps(self):
        stub = _gen_self()
        data = {"steps": 20, "prompt": "cat <lora:turbo_v1:0.8>"}
        generate_mod.GenerateWidget._apply_flux_adjustments(stub, data)
        assert data["steps"] == 8

    def test_turbo_lora_keeps_smaller_steps(self):
        stub = _gen_self()
        data = {"steps": 4, "prompt": "cat <lora:lcm_lora:0.9>"}
        generate_mod.GenerateWidget._apply_flux_adjustments(stub, data)
        assert data["steps"] == 4

    def test_turbo_lora_missing_steps_defaults_to_8(self):
        stub = _gen_self()
        data = {"prompt": "cat <lora:alimama_xl:1.0>"}
        generate_mod.GenerateWidget._apply_flux_adjustments(stub, data)
        assert data["steps"] == 8


class TestQueueLogic:
    def _queue_self(self, queued=0, generating=False):
        stub = SimpleNamespace(
            job_queue=[object() for _ in range(queued)],
            is_generating=generating,
            queue_status_label=_FakeLabel(),
            clear_queue_btn=_FakeButton(),
        )
        stub._update_queue_status = (
            generate_mod.GenerateWidget._update_queue_status.__get__(stub))
        return stub

    def test_status_idle(self):
        stub = self._queue_self(queued=2)
        generate_mod.GenerateWidget._update_queue_status(stub)
        assert stub.queue_status_label.text == "Queue: 2 jobs"
        assert stub.clear_queue_btn.hidden is False

    def test_status_idle_empty_hides_clear(self):
        stub = self._queue_self(queued=0)
        generate_mod.GenerateWidget._update_queue_status(stub)
        assert stub.queue_status_label.text == "Queue: 0 jobs"
        assert stub.clear_queue_btn.hidden is True

    def test_status_generating_with_backlog(self):
        stub = self._queue_self(queued=3, generating=True)
        generate_mod.GenerateWidget._update_queue_status(stub)
        assert stub.queue_status_label.text == "Generating... Queue: 3 jobs"

    def test_status_generating_no_backlog(self):
        stub = self._queue_self(queued=0, generating=True)
        generate_mod.GenerateWidget._update_queue_status(stub)
        assert stub.queue_status_label.text == "Generating..."

    def test_clear_queue_keeps_current_job(self):
        stub = self._queue_self(queued=2)
        generate_mod.GenerateWidget._clear_queue(stub)
        assert stub.job_queue == []
        assert stub.queue_status_label.text == "Queue: 0 jobs"

    def test_endpoint_map(self):
        assert generate_mod.GenerateWidget.GENERATION_ENDPOINT_BY_MODE == {
            "txt2img": "txt2img", "img2img": "img2img", "inpaint": "img2img",
        }

    def test_threadable_run_dispatches_endpoint(self):
        stub = _gen_self(api=SimpleNamespace(txt2img=_Recorder()),
                         results=None, mode="txt2img")
        generate_mod.GenerateWidget.threadable_run(stub, {"prompt": "x"})
        assert len(stub.api.txt2img) == 1

    def test_threadable_run_unsupported_mode_raises(self):
        stub = _gen_self(api=SimpleNamespace(), results=None, mode="upscale")
        with pytest.raises(RuntimeError, match="Unsupported generation mode"):
            generate_mod.GenerateWidget.threadable_run(stub, {})

    def test_generate_enqueues_and_starts_when_idle(self):
        started = _Recorder()
        kc = SimpleNamespace(get_selection_bounds=lambda: (1, 2, 64, 64),
                             get_canvas_size=lambda: (512, 512))
        settings = {"defaults.min_size": None, "defaults.max_size": None,
                    "defaults.enable_max_size": False,
                    "server.save_imgs": False}
        stub = SimpleNamespace(
            settings_controller=SimpleNamespace(get=settings.get),
            api=SimpleNamespace(defaults={"model": "dreamshaper"}, samplers=[]),
            list_of_widgets=[SimpleNamespace(
                get_generation_data=lambda: {"prompt": "a cat"})],
            mode="txt2img", size_dict={"x": 0, "y": 0, "w": 0, "h": 0},
            kc=kc, job_queue=[], is_generating=False,
            queue_status_label=_FakeLabel(), clear_queue_btn=_FakeButton(),
            _restore_hidden_layers=lambda: None,
            _update_queue_status=lambda: None,
            _start_next_job=lambda: started(),
        )
        stub._resolve_generation_bounds = (
            generate_mod.GenerateWidget._resolve_generation_bounds.__get__(stub))
        stub._apply_flux_adjustments = (
            generate_mod.GenerateWidget._apply_flux_adjustments.__get__(stub))
        stub._detect_turbo_lora = (
            generate_mod.GenerateWidget._detect_turbo_lora.__get__(stub))
        generate_mod.GenerateWidget.generate(stub)
        assert len(stub.job_queue) == 1
        job = stub.job_queue[0]
        assert (job.x, job.y, job.width, job.height) == (1, 2, 64, 64)
        assert job.data["prompt"] == "a cat"
        assert len(started) == 1

    def test_generate_empty_prompt_rejected(self):
        started = _Recorder()
        kc = SimpleNamespace(get_selection_bounds=lambda: (0, 0, 0, 0),
                             get_canvas_size=lambda: (512, 512))
        settings = {"defaults.min_size": None, "defaults.max_size": None,
                    "defaults.enable_max_size": False,
                    "server.save_imgs": False}
        stub = SimpleNamespace(
            settings_controller=SimpleNamespace(get=settings.get),
            api=SimpleNamespace(defaults={"model": "dreamshaper"}, samplers=[]),
            list_of_widgets=[SimpleNamespace(get_generation_data=lambda: {})],
            mode="txt2img", size_dict={"x": 0, "y": 0, "w": 0, "h": 0},
            kc=kc, job_queue=[], is_generating=False,
            queue_status_label=_FakeLabel(), clear_queue_btn=_FakeButton(),
            _restore_hidden_layers=lambda: None,
            _update_queue_status=lambda: None,
            _start_next_job=lambda: started(),
        )
        stub._resolve_generation_bounds = (
            generate_mod.GenerateWidget._resolve_generation_bounds.__get__(stub))
        stub._apply_flux_adjustments = (
            generate_mod.GenerateWidget._apply_flux_adjustments.__get__(stub))
        stub._detect_turbo_lora = (
            generate_mod.GenerateWidget._detect_turbo_lora.__get__(stub))
        generate_mod.GenerateWidget.generate(stub)
        assert stub.job_queue == []
        assert stub.queue_status_label.text.startswith("Cannot generate:")
        assert len(started) == 0

    def test_threadable_return_chains_next_job(self):
        started = _Recorder()
        stub = SimpleNamespace(
            results=None, debug=False, current_job=object(),
            job_queue=[object()], abort=False,
            generate_btn=_FakeButton(), progress_bar=_FakeBar(),
            queue_status_label=_FakeLabel(), clear_queue_btn=_FakeButton(),
            kc=SimpleNamespace(delete_preview_layer=lambda: None),
            progress_timer=None, is_generating=True,
            list_of_widgets=[], update=lambda: None,
            update_progress_bar=lambda v: None,
            _restore_hidden_layers=lambda: None,
            _update_queue_status=lambda: None,
            _start_next_job=lambda: started(),
        )
        stub._stop_generation_loop = lambda: setattr(stub, "is_generating", False)
        generate_mod.GenerateWidget.threadable_return(stub, 0, 0, 64, 64, {})
        assert stub.current_job is None
        assert len(started) == 1

    def test_resolve_bounds_prefers_size_dict(self):
        stub = SimpleNamespace(size_dict={"x": 1, "y": 2, "w": 64, "h": 64},
                               kc=MagicMock())
        assert generate_mod.GenerateWidget._resolve_generation_bounds(stub) == (1, 2, 64, 64)
        stub.kc.get_selection_bounds.assert_not_called()

    def test_resolve_bounds_falls_back_to_canvas(self):
        kc = SimpleNamespace(get_selection_bounds=lambda: (0, 0, 0, 0),
                             get_canvas_size=lambda: (512, 256))
        stub = SimpleNamespace(size_dict={"x": 0, "y": 0, "w": 0, "h": 0}, kc=kc)
        assert generate_mod.GenerateWidget._resolve_generation_bounds(stub) == (0, 0, 512, 256)


# ---------------------------------------------------------------------------
# 3. payload_builder gaps
# ---------------------------------------------------------------------------

class TestPayloadGaps:
    def test_zimage_cfg_fixed_forced_over_user_value(self):
        result = build_api_payload({"model": "z-image-turbo", "cfg_scale": 7})
        assert result["cfg_scale"] == 1.0
        assert result["override_settings"]["forge_preset"] == "zit"
        assert "scheduler" not in result

    def test_zimage_shift_applied(self):
        result = build_api_payload({"model": "z-image-turbo"})
        assert result["shift"] == 9.0

    def test_anima_shift_and_sampler_defaults(self):
        result = build_api_payload({"model": "wai-anima-v1"})
        assert result["override_settings"]["forge_preset"] == "anima"
        assert result["sampler_name"] == "ER SDE"
        assert "scheduler" not in result
        assert result["shift"] == 3.0

    def test_krea2_cfg_defaults_and_user_preserved(self):
        result = build_api_payload({"model": "krea2-raw"})
        assert result["override_settings"]["forge_preset"] == "krea"
        assert result["cfg_scale"] == 4.5
        result = build_api_payload({"model": "krea2-raw", "cfg_scale": 6.0})
        assert result["cfg_scale"] == 6.0

    def test_qwen_modules_include_vae(self):
        result = build_api_payload({"model": "qwen-image-v1"})
        assert result["override_settings"]["forge_preset"] == "qwen"
        modules = result["override_settings"]["forge_additional_modules"]
        assert "qwen_image_vae.safetensors" in modules

    def test_wan_adds_no_modules(self):
        result = build_api_payload({"model": "wan-v1"})
        assert result["override_settings"]["forge_preset"] == "wan"
        assert "forge_additional_modules" not in result["override_settings"]

    def test_flux_distilled_cfg_default_and_preserved(self):
        result = build_api_payload({"model": "flux-dev"})
        assert result["distilled_cfg_scale"] == 3.5
        result = build_api_payload({"model": "flux-dev", "distilled_cfg_scale": 2.0})
        assert result["distilled_cfg_scale"] == 2.0

    def test_family_detected_from_override_checkpoint(self):
        result = build_api_payload(
            {"override_settings": {"sd_model_checkpoint": "flux-dev"}})
        assert result["override_settings"]["forge_preset"] == "flux"

    def test_family_detected_from_sd_checkpoint_key(self):
        result = build_api_payload({"sd_model_checkpoint": "z-image-turbo"})
        assert result["override_settings"]["forge_preset"] == "zit"

    def test_empty_modules_list_gets_autopopulated(self):
        result = build_api_payload({"model": "flux-dev",
                                    "override_settings": {
                                        "forge_additional_modules": []}})
        assert "ae.safetensors" in result["override_settings"]["forge_additional_modules"]

    def test_flux2_modules(self):
        result = build_api_payload({"model": "flux2-klein-4b"})
        assert result["override_settings"]["forge_preset"] == "klein"
        modules = result["override_settings"]["forge_additional_modules"]
        assert "flux2-vae.safetensors" in modules

    def test_user_sampler_and_scheduler_preserved(self):
        result = build_api_payload({"model": "flux-dev", "sampler": "DPM++ 2M",
                                    "scheduler": "Karras"})
        assert result["sampler_name"] == "DPM++ 2M"
        assert result["scheduler"] == "Karras"


# ---------------------------------------------------------------------------
# 4. history.py — pagination / search
# ---------------------------------------------------------------------------

def _history_stub(entries, query="", page=0):
    stub = history_mod.HistoryWidget.__new__(history_mod.HistoryWidget)
    stub._all_history = list(entries)
    stub._filtered_history = []
    stub.current_page = page
    stub.search_box = SimpleNamespace(text=lambda: query)
    stub._populate_called = 0

    def _populate():
        stub._populate_called += 1

    stub._populate_page = _populate
    return stub


def _make_entries(n, prefix="cat"):
    return [{"prompt": f"{prefix} picture {i}", "model": "m"} for i in range(n)]


class TestHistoryFilter:
    def test_really_real_classes(self):
        assert isinstance(history_mod.HistoryWidget, type)

    def test_empty_query_returns_all(self):
        stub = _history_stub(_make_entries(5))
        history_mod.HistoryWidget._apply_filter(stub)
        assert len(stub._filtered_history) == 5
        assert stub._populate_called == 1

    def test_query_filters_case_insensitive(self):
        entries = [{"prompt": "A CAT"}, {"prompt": "a dog"}, {"prompt": "catnap"}]
        stub = _history_stub(entries, query="Cat")
        history_mod.HistoryWidget._apply_filter(stub)
        assert len(stub._filtered_history) == 2

    def test_query_matches_nothing(self):
        stub = _history_stub(_make_entries(3), query="zebra")
        history_mod.HistoryWidget._apply_filter(stub)
        assert stub._filtered_history == []
        assert stub.current_page == 0

    def test_missing_prompt_key_matches_empty_query(self):
        stub = _history_stub([{"model": "m"}, {"prompt": "cat"}])
        history_mod.HistoryWidget._apply_filter(stub)
        assert len(stub._filtered_history) == 2

    def test_page_clamped_to_last(self):
        stub = _history_stub(_make_entries(45), page=99)
        history_mod.HistoryWidget._apply_filter(stub)
        assert stub.current_page == 2  # ceil(45/20) - 1

    def test_negative_page_clamped_to_zero(self):
        stub = _history_stub(_make_entries(5), page=-3)
        history_mod.HistoryWidget._apply_filter(stub)
        assert stub.current_page == 0

    def test_on_search_changed_resets_page(self):
        stub = _history_stub(_make_entries(45), page=2)
        history_mod.HistoryWidget._on_search_changed(stub, "cat")
        assert stub.current_page == 0
        assert len(stub._filtered_history) == 45

    def test_prev_page_boundary(self):
        stub = history_mod.HistoryWidget.__new__(history_mod.HistoryWidget)
        stub.current_page = 0
        stub._populate_page = _Recorder()
        history_mod.HistoryWidget._prev_page(stub)
        assert stub.current_page == 0
        assert len(stub._populate_page) == 0

    def test_next_page_boundary(self):
        stub = history_mod.HistoryWidget.__new__(history_mod.HistoryWidget)
        stub.current_page = 0
        stub._filtered_history = _make_entries(5)
        stub._populate_page = _Recorder()
        history_mod.HistoryWidget._next_page(stub)
        assert stub.current_page == 0
        assert len(stub._populate_page) == 0

    def test_prev_next_walk(self):
        stub = history_mod.HistoryWidget.__new__(history_mod.HistoryWidget)
        stub.current_page = 1
        stub._filtered_history = _make_entries(45)
        stub._populate_page = _Recorder()
        history_mod.HistoryWidget._next_page(stub)
        assert stub.current_page == 2
        history_mod.HistoryWidget._prev_page(stub)
        assert stub.current_page == 1
        assert len(stub._populate_page) == 2

    def test_pagination_controls_text_and_buttons(self):
        stub = history_mod.HistoryWidget.__new__(history_mod.HistoryWidget)
        stub.current_page = 0
        stub._filtered_history = _make_entries(45)
        stub.page_label = _FakeLabel()
        stub.prev_btn = _FakeButton()
        stub.next_btn = _FakeButton()
        history_mod.HistoryWidget._update_pagination_controls(stub)
        assert stub.page_label.text == "Page 1 / 3  (45 entries)"
        assert stub.prev_btn.enabled is False
        assert stub.next_btn.enabled is True

    def test_populate_page_slices(self):
        stub = history_mod.HistoryWidget.__new__(history_mod.HistoryWidget)
        stub._filtered_history = _make_entries(25)
        stub._thumbnail_cache = {}
        stub.current_page = 1
        added = []
        stub.scroll_layout = SimpleNamespace(count=lambda: 0,
                                            itemAt=lambda i: None,
                                            addWidget=added.append)
        stub.page_label = _FakeLabel()
        stub.prev_btn = _FakeButton()
        stub.next_btn = _FakeButton()
        history_mod.HistoryWidget._populate_page(stub)
        assert len(added) == 5  # second page of 25 with PAGE_SIZE 20
        assert stub.page_label.text == "Page 2 / 2  (25 entries)"


# ---------------------------------------------------------------------------
# 5. krita_adapter pure helpers
# ---------------------------------------------------------------------------

def _fake_krita(version):
    return SimpleNamespace(instance=lambda: SimpleNamespace(version=lambda: version))


class TestVersionGte:
    @pytest.mark.parametrize("current, target, expected", [
        ("5.2.0", "5.2", True),
        ("5.2", "5.2.0", True),
        ("5.1.5", "5.2", False),
        ("6.0.0", "5.2", True),
        ("5.2.0", "5.2.0", True),
        ("5.10.0", "5.2.0", True),
    ])
    def test_version_compare(self, current, target, expected):
        adapter = ka_mod.KritaAdapter.__new__(ka_mod.KritaAdapter)
        with patch.object(ka_mod, "Krita", _fake_krita(current)):
            assert adapter.version_gte(target) is expected


class TestResolveResultDimensions:
    def _stub(self, selection=(0, 0, 0, 0), canvas=(0, 0, 100, 80)):
        stub = ka_mod.KritaAdapter.__new__(ka_mod.KritaAdapter)
        stub.get_selection_bounds = lambda: selection
        stub.get_canvas_bounds = lambda: canvas
        return stub

    def test_info_dict_wins(self):
        stub = self._stub()
        assert ka_mod.KritaAdapter._resolve_result_dimensions(
            stub, {"info": {"width": 64, "height": 32}}) == (64, 32)

    def test_poses_fallback(self):
        stub = self._stub()
        results = {"poses": [{"canvas_width": 128, "canvas_height": 96}]}
        assert ka_mod.KritaAdapter._resolve_result_dimensions(stub, results) == (128, 96)

    def test_selection_fallback(self):
        stub = self._stub(selection=(0, 0, 200, 150))
        assert ka_mod.KritaAdapter._resolve_result_dimensions(stub, {}) == (200, 150)

    def test_canvas_fallback(self):
        stub = self._stub()
        assert ka_mod.KritaAdapter._resolve_result_dimensions(stub, {}) == (100, 80)

    def test_non_int_info_ignored(self):
        stub = self._stub()
        results = {"info": {"width": "64", "height": None}}
        assert ka_mod.KritaAdapter._resolve_result_dimensions(stub, results) == (100, 80)

    def test_nondict_results_use_canvas(self):
        stub = self._stub()
        assert ka_mod.KritaAdapter._resolve_result_dimensions(stub, None) == (100, 80)
        assert ka_mod.KritaAdapter._resolve_result_dimensions(stub, [1]) == (100, 80)


class TestSeedLayerName:
    def test_seed_used(self):
        assert ka_mod.KritaAdapter._seed_layer_name(
            {"info": {"all_seeds": [11, 22]}}, 1) == "Seed: 22"

    def test_missing_info(self):
        assert ka_mod.KritaAdapter._seed_layer_name({}, 0) == "Image"

    def test_short_seeds(self):
        assert ka_mod.KritaAdapter._seed_layer_name(
            {"info": {"all_seeds": [11]}}, 5) == "Image"

    def test_nondict_info(self):
        assert ka_mod.KritaAdapter._seed_layer_name({"info": "junk"}, 0) == "Image"


class TestBoundsForMode:
    def test_modes(self):
        stub = ka_mod.KritaAdapter.__new__(ka_mod.KritaAdapter)
        stub.get_selection_bounds = lambda: (1, 2, 3, 4)
        stub.get_layer_bounds = lambda: (5, 6, 7, 8)
        stub.get_canvas_bounds = lambda: (0, 0, 100, 100)
        assert ka_mod.KritaAdapter._bounds_for_mode(stub, "selection") == (1, 2, 3, 4)
        assert ka_mod.KritaAdapter._bounds_for_mode(stub, "layer") == (5, 6, 7, 8)
        assert ka_mod.KritaAdapter._bounds_for_mode(stub, "canvas") == (0, 0, 100, 100)
        assert ka_mod.KritaAdapter._bounds_for_mode(stub, "SELECTION") == (1, 2, 3, 4)
        assert ka_mod.KritaAdapter._bounds_for_mode(stub, "junk") == (0, 0, 100, 100)


class TestBase64Helpers:
    def _fake_image_cls(self, requested):
        class _Bits:
            def setsize(self, _n):
                pass

            def asstring(self):
                return b"pixelbytes"

        class _FakeImage:
            FORMAT = "RGBA8888"

            def __init__(self):
                self.converted = False
                self.scaled_w = None

            @classmethod
            def fromData(cls, data, fmt):
                requested["fmt"] = fmt
                requested["data"] = data
                return _FakeImage()

            def isGrayscale(self):
                return requested.get("gray", False)

            def convertToFormat(self, _fmt):
                self.converted = True
                requested["converted"] = True
                return self

            def scaledToWidth(self, w):
                self.scaled_w = w
                return self

            def scaledToHeight(self, h):
                return self

            def bits(self):
                return _Bits()

            def byteCount(self):
                return 10

            def width(self):
                return 4

            def height(self):
                return 3

        _FakeImage.Format_RGBA8888 = "RGBA8888"
        return _FakeImage

    def test_png_prefix_selects_png_format(self):
        import base64 as b64lib
        requested = {}
        raw = b"\x89PNG\r\n\x1a\n" + b"0" * 30
        assert b64lib.b64encode(raw).decode().startswith("iVBORw0KGgo")
        with patch.object(ka_mod, "QImage", self._fake_image_cls(requested)), \
                patch.object(ka_mod, "QByteArray", lambda data: data):
            _data, w, h = ka_mod.KritaAdapter.base64_to_pixeldata(
                b64lib.b64encode(raw).decode())
        assert requested["fmt"] == "PNG"
        assert (w, h) == (4, 3)

    def test_non_png_prefix_selects_jpeg_format(self):
        import base64 as b64lib
        requested = {}
        raw = b"\xff\xd8\xff" + b"1" * 30
        assert not b64lib.b64encode(raw).decode().startswith("iVBORw0KGgo")
        with patch.object(ka_mod, "QImage", self._fake_image_cls(requested)), \
                patch.object(ka_mod, "QByteArray", lambda data: data):
            ka_mod.KritaAdapter.base64_to_pixeldata(b64lib.b64encode(raw).decode())
        assert requested["fmt"] == "JPEG"

    def test_grayscale_converted(self):
        import base64 as b64lib
        requested = {"gray": True}
        raw = b"\xff\xd8\xff" + b"2" * 30
        with patch.object(ka_mod, "QImage", self._fake_image_cls(requested)), \
                patch.object(ka_mod, "QByteArray", lambda data: data):
            ka_mod.KritaAdapter.base64_to_pixeldata(b64lib.b64encode(raw).decode())
        assert requested.get("converted") is True

    def test_qimage_to_b64_round_trip_shape(self):
        saved = {}

        class _FakeBA:
            def toBase64(self):
                return SimpleNamespace(data=lambda: b"QUJD")

        class _FakeBuf:
            def __init__(self, _ba):
                pass

            def open(self, _mode):
                pass

        class _FakeImg:
            def save(self, _buf, fmt):
                saved["fmt"] = fmt

        with patch.object(ka_mod, "QByteArray", _FakeBA), \
                patch.object(ka_mod, "QBuffer", _FakeBuf), \
                patch.object(ka_mod, "QIODevice",
                             SimpleNamespace(OpenModeFlag=SimpleNamespace(WriteOnly=1))):
            assert ka_mod.KritaAdapter.qimage_to_b64_str(_FakeImg()) == "QUJD"
        assert saved["fmt"] == "PNG"

    def test_projection_to_qimage_argb_stride(self):
        seen = {}

        class _FakeQImage:
            Format = SimpleNamespace(Format_ARGB32="ARGB32")

            def __init__(self, pixel_data, width, height, stride, fmt):
                seen.update(pixel_data=pixel_data, width=width,
                            height=height, stride=stride, fmt=fmt)

        _FakeQImage.Format_ARGB32 = "ARGB32"
        with patch.object(ka_mod, "QImage", _FakeQImage):
            ka_mod.KritaAdapter.projection_to_qimage(b"px", 10, 5)
        assert seen["stride"] == 40  # width * 4 bytes per pixel
        assert seen["width"] == 10 and seen["height"] == 5
