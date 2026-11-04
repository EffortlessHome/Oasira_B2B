"""Oasira integration."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import math
import mimetypes
import os
from os import path, walk
from pathlib import Path
import shutil
import time
from typing import TYPE_CHECKING, Any, Callable
from urllib.parse import quote

import aiohttp

import voluptuous as vol

from homeassistant.components.recorder import get_instance
from homeassistant.components import frontend
from homeassistant.config import get_default_config_dir
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback
from homeassistant.components import webhook
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.components.persistent_notification import create as notify_create
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import (
    area_registry as ar,
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
    storage,
    label_registry as lr,
    entity_registry,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceRegistry
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

import homeassistant.util.dt as dt_util
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.http.view import HomeAssistantView
from homeassistant.components.frontend import add_extra_js_url

ATTR_TITLE = "title"
ATTR_DATA = "data"

from .area_manager import AreaManager
from .care_stream import (
    CONF_CARE_API_KEY,
    CONF_CARE_API_URL,
    CareStreamer,
    is_secure_care_api_url,
)
from .auto_area import AutoArea

from .oasira import OasiraAPIClient, OasiraAPIError
from .auth_helper import ensure_valid_id_token, refresh_firebase_id_token, safe_api_call

from .const import (
    DOMAIN,
    LABELS,
    NAME,
    OASIRA_SUPERVISOR_ADDON_REPOSITORY,
    OASIRA_SUPERVISOR_ADDON_SLUG,
    name_internal,
)


from .deviceclassgroupsync import async_setup_devicegroup
from .event import EventHandler
from .MotionSensorGrouper import MotionSensorGrouper


try:
    # Older versions (pre-2025)
    from homeassistant.components.device_tracker import SOURCE_TYPE_GPS
except ImportError:
    # Newer versions (2025+)
    SOURCE_TYPE_GPS = "gps"

from aiohttp import web

LOCATION_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): str,
        vol.Required("latitude"): float,
        vol.Required("longitude"): float,
        vol.Optional("accuracy"): float,
    }
)

_LOGGER = logging.getLogger(__name__)
LEGACY_DOMAIN = "oasira"



class HASSComponent:
    """Hasscomponent."""

    # Class-level property to hold the hass instance
    hass_instance = None

    @classmethod
    def set_hass(cls, hass: HomeAssistant) -> None:
        """Set Hass."""
        cls.hass_instance = hass

    @classmethod
    def get_hass(cls):
        """Get Hass."""
        return cls.hass_instance




ACCOUNT_PLATFORMS = [
    "switch",
    "binary_sensor",
    "sensor",
    "cover",
    "light",
    "stt",
]
# Enrolled hubs keep every local entity; only the cloud-account voice platforms are skipped.
NODE_PLATFORMS = [p for p in ACCOUNT_PLATFORMS if p != "stt"]

NODE_ACCOUNT_DEFAULTS = {
    "emailaddress": "",
    "ha_token": "",
    "ha_url": "",
    "DaysHistoryToKeep": 30,
    "testmode": False,
}


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate older account entries to the current config-entry version."""
    if entry.version != 1:
        _LOGGER.error(
            "Cannot migrate Oasira config entry from unsupported version %s",
            entry.version,
        )
        return False

    data = dict(entry.data)
    if "system_id" not in data and "systemid" in data:
        data["system_id"] = data["systemid"]
    if "customer_id" not in data and "customerid" in data:
        data["customer_id"] = data["customerid"]

    hass.config_entries.async_update_entry(entry, data=data, version=2)
    _LOGGER.info("Migrated Oasira config entry to version 2")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up integration from a config entry."""
    is_node = bool(entry.data.get("api_key"))

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["entry_id"] = entry.entry_id

    # Enrolled hubs have no Oasira account; they are identified by node and facility.
    system_id = entry.data.get("system_id") or entry.data.get("node_id")
    customer_id = entry.data.get("customer_id") or entry.data.get("facility_id")
    id_token = entry.data.get("id_token")

    if not system_id:
        raise HomeAssistantError("System ID is missing in configuration.")

    if not customer_id:
        raise HomeAssistantError("Customer ID is missing in configuration.")

    HASSComponent.set_hass(hass)
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].update(
        {
            "entry_id": entry.entry_id,
            "config_entry": entry,
            "id_token": id_token,
            "refresh_token": entry.data.get("refresh_token"),
        }
    )

    if is_node:
        parsed_data = dict(NODE_ACCOUNT_DEFAULTS, name=entry.data.get("facility_name", ""))
        plan_features = None
    else:
        if not await ensure_valid_id_token(hass):
            _LOGGER.warning(
                "Startup token validation failed; refresh or reauth may be required"
            )

        id_token = hass.data[DOMAIN].get("id_token")
        parsed_data = None
        plan_features = None
        async with OasiraAPIClient(
            system_id=system_id,
            id_token=id_token,
            session=async_get_clientsession(hass),
        ) as api_client:
            async def _run_customer_system() -> Any:
                _id_token = hass.data[DOMAIN].get("id_token")
                if not _id_token:
                    raise OasiraAPIError("Missing id_token for customer/system lookup")
                async with OasiraAPIClient(
                    system_id=system_id,
                    id_token=_id_token,
                    session=async_get_clientsession(hass),
                ) as client:
                    return await client.get_customer_and_system()

            try:
                parsed_data = await safe_api_call(hass, _run_customer_system)
            except OasiraAPIError as e:
                if "401" in str(e):
                    _LOGGER.warning("Customer/system lookup failed after token refresh: %s", e)
                    raise ConfigEntryAuthFailed(
                        f"Failed to fetch customer/system data after refresh: {e}"
                    ) from e
                _LOGGER.error("Failed to fetch customer/system data: %s", e)
                raise

            if parsed_data is None:
                raise HomeAssistantError("Could not retrieve customer/system data.")

            try:
                plan_features = await api_client.get_plan_features_by_system_id()
            except Exception as pf_exc:
                _LOGGER.warning("Failed to fetch plan features: %s", pf_exc)
                plan_features = None

    hass.data[DOMAIN] = {
        "entry_id": entry.entry_id,
        "config_entry": entry,
        "emailaddress": parsed_data.get("emailaddress"),
        "ha_token": parsed_data.get("ha_token"),
        "ha_url": parsed_data.get("ha_url"),
        "systemid": system_id,
        "customerid": customer_id,
        "id_token": id_token,
        "refresh_token": entry.data.get("refresh_token"),
        "DaysHistoryToKeep": parsed_data.get("DaysHistoryToKeep"),
        "testmode": parsed_data.get("testmode"),
        "plan": parsed_data.get("name"),
        "plan_features": plan_features,
    }

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, NAME)},
        name=NAME,
        manufacturer=NAME,
        model=NAME,
    )

    await hass.config_entries.async_forward_entry_setups(
        entry, NODE_PLATFORMS if is_node else ACCOUNT_PLATFORMS
    )

    if is_node:
        care_api_url = entry.data["api_url"]
        care_api_key = entry.data["api_key"]
    else:
        care_api_url = entry.options.get(CONF_CARE_API_URL)
        care_api_key = entry.options.get(CONF_CARE_API_KEY)
    if care_api_url and care_api_key:
        if not is_secure_care_api_url(care_api_url):
            raise HomeAssistantError(
                "The Oasira Care API URL must use HTTPS before streaming can start."
            )
        streamer = CareStreamer(
            hass,
            care_api_url,
            care_api_key,
            on_auth_failed=(lambda: entry.async_start_reauth(hass)) if is_node else None,
        )
        hass.data[DOMAIN]["care_streamer"] = streamer
        await streamer.async_start()
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    register_services(hass, entry)

    # Removed deploy_latest_config(hass) from initialization. Now triggered by button entity.
    label_registry = lr.async_get(hass)

    for desired in LABELS:
        try:
            label_registry.async_create(desired)
            _LOGGER.info("Created missing label: %s", desired)
        except ValueError:
            # Label already exists → ignore
            _LOGGER.info("Label already exists: %s", desired)

    async def after_home_assistant_started(event):
        """Call this function after Home Assistant has started."""
        # Create motion sensor groups
        try:
            grouper = MotionSensorGrouper(hass)
            await grouper.create_sensor_groups()
            await grouper.create_security_sensor_group()
        except Exception as e:
            _LOGGER.warning("Failed to create motion sensor groups: %s", e)

        await loaddevicegroups(None)

    # Listen for the 'homeassistant_started' event
    entry.async_on_unload(
        hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STARTED, after_home_assistant_started
        )
    )

    # Start Firebase token refresh task (refresh every 50 minutes, tokens expire in 60 minutes)
    async def refresh_firebase_token():
        """Periodically refresh the Firebase ID token."""

        while True:
            try:
                _LOGGER.info("Refreshing Firebase ID token...")

                refresh_token = hass.data[DOMAIN].get("refresh_token")
                if not refresh_token:
                    _LOGGER.warning(
                        "No refresh token available - cannot refresh Firebase token"
                    )
                    return

                if await refresh_firebase_id_token(hass):
                    _LOGGER.info("✅ Firebase ID token refreshed successfully")
                else:
                    _LOGGER.error("Failed to refresh Firebase token")

            except OasiraAPIError as e:
                _LOGGER.error("Failed to refresh Firebase token: %s", e)
                # Continue trying even if refresh fails
            except Exception as e:
                _LOGGER.exception("Unexpected error refreshing Firebase token: %s", e)
            await asyncio.sleep(50 * 60)

    # Schedule the refresh task after setup completes to avoid blocking startup
    def schedule_refresh_task(*_) -> None:
        task = hass.async_create_task(
            refresh_firebase_token(), "oasira_b2b Firebase token refresh"
        )

        def cancel_refresh_task() -> None:
            task.cancel()

        entry.async_on_unload(cancel_refresh_task)

    if not is_node:
        entry.async_on_unload(
            hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STARTED, schedule_refresh_task
            )
        )

    return True


def _deploy_latest_config_sync(hass: HomeAssistant):
    """Synchronous helper for deploying config."""
    integration_dir = os.path.dirname(os.path.abspath(__file__))

    source_themes_dir = os.path.join(integration_dir, "themes")
    source_blueprints_dir = os.path.join(integration_dir, "blueprints")
    source_dir = os.path.join(integration_dir, "www/oasira_b2b")

    target_themes_dir = hass.config.path("themes")
    target_dir = hass.config.path("www/oasira_b2b")
    target_blueprints_dir = hass.config.path("blueprints")

    # Ensure destination directories exist
    os.makedirs(target_themes_dir, exist_ok=True)
    os.makedirs(target_dir, exist_ok=True)
    os.makedirs(target_blueprints_dir, exist_ok=True)

    # Copy entire themes directory including subfolders and files
    if os.path.exists(source_themes_dir):
        shutil.copytree(source_themes_dir, target_themes_dir, dirs_exist_ok=True)

    if os.path.exists(source_blueprints_dir):
        shutil.copytree(
            source_blueprints_dir, target_blueprints_dir, dirs_exist_ok=True
        )

    if os.path.exists(source_dir):
        shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)


async def deploy_latest_config(hass: HomeAssistant):
    """Deploy latest: theme, cards, blueprints, etc."""
    _LOGGER.info("[Oasira] Deploying latest configuration files...")
    await hass.async_add_executor_job(_deploy_latest_config_sync, hass)
    _LOGGER.info("[Oasira] Configuration deployment complete.")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""

    is_node = bool(entry.data.get("api_key"))

    unloaded = await hass.config_entries.async_unload_platforms(
        entry, NODE_PLATFORMS if is_node else ACCOUNT_PLATFORMS
    )
    if not unloaded:
        return False

    streamer = hass.data.get(DOMAIN, {}).pop("care_streamer", None)
    if streamer is not None:
        await streamer.async_stop()

    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry so Care API streaming picks up changed options."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_init(hass: HomeAssistant, entry: ConfigEntry, auto_area: AutoArea):
    """Initialize component."""
    await asyncio.sleep(5)  # wait for all area devices to be initialized

    return True


async def add_label_to_entity(call: ServiceCall) -> None:
    """Add a label to an entity."""
    entity_id = call.data.get("entity_id")
    label = call.data.get("label")

    if not entity_id or not label:
        _LOGGER.error(
            "entity_id and label are required for add_label_to_entity service"
        )
        return

    hass = HASSComponent.get_hass()
    ent_reg = er.async_get(hass)
    entity_entry = ent_reg.async_get(entity_id)

    if not entity_entry:
        _LOGGER.error(f"Entity not found: {entity_id}")
        return

    new_labels = set(entity_entry.labels)
    new_labels.add(label)

    ent_reg.async_update_entity(entity_id, labels=new_labels)
    _LOGGER.info(f"Added label '{label}' to entity '{entity_id}'")


@callback
def register_services(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register Oasira services."""

    hass.services.async_register(DOMAIN, "create_event", create_event)
    hass.services.async_register(DOMAIN, "create_alert", create_alert)
    async_register_admin_service(
        hass,
        DOMAIN,
        "update_entity",
        update_entity,
        schema=vol.Schema(
            {
                vol.Required("entity_id"): cv.entity_id,
                vol.Required("area_id"): vol.Any(cv.string, None),
            }
        ),
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        "add_label_to_entity",
        add_label_to_entity,
        schema=vol.Schema(
            {vol.Required("entity_id"): cv.entity_id, vol.Required("label"): cv.string}
        ),
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        "clean_motion_files",
        clean_motion_files,
        schema=vol.Schema(
            {vol.Optional("age", default=30): vol.All(vol.Coerce(int), vol.Range(min=1, max=3650))}
        ),
    )
    hass.services.async_register(
        DOMAIN,
        "confirm_pending_alarm",
        confirm_pending_alarm,
        schema=vol.Schema({vol.Optional("entity_id"): cv.entity_id}),
    )
    hass.services.async_register(
        DOMAIN,
        "set_in_bed_state",
        set_in_bed_state,
        schema=vol.Schema(
            {
                vol.Required("area_id"): cv.string,
                vol.Required("state"): bool,
            }
        ),
    )
    async_register_admin_service(
        hass, DOMAIN, "deploy_latest_config", handle_deploy_latest_config
    )

    def _service_unloader(service_name: str) -> Callable[[], None]:
        def _remove_service() -> None:
            hass.services.async_remove(DOMAIN, service_name)

        return _remove_service

    for service in (
        "add_label_to_entity",
        "clean_motion_files",
        "confirm_pending_alarm",
        "create_alert",
        "create_event",
        "deploy_latest_config",
        "set_in_bed_state",
        "update_entity",
    ):
        entry.async_on_unload(_service_unloader(service))

    def _clear_in_bed_entities() -> None:
        domain_data = hass.data.get(DOMAIN, {})
        domain_data.pop("in_bed_add_entities", None)
        domain_data.pop("in_bed_entities", None)

    entry.async_on_unload(_clear_in_bed_entities)


