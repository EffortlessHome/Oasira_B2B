from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import os
from os import path, walk
from pathlib import Path
import shutil
import subprocess
from typing import TYPE_CHECKING, List

import aiohttp

from google.api_core.exceptions import GoogleAPIError
from google import genai
import voluptuous as vol

from homeassistant.components.recorder import get_instance
from homeassistant.components import frontend
from homeassistant.components.alarm_control_panel import DOMAIN as PLATFORM
from homeassistant.components.notify import BaseNotificationService
from homeassistant.config import get_default_config_dir
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.core import ServiceCall
from homeassistant.components import webhook
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.components.persistent_notification import create as notify_create

from .energy_advisor import async_setup_energy_advisor

import homeassistant.core
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    asyncio,  
    callback,
)
from homeassistant.exceptions import (
    HomeAssistantError,
)
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry,
    entity_registry as er,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceRegistry
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers import label_registry as lr

import homeassistant.util.dt as dt_util
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.http.view import HomeAssistantView
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components import conversation

from .alarm_common import (
    async_cancelalarm,
    async_confirmpendingalarm,
    async_getalarmstatus,
)
from .area_manager import AreaManager
from .auto_area import AutoArea

from .oasiraperson import OasiraPerson

from .const import (
    DOMAIN,
    CUSTOMER_API,
    SECURITY_API,
    LABELS,
    HA_URL,
    WEBHOOK_UPDATE_PUSH_TOKEN,
    CONF_EMAIL, 
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    NAME,
    name_internal
)


from .deviceclassgroupsync import async_setup_devicegroup
from .event import EventHandler
from .MotionSensorGrouper import MotionSensorGrouper
from .SecurityAlarmWebhook import SecurityAlarmWebhook, async_remove
from .BroadcastWebhook import BroadcastWebhook, async_remove

from .virtualpowersensor import VirtualPowerSensor

from .influx import process_trend_data
from .binary_sensor import updateEntity
from .text import AIHomeStatusTextEntity
from .ai_conversation import ConversationAgent

from homeassistant.components import frontend
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.event import async_track_time_change
from homeassistant.components import person

try:
    # Older versions (pre-2025)
    from homeassistant.components.device_tracker import SOURCE_TYPE_GPS
except ImportError:
    # Newer versions (2025+)
    SOURCE_TYPE_GPS = "gps"

from aiohttp import web

LOCATION_SERVICE_SCHEMA = vol.Schema({
    vol.Required("device_id"): str,
    vol.Required("latitude"): float,
    vol.Required("longitude"): float,
    vol.Optional("accuracy"): float,
})

