import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, NAME

CONF_SYSTEM_ID = "system_id"
CONF_CUSTOMER_ID = "customer_id"


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Oasira integration setup."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        errors = {}

        if user_input is not None:
            system_id = user_input.get(CONF_SYSTEM_ID)
            customer_id = user_input.get(CONF_CUSTOMER_ID)

            if not system_id or not customer_id:
                errors["base"] = "missing_fields"
            else:
                return self.async_create_entry(
                    title=f"{NAME} System ID: ({system_id})",
                    data={
                        CONF_SYSTEM_ID: system_id,
                        CONF_CUSTOMER_ID: customer_id,
                    },
                )

        # 🔹 Inline “instruction” text field (non-functional, just info)
        info_text = (
            "New Here? Visit https://my.oasira.ai to create an account."
        )

        data_schema = vol.Schema({
            vol.Optional("info", description={"suggested_value": info_text}): str,
            vol.Required(CONF_SYSTEM_ID): str,
            vol.Required(CONF_CUSTOMER_ID): str,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )
