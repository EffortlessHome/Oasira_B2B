import voluptuous as vol
from typing import List
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN

# Example constants for configuration
CONF_HOST = "host"
CONF_API_KEY = "api_key"
CONF_SYSTEM_ID = "system_id"
CONF_CUSTOMER_ID = "customer_id"

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for My Integration."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        errors = {}

        if user_input is not None:
            system_id = user_input.get(CONF_SYSTEM_ID)
            customer_id = user_input.get(CONF_CUSTOMER_ID)

            if not system_id or not customer_id:
                errors["base"] = "missing_fields"
            else:
                # Create the config entry
                return self.async_create_entry(
                    title=f"System ID: ({system_id})",
                    data={
                        CONF_SYSTEM_ID: system_id,
                        CONF_CUSTOMER_ID: customer_id,
                    },
                )

        data_schema = vol.Schema({
            vol.Required(CONF_SYSTEM_ID): str,
            vol.Required(CONF_CUSTOMER_ID): str,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

