from __future__ import annotations

import copy
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

_SCHEMA_VERSION = 1


class SettingsController:
    """Load, validate, and persist plugin settings.

    User settings are applied on top of `default_settings.json` with strict schema matching.
    Unknown keys and type mismatches are ignored during merge.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        plugin_dir = base_dir or Path(os.path.dirname(os.path.realpath(__file__)))
        self._plugin_dir = plugin_dir
        self._user_settings_file = plugin_dir / "user_settings.json"
        self._default_settings_file = plugin_dir / "default_settings.json"
        self._default_settings: dict[str, Any] = {}
        self.settings: dict[str, Any] = {}
        self._save_timer: threading.Timer | None = None
        self._save_delay: float = 0.3  # 300ms debounce
        self.load()

    def load(self) -> None:
        self._default_settings = self._read_json_or_fail(self._default_settings_file)

        merged_settings = copy.deepcopy(self._default_settings)
        if self._user_settings_file.is_file():
            user_settings = self._read_json_or_empty(self._user_settings_file)

            old_version = user_settings.pop("_schema_version", 0)
            if old_version < _SCHEMA_VERSION:
                user_settings = self._migrate(user_settings, old_version)

            merged_settings = _deep_merge_with_schema(
                defaults=merged_settings,
                user_values=user_settings,
            )

        self.settings = merged_settings
        self.settings["_schema_version"] = _SCHEMA_VERSION

    def save(self) -> None:
        """Persist settings immediately."""
        if self._save_timer is not None:
            self._save_timer.cancel()
            self._save_timer = None
        self._write_json(self._user_settings_file, self.settings)

    def debounced_save(self) -> None:
        """Persist settings after a short delay, coalescing rapid calls.

        Multiple calls within 300ms are merged into a single disk write.
        Use this from slider handlers or other high-frequency callbacks.
        """
        if self._save_timer is not None:
            self._save_timer.cancel()
        self._save_timer = threading.Timer(self._save_delay, self._write_json,
                                          args=(self._user_settings_file, self.settings))
        self._save_timer.daemon = True
        self._save_timer.start()

    def restore_defaults(self) -> None:
        self.settings = copy.deepcopy(self._default_settings)
        self.save()

    def _migrate(self, settings: dict[str, Any], from_version: int) -> dict[str, Any]:
        """Apply migrations from *from_version* up to the current schema version."""
        migrated = settings.copy()

        # if from_version < 2:
        #     if "old_key" in migrated:
        #         migrated["new_key"] = migrated.pop("old_key")

        migrated["_schema_version"] = _SCHEMA_VERSION
        return migrated

    def get(self, path: str, default: Any = None) -> Any:
        try:
            node: Any = self.settings
            for key in _split_path(path):
                node = node[key]
            return node
        except (KeyError, TypeError):
            if default is not None:
                return default
            raise

    def set(self, path: str, value: Any) -> None:
        parent, leaf_key = self._resolve_parent(path)
        if leaf_key not in parent:
            raise KeyError(f"Unknown settings key: {path}")

        expected_value = parent[leaf_key]
        if not _value_matches_type(value=value, expected=expected_value):
            raise TypeError(
                f"Invalid type for '{path}': expected {type(expected_value).__name__}, "
                f"got {type(value).__name__}"
            )

        parent[leaf_key] = value

    def append(self, path: str, value: Any) -> None:
        target = self.get(path)
        if not isinstance(target, list):
            raise TypeError(f"Settings value at '{path}' is not a list")
        if value not in target:
            target.append(value)

    def remove(self, path: str, value: Any) -> None:
        target = self.get(path)
        if not isinstance(target, list):
            raise TypeError(f"Settings value at '{path}' is not a list")
        if value in target:
            target.remove(value)

    def toggle(self, path: str, value: Any | None = None) -> None:
        target = self.get(path)
        if isinstance(target, bool):
            self.set(path, not target)
            return

        if value is None:
            raise ValueError(
                f"toggle('{path}') requires a value for non-boolean settings"
            )
        if not isinstance(target, list):
            raise TypeError(f"Settings value at '{path}' is not boolean or list")

        if value in target:
            target.remove(value)
        else:
            target.append(value)

    def has(self, path: str) -> bool:
        try:
            self.get(path)
            return True
        except (KeyError, TypeError):
            return False

    def _resolve_parent(self, path: str) -> tuple[dict[str, Any], str]:
        keys = _split_path(path)
        if len(keys) == 1:
            return self.settings, keys[0]

        parent: Any = self.settings
        for key in keys[:-1]:
            parent = parent[key]
            if not isinstance(parent, dict):
                raise TypeError(f"Settings path '{path}' traverses non-dict value")

        return parent, keys[-1]

    @staticmethod
    def _read_json_or_empty(path: Path) -> dict[str, Any]:
        try:
            with path.open("r", encoding="utf-8") as file_handle:
                data = json.load(file_handle)
            if not isinstance(data, dict):
                return {}
            return data
        except (OSError, json.JSONDecodeError):
            return {}

    def _read_json_or_fail(self, path: Path) -> dict[str, Any]:
        if not path.is_file():
            raise FileNotFoundError(f"No default settings file found at '{path}'")

        try:
            with path.open("r", encoding="utf-8") as file_handle:
                data = json.load(file_handle)
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(
                f"Failed to load default settings from '{path}': {error}"
            ) from error

        if not isinstance(data, dict):
            raise RuntimeError(
                f"Default settings file '{path}' must contain a JSON object"
            )

        return data

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any]) -> None:
        try:
            with path.open("w", encoding="utf-8") as file_handle:
                json.dump(data, file_handle, indent=4)
        except OSError as error:
            raise RuntimeError(
                f"Error saving user settings to '{path}': {error}"
            ) from error


def _split_path(path: str) -> list[str]:
    keys = [part for part in path.split(".") if part]
    if not keys:
        raise ValueError("Settings path cannot be empty")
    return keys


def _deep_merge_with_schema(
    defaults: dict[str, Any], user_values: dict[str, Any]
) -> dict[str, Any]:
    merged: dict[str, Any] = copy.deepcopy(defaults)

    for key, default_value in defaults.items():
        if key not in user_values:
            continue

        incoming_value = user_values[key]

        if isinstance(default_value, dict):
            if isinstance(incoming_value, dict):
                merged[key] = _deep_merge_with_schema(default_value, incoming_value)
            continue

        if _value_matches_type(value=incoming_value, expected=default_value):
            merged[key] = incoming_value

    return merged


def _value_matches_type(value: Any, expected: Any) -> bool:
    if isinstance(expected, bool):
        return isinstance(value, bool)

    expected_type = type(expected)
    if expected_type is int:
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type is float:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type in (str, list, dict):
        return isinstance(value, expected_type)

    return isinstance(value, expected_type)
