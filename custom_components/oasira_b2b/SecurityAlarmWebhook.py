from __future__ import annotations
import logging
from .const import DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.components import webhook

_LOGGER = logging.getLogger(__name__)

class SecurityAlarmWebhook:
    """Class to handle Security Alarm Webhook functionality."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize."""
        self.hass = hass

    async def async_setup_webhook(self) -> bool:
        _LOGGER.info("Setting up Security Alarm Webhook")

        try:
            webhook.async_register(
                self.hass,
                DOMAIN,
                "Security Alarm Webhook",
                "alarmwebhook",
                self.handle_webhook,
            )
        except Exception as e:
            _LOGGER.info(f"Error setting up Security Alarm Webhook: {e}")

        return True

    async def handle_webhook(self, hass: HomeAssistant, webhook_id, request) -> None:
        """Handle incoming webhook requests."""
        _LOGGER.info("In security alarm handle webhook")

        if request.method not in ["POST", "PUT"]:
            return  # Ignore methods other than POST or PUT

        # Extract the JSON payload from the request
        try:
            responsejson = await request.json()

            _LOGGER.info("webhookjson:" + str(responsejson))

            alarmstate = hass.data[DOMAIN]["alarm_id"]

            if alarmstate is not None and alarmstate != "":
                alarmstatus = hass.data[DOMAIN]["alarmstatus"]

                if alarmstatus == "ACTIVE":
                    latestalarmid = hass.data[DOMAIN]["alarm_id"]

                    for event in responsejson:
                        alarm_id = event["meta"]["alarm_id"]

                        if alarm_id == latestalarmid:
                            event_type = event["event_type"]
                            hass.states.async_set(
                                DOMAIN +".alarmlasteventtype", event_type
                            )

                            if event_type == "alarm.closed":
                                hass.states.async_set(
                                    DOMAIN +".alarmstatus", "Closed"
                                )
                            elif event_type == "alarm.status.canceled":
                                hass.states.async_set(
                                    DOMAIN +".alarmstatus", "Canceled"
                                )

        except ValueError:
            _LOGGER.info("webhookjson error:" + str(ValueError))
            return  # Handle invalid JSON


async def async_remove(self) -> None:
    """Unregister the webhook when the integration is removed."""
    webhook.async_unregister(self.hass, "alarmwebhook")
