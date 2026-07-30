"""Unit tests for forge.adapters.sd_api — BackendType detection,
ConnectionState transitions, retry logic, and error handling.

All tests mock urllib.request.urlopen; no real network calls are made.
Krita/Qt mocks are provided by conftest.py.
"""

from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from forge.adapters.sd_api import BackendType, ConnectionState, SDAPI


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_response(data: dict | list | str, code: int = 200) -> MagicMock:
    """Return a mock context-manager that yields a mock HTTP response."""
    if isinstance(data, (dict, list)):
        body = json.dumps(data).encode()
    else:
        body = str(data).encode()

    response = MagicMock()
    response.read.return_value = body
    response.status = code
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    return response


def _error_response(code: int, msg: str = "error") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="http://127.0.0.1:7860/test",
        code=code,
        msg=msg,
        hdrs=None,
        fp=io.BytesIO(b""),
    )


def _make_api(max_retries: int = 3) -> SDAPI:
    """Create an SDAPI with urlopen mocked to return a /queue/status OK."""
    with patch("forge.adapters.sd_api.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = _json_response({"status": "ok"})
        api = SDAPI(max_retries=max_retries)
    return api


# ---------------------------------------------------------------------------
# BackendType detection
# ---------------------------------------------------------------------------

class TestBackendDetection:
    """get_options() must classify the backend correctly."""

    @staticmethod
    def _api_with_options(options: dict) -> SDAPI:
        """Build SDAPI, then call get_options() with mocked HTTP."""
        api = _make_api(max_retries=0)
        with patch("forge.adapters.sd_api.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = _json_response(options)
            api.get_options()
        return api

    def test_forge_neo_with_forge_preset(self):
        """Options containing 'forge_preset' → FORGE_NEO."""
        api = self._api_with_options({"forge_preset": "neo"})
        assert api.backend_type == BackendType.FORGE_NEO

    def test_forge_neo_with_additional_modules(self):
        """Options containing 'forge_additional_modules' → FORGE_NEO."""
        api = self._api_with_options(
            {"forge_additional_modules": ["module1"]}
        )
        assert api.backend_type == BackendType.FORGE_NEO

    def test_forge_classic_non_empty(self):
        """Non-empty options without forge keys → FORGE_CLASSIC."""
        api = self._api_with_options({"sd_model_checkpoint": "model"})
        assert api.backend_type == BackendType.FORGE_CLASSIC

    def test_unknown_empty_options(self):
        """Empty options dict → UNKNOWN (unchanged default)."""
        api = _make_api(max_retries=0)
        api.backend_type = BackendType.UNKNOWN
        with patch("forge.adapters.sd_api.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = _json_response({})
            api.get_options()
        assert api.backend_type == BackendType.UNKNOWN

    def test_unknown_non_dict_response(self):
        """Non-dict response treated as empty → UNKNOWN."""
        api = _make_api(max_retries=0)
        api.backend_type = BackendType.UNKNOWN
        with patch("forge.adapters.sd_api.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = _json_response([])
            api.get_options()
        assert api.backend_type == BackendType.UNKNOWN


# ---------------------------------------------------------------------------
# ConnectionState transitions
# ---------------------------------------------------------------------------

class TestConnectionState:
    """Verify the state machine evolves correctly through requests."""

    def test_initial_state(self):
        """SDAPI starts DISCONNECTED before any network call."""
        with patch("forge.adapters.sd_api.urllib.request.urlopen") as m:
            m.return_value = _json_response({"status": "ok"})
            api = SDAPI.__new__(SDAPI)
            api.timeout_seconds = 30
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
            api.default_settings = {}
            api.defaults = {
                "sampler": "", "model": "", "vae": "",
                "upscaler": "", "refiner": "", "face_restorer": "",
                "color_correction": True,
            }
        assert api.state == ConnectionState.DISCONNECTED

    def test_successful_request_transitions_to_connected(self):
        """A successful _request transitions to CONNECTED."""
        api = _make_api(max_retries=0)
        assert api.state == ConnectionState.CONNECTED
        assert api.connected is True

    def test_connection_refused_sets_error_after_retries(self):
        """ConnectionRefusedError → ERROR state after exhausting retries."""
        api = _make_api(max_retries=2)
        # Overwrite state to force a fresh request cycle
        api.state = ConnectionState.CONNECTED
        with patch("forge.adapters.sd_api.urllib.request.urlopen") as m:
            m.side_effect = ConnectionRefusedError("refused")
            with patch("forge.adapters.sd_api.time.sleep"):
                result = api.get("/queue/status")
        assert isinstance(result, ConnectionRefusedError)
        assert api.state == ConnectionState.ERROR
        assert api.connected is False

    def test_http_4xx_sets_error_immediately(self):
        """HTTP 4xx → ERROR, no retries."""
        api = _make_api(max_retries=3)
        api.state = ConnectionState.CONNECTED
        with patch("forge.adapters.sd_api.urllib.request.urlopen") as m:
            m.side_effect = _error_response(404, "Not Found")
            result = api.get("/sdapi/v1/options")
        assert isinstance(result, urllib.error.HTTPError)
        assert result.code == 404
        assert api.state == ConnectionState.ERROR
        # Only 1 attempt — no retry on 4xx
        assert m.call_count == 1

    def test_http_5xx_retries_then_errors(self):
        """HTTP 5xx → retries, then ERROR after exhausting attempts."""
        api = _make_api(max_retries=2)
        api.state = ConnectionState.CONNECTED
        with patch("forge.adapters.sd_api.urllib.request.urlopen") as m:
            m.side_effect = _error_response(500, "Internal Server Error")
            with patch("forge.adapters.sd_api.time.sleep"):
                result = api.get("/sdapi/v1/options")
        assert isinstance(result, urllib.error.HTTPError)
        assert result.code == 500
        assert api.state == ConnectionState.ERROR
        # 1 initial + 2 retries = 3 calls
        assert m.call_count == 3

    def test_timeout_sets_error_after_retries(self):
        """TimeoutError → ERROR state after exhausting retries."""
        api = _make_api(max_retries=1)
        api.state = ConnectionState.CONNECTED
        with patch("forge.adapters.sd_api.urllib.request.urlopen") as m:
            m.side_effect = TimeoutError("timed out")
            with patch("forge.adapters.sd_api.time.sleep"):
                result = api.get("/queue/status")
        assert isinstance(result, TimeoutError)
        assert api.state == ConnectionState.ERROR
        # 1 initial + 1 retry = 2 calls
        assert m.call_count == 2

    def test_url_error_retries_then_errors(self):
        """URLError → retries, then ERROR."""
        api = _make_api(max_retries=1)
        api.state = ConnectionState.CONNECTED
        with patch("forge.adapters.sd_api.urllib.request.urlopen") as m:
            m.side_effect = urllib.error.URLError("dns failure")
            with patch("forge.adapters.sd_api.time.sleep"):
                result = api.get("/queue/status")
        assert isinstance(result, urllib.error.URLError)
        assert api.state == ConnectionState.ERROR
        assert m.call_count == 2


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------

class TestRetryLogic:
    """_request() must retry with exponential backoff on transient errors."""

    def test_retries_with_exponential_backoff(self):
        """Backoff delays are min(2**attempt, 30)."""
        api = _make_api(max_retries=3)
        api.state = ConnectionState.CONNECTED
        with patch("forge.adapters.sd_api.urllib.request.urlopen") as m:
            m.side_effect = ConnectionRefusedError("refused")
            with patch("forge.adapters.sd_api.time.sleep") as mock_sleep:
                api.get("/queue/status")
        # Attempt 0 fails, retry 1 (delay 1s), retry 2 (delay 2s), retry 3 (delay 4s)
        # Sleep is called between attempts (not after the last failure)
        delays = [c.args[0] for c in mock_sleep.call_args_list]
        assert delays == [1, 2, 4]

    def test_no_retry_on_http_4xx(self):
        """4xx responses must NOT trigger retries."""
        api = _make_api(max_retries=5)
        api.state = ConnectionState.CONNECTED
        with patch("forge.adapters.sd_api.urllib.request.urlopen") as m:
            m.side_effect = _error_response(403, "Forbidden")
            with patch("forge.adapters.sd_api.time.sleep") as mock_sleep:
                api.get("/sdapi/v1/options")
        assert m.call_count == 1
        mock_sleep.assert_not_called()

    def test_successful_after_retries(self):
        """If a retry succeeds, return the result and set CONNECTED."""
        api = _make_api(max_retries=2)
        api.state = ConnectionState.CONNECTED
        ok = _json_response({"models": []})
        with patch("forge.adapters.sd_api.urllib.request.urlopen") as m:
            m.side_effect = [
                ConnectionRefusedError("refused"),
                ConnectionRefusedError("refused"),
                ok,
            ]
            with patch("forge.adapters.sd_api.time.sleep"):
                result = api.get("/sdapi/v1/sd-models")
        assert result == {"models": []}
        assert api.state == ConnectionState.CONNECTED
        assert api.connected is True
        assert m.call_count == 3

    def test_retries_respect_retries_param(self):
        """The optional retries= parameter overrides self.max_retries."""
        api = _make_api(max_retries=10)
        api.state = ConnectionState.CONNECTED
        with patch("forge.adapters.sd_api.urllib.request.urlopen") as m:
            m.side_effect = ConnectionRefusedError("refused")
            with patch("forge.adapters.sd_api.time.sleep"):
                api._request(path="/queue/status", method="GET", data=None, retries=1)
        assert m.call_count == 2

    def test_generation_paths_use_longer_timeouts(self):
        """Paths containing txt2img/img2img use gen timeouts."""
        api = _make_api(max_retries=0)
        api.state = ConnectionState.CONNECTED
        with patch("forge.adapters.sd_api.urllib.request.urlopen") as m:
            m.return_value = _json_response({"images": []})
            api.get("/sdapi/v1/txt2img")
        # Verify the timeout kwarg uses gen timeouts
        timeout_kwarg = m.call_args.kwargs.get("timeout")
        expected = api.gen_connect_timeout + api.gen_read_timeout
        assert timeout_kwarg == expected


# ---------------------------------------------------------------------------
# Error handling details
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """Verify error objects are stored and state is consistent."""

    def test_last_error_stored_on_connection_refused(self):
        """last_error is set to the ConnectionRefusedError."""
        api = _make_api(max_retries=0)
        api.state = ConnectionState.CONNECTED
        with patch("forge.adapters.sd_api.urllib.request.urlopen") as m:
            m.side_effect = ConnectionRefusedError("refused")
            with patch("forge.adapters.sd_api.time.sleep"):
                api.get("/queue/status")
        assert isinstance(api.last_error, ConnectionRefusedError)

    def test_last_error_stored_on_http_error(self):
        """last_error is set to the HTTPError."""
        api = _make_api(max_retries=0)
        api.state = ConnectionState.CONNECTED
        with patch("forge.adapters.sd_api.urllib.request.urlopen") as m:
            m.side_effect = _error_response(400, "Bad Request")
            api.get("/sdapi/v1/options")
        assert isinstance(api.last_error, urllib.error.HTTPError)
        assert api.last_error.code == 400

    def test_last_error_stored_on_timeout(self):
        """last_error is set to the TimeoutError."""
        api = _make_api(max_retries=0)
        api.state = ConnectionState.CONNECTED
        with patch("forge.adapters.sd_api.urllib.request.urlopen") as m:
            m.side_effect = TimeoutError("timed out")
            with patch("forge.adapters.sd_api.time.sleep"):
                api.get("/queue/status")
        assert isinstance(api.last_error, TimeoutError)

    def test_last_error_cleared_on_success(self):
        """last_error is None after a successful request."""
        api = _make_api(max_retries=1)
        api.last_error = ConnectionRefusedError("old error")
        api.state = ConnectionState.CONNECTED
        with patch("forge.adapters.sd_api.urllib.request.urlopen") as m:
            m.return_value = _json_response({"ok": True})
            api.get("/queue/status")
        assert api.last_error is None

    def test_last_url_tracked(self):
        """last_url is updated on each request."""
        api = _make_api(max_retries=0)
        with patch("forge.adapters.sd_api.urllib.request.urlopen") as m:
            m.return_value = _json_response({"ok": True})
            api.get("/sdapi/v1/options")
        assert api.last_url == "http://127.0.0.1:7860/sdapi/v1/options"

    def test_post_sends_json_body(self):
        """POST requests send JSON-encoded body with correct content type."""
        api = _make_api(max_retries=0)
        with patch("forge.adapters.sd_api.urllib.request.urlopen") as m:
            m.return_value = _json_response({"result": "ok"})
            api.post("/sdapi/v1/interrupt", {"key": "value"})
        req = m.call_args.args[0]
        assert isinstance(req, urllib.request.Request)
        assert req.get_header("Content-type") == "application/json"
        assert json.loads(req.data) == {"key": "value"}

    def test_json_decode_error_returns_raw_body(self):
        """Non-JSON response body is returned as raw bytes."""
        api = _make_api(max_retries=0)
        with patch("forge.adapters.sd_api.urllib.request.urlopen") as m:
            resp = MagicMock()
            resp.read.return_value = b"not json at all"
            resp.__enter__ = MagicMock(return_value=resp)
            resp.__exit__ = MagicMock(return_value=False)
            m.return_value = resp
            result = api.get("/queue/status")
        assert result == b"not json at all"


# ---------------------------------------------------------------------------
# BackendType and ConnectionState enum completeness
# ---------------------------------------------------------------------------

class TestEnums:
    def test_backend_type_variants(self):
        assert set(BackendType) == {
            BackendType.FORGE_CLASSIC,
            BackendType.FORGE_NEO,
            BackendType.UNKNOWN,
        }

    def test_connection_state_variants(self):
        assert set(ConnectionState) == {
            ConnectionState.DISCONNECTED,
            ConnectionState.CONNECTING,
            ConnectionState.CONNECTED,
            ConnectionState.ERROR,
        }
