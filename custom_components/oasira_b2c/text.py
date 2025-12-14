from homeassistant.helpers.entity import Entity
from homeassistant.components.text import TextEntity
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
import logging

from .const import DOMAIN, NAME

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([AIAutomationSuggestionTextEntity()], True)
    async_add_entities([AIWellnessSuggestionTextEntity()], True)
    async_add_entities([AIEnergySuggestionTextEntity()], True)
    async_add_entities([AIMaintenanceSuggestionTextEntity()], True)
    async_add_entities([AIClimateSuggestionTextEntity()], True)
    async_add_entities([AISafetySuggestionTextEntity()], True)
    async_add_entities([AIHomeStatusTextEntity()], True)

class AIAutomationSuggestionTextEntity(TextEntity, RestoreEntity):
    """A simple text entity that allows getting and setting a value."""

    def __init__(self):
        self._attr_name = "AIAutomationSuggestion"
        self._attr_unique_id = "AIAutomationSuggestion"
        self._value = ""

    @property
    def native_value(self):
        return self._value

    @property
    def device_info(self):
        """Return information about the device."""
        return {
            "identifiers": {(DOMAIN, NAME)},
            "name": NAME,
            "manufacturer": NAME,
        }        

    async def async_set_value(self, value: str) -> None:
        self._value = value
        self.async_write_ha_state()

    async def async_added_to_hass(self):
        """Restore previous state when entity is added."""
        await super().async_added_to_hass()

        if (last_state := await self.async_get_last_state()) is not None:
            self._value = last_state.state    

class AIWellnessSuggestionTextEntity(TextEntity, RestoreEntity):
    """A simple text entity that allows getting and setting a value."""

    def __init__(self):
        self._attr_name = "AIWellnessSuggestion"
        self._attr_unique_id = "AIWellnessSuggestion"
        self._value = ""

    @property
    def native_value(self):
        return self._value

    @property
    def device_info(self):
        """Return information about the device."""
        return {
            "identifiers": {(DOMAIN, NAME)},
            "name": NAME,
            "manufacturer": NAME,
        }

    async def async_set_value(self, value: str) -> None:
        self._value = value
        self.async_write_ha_state()  

    async def async_added_to_hass(self):
        """Restore previous state when entity is added."""
        await super().async_added_to_hass()

        if (last_state := await self.async_get_last_state()) is not None:
            self._value = last_state.state    

class AIEnergySuggestionTextEntity(TextEntity, RestoreEntity):
    """A simple text entity that allows getting and setting a value."""

    def __init__(self):
        self._attr_name = "AIEnergySuggestion"
        self._attr_unique_id = "AIEnergySuggestion"
        self._value = ""

    @property
    def native_value(self):
        return self._value

    @property
    def device_info(self):
        """Return information about the device."""
        return {
            "identifiers": {(DOMAIN, NAME)},
            "name": NAME,
            "manufacturer": NAME,
        }

    async def async_set_value(self, value: str) -> None:
        self._value = value
        self.async_write_ha_state()  

    async def async_added_to_hass(self):
        """Restore previous state when entity is added."""
        await super().async_added_to_hass()

        if (last_state := await self.async_get_last_state()) is not None:
            self._value = last_state.state    

class AIMaintenanceSuggestionTextEntity(TextEntity, RestoreEntity):
    """A simple text entity that allows getting and setting a value."""

    def __init__(self):
        self._attr_name = "AIMaintenanceSuggestion"
        self._attr_unique_id = "AIMaintenanceSuggestion"
        self._value = ""

    @property
    def native_value(self):
        return self._value

    @property
    def device_info(self):
        """Return information about the device."""
        return {
            "identifiers": {(DOMAIN, NAME)},
            "name": NAME,
            "manufacturer": NAME,
        }

    async def async_set_value(self, value: str) -> None:
        self._value = value
        self.async_write_ha_state()          

    async def async_added_to_hass(self):
        """Restore previous state when entity is added."""
        await super().async_added_to_hass()

        if (last_state := await self.async_get_last_state()) is not None:
            self._value = last_state.state    

class AIClimateSuggestionTextEntity(TextEntity, RestoreEntity):
    """A simple text entity that allows getting and setting a value."""

    def __init__(self):
        self._attr_name = "AIClimateSuggestion"
        self._attr_unique_id = "AIClimateSuggestion"
        self._value = ""

    @property
    def native_value(self):
        return self._value

    async def async_set_value(self, value: str) -> None:
        self._value = value
        self.async_write_ha_state()      

    @property
    def device_info(self):
        """Return information about the device."""
        return {
            "identifiers": {(DOMAIN, NAME)},
            "name": NAME,
            "manufacturer": NAME,
        }

    async def async_added_to_hass(self):
        """Restore previous state when entity is added."""
        await super().async_added_to_hass()

        if (last_state := await self.async_get_last_state()) is not None:
            self._value = last_state.state                        

class AISafetySuggestionTextEntity(TextEntity, RestoreEntity):
    """A simple text entity that allows getting and setting a value."""

    def __init__(self):
        self._attr_name = "AISafetySuggestion"
        self._attr_unique_id = "AISafetySuggestion"
        self._value = ""

    @property
    def native_value(self):
        return self._value

    async def async_set_value(self, value: str) -> None:
        self._value = value
        self.async_write_ha_state()                          

    @property
    def device_info(self):
        """Return information about the device."""
        return {
            "identifiers": {(DOMAIN, NAME)},
            "name": NAME,
            "manufacturer": NAME,
        }

    async def async_added_to_hass(self):
        """Restore previous state when entity is added."""
        await super().async_added_to_hass()

        if (last_state := await self.async_get_last_state()) is not None:
            self._value = last_state.state    

class AIHomeStatusTextEntity(TextEntity, RestoreEntity):
    """A simple text entity that allows getting and setting a value."""

    def __init__(self):
        self._attr_name = "AIHomeStatusSummary"
        self._attr_unique_id = "AIHomeStatusSummary"
        self._value = ""

    @property
    def native_value(self):
        return self._value

    @property
    def device_info(self):
        """Return information about the device."""
        return {
            "identifiers": {(DOMAIN, NAME)},
            "name": NAME,
            "manufacturer": NAME,
        }

    async def async_set_value(self, value: str) -> None:
        self._value = value
        self.async_write_ha_state()                          

    async def async_added_to_hass(self):
        """Restore previous state when entity is added."""
        await super().async_added_to_hass()

        if (last_state := await self.async_get_last_state()) is not None:
            self._value = last_state.state    