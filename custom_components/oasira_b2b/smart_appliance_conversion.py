
from __future__ import annotations

from functools import cached_property
import logging

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.helpers.typing import UndefinedType

from .auto_area import AutoArea

_LOGGER: logging.Logger = logging.getLogger(__package__)


class SmartApplianceConversionSwitch(SwitchEntity):
    """Set up a SmartApplianceConversionSwitch."""

    _attr_should_poll = False

    def __init__(self, auto_area: AutoArea, name) -> None:
        """Initialize SmartApplianceConversionSwitch"""
        self.auto_area = auto_area
        self._is_on: bool = False
        self.name = name

        _LOGGER.info(
            "%s: Initialized SmartApplianceConversionSwitch (%s)",
            self.auto_area.area_name,
            self.name,
        )

    @cached_property
    def name(self) -> str | UndefinedType | None:
        """Return the name of the entity."""
        return self.name

    @cached_property
    def device_class(self) -> SwitchDeviceClass | None:
        """Return device class."""
        return SwitchDeviceClass.SWITCH

    @cached_property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return f"{self.name}_switch"

    @property
    def is_on(self) -> bool | None:
        """Return the state of the switch."""
        return self._is_on

    def turn_on(self, **kwargs) -> None:
        """Turn on switch."""
        _LOGGER.info("%s: Motion notifications turned on", self.auto_area.area_name)
        self._is_on = True
        self.schedule_update_ha_state()

    def turn_off(self, **kwargs):
        """Turn off switch."""
        _LOGGER.info("%s: Motion notifications turned off", self.auto_area.area_name)
        self._is_on = False
        self.schedule_update_ha_state()