async def update_entity(call):
    """Handle the service call."""
    entity_id = call.data.get("entity_id")
    new_area = call.data.get("area_id")

    hass = call.hass
    ent_reg = entity_registry.async_get(hass)

    ent_reg.async_update_entity(entity_id, area_id=new_area)


async def set_in_bed_state(call: ServiceCall) -> None:
    """Set the in-bed binary sensor for an area."""
    hass = call.hass
    area_id = call.data["area_id"]
    if ar.async_get(hass).async_get_area(area_id) is None:
        raise HomeAssistantError(f"Unknown area: {area_id}")

    add_entities = hass.data.get(DOMAIN, {}).get("in_bed_add_entities")
    if add_entities is None:
        raise HomeAssistantError("The in-bed sensor platform is not available")

    entities = hass.data[DOMAIN].setdefault("in_bed_entities", {})
    sensor = entities.get(area_id)
    if sensor is None:
        from .binary_sensor import InBedSensor

        sensor = InBedSensor(area_id)
        sensor._attr_is_on = call.data["state"]
        entities[area_id] = sensor
        add_entities([sensor])
        return

    sensor.set_state(call.data["state"])


async def confirm_pending_alarm(call: ServiceCall) -> None:
    """Confirm a pending alarm through the Oasira API."""
    hass = call.hass
    system_id = hass.data.get(DOMAIN, {}).get("systemid")
    if not system_id:
        raise HomeAssistantError("Oasira account authentication is not configured")
    if not await ensure_valid_id_token(hass):
        raise HomeAssistantError("Could not obtain a valid Oasira API token")

    async def _confirm() -> Any:
        id_token = hass.data[DOMAIN].get("id_token")
        if not id_token:
            raise OasiraAPIError("Missing id_token for confirm_pending_alarm")
        async with OasiraAPIClient(
            system_id=system_id,
            id_token=id_token,
            session=async_get_clientsession(hass),
        ) as client:
            return await client.confirm_pending_alarm()

    try:
        await safe_api_call(hass, _confirm)
    except OasiraAPIError as err:
        _LOGGER.error("Failed to confirm pending alarm: %s", err)
        raise HomeAssistantError("Failed to confirm pending alarm") from err


