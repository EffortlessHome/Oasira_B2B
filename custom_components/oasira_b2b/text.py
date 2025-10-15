from homeassistant.helpers.entity import Entity
from homeassistant.components.text import TextEntity
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import logging

from . import const

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

class AIAutomationSuggestionTextEntity(TextEntity):
    """A simple text entity that allows getting and setting a value."""

    def __init__(self):
        self._attr_name = "AIAutomationSuggestion"
        self._attr_unique_id = "AIAutomationSuggestion"
        self._value = ""

    @property
    def native_value(self):
        return self._value

    async def async_set_value(self, value: str) -> None:
        self._value = value
        self.async_write_ha_state()

class AIWellnessSuggestionTextEntity(TextEntity):
    """A simple text entity that allows getting and setting a value."""

    def __init__(self):
        self._attr_name = "AIWellnessSuggestion"
        self._attr_unique_id = "AIWellnessSuggestion"
        self._value = ""

    @property
    def native_value(self):
        return self._value

    async def async_set_value(self, value: str) -> None:
        self._value = value
        self.async_write_ha_state()  

class AIEnergySuggestionTextEntity(TextEntity):
    """A simple text entity that allows getting and setting a value."""

    def __init__(self):
        self._attr_name = "AIEnergySuggestion"
        self._attr_unique_id = "AIEnergySuggestion"
        self._value = ""

    @property
    def native_value(self):
        return self._value

    async def async_set_value(self, value: str) -> None:
        self._value = value
        self.async_write_ha_state()  

class AIMaintenanceSuggestionTextEntity(TextEntity):
    """A simple text entity that allows getting and setting a value."""

    def __init__(self):
        self._attr_name = "AIMaintenanceSuggestion"
        self._attr_unique_id = "AIMaintenanceSuggestion"
        self._value = ""

    @property
    def native_value(self):
        return self._value

    async def async_set_value(self, value: str) -> None:
        self._value = value
        self.async_write_ha_state()          

class AIClimateSuggestionTextEntity(TextEntity):
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

class AISafetySuggestionTextEntity(TextEntity):
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

class AIHomeStatusTextEntity(TextEntity):
    """A simple text entity that allows getting and setting a value."""

    def __init__(self):
        self._attr_name = "AIHomeStatusSummary"
        self._attr_unique_id = "AIHomeStatusSummary"
        self._value = ""

    @property
    def native_value(self):
        return self._value

    async def async_set_value(self, value: str) -> None:
        self._value = value
        self.async_write_ha_state()                          