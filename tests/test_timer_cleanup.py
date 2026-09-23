"""Task 14 (High #7): page/widget timers must stop on cleanup.

Failing-first: GenerateWidget/MaskWidget have no cleanup() pre-fix, the
progress timer is unparented, and SettingsController has no close hook, so
every test below fails (AttributeError / leaked pending timer) until fixed.
"""

from __future__ import annotations

import json
import sys
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

# Qt fakes come from tests/conftest.py. conftest's ForgeDocker mock is dropped
# so the real docker is exercised. forge.pages.base stays unimported: BasePage
# mixes QWidget + ABC and that combination cannot be defined outside Krita.

sys.modules.pop("forge.forge", None)


class _DockWidgetStub:
    """Minimal Krita DockWidget: subclassing a MagicMock instance yields
    another mock, so a real base class is needed for the docker."""

    def __init__(self, *args, **kwargs):
        pass

    def setWindowTitle(self, *args, **kwargs):
        pass

    def setWidget(self, *args, **kwargs):
        pass

    def closeEvent(self, event):
        pass


sys.modules["krita"].DockWidget = _DockWidgetStub

from forge.forge import ForgeDocker  # noqa: E402
from forge.pages.inpaint import InpaintPage  # noqa: E402
from forge.pages.txt2img import Txt2ImgPage  # noqa: E402
from forge.settings_controller import SettingsController  # noqa: E402
from forge.widgets.generate import GenerateWidget  # noqa: E402
from forge.widgets.mask import MaskWidget  # noqa: E402


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeTimer:
    """Minimal QTimer double with real active-state tracking."""

    def __init__(self, parent=None):
        self.parent = parent
        self._active = False
        self.stop_calls = 0
        self.timeout = MagicMock()

    def start(self, interval=None):
        self._active = True

    def stop(self):
        self._active = False
        self.stop_calls += 1

    def isActive(self):
        return self._active


def _bare_instance(cls, **attrs):
    """__new__ without __init__ plus mock-safe attribute injection.

    Mock-subclass instances skip MagicMock.__init__, so plain setattr hits
    uninitialised mock machinery; object.__setattr__ bypasses it.
    """
    instance = cls.__new__(cls)
    for key, value in attrs.items():
        object.__setattr__(instance, key, value)
    return instance


def _make_generate_widget():
    """Real GenerateWidget init under Qt mocks (cf. task-13 tests)."""
    settings = MagicMock()
    settings.get.return_value = None
    api = MagicMock()
    api.defaults = {"model": "test-sdxl-ckpt"}
    return GenerateWidget(
        settings, api, [], "txt2img", {"x": 0, "y": 0, "w": 0, "h": 0}
    )


def _make_mask_widget(tmp_path):
    """Real MaskWidget init with file-backed settings (cf. task-13 tests)."""
    defaults = {
        "inpaint": {
            "mask_blur": 0,
            "mask_mode": 0,
            "masked_content": 0,
            "inpaint_area": 0,
            "padding": 0,
            "auto_update_mask": False,
            "results_below_mask": False,
            "hide_mask_on_gen": False,
            "reference_layer": "",
        },
        "hide_ui": {
            "inpaint_auto_update": True,
            "inpaint_below_mask": True,
            "inpaint_hide_mask": True,
        },
    }
    (tmp_path / "default_settings.json").write_text(
        json.dumps(defaults), encoding="utf-8"
    )
    settings = SettingsController(base_dir=tmp_path)
    return MaskWidget(settings, MagicMock(), {"x": 0, "y": 0, "w": 0, "h": 0})


# ---------------------------------------------------------------------------
# GenerateWidget progress QTimer
# ---------------------------------------------------------------------------


class TestGenerateTimerCleanup:
    def test_cleanup_stops_progress_timer(self):
        widget = _make_generate_widget()
        timer = _FakeTimer()
        timer.start(500)
        widget.progress_timer = timer

        widget.cleanup()

        assert timer.stop_calls == 1
        assert timer.isActive() is False

    def test_cleanup_is_idempotent(self):
        widget = _make_generate_widget()
        timer = _FakeTimer()
        timer.start(500)
        widget.progress_timer = timer

        widget.cleanup()
        widget.cleanup()  # second call: no-op, no exception

        assert timer.isActive() is False

    def test_cleanup_with_no_timer_is_safe(self):
        widget = _make_generate_widget()
        widget.progress_timer = None

        widget.cleanup()  # must not raise
        widget.cleanup()

    def test_progress_timer_is_parent_owned(self):
        """Unparented QTimer() leaks past widget destruction; QTimer(self)
        ties lifetime to the widget. Exercises the real creation path."""
        import forge.widgets.generate as generate_mod

        widget = _make_generate_widget()
        widget.kc = MagicMock()
        widget.settings_controller.get.side_effect = (
            lambda path, default=None: 0.5
            if path == "previews.refresh_seconds"
            else None
        )
        widget.job_queue.append(
            SimpleNamespace(
                id="job-1",
                data={"prompt": "a cat"},
                x=0,
                y=0,
                width=64,
                height=64,
                processing_instructions={},
                timestamp=0.0,
            )
        )

        original = generate_mod.QTimer
        generate_mod.QTimer = _FakeTimer
        try:
            widget._start_next_job()
            timer = widget.progress_timer
        finally:
            generate_mod.QTimer = original

        assert isinstance(timer, _FakeTimer)
        assert timer.parent is widget
        assert timer.isActive() is True


