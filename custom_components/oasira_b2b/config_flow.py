"""Config flow for Oasira integration.

Each Home Assistant hub is enrolled as a node of a facility: an admin issues a
one-time enrollment code in Oasira Care, and the hub exchanges it for its own
revocable API key. No user account or OAuth login is involved.
"""

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .care_stream import CONF_CARE_API_KEY, CONF_CARE_API_URL
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CONF_API_URL = "api_url"
CONF_API_KEY = "api_key"
CONF_ENROLLMENT_CODE = "enrollment_code"
CONF_NODE_ID = "node_id"
CONF_NODE_NAME = "node_name"
CONF_FACILITY_ID = "facility_id"
CONF_FACILITY_NAME = "facility_name"


class EnrollmentError(Exception):
    """Raised when a node cannot be enrolled; ``reason`` is a translation error key."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def is_node_entry(entry: config_entries.ConfigEntry) -> bool:
    """Return True for entries enrolled with an API key (vs. legacy account entries)."""
    return bool(entry.data.get(CONF_API_KEY))


async def _async_enroll(hass, api_url: str, code: str, node_name: str) -> dict[str, Any]:
    """Exchange an enrollment code for a node API key."""
    session = async_get_clientsession(hass)
    try:
        async with session.post(
            f"{api_url}/ingest/enroll",
            json={"code": code, "node_name": node_name},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as response:
            if response.status in (400, 401, 404):
                raise EnrollmentError("invalid_code")
            if response.status >= 400:
                raise EnrollmentError("cannot_connect")
            data = await response.json()
    except (aiohttp.ClientError, TimeoutError) as err:
        _LOGGER.warning("Could not reach Oasira Care API at %s: %s", api_url, err)
        raise EnrollmentError("cannot_connect") from err

    if not all(data.get(k) for k in ("api_key", "node_id", "facility_id")):
        raise EnrollmentError("cannot_connect")
    return data


def _normalize_url(value: str) -> str | None:
    url = (value or "").strip().rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3]
    return url if url.startswith(("http://", "https://")) else None


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Enroll this Home Assistant hub as a node of an Oasira Care facility."""

    VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow."""
        return OasiraOptionsFlow()

    @staticmethod
    def async_supports_options_flow(config_entry: config_entries.ConfigEntry) -> bool:
        """Node entries have nothing to configure; only legacy entries keep options."""
        return not is_node_entry(config_entry)

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Collect the API URL and one-time enrollment code."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors: dict[str, str] = {}

        if user_input is not None:
            api_url = _normalize_url(user_input[CONF_API_URL])
            node_name = (user_input.get(CONF_NODE_NAME) or "").strip() or self.hass.config.location_name
            if api_url is None:
                errors[CONF_API_URL] = "invalid_url"
            else:
                try:
                    result = await _async_enroll(
                        self.hass, api_url, user_input[CONF_ENROLLMENT_CODE], node_name
                    )
                except EnrollmentError as err:
                    errors["base"] = err.reason
                else:
                    await self.async_set_unique_id(result["node_id"])
                    self._abort_if_unique_id_configured()
                    facility = result.get("facility_name") or result["facility_id"]
                    return self.async_create_entry(
                        title=f"{facility} - {result.get('node_name') or node_name}",
                        data={
                            CONF_API_URL: api_url,
                            CONF_API_KEY: result["api_key"],
                            CONF_NODE_ID: result["node_id"],
                            CONF_NODE_NAME: result.get("node_name") or node_name,
                            CONF_FACILITY_ID: result["facility_id"],
                            CONF_FACILITY_NAME: facility,
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_API_URL,
                        default=(user_input or {}).get(CONF_API_URL, ""),
                    ): str,
                    vol.Required(CONF_ENROLLMENT_CODE): str,
                    vol.Optional(
                        CONF_NODE_NAME,
                        default=(user_input or {}).get(
                            CONF_NODE_NAME, self.hass.config.location_name
                        ),
                    ): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """The node key was revoked or lost; enroll again with a new code."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict | None = None
    ) -> FlowResult:
        entry = self._get_reauth_entry()
        if not is_node_entry(entry):
            return self.async_abort(reason="legacy_entry")

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                result = await _async_enroll(
                    self.hass,
                    entry.data[CONF_API_URL],
                    user_input[CONF_ENROLLMENT_CODE],
                    entry.data.get(CONF_NODE_NAME, ""),
                )
            except EnrollmentError as err:
                errors["base"] = err.reason
            else:
                if result["facility_id"] != entry.data.get(CONF_FACILITY_ID):
                    return self.async_abort(reason="wrong_facility")
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=result["node_id"],
                    data={
                        **entry.data,
                        CONF_API_KEY: result["api_key"],
                        CONF_NODE_ID: result["node_id"],
                    },
                    reason="reauth_successful",
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_ENROLLMENT_CODE): str}),
            errors=errors,
            description_placeholders={
                "facility": entry.data.get(CONF_FACILITY_NAME, ""),
                "node": entry.data.get(CONF_NODE_NAME, ""),
            },
        )


class OasiraOptionsFlow(config_entries.OptionsFlow):
    """Configure streaming of alerts and telemetry to the Oasira Care API."""

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        """Collect the Care API URL and facility ingest key."""
        errors = {}

        if user_input is not None:
            url = (user_input.get(CONF_CARE_API_URL) or "").strip().rstrip("/")
            key = (user_input.get(CONF_CARE_API_KEY) or "").strip()
            if bool(url) != bool(key):
                errors["base"] = "care_api_incomplete"
            elif url and not url.startswith(("http://", "https://")):
                errors[CONF_CARE_API_URL] = "invalid_url"
            else:
                return self.async_create_entry(
                    data={CONF_CARE_API_URL: url, CONF_CARE_API_KEY: key}
                )

        current = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_CARE_API_URL,
                        description={"suggested_value": current.get(CONF_CARE_API_URL, "")},
                    ): str,
                    vol.Optional(
                        CONF_CARE_API_KEY,
                        description={"suggested_value": current.get(CONF_CARE_API_KEY, "")},
                    ): str,
                }
            ),
            errors=errors,
        )
