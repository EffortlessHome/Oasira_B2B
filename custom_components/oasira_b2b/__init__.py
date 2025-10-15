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
from typing import TYPE_CHECKING

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

from . import const

from .alarm_common import (
    async_cancelalarm,
    async_confirmpendingalarm,
    async_getalarmstatus,
)
from .area_manager import AreaManager
from .auto_area import AutoArea

from .const import (
    DOMAIN,
    DOMAIN,
    CUSTOMER_API,
    SECURITY_API,
    LABELS,
    HA_URL,
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

from aiohttp import web

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

    system_psk = hass.data[DOMAIN]["system_psk"]
    customer_psk = hass.data[DOMAIN]["customer_psk"]
    ha_url = hass.data[DOMAIN]["ha_url"]    

    hass.states.async_set("sensor.customerid", customer_id, {"dev_mode": "off"})
    hass.states.async_set("sensor.systemid", system_id, {"dev_mode": "off"})
    hass.states.async_set("sensor.token", system_psk, {"dev_mode": "off"})
    hass.states.async_set("sensor.ha_url", ha_url, {"dev_mode": "off"})
    hass.states.async_set("sensor.customertoken", customer_psk, {"dev_mode": "off"})
#    hass.states.async_set("sensor.user", username, {"dev_mode": "off"})

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
            "ai_task",
        ],
    )

    agent = ConversationAgent(hass)
    conversation.async_set_agent(hass, entry, agent)

    webhook = SecurityAlarmWebhook(hass)
    await SecurityAlarmWebhook.async_setup_webhook(webhook)

    broadcast_webhook = BroadcastWebhook(hass)
    await BroadcastWebhook.async_setup_webhook(broadcast_webhook)

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
    
    async def after_home_assistant_started(event):
        """Call this function after Home Assistant has started."""
        await loaddevicegroups(None)
        await handle_home_status_summary()
        await handle_climate_suggestion()
        await handle_maintenance_suggestion()
        await handle_safety_suggestion()
        await handle_energy_suggestion()

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
    os.makedirs(target_themes_dir, exist_ok=True)
    os.makedirs(target_dir, exist_ok=True)
    os.makedirs(target_blueprints_dir, exist_ok=True)
    os.makedirs(target_packages_dir, exist_ok=True)
    os.makedirs(target_dashboard_dir, exist_ok=True)

    # Copy entire themes directory including subfolders and files
    if os.path.exists(source_themes_dir):
        shutil.copytree(source_themes_dir, target_themes_dir, dirs_exist_ok=True)

    if os.path.exists(source_packages_dir):
        shutil.copytree(source_packages_dir, target_packages_dir, dirs_exist_ok=True)

    if os.path.exists(source_blueprints_dir):
        shutil.copytree(
            source_blueprints_dir, target_blueprints_dir, dirs_exist_ok=True
        )

    if os.path.exists(source_dir):
        shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)

    if os.path.exists(source_dashboard_dir):
        shutil.copytree(source_dashboard_dir, target_dashboard_dir, dirs_exist_ok=True)

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
        await async_send_message(call)

    hass.services.async_register(
        DOMAIN,
        "notify_person_service",
        async_send_message,
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

from homeassistant.helpers import entity_registry
from homeassistant.components import person

async def async_send_message(calldata):
    """Send a notification message only to a person’s Mobile App device trackers."""
    _LOGGER.info("In async_send_message")

    hass = HASSComponent.get_hass()
    person_name_list = calldata.data.get("target")

    if not person_name_list:
        _LOGGER.info("No person provided")
        return

    message = calldata.data.get("message")
    if not message:
        _LOGGER.info("No message provided")
        return

    title = calldata.data.get("title")
    data = calldata.data.get("data")

    ent_reg = entity_registry.async_get(hass)

    for person_name in person_name_list:
        person_entity = f"{person_name.lower()}"
        person_entry = ent_reg.async_get(person_entity)

        if person_entry is None:
            _LOGGER.info(f"Person entity {person_entity} not found.")
            continue

        _LOGGER.info(f"Person entry {person_entry} found.")

        # Get device trackers associated with this person
        device_trackers = person.entities_in_person(hass, person_entity)

        if not device_trackers:
            _LOGGER.info(f"No device trackers found for person {person_name}.")
            continue

        _LOGGER.info(f"Person device trackers {device_trackers} found.")

        # Filter only device_trackers from the Mobile App integration
        mobile_app_devices = []
        for device_tracker in device_trackers:
            tracker_entry = ent_reg.async_get(device_tracker)
            if tracker_entry and tracker_entry.platform == "mobile_app":
                mobile_app_devices.append(device_tracker)

        if not mobile_app_devices:
            _LOGGER.info(f"No Mobile App device trackers found for {person_name}.")
            continue

        # Send notifications to Mobile App notify services
        for device_tracker in mobile_app_devices:
            notify_service = device_tracker.replace("device_tracker.", "mobile_app_")
            _LOGGER.info(
                f"Sending notification to {notify_service} for {person_name}"
            )
            await hass.services.async_call(
                "notify",
                notify_service,
                {"message": message, "title": title, "data": data},
                blocking=False,
            )

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
                "entity_id": "ai_task."+ DOMAIN +"_ai_task",
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
                "entity_id": "ai_task."+ DOMAIN +"_ai_task",
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
                "entity_id": "ai_task." + DOMAIN + "_ai_task",
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
                "entity_id": "ai_task."+ DOMAIN +"_ai_task",
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
                "entity_id": "ai_task." + DOMAIN + "_ai_task",
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

async def setup_matter_hub():
    """Install and start Home Assistant Matter Hub."""

    # Step 1: install npm
    _LOGGER.info("Installing npm via apk...")
    try:
        proc_apk = await asyncio.create_subprocess_exec(
            "apk", "add", "npm",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc_apk.communicate()
        if out:
            _LOGGER.info("apk stdout: %s", out.decode())
        if err:
            _LOGGER.warning("apk stderr: %s", err.decode())
        if proc_apk.returncode != 0:
            _LOGGER.error("apk add npm failed with code %s", proc_apk.returncode)
            return False
    except FileNotFoundError:
        _LOGGER.error("apk not available in this environment")
        return False

    # Step 2: install home-assistant-matter-hub
    _LOGGER.info("Installing home-assistant-matter-hub...")
    proc_npm = await asyncio.create_subprocess_exec(
        "npm", "install", "-g", "home-assistant-matter-hub",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc_npm.communicate()
    if out:
        _LOGGER.info("npm stdout: %s", out.decode())
    if err:
        _LOGGER.warning("npm stderr: %s", err.decode())
    if proc_npm.returncode != 0:
        _LOGGER.error("npm install failed with code %s", proc_npm.returncode)
        return False

    hass = HASSComponent.get_hass()
    ha_token = hass.data[DOMAIN]["ha_token"]

    # Step 3: run home-assistant-matter-hub start
    _LOGGER.info("Starting home-assistant-matter-hub...")
    proc_hamh = await asyncio.create_subprocess_exec(
        "home-assistant-matter-hub", "start",
        "--home-assistant-url="+ HA_URL,
        "--home-assistant-access-token="+ ha_token,
        "--log-level=debug",
        "--http-port=8482",
        "--storage-location='/config/matterhub'",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    # Keep it running; don’t wait/communicate unless you want blocking
    _LOGGER.info("home-assistant-matter-hub process started with PID %s", proc_hamh.pid)
    return True

async def install_cloudflared():
    """Download and install cloudflared binary manually."""
    url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
    path = "/usr/local/bin/cloudflared"

    try:
        proc = await asyncio.create_subprocess_exec(
            "wget", "-O", path, url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        if proc.returncode != 0:
            _LOGGER.error("wget failed")
            return False

        # Make executable
        proc_chmod = await asyncio.create_subprocess_exec(
            "chmod", "+x", path
        )
        await proc_chmod.communicate()
        _LOGGER.info("cloudflared installed at %s", path)
    
    except Exception as e:
        _LOGGER.error("Error installing cloudflared: %s", e)
        return False

    hass = HASSComponent.get_hass()
    cloudflare_token = hass.data[DOMAIN]["cloudflare_token"]

    try:
        proc = await asyncio.create_subprocess_exec(
            "/usr/local/bin/cloudflared",
            "tunnel",
            "run",
            "--token " + cloudflare_token,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        out, err = await proc.communicate()

        if out:
            _LOGGER.info("cloudflared stdout: %s", out.decode(errors="ignore"))
        if err:
            _LOGGER.warning("cloudflared stderr: %s", err.decode(errors="ignore"))

        if proc.returncode == 0:
            _LOGGER.info("cloudflared service installed successfully")
            return True
        else:
            _LOGGER.error("cloudflared service install failed with exit %s", proc.returncode)
            return False

    except FileNotFoundError:
        _LOGGER.error("cloudflared binary not found")
        return False
    except Exception as exc:
        _LOGGER.exception("Error running cloudflared install: %s", exc)
        return False