def _clean_motion_files_sync(snapshots_dir: str, age_days: int) -> int:
    """Delete regular snapshot files older than age_days without following symlinks."""
    if not os.path.isdir(snapshots_dir):
        return 0

    cutoff = time.time() - age_days * 86400
    deleted = 0
    for root, _, files in os.walk(snapshots_dir, followlinks=False):
        for name in files:
            file_path = os.path.join(root, name)
            try:
                if os.path.islink(file_path):
                    continue
                if os.path.getmtime(file_path) < cutoff:
                    os.remove(file_path)
                    deleted += 1
            except OSError:
                _LOGGER.warning("Unable to remove an expired snapshot file")
    return deleted


async def clean_motion_files(call: ServiceCall) -> None:
    """Delete old snapshot files outside the event loop."""
    age_days = call.data.get("age", 30)
    deleted = await call.hass.async_add_executor_job(
        _clean_motion_files_sync, "/media/snapshots", age_days
    )
    _LOGGER.info("Removed %s expired snapshot files", deleted)


async def handle_deploy_latest_config(call: ServiceCall) -> None:
    """Deploy the packaged themes, blueprints, and frontend assets."""
    await deploy_latest_config(call.hass)


async def loaddevicegroups(calldata) -> None:
    """Load device groups."""
    hass = HASSComponent.get_hass()
    await async_setup_devicegroup(hass)


