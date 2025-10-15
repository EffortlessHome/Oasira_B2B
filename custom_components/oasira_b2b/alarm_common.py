"""Initialization of alarm_control_panel platform."""

import json
import logging

import aiohttp

from homeassistant.core import HomeAssistant

from . import const
from .const import (
    SECURITY_API,
    ALARM_TYPE_MED_ALERT,
    ALARM_TYPE_MONITORING,
    ALARM_TYPE_SECURITY,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

class PendingAlarm:
    def __init__(
        self,
        hass: HomeAssistant,
        open_sensors: dict,
        sensor_device_class: str,
        sensor_device_name: str,
        alarmtype: str,
    ) -> None:
        # Initialize the class with provided parameters
        self.open_sensors = open_sensors
        self.sensor_device_class = sensor_device_class
        self.sensor_device_name = sensor_device_name
        self.hass = hass
        self.alarmtype = alarmtype

class PendingAlarmComponent:
    # Class-level property to hold the pending alarm instance
    _pendingalarm = None

    @classmethod
    def set_pendingalarm(cls, alarm: PendingAlarm) -> None:
        cls._pendingalarm = alarm

    @classmethod
    def get_pendingalarm(cls):
        return cls._pendingalarm


async def async_creatependingalarm(
    hass: HomeAssistant, alarmtype: str, open_sensors: dict | None = None
) -> None:
    _LOGGER.debug("in create pending alarm")

    if open_sensors is not None:
        _LOGGER.debug("open_sensors" + str(open_sensors))

    sensor_device_class = None
    sensor_device_name = None

    if open_sensors is not None:
        for entity_id in open_sensors:
            devicestate = hass.states.get(entity_id)
            if devicestate and devicestate.attributes.get("friendly_name"):
                sensor_device_name = devicestate.attributes["friendly_name"]
            if devicestate and devicestate.attributes.get("device_class"):
                sensor_device_class = devicestate.attributes["device_class"]

    if sensor_device_class is not None:
        _LOGGER.debug("sensor_device_class" + sensor_device_class)

    if sensor_device_name is not None:
        _LOGGER.debug("sensor_device_name" + sensor_device_name)

    alarm = PendingAlarm(
        hass, open_sensors, sensor_device_class, sensor_device_name, alarmtype
    )

    PendingAlarmComponent.set_pendingalarm(alarm)

    hass.data[DOMAIN]["alarm_id"] = "pending"
    hass.data[DOMAIN]["alarmcreatemessage"] = "pending"
    hass.data[DOMAIN]["alarmownerid"] = "pending"
    hass.data[DOMAIN]["alarmstatus"] = "PENDING"
    hass.data[DOMAIN]["alarmlasteventtype"] = "alarm.status.pending"
    hass.data[DOMAIN]["alarmtype"] = alarmtype


async def async_confirmpendingalarm(hass: HomeAssistant):
    """Call the API to confirm pending alarm."""
    _LOGGER.debug("in confirm pending alarm")

    pendingAlarm = PendingAlarmComponent.get_pendingalarm()


    _LOGGER.info("Pending Alarm: %s", pendingAlarm)

    if pendingAlarm is None:
        return

    if pendingAlarm.alarmtype == ALARM_TYPE_MONITORING:
        await async_createmonitoringalarm(pendingAlarm)
    elif pendingAlarm.alarmtype == ALARM_TYPE_SECURITY:
        await async_createsecurityalarm(pendingAlarm)
    elif pendingAlarm.alarmtype == ALARM_TYPE_MED_ALERT:
        await async_createmedicalalertalarm(pendingAlarm)


async def async_createsecurityalarm(pendingAlarm):
    """Call the API to create a security alarm."""
    _LOGGER.debug("in create security alarm")

    _LOGGER.info("Pending Alarm: %s", pendingAlarm)

    if pendingAlarm is None:
        return

    hass = pendingAlarm.hass

    _LOGGER.info("Pending Alarm HASS: %s", pendingAlarm.hass)

    #TODO: Jermie enable plan feature checks
    #hasSecurityPlan = hass.states.get(DOMAIN +".activesecurityplan")

    #if not hasSecurityPlan:
    #    _LOGGER.info("No Active Security Plan")
    #    return

    systemid = hass.data[DOMAIN].get("systemid")
    system_psk = hass.data[DOMAIN].get("system_psk")

    _LOGGER.info("System ID: %s", hass.data[DOMAIN].get("systemid"))  
    _LOGGER.info("Email Address: %s", hass.data[DOMAIN].get("username"))  
    _LOGGER.info("Token: %s", system_psk)

    url = SECURITY_API + "createsecurityalarm/0"
    headers = {
        "accept": "application/json, text/html",
        "system_psk": system_psk,
        "eh_system_id": systemid,
        "Content-Type": "application/json; charset=utf-8",
    }

    #TODO: Jermie replace hardcoded sensor
    payload = '{"sensor_device_class":"door", "sensor_device_name":"frontdoor"}'

    _LOGGER.info("Calling create alarm API with payload: %s", payload)

    async with (
        aiohttp.ClientSession() as session,
        session.post(url, headers=headers, json=json.loads(payload)) as response,
    ):
        _LOGGER.info("API response status: %s", response.status)
        _LOGGER.info("API response headers: %s", response.headers)
        content = await response.text()
        _LOGGER.info("API response content: %s", content)

        if response is not None and response.status==200:
            json_dict = json.loads(content)
            hass.data[DOMAIN]["alarm_id"] = json_dict.get("AlarmID")
            hass.data[DOMAIN]["alarmcreatemessage"] = json_dict.get("Message")
            hass.data[DOMAIN]["alarmownerid"] = json_dict.get("OwnerID")
            hass.data[DOMAIN]["alarmstatus"] = json_dict.get("Status")
            hass.data[DOMAIN]["alarmlasteventtype"] = "alarm.status.created"
            hass.data[DOMAIN]["alarmtype"] = ALARM_TYPE_SECURITY

            PendingAlarmComponent.set_pendingalarm(None)

async def async_createmonitoringalarm(pendingAlarm):
    """Call the API to create a monitoring alarm."""

    _LOGGER.debug("in create monitoring alarm")

    if pendingAlarm is None:
        return

    hass = pendingAlarm.hass

    #TODO: Jermie enable plan feature checks
    #hasMonitoringPlan = hass.states.get(DOMAIN +".activemonitoringplan")

    #if not hasMonitoringPlan:
    #    _LOGGER.info("No Active Monitoring Plan")
    #    return

    systemid = hass.data[DOMAIN].get("systemid") 
    system_psk = hass.data[DOMAIN].get("system_psk")

    url = SECURITY_API + "createmonitoringalarm/0"
    headers = {
        "accept": "application/json, text/html",
        "system_psk": system_psk,
        "eh_system_id": systemid,
        "Content-Type": "application/json; charset=utf-8",
    }

    #TODO: Jermie: replace hardcoded sensor
    payload = (
        '{"sensor_device_class":"'
        + "smoke"
        + '", "sensor_device_name":"'
        + "smoke alarm"
        + '"}'
    )

    _LOGGER.info("Calling create monitoring alarm API with payload: %s", payload)

    async with (
        aiohttp.ClientSession() as session,
        session.post(url, headers=headers, json=json.loads(payload)) as response,
    ):
        _LOGGER.debug("API response status: %s", response.status)
        _LOGGER.debug("API response headers: %s", response.headers)
        content = await response.text()
        _LOGGER.debug("API response content: %s", content)

        if response is not None:
            json_dict = json.loads(content)
            hass.data[DOMAIN]["alarm_id"] = json_dict["AlarmID"]
            hass.data[DOMAIN]["alarmcreatemessage"] = json_dict["Message"]
            hass.data[DOMAIN]["alarmownerid"] = json_dict["OwnerID"]
            hass.data[DOMAIN]["alarmstatus"] = json_dict["Status"]
            hass.data[DOMAIN]["alarmlasteventtype"] = "alarm.status.created"
            hass.data[DOMAIN]["alarmtype"] = ALARM_TYPE_MONITORING

            PendingAlarmComponent.set_pendingalarm(None)

async def async_createmedicalalertalarm(pendingAlarm):
    """Call the API to create a medical alarm."""
    _LOGGER.debug("in create medical alert alarm")

    if pendingAlarm is None:
        return

    hass = pendingAlarm.hass

    #TODO: Jermie enable plan feature checks
    #hasMedAlertPlan = hass.states.get(DOMAIN +".activemedicalalertplan")

    #if not hasMedAlertPlan:
    #    _LOGGER.info("No Active Medical Alert Alarm Plan")
    #    return

    systemid = hass.data[DOMAIN].get("systemid") 
    system_psk = hass.data[DOMAIN].get("system_psk")

    url = SECURITY_API + "createmedicalalarm/0"
    headers = {
        "accept": "application/json, text/html",
        "system_psk": system_psk,
        "eh_system_id": systemid,
        "Content-Type": "application/json; charset=utf-8",
    }
    payload = (
        '{"sensor_device_class":"'
        + "safety"
        + '", "sensor_device_name":"'
        + "medicalalertsensor"
        + '"}'
    )

    _LOGGER.info("Calling create medical alert alarm API with payload: %s", payload)

    async with (
        aiohttp.ClientSession() as session,
        session.post(url, headers=headers, json=json.loads(payload)) as response,
    ):
        _LOGGER.debug("API response status: %s", response.status)
        _LOGGER.debug("API response headers: %s", response.headers)

        content = await response.text()

        _LOGGER.debug("API response content: %s", content)

        if response is not None:
            json_dict = json.loads(content)
            hass.data[DOMAIN]["alarm_id"] = json_dict["AlarmID"]
            hass.data[DOMAIN]["alarmcreatemessage"] = json_dict["Message"]
            hass.data[DOMAIN]["alarmownerid"] = json_dict["OwnerID"]
            hass.data[DOMAIN]["alarmstatus"] = json_dict["Status"]
            hass.data[DOMAIN]["alarmlasteventtype"] = "alarm.status.created"
            hass.data[DOMAIN]["alarmtype"] = ALARM_TYPE_MED_ALERT

            PendingAlarmComponent.set_pendingalarm(None)

async def async_cancelalarm(hass: HomeAssistant):
    """Call the API to create a medical alarm."""
    _LOGGER.debug("in cancel alarm")

    alarmstate = hass.data[DOMAIN]["alarm_id"]

    if alarmstate is not None and alarmstate != "":
        alarmstatus = hass.data[DOMAIN]["alarmstatus"]

        if alarmstatus == "PENDING":
            PendingAlarmComponent.set_pendingalarm(None)

            hass.data[DOMAIN]["alarm_id"] = ""
            hass.data[DOMAIN]["alarmcreatemessage"] = ""
            hass.data[DOMAIN]["alarmownerid"] = ""
            hass.data[DOMAIN]["alarmstatus"] = ""
            hass.data[DOMAIN]["alarmlasteventtype"] = ""
            hass.data[DOMAIN]["alarmtype"] = ""

            return None

        if alarmstatus == "ACTIVE":
            alarmid = hass.data[DOMAIN]["alarm_id"]
            _LOGGER.debug("alarm id =" + alarmid)

            systemid = hass.data[DOMAIN].get("systemid")
            system_psk = hass.data[DOMAIN].get("system_psk")

            url = SECURITY_API + "cancelalarm/" + alarmid
            headers = {
                "accept": "application/json, text/html",
                "system_psk": system_psk,
                "eh_system_id": systemid,
                "Content-Type": "application/json; charset=utf-8",
            }

            _LOGGER.info("Calling cancel alarm API")

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers) as response:
                    _LOGGER.debug("API response status: %s", response.status)
                    _LOGGER.debug("API response headers: %s", response.headers)
                    content = await response.text()
                    _LOGGER.debug("API response content: %s", content)

                    # {"status":"CANCELED","created_at":"2024-09-21T15:13:24.895Z"}
                    if content is not None:
                        json_dict = json.loads(content)
                        alarmstatus = json_dict["status"]

                        hass.data[DOMAIN]["alarm_id"] = ""
                        hass.data[DOMAIN]["alarmcreatemessage"] = ""
                        hass.data[DOMAIN]["alarmownerid"] = ""
                        hass.data[DOMAIN]["alarmstatus"] = ""
                        hass.data[DOMAIN]["alarmlasteventtype"] = alarmstatus
                        hass.data[DOMAIN]["alarmtype"] = ""

                        return content
    return None

async def async_getalarmstatus(hass: HomeAssistant):
    """Call the API to create a medical alarm."""
    _LOGGER.debug("in get alarm status")

    alarmstate = hass.data[DOMAIN]["alarm_id"]

    if alarmstate is not None and alarmstate != "":
        alarmid = hass.data[DOMAIN]["alarm_id"]

        if alarmid == "pending":
            return None

        systemid = hass.data[DOMAIN]["systemid"]
        system_psk = hass.data[DOMAIN]["system_psk"]

        url = SECURITY_API + "getalarmstatus/" + alarmid
        headers = {
            "accept": "application/json, text/html",
            "system_psk": system_psk,
            "eh_system_id": systemid,
            "Content-Type": "application/json; charset=utf-8",
        }

        _LOGGER.info("Calling get alarm status API")

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers) as response:
                _LOGGER.debug("API response status: %s", response.status)
                _LOGGER.debug("API response headers: %s", response.headers)
                content = await response.text()
                _LOGGER.debug("API response content: %s", content)

                if content is not None:
                    json_dict = json.loads(content)
                    alarmstatus = json_dict["status"]
                    hass.states.async_set(DOMAIN + ".alarmstatus", alarmstatus)

                return content
    return None
