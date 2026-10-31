"""Switch platform for integration_blueprint."""

from __future__ import annotations

from functools import cached_property
import logging
import re
import pytz

from homeassistant.util.dt import as_local
from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import UndefinedType
from homeassistant.helpers.restore_state import RestoreEntity

from .auto_area import AutoArea
from .const import DOMAIN, NAME
from .motion_notification import MotionNotificationsSwitch
from .renter_occupied import RenterOccupiedSwitch
from .sleep_mode import SleepModeSwitch
from .smart_appliance_conversion import SmartApplianceConversionSwitch
from datetime import timedelta
import asyncio
from datetime import datetime, timedelta
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import discovery
from homeassistant.helpers.event import async_track_state_change
from homeassistant.components.recorder.history import get_significant_states
from homeassistant.const import STATE_ON, STATE_OFF

SCAN_INTERVAL = timedelta(seconds=5)

_LOGGER: logging.Logger = logging.getLogger(__package__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up entities."""

    auto_area = AutoArea(hass=hass, areaid="unknown")

    async_add_entities(
        [
            SmartApplianceConversionSwitch("SmartAppliance1"),
            SmartApplianceConversionSwitch("SmartAppliance2"),
            SmartApplianceConversionSwitch("SmartAppliance3"),
        ]
    )

    async_add_entities([PresenceSimulationSwitch(hass)])


class PresenceSimulationSwitch(SwitchEntity, RestoreEntity):
    """Set up a presence simulation switch."""

    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize switch."""
        self._is_on: bool = False
        self.hass = hass
        self._attr_name = "Presence Simulation"
        self.entity_id = "switch.presence_simulation"

    @property
    def device_info(self):
        """Return information about the device."""
        return {
            "identifiers": {(DOMAIN, NAME)},
            "name": NAME,
            "manufacturer": NAME,
        }

    @cached_property
    def name(self) -> str | UndefinedType | None:
        """Return the name of the entity."""
        return self._attr_name

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
        self._is_on = True
        self.schedule_update_ha_state()

    def turn_off(self, **kwargs):
        """Turn off switch."""
        self._is_on = False
        self.schedule_update_ha_state()

    async def async_added_to_hass(self):
        """Restore previous state when entity is added."""
        await super().async_added_to_hass()

        if (last_state := await self.async_get_last_state()) is not None:
            self._is_on = last_state.state == "on"


