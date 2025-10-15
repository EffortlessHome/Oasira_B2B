import logging

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
)

from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .alarm_common import async_cancelalarm, async_creatependingalarm
from .const import DOMAIN, ALARM_TYPE_SECURITY, VERSION, DOMAIN

CONF_HOME_MODE_NAME = "home"
CONF_AWAY_MODE_NAME = "away"
CONF_NIGHT_MODE_NAME = "night"
CONST_ALARM_CONTROL_PANEL_NAME = "Alarm Panel"

_LOGGER = logging.getLogger(__name__)
hass = None

async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities):
    """Set up the alarm control panel."""
    hass = hass
    async_add_entities([AlarmControlPanel(hass)], True)

class AlarmControlPanel(AlarmControlPanelEntity):
    """Representation of an alarm control panel."""

    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_HOME
        | AlarmControlPanelEntityFeature.ARM_AWAY
        | AlarmControlPanelEntityFeature.TRIGGER
    )
    _attr_code_arm_required = False
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, hass: HomeAssistant):
        """Initialize the alarm control panel."""
        # self._client = client
        # self._attr_unique_id = f"{client.unique}_CP"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "SecurityAlarm")},
            name=f"{DOMAIN} {CONST_ALARM_CONTROL_PANEL_NAME}",
            manufacturer=DOMAIN,
            model=CONST_ALARM_CONTROL_PANEL_NAME,
            sw_version=VERSION,
        )

        self.hass = hass
        self._alarmstate = AlarmControlPanelState.DISARMED
        self.hass.data[DOMAIN]["alarm_id"] = ""

    @property
    def name(self):
        """Return the name of the alarm control panel."""
        return "Security Alarm"

    @property
    def alarm_state(self):
        """Return the state of the alarm control panel."""
        return self._alarmstate

    @property
    def supported_features(self):
        """Return the supported features of the alarm control panel."""
        return self._attr_supported_features

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return "alarm_control_panel"

    async def async_alarm_disarm(self, code=None):
        """Send disarm command."""

        self._alarmstate = AlarmControlPanelState.DISARMED
        self.async_write_ha_state()

        await async_cancelalarm(self.hass)

    async def async_alarm_arm_home(self, code=None):
        """Send arm home command."""

        self._alarmstate = AlarmControlPanelState.ARMED_HOME
        self.async_write_ha_state()

    async def async_alarm_arm_away(self, code=None):
        """Send arm away command."""

        self._alarmstate = AlarmControlPanelState.ARMED_AWAY
        self.async_write_ha_state()

    async def async_alarm_trigger(self, code=None):
        """Trigger the alarm."""

        self._alarmstate = AlarmControlPanelState.TRIGGERED
        self.async_write_ha_state()
        await async_creatependingalarm(self.hass, ALARM_TYPE_SECURITY, None)

    @property
    def icon(self):
        # Return the specified icon or a default one
        return "mdi:shield-lock-outline"
