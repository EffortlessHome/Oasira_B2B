"""Extended Presence entity definition for my_custom_integration."""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import DOMAIN

class ExtendedPersonEntity(Entity):
    """A custom entity that tracks a single device_tracker."""

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        unique_id: str,
        device_tracker_id: str,
    ) -> None:
        """Initialize an extended presence entity."""
        self._hass = hass
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._device_tracker_id = device_tracker_id
        self._attr_icon = "mdi:account"
        
        # Initial state is unknown until the device tracker is ready
        self._attr_state = "unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        # Add the primary device tracker to the attributes
        attributes = {"primary_device_tracker": self._device_tracker_id}
        
        # Add other custom attributes here
        
        return attributes

    async def async_added_to_hass(self) -> None:
        """Register callbacks when entity is added to Home Assistant."""
        # Listen for state changes on the linked device tracker
        self.async_on_remove(
            self._hass.helpers.event.async_track_state_change_event(
                self._device_tracker_id, self._handle_tracker_update
            )
        )
        
        # Immediately call for an update in case the device tracker has already reported state
        await self._async_update_state()

    async def _handle_tracker_update(self, event) -> None:
        """Handle state changes for the single tracked device."""
        await self._async_update_state()

    async def _async_update_state(self) -> None:
        """Fetch the latest state from the device tracker."""
        tracker_state: State | None = self._hass.states.get(self._device_tracker_id)
        
        if tracker_state:
            # Sync the state of the custom entity to match the device tracker
            self._attr_state = tracker_state.state
            
            # Optionally, sync any attributes from the device tracker
            # self._attr_extra_state_attributes["source"] = tracker_state.attributes.get("source")

        self.async_write_ha_state()
