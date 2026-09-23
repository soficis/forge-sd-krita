"""Todo 24 (Phase 1 leftover): robust connection error handling.

Contract under test (surfacing only; retry/backoff numbers unchanged):
- Every network exception path in SDAPI._request (URLError, timeout,
  ConnectionRefusedError, ConnectionResetError, OSError, HTTP 4xx/5xx,
  partial JSON) lands in ConnectionState.ERROR with a non-empty,
  human-readable last_error_message distinct per failure class.
- ForgeDocker._update_connection_state shows the banner with the reason
  (not just a boolean) and disables Generate/Cancel/Remove Background;
  recover-on-success clears the banner.
- change_host() while a request is in flight refuses cleanly (False, host
  unchanged, no exception) instead of swapping the host mid-generation.

Falling-first: pre-fix, ConnectionResetError escapes _request, partial
JSON stays CONNECTED, no per-failure message exists, the banner never
carries a reason, and change_host swaps unconditionally.
"""

from __future__ import annotations

import importlib.util
import io
import json
import pathlib
import sys
import urllib.error
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from forge.adapters.sd_api import BackendType, ConnectionState, SDAPI


# ---------------------------------------------------------------------------
# Real ForgeDocker without disturbing conftest's forge.forge mock
# ---------------------------------------------------------------------------

class _DockWidgetStub:
    def __init__(self, *args, **kwargs):
        pass

    def setWindowTitle(self, *args, **kwargs):
        pass

    def setWidget(self, *args, **kwargs):
        pass

    def closeEvent(self, event):
        pass


def _load_forge_docker():
    mod_name = "forge.forge_task24"
    if mod_name in sys.modules:
        return sys.modules[mod_name].ForgeDocker
    krita_mod = sys.modules.get("krita")
    old_dock = getattr(krita_mod, "DockWidget", None)
    krita_mod.DockWidget = _DockWidgetStub
    try:
        path = (
            pathlib.Path(__file__).resolve().parent.parent
            / "forge" / "forge.py"
        )
        spec = importlib.util.spec_from_file_location(mod_name, str(path))
        mod = importlib.util.module_from_spec(spec)
        mod.__package__ = "forge"
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        return mod.ForgeDocker
    finally:
        krita_mod.DockWidget = old_dock


ForgeDocker = _load_forge_docker()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _blank_api(**overrides) -> SDAPI:
    api = SDAPI.__new__(SDAPI)
    api.timeout_seconds = 30.0
    api.max_retries = 0
    api.status_connect_timeout = 3.05
    api.status_read_timeout = 10.0
    api.gen_connect_timeout = 5.05
    api.gen_read_timeout = 600.0
    api.host = "http://127.0.0.1:7860"
    api.state = ConnectionState.DISCONNECTED
    api.connected = False
    api.backend_type = BackendType.UNKNOWN
    api.last_url = ""
    api.last_error = None
    api.last_error_message = ""
    api._in_flight = 0
    api.models = []
    api.vaes = []
    api.samplers = []
    api.upscalers = []
    api.facerestorers = []
    api.styles = []
    api.scripts = {}
    api.loras = []
    api.embeddings = {}
    api.hypernetworks = []
    api.additional_modules = []
    api.adetailer_models = []
    api.default_settings = {}
    api.defaults = {
        "sampler": "", "model": "", "vae": "",
        "upscaler": "", "refiner": "", "face_restorer": "",
        "color_correction": True,
    }
    api._cache = {}
    api._cache_ttl = 60.0
    for key, value in overrides.items():
        setattr(api, key, value)
    return api


def _json_response(data) -> MagicMock:
    response = MagicMock()
    response.read.return_value = json.dumps(data).encode()
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    return response


def _raw_response(body: bytes) -> MagicMock:
    response = MagicMock()
    response.read.return_value = body
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    return response


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="http://127.0.0.1:7860/test",
        code=code,
        msg="error",
        hdrs=None,
        fp=io.BytesIO(b""),
    )


# ---------------------------------------------------------------------------
# (a) every network exception path -> ERROR + human message
# ---------------------------------------------------------------------------

