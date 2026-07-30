from __future__ import annotations

from abc import ABC, abstractmethod

from ..qt_compat import QCheckBox, QSpinBox, QVBoxLayout, QWidget
from ..adapters.sd_api import SDAPI
from ..settings_controller import SettingsController


class SettingsAwareWidget:
    """Mixin providing helper methods for settings-connected widgets."""

    def create_checkbox(self, settings_key: str) -> QCheckBox:
        """Create a QCheckBox whose state is persisted to settings_controller."""
        checkbox = QCheckBox()
        checkbox.setChecked(self.settings_controller.get(settings_key))
        checkbox.toggled.connect(
            lambda: self._update_setting(settings_key, checkbox.isChecked())
        )
        return checkbox

    def create_spinbox(
        self,
        settings_key: str,
        min_val: int = 0,
        max_val: int = 100,
        step: int = 1,
    ) -> QSpinBox:
        """Create a QSpinBox whose value is persisted to settings_controller."""
        spinbox = QSpinBox()
        spinbox.setRange(min_val, max_val)
        spinbox.setSingleStep(step)
        spinbox.setValue(self.settings_controller.get(settings_key))
        spinbox.valueChanged.connect(
            lambda: self._update_setting(settings_key, spinbox.value())
        )
        return spinbox

    def add_tooltip(self, form: QWidget, text: str) -> None:
        """Set tooltip on the last two widgets in a form layout."""
        index = len(form.children()) - 2
        form.layout().itemAt(index).widget().setToolTip(text)
        form.layout().itemAt(index - 1).widget().setToolTip(text)

    def _update_setting(self, key: str, value) -> None:
        """Update a setting in the settings controller."""
        self.settings_controller.set(key, value)


class BasePage(QWidget, SettingsAwareWidget, ABC):
    """Base class for plugin pages with shared init/cleanup and settings helpers.

    Subclasses must implement draw_ui() to build their interface.
    Subclasses may override cleanup() to perform teardown.
    """

    def __init__(self, settings_controller: SettingsController, api: SDAPI) -> None:
        super().__init__()
        self.settings_controller = settings_controller
        self.api = api
        self.setLayout(QVBoxLayout())
        self.draw_ui()

    @abstractmethod
    def draw_ui(self) -> None:
        """Build the page UI. Called automatically after __init__ setup."""

    def cleanup(self) -> None:
        """Teardown hook. Subclasses may override for cleanup logic."""
