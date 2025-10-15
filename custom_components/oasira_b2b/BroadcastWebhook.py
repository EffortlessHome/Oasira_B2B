from __future__ import annotations
import logging
from .const import DOMAIN
from homeassistant.core import HomeAssistant, callback
from homeassistant.components import webhook

_LOGGER = logging.getLogger(__name__)

class BroadcastWebhook:
    """Class to handle Broadcast Webhook functionality."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize."""
        self.hass = hass

    async def async_setup_webhook(self) -> bool:
        _LOGGER.info("Setting up Broadcast Webhook")

        try:
            webhook.async_register(
                self.hass,
                DOMAIN,
                "Broadcast Webhook",
                "oasira_broadcast",
                self.handle_webhook,
            )
        except Exception as e:
            _LOGGER.info(f"Error setting up Broadcast Webhook: {e}")

        return True

    async def handle_webhook(self, hass: HomeAssistant, webhook_id, request) -> None:
        """Handle incoming webhook requests."""
        _LOGGER.info("In broadcast handle webhook")

        if request.method not in ["POST", "PUT"]:
            return  # Ignore methods other than POST or PUT

        try:
            responsejson = await request.json()
            _LOGGER.info("Webhook JSON: %s", responsejson)

            # 1) Send notification using notify.notify
            await hass.services.async_call(
                "notify",
                "notify",
                {
                    "message": responsejson.get("message", str(responsejson)),
                    "title": responsejson.get("title", "Broadcast Message"),
                    "data": responsejson.get("data", {}),
                },
                blocking=False,
            )

            # 2) Fire a custom event in HA for automations
            hass.bus.async_fire(
                f"{DOMAIN}_broadcast_received",
                {"payload": responsejson},
            )
            _LOGGER.debug("Fired event %s_broadcast_received", DOMAIN)

        except ValueError:
            _LOGGER.info("Webhook JSON error: invalid JSON body")
            return

async def async_remove(self) -> None:
    """Unregister the webhook when the integration is removed."""
    try:
        webhook.async_unregister(self.hass, "oasira_broadcast")
        _LOGGER.info("Broadcast Webhook unregistered")
    except Exception as e:
        _LOGGER.info(f"Error unregistering webhook: {e}")