# ---------------------------------------------------------------------------
# MaskWidget brush-poll QTimer
# ---------------------------------------------------------------------------


class TestMaskTimerCleanup:
    def test_cleanup_stops_brush_poll_timer(self, tmp_path):
        widget = _make_mask_widget(tmp_path)
        timer = _FakeTimer()
        timer.start(500)
        widget._brush_poll_timer = timer

        widget.cleanup()

        assert timer.stop_calls == 1
        assert timer.isActive() is False

    def test_cleanup_is_idempotent(self, tmp_path):
        widget = _make_mask_widget(tmp_path)
        timer = _FakeTimer()
        timer.start(500)
        widget._brush_poll_timer = timer

        widget.cleanup()
        widget.cleanup()  # second call: no-op, no exception

        assert timer.isActive() is False


# ---------------------------------------------------------------------------
# SettingsController debounce timer (BY DESIGN 300ms — only cancel pending)
# ---------------------------------------------------------------------------


def _write_defaults(tmp_path):
    (tmp_path / "default_settings.json").write_text(
        json.dumps({"x": 1}), encoding="utf-8"
    )


class TestSettingsDebounceClose:
    def test_debounce_interval_unchanged(self, tmp_path):
        _write_defaults(tmp_path)
        controller = SettingsController(base_dir=tmp_path)
        assert controller._save_delay == 0.3

    def test_close_cancels_pending_save(self, tmp_path):
        _write_defaults(tmp_path)
        controller = SettingsController(base_dir=tmp_path)
        controller.set("x", 99)
        controller.debounced_save()
        assert controller._save_timer is not None

        controller.close()

        assert controller._save_timer is None
        time.sleep(0.5)
        # Pending write was cancelled: no user file may appear afterwards.
        assert not (tmp_path / "user_settings.json").is_file()

    def test_close_is_idempotent(self, tmp_path):
        _write_defaults(tmp_path)
        controller = SettingsController(base_dir=tmp_path)

        controller.close()
        controller.close()  # no pending timer: must not raise

    def test_save_still_cancels_pending_timer(self, tmp_path):
        _write_defaults(tmp_path)
        controller = SettingsController(base_dir=tmp_path)
        controller.set("x", 7)
        controller.debounced_save()
        controller.save()  # immediate save flushes + drops the pending timer

        assert controller._save_timer is None
        data = json.loads(
            (tmp_path / "user_settings.json").read_text(encoding="utf-8")
        )
        assert data["x"] == 7


# ---------------------------------------------------------------------------
# BasePage cleanup hook cascades to timer-owning children
# ---------------------------------------------------------------------------


class TestPageCleanup:
    def test_txt2img_cleanup_stops_generate_timer(self):
        generate_widget = SimpleNamespace(cleanup=MagicMock())
        page = _bare_instance(
            Txt2ImgPage,
            generate_widget=generate_widget,
            widgets=[generate_widget],
        )

        page.cleanup()

        generate_widget.cleanup.assert_called_once_with()

    def test_inpaint_cleanup_stops_generate_and_brush_timers(self):
        generate_widget = SimpleNamespace(cleanup=MagicMock())
        mask_widget = SimpleNamespace(cleanup=MagicMock())
        page = _bare_instance(
            InpaintPage,
            generate_widget=generate_widget,
            mask_widget=mask_widget,
            widgets=[mask_widget, generate_widget],
        )

        page.cleanup()

        generate_widget.cleanup.assert_called_once_with()
        mask_widget.cleanup.assert_called_once_with()

    def test_page_cleanup_is_idempotent(self):
        generate_widget = SimpleNamespace(cleanup=MagicMock())
        page = _bare_instance(
            Txt2ImgPage,
            generate_widget=generate_widget,
            widgets=[generate_widget],
        )

        page.cleanup()
        page.cleanup()


# ---------------------------------------------------------------------------
# Page-switch + docker-close wiring (forge.ForgeDocker)
# ---------------------------------------------------------------------------


def _make_docker_shell():
    """ForgeDocker without real Qt init: stub tab bar / scroll area / api."""
    settings_controller = MagicMock()
    settings_controller.has.return_value = False
    old_widget = MagicMock()
    docker = _bare_instance(
        ForgeDocker,
        settings_controller=settings_controller,
        api=SimpleNamespace(connected=True),
        page_tabs=SimpleNamespace(currentIndex=MagicMock(return_value=0)),
        content_area=SimpleNamespace(
            widget=MagicMock(return_value=old_widget),
            setWidget=MagicMock(),
        ),
        pages=[{"name": "Settings", "icon": "x", "content": MagicMock()}],
        connection_banner=SimpleNamespace(setHidden=MagicMock()),
        update=MagicMock(),
        _old_widget=old_widget,
    )
    return docker


class TestDockerPageSwitch:
    def test_change_page_cleans_up_previous_widget(self):
        docker = _make_docker_shell()

        docker.change_page()

        docker._old_widget.cleanup.assert_called_once_with()

    def test_close_event_cleans_up_and_cancels_save(self):
        docker = _make_docker_shell()
        event = MagicMock()

        ForgeDocker.closeEvent(docker, event)

        docker._old_widget.cleanup.assert_called_once_with()
        docker.settings_controller.close.assert_called_once_with()
