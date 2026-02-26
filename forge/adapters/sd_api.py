from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable

from ..domain.payload_builder import build_api_payload


class SDAPI:
    DEFAULT_HOST = "http://127.0.0.1:7860"

    def __init__(self, host: str = DEFAULT_HOST, timeout_seconds: float = 30.0) -> None:
        self.timeout_seconds = timeout_seconds

        self.host = _normalize_host(host)
        self.connected = False
        self.last_url = ""

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

        self.refresh()

    def change_host(self, host: str = DEFAULT_HOST) -> None:
        self.host = _normalize_host(host)
        self.refresh()

    def refresh(self) -> None:
        if self.get_status() is None:
            self.connected = False
            return

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

    def get(self, path: str) -> Any:
        return self._request(path=path, method="GET", data=None)

    def post(self, path: str, data: dict[str, Any]) -> Any:
        return self._request(path=path, method="POST", data=data)

    def _request(self, *, path: str, method: str, data: dict[str, Any] | None) -> Any:
        url = f"{self.host}{path}"
        self.last_url = url

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
                request, timeout=self.timeout_seconds
            ) as response:
                body = response.read()

        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            return None

        try:
            return json.loads(body)
        except (TypeError, json.JSONDecodeError):
            return body

    def get_status(self) -> Any:
        return self.get("/queue/status")

    def get_system_status(self) -> Any:
        return self.get("/sdapi/v1/system-info/status")

    def get_progress(self) -> Any:
        return self.get("/sdapi/v1/progress")

    def get_options(self) -> dict[str, Any]:
        options = self.get("/sdapi/v1/options")
        if not isinstance(options, dict):
            options = {}

        self.default_settings = options

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
        samplers = self.get("/sdapi/v1/samplers")
        self.samplers = samplers if isinstance(samplers, list) else []
        return self.samplers

    def get_upscalers(self) -> list[dict[str, Any]]:
        upscalers = self.get("/sdapi/v1/upscalers")
        self.upscalers = upscalers if isinstance(upscalers, list) else []
        return self.upscalers

    def get_models(self) -> list[dict[str, Any]]:
        models = self.get("/sdapi/v1/sd-models")
        self.models = models if isinstance(models, list) else []
        return self.models

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
        restorers = self.get("/sdapi/v1/face-restorers")
        self.facerestorers = restorers if isinstance(restorers, list) else []
        return self.facerestorers

    def get_styles(self) -> list[dict[str, Any]]:
        styles = self.get("/sdapi/v1/prompt-styles")
        self.styles = styles if isinstance(styles, list) else []
        return self.styles

    def get_vaes(self) -> list[dict[str, Any]]:
        vaes = self.get("/sdapi/v1/sd-vae")
        self.vaes = vaes if isinstance(vaes, list) else []
        return self.vaes

    def get_scripts(self) -> dict[str, list[str]]:
        scripts = self.get("/sdapi/v1/scripts")
        self.scripts = scripts if isinstance(scripts, dict) else {}
        return self.scripts

    def get_loras(self) -> list[dict[str, Any]]:
        loras = self.get("/sdapi/v1/loras")
        self.loras = loras if isinstance(loras, list) else []
        return self.loras

    def get_embeddings(self) -> dict[str, Any]:
        embeddings = self.get("/sdapi/v1/embeddings")
        self.embeddings = embeddings if isinstance(embeddings, dict) else {}
        return self.embeddings

    def get_hypernetworks(self) -> list[dict[str, Any]]:
        hypernetworks = self.get("/sdapi/v1/hypernetworks")
        self.hypernetworks = hypernetworks if isinstance(hypernetworks, list) else []
        return self.hypernetworks

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


__all__ = ["SDAPI"]