_LOGGER = logging.getLogger(__name__)

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

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up integration from a config entry."""
    hass.data.setdefault(DOMAIN, {})   

    # Prefer the values from entry.options (persistent & editable)
    #hass.data[DOMAIN][entry.entry_id] = entry.data

    system_id = entry.data["system_id"]
    customer_id = entry.data["customer_id"]

    if not system_id:
        raise HomeAssistantError("System ID is missing in configuration.")

    if not customer_id:
        raise HomeAssistantError("Customer ID is missing in configuration.")

    HASSComponent.set_hass(hass)

    url = CUSTOMER_API + "getcustomerandsystem/0"

    headers = {
        "accept": "application/json, text/html",
        "eh_customer_id": customer_id,
        "eh_system_id": system_id,
        "Content-Type": "application/json; charset=utf-8",
        "Accept-Encoding": "gzip, deflate, br",  # Avoid zstd
        "User-Agent": "Oasira-HA/1.0",
    }

    async with aiohttp.ClientSession() as session:  
        async with session.post(url, headers=headers, json={}) as response:
            _LOGGER.info("API response status: %s", response.status)
            _LOGGER.info("API response headers: %s", response.headers)
            content = await response.text()
            _LOGGER.info("API response content: %s", content)

            if response.status == 200 and content is not None:
                parsed_data_all = json.loads(content)
                parsed_data = parsed_data_all["results"][0]

                hass.data[DOMAIN] = {
                    "customer_psk": parsed_data["psk"],
                    "fullname": parsed_data["fullname"],
                    "phonenumber": parsed_data["phonenumber"],
                    "emailaddress": parsed_data["emailaddress"],
                    "system_psk": parsed_data["ha_security_token"],
                    "ha_token": parsed_data["ha_token"],
                    "ha_url": parsed_data["ha_url"],
                    "ai_key": parsed_data["ai_key"],
                    "ai_model": parsed_data["ai_model"],
                    "email": parsed_data["emailaddress"],
                    "username": parsed_data["emailaddress"],
                    "systemid": system_id,
                    "influx_url": parsed_data["influx_url"],
                    "influx_token": parsed_data["influx_token"],
                    "influx_bucket": parsed_data["influx_bucket"],
                    "influx_org": parsed_data["influx_org"],
                    "DaysHistoryToKeep": parsed_data["DaysHistoryToKeep"],
                    "LowTemperatureWarning": parsed_data["LowTemperatureWarning"],
                    "HighTemperatureWarning": parsed_data["HighTemperatureWarning"],
                    "LowHumidityWarning": parsed_data["LowHumidityWarning"],
                    "HighHumidityWarning": parsed_data["HighHumidityWarning"],
                    "cloudflare_token": parsed_data["cloudflare_token"],
                    "address_json": parsed_data["address_json"],
                    "systemphotolurl": parsed_data["systemphotolurl"],
                    "testmode": parsed_data["testmode"],
                    "additional_contacts_json": parsed_data["additional_contacts_json"],
                    "instructions_json": parsed_data["instructions_json"],
                    "plan": parsed_data["name"],
                    "trial_expiration": parsed_data["trial_expiration"],
                }

    #system_psk = hass.data[DOMAIN]["system_psk"]
    #customer_psk = hass.data[DOMAIN]["customer_psk"]
    #ha_url = hass.data[DOMAIN]["ha_url"]    

    #hass.states.async_set("sensor.customerid", customer_id, {"dev_mode": "off"})
    #hass.states.async_set("sensor.systemid", system_id, {"dev_mode": "off"})
    #hass.states.async_set("sensor.token", system_psk, {"dev_mode": "off"})
    #hass.states.async_set("sensor.ha_url", ha_url, {"dev_mode": "off"})
    #hass.states.async_set("sensor.customertoken", customer_psk, {"dev_mode": "off"})
#    hass.states.async_set("sensor.user", username, {"dev_mode": "off"})

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, NAME)},
        name=NAME,
        manufacturer=NAME,
        model=NAME,
    )

    ##### Get all the system's users and their roles and create entities for each ######
    url = CUSTOMER_API + "getsystemusersbysystemid/0"

    headers = {
        "accept": "application/json, text/html",
        "eh_system_id": system_id,
        "Content-Type": "application/json; charset=utf-8",
        "Accept-Encoding": "gzip, deflate, br",  # Avoid zstd
        "User-Agent": "Oasira-HA/1.0",
    }

    hass.data[DOMAIN]["persons"]: List[OasiraPerson] = []

    async with aiohttp.ClientSession() as session:  
        async with session.post(url, headers=headers, json={}) as response:
            _LOGGER.info("API response status: %s", response.status)
            _LOGGER.info("API response headers: %s", response.headers)
            content = await response.text()
            _LOGGER.info("API response content: %s", content)

            if response.status == 200 and content is not None:
                data = json.loads(content)
                for user in data["results"]:
                    person = OasiraPerson(
                        hass,
                        email=user["user_email"]
                    )

                    hass.data[DOMAIN]["persons"].append(person)

    await hass.config_entries.async_forward_entry_setups(
        entry,
        [
            "switch",
            "binary_sensor",
            "sensor",
            "cover",
            "light",
            "alarm_control_panel",
            "tts",
            "text",
            "ai_task"
        ],
    )

    agent = ConversationAgent(hass)
    conversation.async_set_agent(hass, entry, agent)

    security_webhook = SecurityAlarmWebhook(hass)
    await SecurityAlarmWebhook.async_setup_webhook(security_webhook)

    broadcast_webhook = BroadcastWebhook(hass)
    await BroadcastWebhook.async_setup_webhook(broadcast_webhook)

    webhook_id = "oasira_push_token"

    webhook.async_register(
        hass,
        DOMAIN,
        "Oasira Push Token",
        webhook_id,
        handle_oasira_push_token_webhook,
    )

    webhook_id = "oasira_location_update"

    webhook.async_register(
        hass,
        DOMAIN,
        "Oasira Push Token",
        webhook_id,
        handle_oasira_location_update_webhook,
    )

    _LOGGER.info("[Oasira] Webhook registered: %s", webhook_id)

    webhook_id = "oasira_track_device_update"

    webhook.async_register(
        hass,
        DOMAIN,
        "Oasira Tracking Devices",
        webhook_id,
        handle_set_person_location_devices,
    )

    _LOGGER.info("[Oasira] Webhook registered: %s", webhook_id)

    register_services(hass)

    # Initialize the Motion Sensor Grouper
    grouper = MotionSensorGrouper(hass)

    # Create groups for motion sensors
    await grouper.create_sensor_groups()
    await grouper.create_security_sensor_group()

    await deploy_latest_config(hass)
    label_registry = lr.async_get(hass)

    for desired in LABELS:
        try:
            label_registry.async_create(desired)
            _LOGGER.info("Created missing label: %s", desired)
        except ValueError:
            # Label already exists → ignore
            _LOGGER.info("Label already exists: %s", desired)
    
    await async_setup_energy_advisor(hass)

    async def after_home_assistant_started(event):
        """Call this function after Home Assistant has started."""
        await loaddevicegroups(None)
        await handle_home_status_summary()
        await handle_climate_suggestion()
        await handle_maintenance_suggestion()
        await handle_safety_suggestion()
        await handle_energy_suggestion()

        notify_create(
            hass,
            title="Oasira Add-on Required",
            message=(
                "The Oasira integration needs the Oasira Add-on. "
                "Click [here](https://my.home-assistant.io/redirect/supervisor_addon/?addon=<your_slug>) to install it."
            ),
        )

    # Listen for the 'homeassistant_started' event
    hass.bus.async_listen_once(
        homeassistant.core.EVENT_HOMEASSISTANT_STARTED, after_home_assistant_started
    )

    return True

async def deploy_latest_config(hass: HomeAssistant):
    # deploy latest: theme, cards, blueprints, etc.
    print("in deploy latest config")

    integration_dir = os.path.dirname(os.path.abspath(__file__))

    source_themes_dir = os.path.join(integration_dir, "themes")
    source_blueprints_dir = os.path.join(integration_dir, "blueprints")
    source_packages_dir = os.path.join(integration_dir, "packages")
    source_dir = os.path.join(integration_dir, "www/oasira")  #+ DOMAIN) #TODO: Jermie fix this
    source_dashboard_dir = os.path.join(integration_dir, "dashboards")

    target_themes_dir = "/config/themes"
    target_dir = "/config/www/oasira" #+ DOMAIN #TODO: Jermie fix this
    target_blueprints_dir = "/config/blueprints"
    target_packages_dir = "/config/packages"
    target_dashboard_dir = "/config/dashboards"

    # Ensure destination directories exist
    #os.makedirs(target_themes_dir, exist_ok=True)
    #os.makedirs(target_dir, exist_ok=True)
    os.makedirs(target_blueprints_dir, exist_ok=True)
    #os.makedirs(target_packages_dir, exist_ok=True)
    #os.makedirs(target_dashboard_dir, exist_ok=True)

    # Copy entire themes directory including subfolders and files
    #if os.path.exists(source_themes_dir):
    #    shutil.copytree(source_themes_dir, target_themes_dir, dirs_exist_ok=True)

    #if os.path.exists(source_packages_dir):
    #    shutil.copytree(source_packages_dir, target_packages_dir, dirs_exist_ok=True)

    if os.path.exists(source_blueprints_dir):
        shutil.copytree(
            source_blueprints_dir, target_blueprints_dir, dirs_exist_ok=True
        )

    #if os.path.exists(source_dir):
    #    shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)

    #if os.path.exists(source_dashboard_dir):
    #    shutil.copytree(source_dashboard_dir, target_dashboard_dir, dirs_exist_ok=True)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""

    await hass.config_entries.async_unload_platforms(
        entry,
        [
            "switch",
            "binary_sensor",
            "sensor",
            "cover",
            "light",
            "alarm_control_panel",
            "tts",
            "text",
            "ai_task",
        ],        
    )

    webhook.async_unregister(hass, "oasira_location_update")
    webhook.async_unregister(hass, "oasira_push_token")
    webhook.async_unregister(hass, "oasira_broadcast")
    webhook.async_unregister(hass, "oasira_track_device_update")

    return True

async def async_init(hass: HomeAssistant, entry: ConfigEntry, auto_area: AutoArea):
    """Initialize component."""
    await asyncio.sleep(5)  # wait for all area devices to be initialized

    return True

@callback
def register_services(hass) -> None:
    """Register security services."""

    @callback
    async def createcleanmotionfilesservice(call: ServiceCall) -> None:
        await cleanmotionfiles(call)

    hass.services.async_register(
        DOMAIN, "createcleanmotionfilesservice", cleanmotionfiles
    )

    @callback
    async def notify_person_service(call: ServiceCall) -> None:
        await handle_notify_person_service(call)

    hass.services.async_register(
        DOMAIN,
        "notify_person_service",
        handle_notify_person_service,
    )

    @callback
    async def createeventservice(call: ServiceCall) -> None:
        await createevent(call)

    @callback
    async def cancelalarmservice(call: ServiceCall) -> None:
        await cancelalarm(call)

    @callback
    async def getalarmstatusservice(call: ServiceCall) -> None:
        await getalarmstatus(call)

    @callback
    async def confirmpendingalarmservice(call: ServiceCall) -> None:
        await confirmpendingalarm(call)

    # Register our service with Home Assistant.
    hass.services.async_register(DOMAIN, "createeventservice", createevent)
    hass.services.async_register(DOMAIN, "cancelalarmservice", cancelalarm)
    hass.services.async_register(DOMAIN, "getalarmstatusservice", getalarmstatus)
    hass.services.async_register(
        DOMAIN, "confirmpendingalarmservice", confirmpendingalarm
    )

    hass.services.async_register(DOMAIN, "update_entity", update_entity)

    @callback
    async def create_alert_service(call: ServiceCall) -> None:
        await createalert(call)

    hass.services.async_register(DOMAIN, "create_alert_service", createalert)

    @callback
    async def processtrenddata(call: ServiceCall) -> None:
        await process_trend_data(call)

    hass.services.async_register(DOMAIN, "processtrenddata", process_trend_data)

    @callback
    async def deploylatestconfig(call: ServiceCall) -> None:
        await handle_deploy_latest_config(call)

    hass.services.async_register(DOMAIN, "deploylatestconfig", handle_deploy_latest_config)

    @callback
    async def set_in_bed_state(call: ServiceCall) -> None:
        await handle_set_in_bed_state(call)

    hass.services.async_register(
        DOMAIN,
        "set_in_bed_state",
        handle_set_in_bed_state,
    )

    @callback
    async def add_label_to_entity(call: ServiceCall) -> None:
        """Add a label to an entity."""
        entity_id = call.data.get("entity_id")
        label = call.data.get("label")

        if not entity_id or not label:
            _LOGGER.error(
                "entity_id and label are required for add_label_to_entity service"
            )
            return

        ent_reg = er.async_get(hass)
        entity_entry = ent_reg.async_get(entity_id)

        if not entity_entry:
            _LOGGER.error(f"Entity not found: {entity_id}")
            return

        new_labels = set(entity_entry.labels)
        new_labels.add(label)

        ent_reg.async_update_entity(entity_id, labels=new_labels)
        _LOGGER.info(f"Added label '{label}' to entity '{entity_id}'")

    hass.services.async_register(
        DOMAIN,
        "add_label_to_entity",
        add_label_to_entity,
        schema=vol.Schema(
            {vol.Required("entity_id"): cv.entity_id, vol.Required("label"): cv.string}
        ),
    )

async def update_entity(call):
    """Handle the service call."""
    entity_id = call.data.get("entity_id")
    new_area = call.data.get("area_id")

    hass = HASSComponent.get_hass()
    ent_reg = entity_registry.async_get(hass)

    ent_reg.async_update_entity(entity_id, area_id=new_area)

async def loaddevicegroups(calldata) -> None:  
    """Load device groups."""
    hass = HASSComponent.get_hass()
    await async_setup_devicegroup(hass)

async def createevent(calldata) -> None:  
    """Create event."""
    _LOGGER.info("create event calldata =" + str(calldata.data))

    hass = HASSComponent.get_hass()

    devicestate = hass.states.get(calldata.data["entity_id"])
    sensor_device_class = None
    sensor_device_name = None

    if devicestate and devicestate.attributes.get("friendly_name"):
        sensor_device_name = devicestate.attributes["friendly_name"]

    if devicestate and devicestate.attributes.get("device_class"):
        sensor_device_class = devicestate.attributes["device_class"]

    if sensor_device_class is not None and sensor_device_name is not None:
        alarmstate = hass.data[DOMAIN]["alarm_id"]

        jsonpayload = (
            '{ "sensor_device_class":"'
            + sensor_device_class
            + '", "sensor_device_name":"'
            + sensor_device_name
            + '" }'
        )

        if alarmstate is not None and alarmstate != "":
            alarmstatus = hass.data[DOMAIN]["alarmstatus"]

            if alarmstatus == "ACTIVE":
                alarmid = hass.data[DOMAIN]["alarm_id"]  # type: ignore  # noqa: PGH003
                _LOGGER.info("alarm id =" + alarmid)  # noqa: G003

                """Call the API to create event."""
                systemid = hass.data[DOMAIN]["systemid"]  # type: ignore  # noqa: PGH003
                system_psk = hass.data[DOMAIN]["system_psk"]  # type: ignore  # noqa: PGH003

                url = SECURITY_API + "createevent/" + alarmid
                headers = {
                    "accept": "application/json, text/html",
                    "system_psk": system_psk,
                    "eh_system_id": systemid,
                    "Content-Type": "application/json; charset=utf-8",
                }

                _LOGGER.info("Calling create event API with payload: %s", jsonpayload)

                async with (
                    aiohttp.ClientSession() as session,
                    session.post(
                        url, headers=headers, json=json.loads(jsonpayload)
                    ) as response,
                ):
                    _LOGGER.info("API response status: %s", response.status)
                    _LOGGER.info("API response headers: %s", response.headers)
                    content = await response.text()
                    _LOGGER.info("API response content: %s", content)

                    return content
            return None
        return None
    return None

async def createalert(calldata) -> None:  
    """Create alert."""
    _LOGGER.info("create alert calldata =" + str(calldata.data))

    hass = HASSComponent.get_hass()
    alert_type = calldata.data["alert_type"]
    alert_description = calldata.data["alert_description"]
    status = calldata.data["status"]

    jsonpayload = (
        '{ "alert_type":"'
        + alert_type
        + '", "alert_description":"'
        + alert_description
        + '", "status":"'
        + status
        + '" }'
    )

    """Call the API to create event."""
    systemid = hass.data[DOMAIN]["systemid"]  
    system_psk = hass.data[DOMAIN]["system_psk"] 

    url = SECURITY_API + "createalert/0"
    headers = {
        "accept": "application/json, text/html",
        "system_psk": system_psk,
        "eh_system_id": systemid,
        "Content-Type": "application/json; charset=utf-8",
    }

    _LOGGER.info("Calling alert API with payload: %s", jsonpayload)

    async with (
        aiohttp.ClientSession() as session,
        session.post(
            url, headers=headers, json=json.loads(jsonpayload)
        ) as response,
    ):
        _LOGGER.info("API response status: %s", response.status)
        _LOGGER.info("API response headers: %s", response.headers)
        content = await response.text()
        _LOGGER.info("API response content: %s", content)

        return content

async def cancelalarm(calldata):
    """Cancel alarm."""
    hass = HASSComponent.get_hass()

    return await async_cancelalarm(hass)


async def getalarmstatus(calldata):
    """Get alarm status."""
    hass = HASSComponent.get_hass()

    return await async_getalarmstatus(hass)


async def confirmpendingalarm(calldata):
    """Confirm pending alarm."""
    hass = HASSComponent.get_hass()

    return await async_confirmpendingalarm(hass)


async def cleanmotionfiles(calldata):
    """Execute the shell command to delete old snapshots."""

    age = "30"

    try:
        age = calldata.data["age"]
    except:
        _LOGGER.error("Invalid Args To Clean Motion Service. Using Default 30 days")

    command = "find /media/snapshots/* -mtime +" + str(age) + " -exec rm {} \\;"

    # Use subprocess to execute the shell command
    process = subprocess.run(
        command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
    )

    if process.returncode == 0:
        _LOGGER.info("Successfully deleted old snapshots.")
    else:
        _LOGGER.error(f"Error deleting snapshots: {process.stderr.decode()}")

async def handle_notify_person_service(calldata):
    """Send a notification message only to a person’s Mobile App device trackers."""
    _LOGGER.info("In async_send_message")

    hass = HASSComponent.get_hass()
    email = calldata.data.get("email")

    if not email:
        _LOGGER.info("No person provided")
        return

    message = calldata.data.get("message")
    if not message:
        _LOGGER.info("No message provided")
        return

    title = calldata.data.get("title")
    data = calldata.data.get("data")

    targetperson = None
    persons = hass.data.get(DOMAIN, {}).get("persons", [])
    for person in persons:
        if person.name == email:
            targetperson = person
            break

    if targetperson is not None:
        _LOGGER.info("[Oasira] Push Notification Target Person: "+ targetperson.name)
        await targetperson.async_send_notification(message, title, data)     
        
    else:
        _LOGGER.info("[Oasira] No matching person found for email: "+ email)
        return


async def handle_deploy_latest_config(call: ServiceCall) -> None:
    """Handle the service call."""
    hass = HASSComponent.get_hass()

    await deploy_latest_config(hass)

async def handle_set_in_bed_state(call):
    area_id = call.data.get("area_id")
    state = call.data.get("state")

    await updateEntity(area_id, state)

async def handle_home_status_summary():
    """Handle the service call to summarize home status using AI."""

    hass = HASSComponent.get_hass()

    entity_states = []
    domains_to_include = [
        "light",
        "lock",
        "binary_sensor",  # door/window only
        "climate",
        "alarm_control_panel",
        "cover",
        "media_player",
    ]

    # Gather entity states
    for state in hass.states.async_all():
        if state.domain in domains_to_include:
            if state.domain == "binary_sensor":
                device_class = state.attributes.get("device_class")
                if device_class not in ("door", "window"):
                    continue
            entity_states.append(f"{state.name}: {state.state}")

    # Build prompt for AI
    prompt = (
        "Provide a concise home status summary under 200 characters to ensure "
        "security and reduce power use when leaving home or going to bed. "
        "Provide the response in readable paragraph form suitable for TTS. "
        "Focus on: lights, locks, doors and windows, climate, alarm systems, "
        "covers, and media players. Do not include any data or anything other than the suggestion value in the response.\n\n"
        "Current states:\n" + "\n".join(entity_states)
    )

    _LOGGER.info("Generated home status prompt: %s", prompt)

    try:
        # Call the AI Task service
        response = await hass.services.async_call(
            "ai_task",
            "generate_data",
            {
                "entity_id": "ai_task."+ name_internal +"_ai_task",
                "task_name": "summarize",
                "instructions": prompt,
            },
            blocking=True,
            return_response=True,  # ensures we get the result back
        )

        if not response or "data" not in response:
            raise HomeAssistantError("No response from AI Task")

        responsetext = response["data"][:250]

        _LOGGER.info("Home status summary: %s", responsetext)

        # Store result in a text helper entity
        await hass.services.async_call(
            "text",
            "set_value",
            {
                "entity_id": "text.aihomestatussummary",
                "value": responsetext,
            },
            blocking=True,
        )

    except Exception as err:
        raise HomeAssistantError(f"Error getting AI home status: {err}") from err

async def handle_climate_suggestion():
    """Handle the service call to suggest climate improvements using AI."""

    hass = HASSComponent.get_hass()

    entity_states = []
    domains_to_include = [
        "sensor",
        "climate",
    ]

    # Gather entity states
    for state in hass.states.async_all():
        if state.domain in domains_to_include:
            entity_states.append(f"{state.name}: {state.state}")

    # Build prompt for AI
    prompt = (
        "Provide one clear and actionable suggestion to improve the climate and comfort in the home based on best practices.Tailor the advice based on the data. Keep it specific and concise. Limit to 255 chars or less. Do not include any data or anything other than the suggestion value in the response.\n\n"
        "Current states:\n" + "\n".join(entity_states)
    )

    _LOGGER.info("Generated climate suggestion prompt: %s", prompt)

    try:
        # Call the AI Task service
        response = await hass.services.async_call(
            "ai_task",
            "generate_data",
            {
                "entity_id": "ai_task."+ name_internal +"_ai_task",
                "task_name": "summarize",
                "instructions": prompt,
            },
            blocking=True,
            return_response=True,  # ensures we get the result back
        )

        if not response or "data" not in response:
            raise HomeAssistantError("No response from AI Task")

        responsetext = response["data"][:250]

        _LOGGER.info("Climate Suggestion: %s", responsetext)

        # Store result in a text helper entity
        await hass.services.async_call(
            "text",
            "set_value",
            {
                "entity_id": "text.aiclimatesuggestion",
                "value": responsetext,
            },
            blocking=True,
        )

    except Exception as err:
        raise HomeAssistantError(f"Error getting AI climate suggestion: {err}") from err

async def handle_safety_suggestion():
    """Handle the service call to suggest safety improvements using AI."""

    hass = HASSComponent.get_hass()

    entity_states = []

    # Device classes that indicate safety-related sensors
    safety_device_classes = {
        "smoke",
        "carbon_monoxide",
        "gas",
        "safety",
        "problem",
        "air_quality",
        "pm25",
        "pm10",
        "co2",
        "humidity",  # optional, some air quality sensors expose this
    }

    # Gather entity states
    for state in hass.states.async_all():
        if state.domain == "sensor" or state.domain == "binary_sensor":
            device_class = state.attributes.get("device_class")
            if device_class in safety_device_classes:
                entity_states.append(f"{state.name}: {state.state}")
        elif state.domain == "climate":
            # Optional: include air quality/humidity if climate exposes it
            if "air_quality" in state.attributes or "humidity" in state.attributes:
                entity_states.append(f"{state.name}: {state.state}")

    # Build prompt for AI
    prompt = (
        "Provide one clear and actionable suggestion to improve safety around the home. "
        "Limit to 255 chars or less.\n\n"
        "Current safety-related states:\n" + "\n".join(entity_states)
    )

    _LOGGER.info("Generated safety suggestion prompt: %s", prompt)

    try:
        # Call the AI Task service
        response = await hass.services.async_call(
            "ai_task",
            "generate_data",
            {
                "entity_id": "ai_task." + name_internal + "_ai_task",
                "task_name": "summarize",
                "instructions": prompt,
            },
            blocking=True,
            return_response=True,  # ensures we get the result back
        )

        if not response or "data" not in response:
            raise HomeAssistantError("No response from AI Task")

        responsetext = response["data"][:250]

        _LOGGER.info("Safety Suggestion: %s", responsetext)

        # Store result in a text helper entity
        await hass.services.async_call(
            "text",
            "set_value",
            {
                "entity_id": "text.aisafetysuggestion",
                "value": responsetext,
            },
            blocking=True,
        )

    except Exception as err:
        raise HomeAssistantError(f"Error getting AI safety suggestion: {err}") from err

async def handle_maintenance_suggestion():
    """Handle the service call to suggest maintenance improvements using AI."""

    hass = HASSComponent.get_hass()

    entity_states = []
    domains_to_include = [
        "sensor",
        "climate",
    ]

    # Gather entity states
    for state in hass.states.async_all():
        if state.domain in domains_to_include:
            entity_states.append(f"{state.name}: {state.state}")

    # Build prompt for AI
    prompt = (
        "Suggest one specific and practical home maintenance task (e.g., inspect HVAC filters, check for excess humidity,adjust insulation, service the AC, monitor condensation) that could help preserve home health or efficiency. Limit to 255 chars or less..\n\n"
        "Current states:\n" + "\n".join(entity_states)
    )

    _LOGGER.info("Generated maintenance suggestion prompt: %s", prompt)

    try:
        # Call the AI Task service
        response = await hass.services.async_call(
            "ai_task",
            "generate_data",
            {
                "entity_id": "ai_task."+ name_internal +"_ai_task",
                "task_name": "summarize",
                "instructions": prompt,
            },
            blocking=True,
            return_response=True,  # ensures we get the result back
        )

        if not response or "data" not in response:
            raise HomeAssistantError("No response from AI Task")

        responsetext = response["data"][:250]

        _LOGGER.info("Maintenance Suggestion: %s", responsetext)

        # Store result in a text helper entity
        await hass.services.async_call(
            "text",
            "set_value",
            {
                "entity_id": "text.aimaintenancesuggestion",
                "value": responsetext,
            },
            blocking=True,
        )

    except Exception as err:
        raise HomeAssistantError(f"Error getting AI Maintenance Suggestion: {err}") from err


async def handle_energy_suggestion():
    """Handle using AI for energy-related suggestions."""

    hass = HASSComponent.get_hass()

    entity_states = []

    # Allowed device_classes for energy/power-related sensors
    energy_device_classes = {
        "energy",
        "power",
        "current",
        "voltage",
        "apparent_power",
        "reactive_power",
        "power_factor",
        "battery",  # optional, if you want battery monitoring included
    }

    # Gather entity states
    for state in hass.states.async_all():
        if state.domain == "sensor":
            device_class = state.attributes.get("device_class")
            unit = state.attributes.get("unit_of_measurement", "").lower()

            # Include if device_class or unit looks energy/power-related
            if (
                device_class in energy_device_classes
                or "w" in unit  # W, kW
                or "wh" in unit  # Wh, kWh
                or "va" in unit  # Volt-amps
            ):
                entity_states.append(f"{state.name}: {state.state} {unit}")

    # Build prompt for AI
    prompt = (
        "Provide one clear and actionable suggestion to reduce energy consumption in the home. "
        "Tailor the advice based on the data. "
        "Limit to 255 chars or less.\n\n"
        "Current energy/power states:\n" + "\n".join(entity_states)
    )

    _LOGGER.info("Generated energy status prompt: %s", prompt)

    try:
        # Call the AI Task service
        response = await hass.services.async_call(
            "ai_task",
            "generate_data",
            {
                "entity_id": "ai_task." + name_internal + "_ai_task",
                "task_name": "summarize",
                "instructions": prompt,
            },
            blocking=True,
            return_response=True,
        )

        if not response or "data" not in response:
            raise HomeAssistantError("No response from AI Task")

        responsetext = response["data"][:250]

        _LOGGER.info("Energy Recommendation summary: %s", responsetext)

        # Store result in a text helper entity
        await hass.services.async_call(
            "text",
            "set_value",
            {
                "entity_id": "text.aienergysuggestion",
                "value": responsetext,
            },
            blocking=True,
        )

    except Exception as err:
        raise HomeAssistantError(f"Error getting AI energy recommendation: {err}") from err




@callback
async def handle_oasira_location_update_webhook(hass, webhook_id, request):
    """Register Oasira location update service."""

    _LOGGER.info("[Oasira] Handling location update webhook")

    try:
        data = await request.json()
    except Exception as e:
        _LOGGER.error("[Oasira] Invalid JSON payload: %s", e)
        return

    ####TODO: Jermie: get user's email here and link this device tracker to them (local and online) #####

    device_id = data.get("device_id")
    lat = data.get("latitude")
    lon = data.get("longitude")
    accuracy = data.get("accuracy", 30.0)

    device_id_new = device_id.lower().replace('@', '_').replace('.', '_')

    entity_id = f"device_tracker.{device_id_new}"

    # Update or create entity
    hass.states.async_set(
        entity_id,
        "home",  # You can change this dynamically later
        {
            "latitude": lat,
            "longitude": lon,
            "gps_accuracy": accuracy,
            "source_type": SOURCE_TYPE_GPS,
            "friendly_name": f"Oasira {device_id_new.title()}",
        },
    )

#sampledata
#{
#    email: jermie@effortlesshome.co
#    token: dQRbs1AlRkiSG0mlZUi886:APA91bGW21-E3C4hyX0gRTaMb4QuGHWYWk4Qjj0sldhyMwPkTTmgZis1SzwsGdgEBg1brh8KcXIJt6MecJroxIBFm0JuGctm0Ebr1_Qv8k3999999999
#    device_name: master_bedroom_tv
#    platform: android
#}

@callback
async def handle_oasira_push_token_webhook(hass, webhook_id, request):
    """Handle incoming Oasira Push Token webhook (device token)."""

    _LOGGER.info("[Oasira] Handling push token webhook")

    try:
        data = await request.json()
    except Exception as e:
        _LOGGER.info("[Oasira] Invalid JSON payload: %s", e)
        return

    email = data.get("email")
    token = data.get("token")
    device_name = data.get("device_name")
    platform_name = data.get("platform")

    if not email:
        _LOGGER.info("[Oasira] Webhook called without 'email' field.")
        return

    targetperson = None
    persons = hass.data.get(DOMAIN, {}).get("persons", [])
    for person in persons:
        if person.name == email:
            targetperson = person
            break

    if targetperson is not None:
        _LOGGER.info("[Oasira] Push Notification Target Person: "+ targetperson.name)
        await targetperson.async_set_notification_devices(hass, token, device_name, platform_name)

@callback
async def handle_set_person_location_devices(hass, webhook_id, request):
    """Handle incoming webhook."""

    _LOGGER.info("[Oasira] Handling set person location webhook")

    try:
        data = await request.json()
    except Exception as e:
        _LOGGER.info("[Oasira] Invalid JSON payload: %s", e)
        return

    email = data.get("email")
    inhometracker = data.get("inhometracker")
    remotetracker = data.get("remotetracker")

    if not email:
        _LOGGER.info("[Oasira] Set Person Location Devices Webhook called without 'email' field.")
        return

    targetperson = None
    persons = hass.data.get(DOMAIN, {}).get("persons", [])
    for person in persons:
        if person.name == email:
            targetperson = person
            break

    if targetperson is not None:
        _LOGGER.info("[Oasira] Push Notification Target Person: "+ targetperson.name)
        if inhometracker is not None and inhometracker != "":
            await targetperson.async_set_local_tracker(inhometracker)
        
        if remotetracker is not None and remotetracker != "":
            await targetperson.async_set_remote_tracker(remotetracker)