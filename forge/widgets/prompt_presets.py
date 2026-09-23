"""Prompt presets: named {prompt, negative} pairs stored in settings.

Storage lives under the top-level ``presets`` object in
``default_settings.json`` (name -> {prompt, negative}). CRUD helpers are
plain functions over ``SettingsController`` so they stay unit-testable
without Qt; ``PromptPresetsWidget`` provides the small inline UI and
merges loads into a ``PromptWidget`` through its existing
``set_generation_data`` path.
"""

from __future__ import annotations

from ..qt_compat import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
    QWidget,
)
from ..settings_controller import SettingsController

MAX_PRESETS = 50
PRESETS_KEY = "presets"


class PresetLimitError(ValueError):
    """Raised when saving a new preset would exceed ``MAX_PRESETS``."""


def list_presets(settings_controller: SettingsController) -> dict:
    """Return name -> {prompt, negative}, skipping malformed entries."""
    raw = settings_controller.get(PRESETS_KEY)
    if not isinstance(raw, dict):
        return {}
    return {
        str(name): entry
        for name, entry in raw.items()
        if isinstance(entry, dict)
    }


def get_preset(settings_controller: SettingsController, name: str):
    """Return the named preset as {prompt, negative}, or None if absent."""
    entry = list_presets(settings_controller).get(name)
    if entry is None:
        return None
    return {
        "prompt": str(entry.get("prompt", "")),
        "negative": str(entry.get("negative", "")),
    }


def _normalize_name(name: str) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Preset name is required")
    return name.strip()


def save_preset(
    settings_controller: SettingsController,
    name: str,
    prompt: str,
    negative: str = "",
) -> None:
    """Create or overwrite a preset. Raises PresetLimitError on the 51st new name."""
    name = _normalize_name(name)
    presets = list_presets(settings_controller)
    if name not in presets and len(presets) >= MAX_PRESETS:
        raise PresetLimitError(
            "Maximum of %d prompt presets reached - delete one first"
            % MAX_PRESETS
        )
    presets[name] = {"prompt": str(prompt), "negative": str(negative)}
    settings_controller.set(PRESETS_KEY, presets)
    settings_controller.save()


def rename_preset(
    settings_controller: SettingsController,
    old_name: str,
    new_name: str,
) -> bool:
    """Rename a preset; False (no-op) when *old_name* does not exist."""
    new_name = _normalize_name(new_name)
    presets = list_presets(settings_controller)
    if old_name not in presets:
        return False
    if new_name == old_name:
        return True
    presets[new_name] = presets.pop(old_name)
    settings_controller.set(PRESETS_KEY, presets)
    settings_controller.save()
    return True


def delete_preset(settings_controller: SettingsController, name: str) -> bool:
    """Delete a preset; False (no-op) when *name* does not exist."""
    presets = list_presets(settings_controller)
    if name not in presets:
        return False
    presets.pop(name)
    settings_controller.set(PRESETS_KEY, presets)
    settings_controller.save()
    return True


