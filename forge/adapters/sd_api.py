from __future__ import annotations

import base64
import json
import logging
import os
import time
import urllib.error
import urllib.request
from enum import Enum
from typing import Any, Callable, Union

from ..domain.payload_builder import build_api_payload
from ..qt_compat import QColor, QPainter, QByteArray, QBuffer, QImage, QIODevice

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """Connection state machine for SD API."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class BackendType(Enum):
    """Detected Forge backend variant."""
    FORGE_CLASSIC = "forge_classic"
    FORGE_NEO = "forge_neo"
    UNKNOWN = "unknown"


class SDAPI:
    DEFAULT_HOST = "http://127.0.0.1:7860"

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        timeout_seconds: float = 30.0,
        max_retries: int = 5,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

        # Split timeouts: status checks vs generation
        self.status_connect_timeout = 3.05
        self.status_read_timeout = 10.0
        self.gen_connect_timeout = 5.05
        self.gen_read_timeout = 600.0

        self.host = _normalize_host(host)
        self.state = ConnectionState.DISCONNECTED
        self.connected = False  # backward compatibility
        self.backend_type = BackendType.UNKNOWN
        self.last_url = ""
        self.last_error: Union[
            ConnectionRefusedError, TimeoutError, urllib.error.HTTPError,
            urllib.error.URLError, None
        ] = None

        self.models: list[dict[str, Any]] = []
        self.vaes: list[dict[str, Any]] = []
        self.samplers: list[dict[str, Any]] = []
        self.upscalers: list[dict[str, Any]] = []
        self.facerestorers: list[dict[str, Any]] = []
        self.styles: list[dict[str, Any]] = []
        self.scripts: dict[str, list[str]] = {}
        self.loras: list[dict[str, Any]] = []
        self.embeddings: dict[str, Any] = {}
        self.hypernetworks: list[dict[str, Any]] = []
        self.additional_modules: list[dict[str, Any]] = []

        self.default_settings: dict[str, Any] = {}
        self.defaults = {
            "sampler": "",
            "model": "",
            "vae": "",
            "upscaler": "",
            "refiner": "",
            "face_restorer": "",
            "color_correction": True,
        }

        # TTL cache for API responses (60 seconds)
        self._cache: dict[str, tuple[float, Any]] = {}
        self._cache_ttl: float = 60.0

        self.refresh()

    def change_host(self, host: str = DEFAULT_HOST) -> None:
        self.host = _normalize_host(host)
        self._cache.clear()
        self.refresh()

    def _get_cached(self, key: str, fetch_fn) -> Any:
        """Return cached value if still fresh, otherwise fetch and cache."""
        now = time.time()
        entry = self._cache.get(key)
        if entry is not None:
            ts, value = entry
            if now - ts < self._cache_ttl:
                return value
        value = fetch_fn()
        self._cache[key] = (now, value)
        return value

    def _invalidate_cache(self, *keys: str) -> None:
        if keys:
            for k in keys:
                self._cache.pop(k, None)
        else:
            self._cache.clear()

    def refresh(self) -> None:
        status = self.get_status()
        if status is None or isinstance(self.last_error, (
            ConnectionRefusedError, urllib.error.URLError, TimeoutError
        )):
            self.state = ConnectionState.ERROR
            self.connected = False
            return

        self.state = ConnectionState.CONNECTED
        self.connected = True
        refresh_calls: list[Callable[[], Any]] = [
            self.get_models,
            self.get_vaes,
            self.get_samplers,
            self.get_upscalers,
            self.get_facerestorers,
            self.get_styles,
            self.get_scripts,
            self.get_loras,
            self.get_embeddings,
            self.get_hypernetworks,
            self.get_options,
        ]

        for refresh_call in refresh_calls:
            refresh_call()

        if self.backend_type == BackendType.FORGE_NEO:
            self.get_additional_modules()

    def get(self, path: str) -> Any:
        return self._request(path=path, method="GET", data=None)

    def post(self, path: str, data: dict[str, Any]) -> Any:
        return self._request(path=path, method="POST", data=data)

    def _request(
        self,
        *,
        path: str,
        method: str,
        data: dict[str, Any] | None,
        retries: int | None = None,
    ) -> Any:
        url = f"{self.host}{path}"
        self.last_url = url

        is_generation = any(
            kw in path
            for kw in ("txt2img", "img2img", "extra-single-image", "interrogate")
        )
        if is_generation:
            connect_timeout = self.gen_connect_timeout
            read_timeout = self.gen_read_timeout
        else:
            connect_timeout = self.status_connect_timeout
            read_timeout = self.status_read_timeout

        max_attempts = (retries if retries is not None else self.max_retries) + 1
        last_error: Union[
            ConnectionRefusedError, TimeoutError,
            urllib.error.HTTPError, urllib.error.URLError, None
        ] = None

        for attempt in range(max_attempts):
            self.state = ConnectionState.CONNECTING

            try:
                if method == "GET":
                    request = urllib.request.Request(url)
                else:
                    payload = json.dumps(data or {}).encode("utf-8")
                    request = urllib.request.Request(
                        url,
                        data=payload,
                        headers={"Content-Type": "application/json"},
                    )

                with urllib.request.urlopen(
                    request, timeout=(connect_timeout + read_timeout)
                ) as response:
                    body = response.read()

                self.state = ConnectionState.CONNECTED
                self.connected = True
                self.last_error = None

                try:
                    return json.loads(body)
                except (TypeError, json.JSONDecodeError):
                    return body

            except urllib.error.HTTPError as exc:
                last_error = exc
                self.last_error = exc
                logger.warning(
                    "HTTP %d from %s (attempt %d/%d)",
                    exc.code, url, attempt + 1, max_attempts,
                )
                if exc.code < 500:
                    self.state = ConnectionState.ERROR
                    return exc

            except urllib.error.URLError as exc:
                last_error = exc
                self.last_error = exc
                logger.warning(
                    "URL error from %s (attempt %d/%d): %s",
                    url, attempt + 1, max_attempts, exc.reason,
                )

            except TimeoutError:
                last_error = TimeoutError(
                    f"Connection to {url} timed out"
                )
                self.last_error = last_error
                logger.warning(
                    "Timeout connecting to %s (attempt %d/%d)",
                    url, attempt + 1, max_attempts,
                )

            except ConnectionRefusedError:
                last_error = ConnectionRefusedError(
                    f"Connection to {url} refused"
                )
                self.last_error = last_error
                logger.warning(
                    "Connection refused by %s (attempt %d/%d)",
                    url, attempt + 1, max_attempts,
                )

            if attempt < max_attempts - 1:
                delay = min(2 ** attempt, 30)
                logger.debug("Retrying in %ss...", delay)
                time.sleep(delay)

        self.state = ConnectionState.ERROR
        self.connected = False
        return last_error

    def get_status(self) -> Any:
        return self.get("/queue/status")

    def get_system_status(self) -> Any:
        return self.get("/sdapi/v1/system-info/status")

    def get_progress(self) -> Any:
        return self.get("/sdapi/v1/progress")

    def get_options(self) -> dict[str, Any]:
        self._invalidate_cache()
        options = self.get("/sdapi/v1/options")
        if not isinstance(options, dict):
            options = {}

        self.default_settings = options

        if "forge_preset" in options or "forge_additional_modules" in options:
            self.backend_type = BackendType.FORGE_NEO
        elif options:
            self.backend_type = BackendType.FORGE_CLASSIC

        self.defaults["sampler"] = options.get("sampler_name") or _safe_name(
            self.samplers[0] if self.samplers else {},
            "name",
        )
        self.defaults["model"] = options.get("sd_model_checkpoint", "")
        self.defaults["vae"] = options.get("sd_vae", "")
        self.defaults["upscaler"] = _safe_name(
            self.upscalers[0] if self.upscalers else {},
            "name",
        )
        self.defaults["refiner"] = options.get("sd_model_refiner", "")
        self.defaults["face_restorer"] = options.get("face_restoration_model", "")
        self.defaults["color_correction"] = bool(
            options.get("img2img_color_correction", True)
        )

        return options

    def get_samplers(self) -> list[dict[str, Any]]:
        def _fetch():
            samplers = self.get("/sdapi/v1/samplers")
            self.samplers = samplers if isinstance(samplers, list) else []
            return self.samplers
        return self._get_cached("samplers", _fetch)

    def get_upscalers(self) -> list[dict[str, Any]]:
        def _fetch():
            upscalers = self.get("/sdapi/v1/upscalers")
            self.upscalers = upscalers if isinstance(upscalers, list) else []
            return self.upscalers
        return self._get_cached("upscalers", _fetch)

    def get_models(self) -> list[dict[str, Any]]:
        def _fetch():
            models = self.get("/sdapi/v1/sd-models")
            self.models = models if isinstance(models, list) else []
            return self.models
        return self._get_cached("models", _fetch)

    def get_model_names(self) -> list[str]:
        if not self.connected:
            return []
        return [_safe_name(model, "model_name") for model in self.models]

    def get_model_name(self, title: str) -> str:
        if not title:
            return "None"

        for model in self.models:
            if _safe_name(model, "title") == title:
                return _safe_name(model, "model_name")
        return "None"

    def get_vae_names(self) -> list[str]:
        if not self.connected:
            return []
        return [_safe_name(vae, "model_name") for vae in self.vaes]

    def get_face_restorer_names(self) -> list[str]:
        if not self.connected:
            return []
        return [_safe_name(restorer, "name") for restorer in self.facerestorers]

    def get_upscaler_names(self) -> list[str]:
        if not self.connected:
            return []
        return [_safe_name(upscaler, "name") for upscaler in self.upscalers]

    def get_facerestorers(self) -> list[dict[str, Any]]:
        def _fetch():
            restorers = self.get("/sdapi/v1/face-restorers")
            self.facerestorers = restorers if isinstance(restorers, list) else []
            return self.facerestorers
        return self._get_cached("facerestorers", _fetch)

    def get_styles(self) -> list[dict[str, Any]]:
        def _fetch():
            styles = self.get("/sdapi/v1/prompt-styles")
            self.styles = styles if isinstance(styles, list) else []
            return self.styles
        return self._get_cached("styles", _fetch)

    def get_vaes(self) -> list[dict[str, Any]]:
        def _fetch():
            vaes = self.get("/sdapi/v1/sd-vae")
            self.vaes = vaes if isinstance(vaes, list) else []
            return self.vaes
        return self._get_cached("vaes", _fetch)

    def get_scripts(self) -> dict[str, list[str]]:
        def _fetch():
            scripts = self.get("/sdapi/v1/scripts")
            self.scripts = scripts if isinstance(scripts, dict) else {}
            return self.scripts
        return self._get_cached("scripts", _fetch)

    def get_loras(self) -> list[dict[str, Any]]:
        def _fetch():
            loras = self.get("/sdapi/v1/loras")
            self.loras = loras if isinstance(loras, list) else []
            return self.loras
        return self._get_cached("loras", _fetch)

    def get_embeddings(self) -> dict[str, Any]:
        def _fetch():
            embeddings = self.get("/sdapi/v1/embeddings")
            self.embeddings = embeddings if isinstance(embeddings, dict) else {}
            return self.embeddings
        return self._get_cached("embeddings", _fetch)

    def get_hypernetworks(self) -> list[dict[str, Any]]:
        def _fetch():
            hypernetworks = self.get("/sdapi/v1/hypernetworks")
            self.hypernetworks = hypernetworks if isinstance(hypernetworks, list) else []
            return self.hypernetworks
        return self._get_cached("hypernetworks", _fetch)

    def get_additional_modules(self) -> list[dict[str, Any]]:
        def _fetch():
            modules = self.get("/sdapi/v1/forge-additional-modules")
            self.additional_modules = modules if isinstance(modules, list) else []
            return self.additional_modules
        return self._get_cached("additional_modules", _fetch)

    def get_additional_modules_names(self) -> list[str]:
        if not self.connected:
            return []
        return [_safe_name(m, "name") for m in self.additional_modules]

    def get_samplers_and_default(self) -> tuple[list[str], str]:
        if not self.connected:
            return [], "None"
        names = [_safe_name(sampler, "name") for sampler in self.samplers]
        return names, self.defaults["sampler"]

    def get_models_and_default(self) -> tuple[list[str], str]:
        if not self.connected:
            return [], "None"
        titles = [_safe_name(model, "title") for model in self.models]
        return titles, self.defaults["model"]

    def get_vaes_and_default(self) -> tuple[list[str], str]:
        if not self.connected:
            return [], "None"
        names = [_safe_name(vae, "model_name") for vae in self.vaes]
        return names, self.defaults["vae"]

    def get_upscaler_and_default(self) -> tuple[list[str], str]:
        if not self.connected:
            return [], "None"
        names = [_safe_name(upscaler, "name") for upscaler in self.upscalers]
        return names, self.defaults["upscaler"]

    def get_refiners_and_default(self) -> tuple[list[str], str]:
        if not self.connected:
            return [], "None"

        refiner_titles = [_safe_name(model, "title") for model in self.models]
        if "None" not in refiner_titles:
            refiner_titles = ["None", *refiner_titles]
        return refiner_titles, self.defaults["refiner"]

    def get_face_restorers_and_default(self) -> tuple[list[str], str]:
        if not self.connected:
            return [], "None"
        names = [_safe_name(restorer, "name") for restorer in self.facerestorers]
        return names, self.defaults["face_restorer"]

    def script_installed(self, script_name: str) -> bool:
        if not self.connected or not self.scripts:
            return False

        script_name_lower = script_name.lower()
        for scripts_for_mode in self.scripts.values():
            if not isinstance(scripts_for_mode, list):
                continue
            if script_name_lower in [item.lower() for item in scripts_for_mode]:
                return True
        return False

    def get_style_names(self) -> list[str]:
        if not self.connected:
            return []
        return [_safe_name(style, "name") for style in self.styles]

    def get_style_prompts(self, names: list[str]) -> tuple[str, str]:
        if not self.connected:
            return "", ""

        prompts = [
            str(style.get("prompt", ""))
            for style in self.styles
            if style.get("name") in names
        ]
        negative_prompts = [
            str(style.get("negative_prompt", ""))
            for style in self.styles
            if style.get("name") in names
        ]

        return ", ".join(filter(None, prompts)), ", ".join(
            filter(None, negative_prompts)
        )

    def get_lora_names(self) -> list[str]:
        if not self.connected:
            return []
        return [_safe_name(lora, "name") for lora in self.loras]

    def get_embedding_names(self) -> list[str]:
        loaded = self.embeddings.get("loaded")
        if isinstance(loaded, dict):
            return list(loaded.keys())
        return []

    def get_hypernetwork_names(self) -> list[str]:
        if not self.connected:
            return []
        return [_safe_name(network, "name") for network in self.hypernetworks]

    def interrupt(self) -> None:
        self.post("/sdapi/v1/interrupt", {})

    def build_payload(self, data: dict[str, Any]) -> dict[str, Any]:
        return build_api_payload(data)

    def txt2img(self, data: dict[str, Any]) -> dict[str, Any] | None:
        payload = self.build_payload(data)
        results = self.post("/sdapi/v1/txt2img", payload)
        return self._normalize_generation_results(payload, results)

    def img2img(self, data: dict[str, Any]) -> dict[str, Any] | None:
        payload = self.build_payload(data)
        results = self.post("/sdapi/v1/img2img", payload)
        return self._normalize_generation_results(payload, results)

    def extra(self, data: dict[str, Any]) -> dict[str, Any] | None:
        payload = self.build_payload(data)
        results = self.post("/sdapi/v1/extra-single-image", payload)
        if isinstance(results, dict):
            self.log_request_and_response(payload, results)
            return results
        return None

    def interrogate(self, data: dict[str, Any]) -> dict[str, Any] | None:
        results = self.post("/sdapi/v1/interrogate", data)
        if isinstance(results, dict):
            self.log_request_and_response(data, results)
            return results
        return None

    def _normalize_generation_results(
        self, payload: dict[str, Any], results: Any
    ) -> dict[str, Any] | None:
        if not isinstance(results, dict):
            return None

        info = results.get("info")
        if isinstance(info, str):
            try:
                results["info"] = json.loads(info)
            except json.JSONDecodeError:
                pass

        self.log_request_and_response(payload, results)
        return results

    def log_request_and_response(
        self,
        data: dict[str, Any],
        response: dict[str, Any],
        filename: str = "log.json",
    ) -> None:
        plugin_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        log_path = os.path.join(plugin_dir, filename)
        with open(log_path, "w", encoding="utf-8") as output_file:
            json.dump({"request": data, "response": response}, output_file)

    def write_img_to_file(self, base64_str: str, filename: str = "saved.png") -> None:
        with open(filename, "wb") as output_file:
            output_file.write(base64.b64decode(base64_str))

    def read_img_from_file(self, filename: str = "saved.png") -> str:
        with open(filename, "rb") as input_file:
            encoded = base64.b64encode(input_file.read())
        return encoded.decode("utf-8")

    def read_json_file(self, filename: str = "log.json") -> dict[str, Any]:
        with open(filename, "r", encoding="utf-8") as input_file:
            return json.load(input_file)

    def tiled_generate(
        self,
        data: dict[str, Any],
        tile_size: int = 1024,
        overlap: int = 64,
    ) -> dict[str, Any] | None:
        """Generate a large image by splitting into tiles, generating each, and blending."""
        src_b64: str | None = (
            data.get("img2img_img")
            or data.get("inpaint_img")
        )

        if src_b64 is None:
            logger.warning(
                "tiled_generate: no source image found in data; "
                "falling back to regular txt2img"
            )
            return self.txt2img(data)

        src_bytes = base64.b64decode(src_b64)
        fmt = "PNG" if src_b64[:8] == "iVBORw0KGgo" else "JPEG"
        src_image = QImage.fromData(src_bytes, fmt)
        if src_image.isNull():
            logger.error("tiled_generate: failed to decode source image")
            return None

        full_width = src_image.width()
        full_height = src_image.height()

        if full_width <= tile_size and full_height <= tile_size:
            return self.img2img(data)

        tiles = self.split_into_tiles(src_b64, tile_size, overlap)
        if not tiles:
            logger.error("tiled_generate: tile splitting returned no tiles")
            return None

        logger.info(
            "tiled_generate: split %dx%d image into %d tiles (tile=%d, overlap=%d)",
            full_width, full_height, len(tiles), tile_size, overlap,
        )

        generated_tiles: list[dict[str, Any]] = []

        for idx, tile in enumerate(tiles):
            tile_data = dict(data)
            tile_data["img2img_img"] = tile["tile_b64"]
            tile_data["width"] = tile["w"]
            tile_data["height"] = tile["h"]
            tile_data["resize_mode"] = 1

            logger.debug(
                "tiled_generate: generating tile %d/%d at (%d,%d) %dx%d",
                idx + 1, len(tiles), tile["x"], tile["y"], tile["w"], tile["h"],
            )

            result = self.img2img(tile_data)
            if result is None:
                logger.error("tiled_generate: tile %d generation failed", idx)
                return None

            images = result.get("images", [])
            if not images:
                logger.error("tiled_generate: tile %d returned no images", idx)
                return None

            generated_tiles.append({
                "x": tile["x"],
                "y": tile["y"],
                "w": tile["w"],
                "h": tile["h"],
                "tile_b64": images[0],
            })

        reconstructed_b64 = self.reconstruct_from_tiles(
            generated_tiles, full_width, full_height, overlap,
        )

        if not reconstructed_b64:
            logger.error("tiled_generate: reconstruction failed")
            return None

        return {
            "images": [reconstructed_b64],
            "info": result.get("info", {}) if result else {},
        }

    @staticmethod
    def split_into_tiles(
        image_data_b64: str,
        tile_size: int,
        overlap: int,
    ) -> list[dict[str, Any]]:
        """Split a base64-encoded image into overlapping tiles.

        Returns a list of dicts with keys: x, y, w, h, tile_b64.
        """
        src_bytes = base64.b64decode(image_data_b64)
        fmt = "PNG" if image_data_b64[:8] == "iVBORw0KGgo" else "JPEG"
        src_image = QImage.fromData(src_bytes, fmt)
        if src_image.isNull():
            return []

        if src_image.format() != QImage.Format.Format_RGBA8888:
            src_image = src_image.convertToFormat(QImage.Format.Format_RGBA8888)

        full_width = src_image.width()
        full_height = src_image.height()
        step = max(tile_size - overlap, 1)

        tiles: list[dict[str, Any]] = []

        y = 0
        while y < full_height:
            x = 0
            while x < full_width:
                tw = min(tile_size, full_width - x)
                th = min(tile_size, full_height - y)

                tile_img = src_image.copy(x, y, tw, th)

                byte_arr = QByteArray()
                buf = QBuffer(byte_arr)
                buf.open(QIODevice.OpenModeFlag.WriteOnly)
                tile_img.save(buf, "PNG")
                tile_b64 = byte_arr.toBase64().data().decode()

                tiles.append({
                    "x": x,
                    "y": y,
                    "w": tw,
                    "h": th,
                    "tile_b64": tile_b64,
                })

                if x + tile_size >= full_width:
                    break
                x += step

            if y + tile_size >= full_height:
                break
            y += step

        return tiles

    @staticmethod
    def reconstruct_from_tiles(
        tiles: list[dict[str, Any]],
        full_width: int,
        full_height: int,
        overlap: int,
    ) -> str:
        """Reconstruct full image from generated tiles with seam blending.

        Returns a base64-encoded PNG of the reconstructed image.
        """
        result = QImage(full_width, full_height, QImage.Format.Format_RGBA8888)
        result.fill(0)

        weight = QImage(full_width, full_height, QImage.Format.Format_Grayscale8)
        weight.fill(0)

        half_overlap = max(overlap // 2, 1)

        for tile in tiles:
            tile_b64 = tile["tile_b64"]
            tx, ty = tile["x"], tile["y"]
            tw, th = tile["w"], tile["h"]

            tile_bytes = base64.b64decode(tile_b64)
            fmt = "PNG" if tile_b64[:8] == "iVBORw0KGgo" else "JPEG"
            tile_img = QImage.fromData(tile_bytes, fmt)
            if tile_img.isNull():
                continue

            if tile_img.format() != QImage.Format.Format_RGBA8888:
                tile_img = tile_img.convertToFormat(QImage.Format.Format_RGBA8888)

            for ty_off in range(th):
                for tx_off in range(tw):
                    gx = tx + tx_off
                    gy = ty + ty_off

                    if gx >= full_width or gy >= full_height:
                        continue

                    dist_left = tx_off
                    dist_right = tw - 1 - tx_off
                    dist_top = ty_off
                    dist_bottom = th - 1 - ty_off

                    min_dist = min(dist_left, dist_right, dist_top, dist_bottom)

                    if overlap > 0:
                        fade = min(float(min_dist) / float(half_overlap), 1.0)
                    else:
                        fade = 1.0

                    tile_color = tile_img.pixelColor(tx_off, ty_off)
                    existing_color = result.pixelColor(gx, gy)

                    # QImage.pixel(row, col) — row=gy, col=gx for Grayscale8
                    w_val = weight.pixel(gy, gx) & 0xFF
                    existing_weight = w_val

                    new_weight = existing_weight + fade
                    if new_weight <= 0:
                        continue

                    alpha = fade / new_weight

                    r = int(existing_color.red() * (1 - alpha) + tile_color.red() * alpha)
                    g = int(existing_color.green() * (1 - alpha) + tile_color.green() * alpha)
                    b = int(existing_color.blue() * (1 - alpha) + tile_color.blue() * alpha)
                    a = int(existing_color.alpha() * (1 - alpha) + tile_color.alpha() * alpha)

                    result.setPixelColor(gx, gy, QColor(r, g, b, a))
                    weight.setPixel(gy, gx, min(int(new_weight * 255), 255))

        byte_arr = QByteArray()
        buf = QBuffer(byte_arr)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        result.save(buf, "PNG")
        return byte_arr.toBase64().data().decode()

    @staticmethod
    def blend_seams(
        tile_a: QImage,
        tile_b: QImage,
        overlap: int,
        direction: str,
    ) -> QImage:
        """Blend overlapping regions between two adjacent tiles.

        Args:
            tile_a: Left (horizontal) or top (vertical) tile.
            tile_b: Right (horizontal) or bottom (vertical) tile.
            overlap: Width of the overlapping region in pixels.
            direction: ``"horizontal"`` or ``"vertical"``.
        """
        if direction == "horizontal":
            return SDAPI._blend_horizontal(tile_a, tile_b, overlap)
        elif direction == "vertical":
            return SDAPI._blend_vertical(tile_a, tile_b, overlap)
        else:
            logger.warning("blend_seams: unknown direction %r, returning tile_a", direction)
            return tile_a.copy()

    @staticmethod
    def _blend_horizontal(
        tile_a: QImage, tile_b: QImage, overlap: int
    ) -> QImage:
        if tile_a.format() != QImage.Format.Format_RGBA8888:
            tile_a = tile_a.convertToFormat(QImage.Format.Format_RGBA8888)
        if tile_b.format() != QImage.Format.Format_RGBA8888:
            tile_b = tile_b.convertToFormat(QImage.Format.Format_RGBA8888)

        ha = tile_a.height()
        hb = tile_b.height()
        result_height = max(ha, hb)
        result_width = tile_a.width() + tile_b.width() - overlap
        result = QImage(result_width, result_height, QImage.Format.Format_RGBA8888)
        result.fill(0)

        painter = QPainter(result)
        painter.drawImage(0, 0, tile_a)

        overlap_start_x = tile_a.width() - overlap
        for x in range(overlap):
            fade_a = 1.0 - (x / max(overlap, 1))
            fade_b = x / max(overlap, 1)
            src_x = overlap_start_x + x
            dst_x = tile_a.width() + x

            for y in range(result_height):
                if y >= hb:
                    continue

                ca = tile_a.pixelColor(src_x, y) if src_x < tile_a.width() else QColor(0, 0, 0, 0)
                cb = tile_b.pixelColor(x, y)

                r = int(ca.red() * fade_a + cb.red() * fade_b)
                g = int(ca.green() * fade_a + cb.green() * fade_b)
                b = int(ca.blue() * fade_a + cb.blue() * fade_b)
                a = int(ca.alpha() * fade_a + cb.alpha() * fade_b)

                result.setPixelColor(dst_x, y, QColor(r, g, b, a))

        non_overlap_width = tile_b.width() - overlap
        if non_overlap_width > 0:
            painter.drawImage(
                tile_a.width(), 0,
                tile_b, overlap, 0, non_overlap_width, hb,
            )

        painter.end()
        return result

    @staticmethod
    def _blend_vertical(
        tile_a: QImage, tile_b: QImage, overlap: int
    ) -> QImage:
        if tile_a.format() != QImage.Format.Format_RGBA8888:
            tile_a = tile_a.convertToFormat(QImage.Format.Format_RGBA8888)
        if tile_b.format() != QImage.Format.Format_RGBA8888:
            tile_b = tile_b.convertToFormat(QImage.Format.Format_RGBA8888)

        wb = tile_b.width()
        result_width = max(tile_a.width(), wb)
        result_height = tile_a.height() + tile_b.height() - overlap
        result = QImage(result_width, result_height, QImage.Format.Format_RGBA8888)
        result.fill(0)

        painter = QPainter(result)
        painter.drawImage(0, 0, tile_a)

        overlap_start_y = tile_a.height() - overlap
        for y in range(overlap):
            fade_a = 1.0 - (y / max(overlap, 1))
            fade_b = y / max(overlap, 1)
            src_y = overlap_start_y + y
            dst_y = tile_a.height() + y

            for x in range(result_width):
                if x >= wb:
                    continue

                ca = tile_a.pixelColor(x, src_y) if src_y < tile_a.height() else QColor(0, 0, 0, 0)
                cb = tile_b.pixelColor(x, y)

                r = int(ca.red() * fade_a + cb.red() * fade_b)
                g = int(ca.green() * fade_a + cb.green() * fade_b)
                b = int(ca.blue() * fade_a + cb.blue() * fade_b)
                a = int(ca.alpha() * fade_a + cb.alpha() * fade_b)

                result.setPixelColor(x, dst_y, QColor(r, g, b, a))

        non_overlap_height = tile_b.height() - overlap
        if non_overlap_height > 0:
            painter.drawImage(
                0, tile_a.height(),
                tile_b, 0, overlap, wb, non_overlap_height,
            )

        painter.end()
        return result


def _normalize_host(host: str) -> str:
    host = host.strip()
    if not host:
        return SDAPI.DEFAULT_HOST
    return host.rstrip("/")


def _safe_name(item: Any, key: str) -> str:
    if isinstance(item, dict):
        value = item.get(key, "")
        if isinstance(value, str):
            return value
    return ""


__all__ = ["SDAPI", "BackendType", "ConnectionState"]
