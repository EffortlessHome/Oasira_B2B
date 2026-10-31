"""constants."""

import datetime
import logging

from homeassistant.const import CONF_LLM_HASS_API
from homeassistant.helpers import llm

import voluptuous as vol

from homeassistant.helpers import config_validation as cv
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    DOMAIN as BINARY_SENSOR_DOMAIN,
)
from homeassistant.components.cover import DOMAIN as COVER_DOMAIN
from homeassistant.components.group.const import DOMAIN as GROUP_DOMAIN
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.sensor.const import DOMAIN as SENSOR_DOMAIN
from homeassistant.components.switch.const import DOMAIN as SWITCH_DOMAIN

VERSION = "1.2.6"
NAME = "Oasira"
DOMAIN="oasira_b2b"
name_internal = "oasira"

# API Base URLs
SECURITY_API = "https://securityapi.effortlesshome.co/"
CUSTOMER_API = "https://cust.effortlesshome.co/"

# Firebase Authentication
FIREBASE_AUTH_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
FIREBASE_TOKEN_URL = "https://securetoken.googleapis.com/v1/token"
FIREBASE_USER_INFO_URL = "https://identitytoolkit.googleapis.com/v1/accounts:lookup"

LABELS = [
    "Favorite",
    "NotForSecurityMonitoring",
]

# Configuration and options
CONF_ENABLED = "enabled"
CONF_USERNAME = "username"
CONF_SYSTEMID = "systemid"

CUSTOM_COMPONENTS = "custom_components"
INTEGRATION_FOLDER = "oasira_b2b"

PRESENCE_LOCK_SWITCH_PREFIX = ""
PRESENCE_LOCK_SWITCH_ENTITY_PREFIX = "switch.area_presence_lock_"

SLEEP_MODE_SWITCH_PREFIX = "Sleep Mode "
SLEEP_MODE_SWITCH_ENTITY_PREFIX = "switch.area_sleep_mode_"

PRESENCE_BINARY_SENSOR_PREFIX = ""
PRESENCE_BINARY_SENSOR_ENTITY_PREFIX = "binary_sensor.area_presence_"

ILLUMINANCE_SENSOR_PREFIX = ""
ILLUMINANCE_SENSOR_ENTITY_PREFIX = "sensor.area_illuminance_"

TEMPERATURE_SENSOR_PREFIX = ""
TEMPERATURE_SENSOR_ENTITY_PREFIX = "sensor.area_temperature_"

HUMIDITY_SENSOR_PREFIX = ""
HUMIDITY_SENSOR_ENTITY_PREFIX = "sensor.area_humidity_"

COVER_GROUP_PREFIX = ""
COVER_GROUP_ENTITY_PREFIX = "cover.area_covers_"

LIGHT_GROUP_PREFIX = ""
LIGHT_GROUP_ENTITY_PREFIX = "light.area_"

INITIALIZATION_TIME = datetime.timedelta(seconds=60)
ISSUE_TYPE_INVALID_AREA = "invalid_area_config"

# Fetch entities from these domains:
RELEVANT_DOMAINS = [
    BINARY_SENSOR_DOMAIN,
    SENSOR_DOMAIN,
    SWITCH_DOMAIN,
    LIGHT_DOMAIN,
    COVER_DOMAIN,
]