async def create_event(call: ServiceCall) -> None:
    """Create event."""
    hass = HASSComponent.get_hass()

    entity_id = call.data.get("entity_id")
    if not entity_id:
        _LOGGER.error("entity_id is required for create_event service")
        return

    devicestate = hass.states.get(entity_id)
    sensor_device_class = None
    sensor_device_name = None

    if devicestate and devicestate.attributes.get("friendly_name"):
        sensor_device_name = devicestate.attributes["friendly_name"]

    if devicestate and devicestate.attributes.get("device_class"):
        sensor_device_class = devicestate.attributes["device_class"]

    if sensor_device_class is not None and sensor_device_name is not None:
        alarmstate = hass.data[DOMAIN].get("alarm_id")

        if alarmstate and alarmstate != "":
            alarmstatus = hass.data[DOMAIN].get("alarmstatus")

            if alarmstatus == "ACTIVE":
                alarmid = alarmstate

                # Call the API to create event
                systemid = hass.data[DOMAIN].get("systemid")
                id_token = hass.data[DOMAIN].get("id_token")

                event_data = {
                    "sensor_device_class": sensor_device_class,
                    "sensor_device_name": sensor_device_name,
                }

                if not await ensure_valid_id_token(hass):
                    _LOGGER.error("Cannot create event: invalid or expired id_token")
                    return None

                async def _run_create_event() -> Any:
                    id_token = hass.data[DOMAIN].get("id_token")
                    if not id_token:
                        raise OasiraAPIError("Missing id_token for create_event")
                    async with OasiraAPIClient(
                        system_id=systemid,
                        id_token=id_token,
                        session=async_get_clientsession(hass),
                    ) as api_client:
                        return await api_client.create_event(alarmid, event_data)

                try:
                    result = await safe_api_call(hass, _run_create_event)
                    return result
                except OasiraAPIError as e:
                    _LOGGER.error("Failed to create event: %s", e)
                    return None
            return None
        return None
    return None

