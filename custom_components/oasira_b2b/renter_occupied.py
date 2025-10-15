from __future__ import annotations

from functools import cached_property
import logging

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.typing import UndefinedType

from .auto_area import AutoArea

_LOGGER: logging.Logger = logging.getLogger(__package__)


class RenterOccupiedSwitch(SwitchEntity):
    """Set up a renter occupied switch."""

    _attr_should_poll = False

    def __init__(self, auto_area: AutoArea) -> None:
        """Initialize switch."""
        self.auto_area = auto_area
        self._is_on: bool = False
        _LOGGER.info(
            "%s: Initialized renter occupied switch (%s)",
            self.auto_area.area_name,
            self.name,
        )

    @cached_property
    def name(self) -> str | UndefinedType | None:
        """Return the name of the entity."""
        return "Renter Occupied"

    @cached_property
    def device_info(self) -> DeviceInfo:
        """Information about this device."""
        return self.auto_area.device_info

    @property
    def unique_id(self) -> str:
        """Return the unique ID of the sensor."""
        return "renter_occupied"

    @cached_property
    def device_class(self) -> SwitchDeviceClass | None:
        """Return device class."""
        return SwitchDeviceClass.SWITCH

    @property
    def is_on(self) -> bool | None:
        """Return the state of the switch."""
        return self._is_on

    def turn_on(self, **kwargs) -> None:
        """Turn on switch."""
        _LOGGER.info("%s: Renter Occupied turned on", self.auto_area.area_name)
        self._is_on = True
        self.schedule_update_ha_state()

    def turn_off(self, **kwargs):
        """Turn off switch."""
        _LOGGER.info("%s: Renter Occupied turned off", self.auto_area.area_name)
        self._is_on = False
        self.schedule_update_ha_state()