class TestFailureMapping:
    @pytest.mark.parametrize("exc", [
        urllib.error.URLError("dns failure"),
        urllib.error.URLError(ConnectionRefusedError("refused")),
        TimeoutError("timed out"),
        ConnectionRefusedError("refused"),
        ConnectionResetError("reset by peer"),
        OSError("broken pipe"),
    ])
    def test_network_exceptions_map_to_error_with_message(self, exc):
        api = _blank_api()
        with patch(
            "forge.adapters.sd_api.urllib.request.urlopen",
            side_effect=exc,
        ):
            api.get("/queue/status")
        assert api.state == ConnectionState.ERROR
        assert api.connected is False
        assert isinstance(api.last_error_message, str)
        assert api.last_error_message.strip()

    def test_timeout_message_names_timeout(self):
        api = _blank_api()
        with patch(
            "forge.adapters.sd_api.urllib.request.urlopen",
            side_effect=TimeoutError("timed out"),
        ):
            api.get("/queue/status")
        assert "timeout" in api.last_error_message.lower()

    def test_refused_message_names_refused(self):
        api = _blank_api()
        with patch(
            "forge.adapters.sd_api.urllib.request.urlopen",
            side_effect=ConnectionRefusedError("refused"),
        ):
            api.get("/queue/status")
        assert "refus" in api.last_error_message.lower()

    def test_reset_message_names_reset(self):
        api = _blank_api()
        with patch(
            "forge.adapters.sd_api.urllib.request.urlopen",
            side_effect=ConnectionResetError("reset by peer"),
        ):
            api.get("/queue/status")
        assert "reset" in api.last_error_message.lower()

    def test_url_error_message_carries_reason(self):
        api = _blank_api()
        with patch(
            "forge.adapters.sd_api.urllib.request.urlopen",
            side_effect=urllib.error.URLError("dns failure"),
        ):
            api.get("/queue/status")
        assert "dns failure" in api.last_error_message

    @pytest.mark.parametrize("body", [
        b'{"images": ["abc',
        b"not json at all",
        b"",
    ])
    def test_partial_json_maps_to_error_with_message(self, body):
        api = _blank_api()
        with patch(
            "forge.adapters.sd_api.urllib.request.urlopen",
            return_value=_raw_response(body),
        ):
            result = api.get("/queue/status")
        assert result == body
        assert api.state == ConnectionState.ERROR
        assert api.connected is False
        assert api.last_error_message.strip()

    def test_http_4xx_error_with_message_and_no_retry(self):
        api = _blank_api()
        with patch(
            "forge.adapters.sd_api.urllib.request.urlopen",
            side_effect=_http_error(404),
        ) as m:
            result = api.get("/sdapi/v1/options")
        assert isinstance(result, urllib.error.HTTPError)
        assert api.state == ConnectionState.ERROR
        assert m.call_count == 1
        assert api.last_error_message.strip()

    def test_http_5xx_error_with_message_after_retries(self):
        api = _blank_api(max_retries=2)
        with patch(
            "forge.adapters.sd_api.urllib.request.urlopen",
            side_effect=_http_error(500),
        ) as m:
            with patch("forge.adapters.sd_api.time.sleep"):
                result = api.get("/sdapi/v1/options")
        assert isinstance(result, urllib.error.HTTPError)
        assert api.state == ConnectionState.ERROR
        assert m.call_count == 3
        assert api.last_error_message.strip()


# ---------------------------------------------------------------------------
# Retry/backoff policy byte-identical (guards against surfacing regressions)
# ---------------------------------------------------------------------------

class TestRetryPolicyPreserved:
    def test_backoff_delays_unchanged(self):
        api = _blank_api(max_retries=3)
        with patch(
            "forge.adapters.sd_api.urllib.request.urlopen",
            side_effect=ConnectionRefusedError("refused"),
        ):
            with patch(
                "forge.adapters.sd_api.time.sleep",
            ) as mock_sleep:
                api.get("/queue/status")
        assert [c.args[0] for c in mock_sleep.call_args_list] == [1, 2, 4]

    def test_default_max_retries_is_five(self):
        with patch(
            "forge.adapters.sd_api.urllib.request.urlopen",
            return_value=_json_response({"status": "ok"}),
        ):
            api = SDAPI()
        assert api.max_retries == 5

    def test_split_timeouts_unchanged(self):
        with patch(
            "forge.adapters.sd_api.urllib.request.urlopen",
            return_value=_json_response({"status": "ok"}),
        ):
            api = SDAPI()
        assert api.status_connect_timeout == 3.05
        assert api.status_read_timeout == 10.0
        assert api.gen_connect_timeout == 5.05
        assert api.gen_read_timeout == 600.0

    def test_constructor_starts_clean(self):
        with patch(
            "forge.adapters.sd_api.urllib.request.urlopen",
            return_value=_json_response({"status": "ok"}),
        ):
            api = SDAPI()
        assert api.last_error_message == ""
        assert api._in_flight == 0


# ---------------------------------------------------------------------------
# (c) recover-on-success clears the error
# ---------------------------------------------------------------------------

class TestRecovery:
    def test_success_after_failure_recovers(self):
        api = _blank_api()
        with patch(
            "forge.adapters.sd_api.urllib.request.urlopen",
            side_effect=urllib.error.URLError("down"),
        ):
            api.get("/queue/status")
        assert api.state == ConnectionState.ERROR
        assert api.last_error_message.strip()

        with patch(
            "forge.adapters.sd_api.urllib.request.urlopen",
            return_value=_json_response({"status": "ok"}),
        ):
            result = api.get("/queue/status")
        assert result == {"status": "ok"}
        assert api.state == ConnectionState.CONNECTED
        assert api.connected is True
        assert api.last_error is None
        assert api.last_error_message == ""

    def test_refresh_recovers_to_connected(self):
        api = _blank_api()
        with patch(
            "forge.adapters.sd_api.urllib.request.urlopen",
            side_effect=TimeoutError("timed out"),
        ):
            api.get("/queue/status")
        assert api.state == ConnectionState.ERROR

        with patch(
            "forge.adapters.sd_api.urllib.request.urlopen",
            return_value=_json_response({"status": "ok"}),
        ):
            api.refresh()
        assert api.state == ConnectionState.CONNECTED
        assert api.connected is True
        assert api.last_error_message == ""