# Keep old name for backward compatibility
async def createevent(calldata) -> None:
    """Create event (deprecated name)."""
    await create_event(calldata)

async def create_alert(call: ServiceCall) -> None:
    """Create alert."""
    hass = HASSComponent.get_hass()
    alert_type = call.data.get("alert_type")
    alert_description = call.data.get("alert_description")
    status = call.data.get("status")

    if not alert_type or not alert_description or not status:
        _LOGGER.error(
            "alert_type, alert_description, and status are required for create_alert service"
        )
        return

    alert_data = {
        "alert_type": alert_type,
        "alert_description": alert_description,
        "status": status,
    }

    # Call the API to create alert
    systemid = hass.data[DOMAIN].get("systemid")
    id_token = hass.data[DOMAIN].get("id_token")

    if not await ensure_valid_id_token(hass):
        _LOGGER.error("Cannot create alert: invalid or expired id_token")
        return None

    async def _run_create_alert() -> Any:
        id_token = hass.data[DOMAIN].get("id_token")
        if not id_token:
            raise OasiraAPIError("Missing id_token for create_alert")
        async with OasiraAPIClient(
            system_id=systemid,
            id_token=id_token,
            session=async_get_clientsession(hass),
        ) as api_client:
            return await api_client.create_alert(alert_data)

    try:
        result = await safe_api_call(hass, _run_create_alert)
        return result
    except OasiraAPIError as e:
        _LOGGER.error("Failed to create alert: %s", e)
        return None


# Keep old name for backward compatibility
async def createalert(calldata) -> None:
    """Create alert (deprecated name)."""
    await create_alert(calldata)