class PromptPresetsWidget(QWidget):
    """Inline save/load/rename/delete UI for named prompt presets."""

    def __init__(
        self,
        settings_controller: SettingsController,
        prompt_widget,
    ):
        super().__init__()
        self.settings_controller = settings_controller
        self.prompt_widget = prompt_widget
        self.selected = ""
        self.last_error = ""
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.draw_ui()
        self.refresh_presets()

    def draw_ui(self):
        select_row = QWidget()
        select_row.setLayout(QHBoxLayout())
        select_row.layout().setContentsMargins(0, 0, 0, 0)

        self.preset_select = QComboBox()
        self.preset_select.setToolTip("Saved prompt presets")
        self.preset_select.currentTextChanged.connect(self._on_selection_changed)
        select_row.layout().addWidget(self.preset_select)

        load_btn = QPushButton("Load")
        load_btn.setToolTip("Load the selected preset into the prompt boxes")
        load_btn.clicked.connect(lambda: self.on_load())
        select_row.layout().addWidget(load_btn)

        rename_btn = QPushButton("Rename")
        rename_btn.setToolTip("Rename using the name field below")
        rename_btn.clicked.connect(lambda: self.on_rename())
        select_row.layout().addWidget(rename_btn)

        delete_btn = QPushButton("Delete")
        delete_btn.setToolTip("Delete the selected preset")
        delete_btn.clicked.connect(lambda: self.on_delete())
        select_row.layout().addWidget(delete_btn)
        self.layout().addWidget(select_row)

        save_row = QWidget()
        save_row.setLayout(QHBoxLayout())
        save_row.layout().setContentsMargins(0, 0, 0, 0)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Preset name")
        save_row.layout().addWidget(self.name_edit)

        save_btn = QPushButton("Save")
        save_btn.setToolTip("Save the current prompt as a preset")
        save_btn.clicked.connect(lambda: self.on_save())
        save_row.layout().addWidget(save_btn)
        self.layout().addWidget(save_row)

        self.status_label = QLabel("")
        self.layout().addWidget(self.status_label)

    def refresh_presets(self, select: str = None):
        names = sorted(list_presets(self.settings_controller))
        try:
            self.preset_select.clear()
            self.preset_select.addItems(names)
            if select is not None:
                self.preset_select.setCurrentText(select)
        except RuntimeError:
            pass
        if select is not None and select in names:
            self.selected = select

    def _on_selection_changed(self, text):
        self.selected = str(text)

    def _edit_name(self) -> str:
        return str(self.name_edit.text())

    def _set_error(self, message: str) -> None:
        self.last_error = message or ""
        try:
            self.status_label.setText(self.last_error)
        except RuntimeError:
            pass

    def on_save(self, name: str = None) -> bool:
        if name is None:
            name = self._edit_name()
        data = self.prompt_widget.get_generation_data()
        prompt = data.get("prompt", "") if isinstance(data, dict) else ""
        negative = data.get("negative_prompt", "") if isinstance(data, dict) else ""
        try:
            save_preset(self.settings_controller, name, prompt, negative)
        except (PresetLimitError, ValueError) as error:
            self._set_error(str(error))
            return False
        self._set_error("")
        self.refresh_presets(select=str(name).strip())
        return True

    def on_load(self, name: str = None) -> bool:
        if name is None:
            name = self.selected
        entry = get_preset(self.settings_controller, name)
        if entry is None:
            self._set_error(
                "Preset '%s' not found" % name if name else "No preset selected"
            )
            return False
        self.prompt_widget.set_generation_data(
            {"prompt": entry["prompt"], "negative_prompt": entry["negative"]}
        )
        self._set_error("")
        self.selected = name
        try:
            self.preset_select.setCurrentText(name)
        except RuntimeError:
            pass
        return True

    def on_rename(self, new_name: str = None, old_name: str = None) -> bool:
        if old_name is None:
            old_name = self.selected
        if new_name is None:
            new_name = self._edit_name()
        try:
            renamed = rename_preset(self.settings_controller, old_name, new_name)
        except (PresetLimitError, ValueError) as error:
            self._set_error(str(error))
            return False
        if not renamed:
            self._set_error("Preset '%s' not found" % old_name)
            return False
        self._set_error("")
        self.refresh_presets(select=str(new_name).strip())
        return True

    def on_delete(self, name: str = None) -> bool:
        if name is None:
            name = self.selected
        if not delete_preset(self.settings_controller, name):
            self._set_error(
                "Preset '%s' not found" % name if name else "No preset selected"
            )
            return False
        self._set_error("")
        if self.selected == name:
            self.selected = ""
        self.refresh_presets()
        return True

    def get_generation_data(self) -> dict:
        return {"preset": self.selected}

    def set_generation_data(self, data: dict) -> None:
        if not isinstance(data, dict):
            return
        if "preset" in data and isinstance(data["preset"], str):
            name = data["preset"]
            self.selected = name
            try:
                self.preset_select.setCurrentText(name)
            except RuntimeError:
                pass