# ---------------------------------------------------------------------------
# (b)/(c) banner carries the reason; recovery hides it
# ---------------------------------------------------------------------------

class _FakeBanner:
    def __init__(self):
        self._text = "No Connection"
        self._hidden = True

    def setText(self, text):
        self._text = text

    def text(self):
        return self._text

    def setHidden(self, hidden):
        self._hidden = bool(hidden)

    def isHidden(self):
        return self._hidden


class _FakeButton:
    def __init__(self, label):
        self._label = label
        self._enabled = True

    def text(self):
        return self._label

    def setEnabled(self, value):
        self._enabled = bool(value)

    def isEnabled(self):
        return self._enabled


class _FakeScroll:
    def __init__(self, buttons):
        self._buttons = buttons

    def widget(self):
        return self

    def findChildren(self, cls):
        return list(self._buttons)


def _make_docker(api, labels):
    docker = ForgeDocker.__new__(ForgeDocker)
    docker.api = api
    docker.connection_banner = _FakeBanner()
    docker.content_area = _FakeScroll([_FakeButton(label) for label in labels])
    return docker


_BUTTON_LABELS = ["Generate", "Cancel", "Remove Background", "Foo"]


class TestConnectionBanner:
    def test_error_shows_banner_with_reason_and_disables_buttons(self):
        reason = "Could not connect - connection refused. Is Forge running?"
        api = SimpleNamespace(connected=False, last_error_message=reason)
        docker = _make_docker(api, _BUTTON_LABELS)

        ForgeDocker._update_connection_state(docker)

        assert docker.connection_banner.isHidden() is False
        assert reason in docker.connection_banner.text()
        states = {
            b._label: b.isEnabled() for b in docker.content_area._buttons
        }
        assert states["Generate"] is False
        assert states["Cancel"] is False
        assert states["Remove Background"] is False
        assert states["Foo"] is True

    def test_connected_hides_banner_and_enables_buttons(self):
        api = SimpleNamespace(connected=True, last_error_message="")
        docker = _make_docker(api, _BUTTON_LABELS)

        ForgeDocker._update_connection_state(docker)

        assert docker.connection_banner.isHidden() is True
        assert all(b.isEnabled() for b in docker.content_area._buttons)

    def test_recovery_clears_banner(self):
        api = SimpleNamespace(
            connected=False, last_error_message="boom",
        )
        docker = _make_docker(api, _BUTTON_LABELS)
        ForgeDocker._update_connection_state(docker)
        assert docker.connection_banner.isHidden() is False

        api.connected = True
        api.last_error_message = ""
        ForgeDocker._update_connection_state(docker)
        assert docker.connection_banner.isHidden() is True

    def test_empty_reason_falls_back_to_nonempty_banner(self):
        api = SimpleNamespace(connected=False, last_error_message="")
        docker = _make_docker(api, _BUTTON_LABELS)

        ForgeDocker._update_connection_state(docker)

        assert docker.connection_banner.isHidden() is False
        assert docker.connection_banner.text().strip()


# ---------------------------------------------------------------------------
# (d) host change mid-generation refuses cleanly
# ---------------------------------------------------------------------------

class TestHostChange:
    def test_change_host_idle_switches(self):
        api = _blank_api()
        with patch.object(SDAPI, "refresh"):
            ok = api.change_host("http://127.0.0.1:9999")
        assert ok is True
        assert api.host == "http://127.0.0.1:9999"

    def test_change_host_empty_falls_back_to_default(self):
        api = _blank_api()
        with patch.object(SDAPI, "refresh"):
            ok = api.change_host("")
        assert ok is True
        assert api.host == SDAPI.DEFAULT_HOST

    def test_change_host_refused_while_generation_in_flight(self):
        api = _blank_api()
        refusals = []

        def _during(request, timeout=None):
            refusals.append(api.change_host("http://127.0.0.1:9999"))
            raise ConnectionRefusedError("refused")

        with patch(
            "forge.adapters.sd_api.urllib.request.urlopen",
            side_effect=_during,
        ):
            result = api.post("/sdapi/v1/txt2img", {"prompt": "x"})

        assert refusals == [False]
        assert api.host == "http://127.0.0.1:7860"
        assert api.state == ConnectionState.ERROR
        assert isinstance(result, ConnectionRefusedError)
        assert api.last_error_message.strip()
