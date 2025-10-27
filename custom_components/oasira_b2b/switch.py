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
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import UndefinedType
from homeassistant.helpers.restore_state import RestoreEntity

from .auto_area import AutoArea
from .const import DOMAIN
from .medication_tracking import MedicationTrackingSwitch
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
            # PresenceLockSwitch(auto_area),
            SleepModeSwitch(auto_area),
            RenterOccupiedSwitch(auto_area),
            MotionNotificationsSwitch(auto_area),
            MedicalAlertAlarmSwitch(auto_area, "medicalalertalarm"),
            MonitoringAlarmSwitch(auto_area, "monitoringalarm"),
            MedicationTrackingSwitch(auto_area, "medicationtracking1"),
            MedicationTrackingSwitch(auto_area, "medicationtracking2"),
            MedicationTrackingSwitch(auto_area, "medicationtracking3"),
            SmartApplianceConversionSwitch(auto_area, "SmartAppliance1"),
            SmartApplianceConversionSwitch(auto_area, "SmartAppliance2"),
            SmartApplianceConversionSwitch(auto_area, "SmartAppliance3"),
        ]
    )

    async_add_entities([PresenceSimulationSwitch(hass)])


class MedicalAlertAlarmSwitch(SwitchEntity, RestoreEntity):
    """Set up a medical alert alarm switch."""

    _attr_should_poll = False

    def __init__(self, auto_area: AutoArea, name) -> None:
        """Initialize switch."""
        self.auto_area = auto_area
        self._is_on: bool = False
        self.name = name
        self.entity_id = "switch." + name

        _LOGGER.info(
            "%s: Initialized medical alert alarm switch (%s)",
            self.auto_area.area_name,
            self.name,
        )

    @cached_property
    def name(self) -> str | UndefinedType | None:
        """Return the name of the entity."""
        return self.name

    @cached_property
    def device_info(self) -> DeviceInfo:
        """Information about this device."""
        return self.auto_area.device_info

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
        _LOGGER.info("%s: medical alert alarm turned on", self.auto_area.area_name)
        self._is_on = True
        self.schedule_update_ha_state()
        self.hass.add_job(
            self.hass.bus.async_fire,
            "medical_alert_switch_updated",
            {"is_on": self._is_on}
        )

    def turn_off(self, **kwargs):
        """Turn off switch."""
        _LOGGER.info("%s: medical alert alarm turned off", self.auto_area.area_name)
        self._is_on = False
        self.schedule_update_ha_state()
        self.hass.add_job(
            self.hass.bus.async_fire,
            "medical_alert_switch_updated",
            {"is_on": self._is_on}
        )

    async def async_added_to_hass(self):
        """Restore previous state when entity is added."""
        await super().async_added_to_hass()

        if (last_state := await self.async_get_last_state()) is not None:
            self._is_on = last_state.state == "on"        

class MonitoringAlarmSwitch(SwitchEntity, RestoreEntity):
    """Set up a monitoring alert alarm switch."""

    _attr_should_poll = False

    def __init__(self, auto_area: AutoArea, name) -> None:
        """Initialize switch."""
        self.auto_area = auto_area
        self._is_on: bool = False
        self.name = name

        _LOGGER.info(
            "%s: Initialized monitoring alarm switch (%s)",
            self.auto_area.area_name,
            self.name,
        )

    @cached_property
    def name(self) -> str | UndefinedType | None:
        """Return the name of the entity."""
        return self.name

    @property
    def unique_id(self) -> str:
        """Return the unique ID of the sensor."""
        return "monitoring_alarm"

    @cached_property
    def device_info(self) -> DeviceInfo:
        """Information about this device."""
        return self.auto_area.device_info

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
        _LOGGER.info("%s: mmonitoring alarm turned on", self.auto_area.area_name)
        self._is_on = True
        self.schedule_update_ha_state()
        self.hass.add_job(
            self.hass.bus.async_fire,
            "monitoring_alarm_switch_updated",
            {"is_on": self._is_on}
        )

    def turn_off(self, **kwargs):
        """Turn off switch."""
        _LOGGER.info("%s: monitoring alarm turned off", self.auto_area.area_name)
        self._is_on = False
        self.schedule_update_ha_state()
        self.hass.add_job(
            self.hass.bus.async_fire,
            "monitoring_alarm_switch_updated",
            {"is_on": self._is_on}
        )        

    async def async_added_to_hass(self):
        """Restore previous state when entity is added."""
        await super().async_added_to_hass()

        if (last_state := await self.async_get_last_state()) is not None:
            self._is_on = last_state.state == "on"        

class PresenceSimulationSwitch(SwitchEntity, RestoreEntity):
    """Set up a presence simulation switch."""

    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize switch."""
        self._is_on: bool = False
        self.hass = hass
        self.name = "Presence Simulation"
        self.entity_id = "switch.presence_simulation"

    @cached_property
    def name(self) -> str | UndefinedType | None:
        """Return the name of the entity."""
        return self.name

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
        self.replay_lights()

    def turn_off(self, **kwargs):
        """Turn off switch."""
        self._is_on = False
        self.schedule_update_ha_state()

    async def async_added_to_hass(self):
        """Restore previous state when entity is added."""
        await super().async_added_to_hass()

        if (last_state := await self.async_get_last_state()) is not None:
            self._is_on = last_state.state == "on"

    def replay_lights(self):
        """Replay the light states from the prior day with correct timing."""
        now = datetime.now()
        yesterday = now - timedelta(days=1)

        # Fetch historical state changes for all entities
        dic = get_significant_states(
            hass=self.hass,
            start_time=yesterday,
            entity_ids=self.hass.states.async_entity_ids("light"),
            include_start_time_state=True,
            significant_changes_only=False,
        )

        for entity_id, states in dic.items():
            if not entity_id.startswith("light."):
                continue

            for state in states:
                if state.state not in (STATE_ON, STATE_OFF):
                    continue

                # Calculate the delay from 'yesterday' to when the state change occurred
                timestamp = as_local(state.last_changed)
                delay = (timestamp - yesterday).total_seconds()

                # Avoid negative delays (in case of clock skew or bad data)
                if delay < 0:
                    continue

                # Define the coroutine to change the light state
                async def change_light(entity_id=entity_id, new_state=state.state):
                    await self.hass.services.async_call(
                        "light",
                        "turn_on" if new_state == STATE_ON else "turn_off",
                        {"entity_id": entity_id},
                    )

                # Schedule the state change with proper delay
                self.hass.loop.call_later(
                    delay,
                    lambda coro=change_light(): self.hass.async_create_task(coro)
                )
                