"""Event-driven presence stream to the Oasira Care API.

Instead of mirroring every Home Assistant state change, this module
aggregates raw sensors into a small set of high-signal events that
Care staff actually act on:

* **Safety alerts** (``POST /ingest/alerts``) -- smoke, CO, water, gas,
  alarm triggered, fall, panic button, low battery, device offline,
  cold/heat, sound/vibration, firmware update, ... Sent immediately on
  active/resolved transitions and made idempotent via ``external_id``.
* **Discrete telemetry events** (``POST /ingest/telemetry``) -- motion
  detected, door/window opened/closed, person home/away, lock state,
  in-bed/out-of-bed, alarm arm/disarm, generic HA ``event`` triggers.
  Only transitions are sent, with per-area / per-entity debouncing so
  a chatty sensor cannot flood the API.
* **Presence summaries** (``POST /ingest/telemetry``) -- one reading per
  area, sent only when the area's presence state changes, carrying
  ``last_movement_at``, ``minutes_since_movement``, occupancy state,
  open doors/windows, lights/alarm/in-bed state, person-at-home,
  averaged temperature/humidity/CO2, low-battery and offline counts,
  and ``last_fall_at``. Continuous values are excluded from the change
  detection, so they never trigger a send on their own.
* **Derived alerts** -- computed locally: ``no_movement`` per area,
  ``door_left_open`` after 5 min, ``device_offline`` after 10 min
  unavailable, and hysteresis threshold alerts for battery, temperature,
  humidity, CO2 and PM2.5.

Every reading is change-driven: a value is only sent when it differs
from the last one sent for that device, so an unchanged state is never
re-sent. Occurrence events (motion, face recognition, HA events and
manual ``send_event`` calls) are exempt, because each of those is a
distinct event rather than a state.

Discovery is zero-config: sensors are matched by HA ``device_class``
and resolved to areas via the entity/device registries. Assign an
entity to an area in HA and it is picked up automatically.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from aiohttp import ClientError, ClientTimeout
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

_LOGGER = logging.getLogger(__name__)

CONF_CARE_API_URL = "care_api_url"
CONF_CARE_API_KEY = "care_api_key"
CONF_NO_MOVEMENT_MINUTES = "no_movement_minutes"
CONF_SUMMARY_INTERVAL_MINUTES = "summary_interval_minutes"

DEFAULT_NO_MOVEMENT_MINUTES = 60
DEFAULT_SUMMARY_INTERVAL_MINUTES = 30

FLUSH_INTERVAL = timedelta(seconds=30)
NO_MOVEMENT_CHECK_INTERVAL = timedelta(seconds=30)
MOTION_DEBOUNCE = timedelta(minutes=5)
PERSON_DEBOUNCE = timedelta(minutes=5)
DOOR_FLAP_GUARD = timedelta(seconds=10)
OCCUPANCY_CLEAR_DELAY = timedelta(seconds=60)
# Minimum spacing between two presence summaries for the same area. State
# changes that happen faster than this collapse into one summary.
SUMMARY_MIN_SPACING = timedelta(minutes=1)
BATCH_SIZE = 200
MAX_QUEUED_TELEMETRY = 500
MAX_QUEUED_ALERTS = 200
REQUEST_TIMEOUT = ClientTimeout(total=15)

IGNORED_STATES = {"unknown", "", "unavailable"}

MOTION_DEVICE_CLASSES = {"motion"}
OCCUPANCY_DEVICE_CLASSES = {"occupancy", "presence"}
DOOR_DEVICE_CLASSES = {"door", "window", "garage_door", "opening"}
PERSON_DOMAINS = {"person", "device_tracker"}

# binary_sensor device_class -> (alert type, severity) raised while the sensor is "on"
BINARY_ALERT_CLASSES: dict[str, tuple[str, str]] = {
    "smoke": ("smoke", "critical"),
    "carbon_monoxide": ("carbon_monoxide", "critical"),
    "gas": ("gas_leak", "critical"),
    "heat": ("high_temperature", "high"),
    "cold": ("low_temperature", "high"),
    "moisture": ("water_leak", "high"),
    "safety": ("safety", "high"),
    "tamper": ("tamper", "high"),
    "problem": ("device_problem", "medium"),
    "sound": ("sound_detected", "medium"),
    "vibration": ("vibration_detected", "medium"),
    "update": ("firmware_update", "low"),
    "battery": ("low_battery", "low"),
}

# device_classes where "off" (not "on") is the alert state, e.g. connectivity.
INVERTED_ALERT_CLASSES = {"connectivity"}
INVERTED_ALERT_TYPES: dict[str, tuple[str, str]] = {
    "connectivity": ("device_offline", "medium"),
}

# Numeric sensor thresholds (with hysteresis). Battery / environment alerts
# fire once on crossing and auto-resolve past the recover threshold, so a
# sensor hovering at the boundary cannot spam the API.
BATTERY_LOW_PCT = 20.0
BATTERY_RECOVER_PCT = 25.0
TEMP_HIGH_C = 30.0
TEMP_HIGH_RECOVER_C = 28.0
TEMP_LOW_C = 12.0
TEMP_LOW_RECOVER_C = 14.0
HUMIDITY_HIGH_PCT = 70.0
HUMIDITY_HIGH_RECOVER_PCT = 65.0
CO2_HIGH_PPM = 1500.0
CO2_RECOVER_PPM = 1200.0
PM25_HIGH = 35.0
PM25_RECOVER = 25.0

DOOR_LEFT_OPEN_MIN = 5
OFFLINE_ALERT_MIN = 10

# Derived-only alert types (no binary_sensor device_class backs them).
DERIVED_ALERT_TYPES: dict[str, tuple[str, str]] = {
    "fall_detected": ("fall_detected", "critical"),
    "panic_button": ("panic_button", "critical"),
    "door_left_open": ("door_left_open", "medium"),
    "device_offline": ("device_offline", "medium"),
    "high_humidity": ("high_humidity", "medium"),
    "high_co2": ("high_co2", "medium"),
    "high_pm25": ("high_pm25", "medium"),
    "low_temperature": ("low_temperature", "high"),
    "high_temperature": ("high_temperature", "high"),
    "low_battery": ("low_battery", "low"),
}

# Tokens that mark a binary_sensor / input_boolean as a fall or panic signal.
# Matched as whole tokens so "fallback" does not trip a fall alert.
FALL_KEYWORDS = {"fall"}
PANIC_KEYWORDS = {"panic", "sos", "emergency"}

ENV_DEVICE_CLASSES = {
    "temperature",
    "humidity",
    "battery",
    "co2",
    "pm25",
    "pm2.5",
    "pm10",
    "aqi",
}

HUB_AREA_ID = "hub"


def is_valid_care_api_url(url: str) -> bool:
    """Return whether a Care API base URL uses HTTP(S) without embedded credentials."""
    try:
        parsed = urlsplit(url)
        return (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
            and (parsed.port is None or 1 <= parsed.port <= 65535)
        )
    except ValueError:
        return False


def parse_value(state: str) -> float | str:
    """Return numeric readings as numbers so the backend can chart them."""
    try:
        return float(state)
    except ValueError:
        return state


def _name_tokens(state: State) -> set[str]:
    """Lowercased tokens from the entity_id and friendly_name for keyword matching."""
    import re

    blob = f"{state.entity_id} {state.attributes.get('friendly_name') or ''}"
    return set(re.split(r"[^a-z0-9]+", blob.lower())) - {""}


def _heuristic_alert(state: State) -> tuple[str, str, str] | None:
    """Name-based fall / panic detection (HA has no fall device_class).

    Returns (alert_type, severity, description) or None.
    """
    name = state.attributes.get("friendly_name") or state.entity_id
    tokens = _name_tokens(state)
    if tokens & FALL_KEYWORDS:
        return ("fall_detected", "critical", f"Fall detected: {name}")
    if tokens & PANIC_KEYWORDS:
        return ("panic_button", "critical", f"Panic button pressed: {name}")
    return None


def build_alert(
    state: State, location: str | None, resolved: bool = False
) -> dict[str, Any] | None:
    """Map an entity state to an alert payload, or None if it is not alert-worthy."""
    entity_id = state.entity_id
    name = state.attributes.get("friendly_name") or entity_id
    domain = entity_id.split(".", 1)[0]

    if domain == "alarm_control_panel":
        if state.state != "triggered" and not resolved:
            return None
        alert_type, severity = "security", "critical"
        description = f"Alarm triggered: {name}"
    elif domain in ("binary_sensor", "input_boolean", "input_button", "button"):
        heuristic = _heuristic_alert(state)
        if heuristic is not None:
            # Buttons fire with a timestamp as their state, so anything that
            # is not a plain "off" counts as a press.
            if state.state == "off" and not resolved:
                return None
            alert_type, severity, description = heuristic
        else:
            dc = state.attributes.get("device_class", "")
            if dc in INVERTED_ALERT_CLASSES:
                if state.state == "on" and not resolved:
                    return None
                if state.state in IGNORED_STATES:
                    return None
                alert_type, severity = INVERTED_ALERT_TYPES[dc]
                description = f"{name} is offline (connectivity lost)"
            else:
                mapping = BINARY_ALERT_CLASSES.get(dc)
                if mapping is None or (state.state != "on" and not resolved):
                    return None
                alert_type, severity = mapping
                description = f"{name} detected {alert_type.replace('_', ' ')}"
    elif domain == "event":
        if resolved:
            return None
        event_type = str(state.state or "").lower()
        if "fall" in event_type:
            alert_type, severity = "fall_detected", "critical"
            description = f"Fall detected: {name} ({event_type})"
        else:
            return None
    else:
        return None

    return {
        "external_id": entity_id,
        "type": alert_type,
        "severity": severity,
        "location": location,
        "description": description,
        "status": "resolved" if resolved else "active",
        "occurred_at": state.last_changed.isoformat(),
    }


def alert_transition(old_state: State | None, new_state: State) -> str | None:
    """Return 'active' or 'resolved' when an entity enters or leaves an alert state."""
    domain = new_state.entity_id.split(".", 1)[0]
    if domain in ("button", "input_button"):
        # Presses are one-shot: the state is a timestamp, not a level.
        return "active"
    if domain not in ("alarm_control_panel", "binary_sensor", "input_boolean", "event"):
        return None
    if domain == "event":
        # Handled directly in the streamer (one-shot fall events).
        return None
    if domain == "alarm_control_panel":
        active_value = "triggered"
        was_active = old_state is not None and old_state.state == active_value
        is_active = new_state.state == active_value
    elif domain == "binary_sensor" and _device_class(new_state) in INVERTED_ALERT_CLASSES:
        # Inverted: "off" means alert (e.g. device lost connectivity).
        # "unavailable"/"unknown" are handled by the offline path, not here.
        if new_state.state in IGNORED_STATES:
            return None
        was_active = old_state is not None and old_state.state == "off"
        is_active = new_state.state == "off"
    else:
        active_value = "on"
        was_active = old_state is not None and old_state.state == active_value
        is_active = new_state.state == active_value
    if is_active and not was_active:
        return "active"
    if was_active and not is_active:
        return "resolved"
    return None


def _device_class(state: State) -> str:
    """Best-effort device_class for a state."""
    return str(state.attributes.get("device_class", "") or "")


@dataclass
class AreaPresence:
    """Aggregated presence state for one area (or the whole hub)."""

    area_id: str
    area_name: str
    last_movement: datetime | None = None
    motion_on: bool = False
    occupancy_on: bool = False
    occupancy_cleared_at: datetime | None = None
    last_motion_sent: datetime | None = None
    no_movement_alert_active: bool = False
    has_motion: bool = False
    motion_entity_ids: set[str] = field(default_factory=set)
    occupancy_entity_ids: set[str] = field(default_factory=set)
    door_entity_ids: set[str] = field(default_factory=set)
    light_entity_ids: set[str] = field(default_factory=set)
    in_bed: bool = False
    blocked: bool = False


class CareStreamer:
    """Aggregate HA sensors into low-noise presence events for the Care API."""

    def __init__(
        self,
        hass: HomeAssistant,
        base_url: str,
        api_key: str,
        on_auth_failed: Callable[[], None] | None = None,
        *,
        no_movement_minutes: int = DEFAULT_NO_MOVEMENT_MINUTES,
        summary_interval_minutes: int = DEFAULT_SUMMARY_INTERVAL_MINUTES,
    ) -> None:
        self._hass = hass
        self._on_auth_failed = on_auth_failed
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._no_movement_minutes = max(5, int(no_movement_minutes or DEFAULT_NO_MOVEMENT_MINUTES))
        # 0 disables the periodic refresh; summaries are then only sent when
        # the presence state of an area actually changes.
        summary_value = (
            DEFAULT_SUMMARY_INTERVAL_MINUTES
            if summary_interval_minutes is None
            else int(summary_interval_minutes)
        )
        self._summary_interval = timedelta(minutes=max(0, summary_value))
        self._telemetry: list[dict[str, Any]] = []
        self._alerts: list[dict[str, Any]] = []
        self._flush_lock = asyncio.Lock()
        self._unsub_bus = None
        self._unsub_timer = None
        self._auth_failed = False

        self._areas: dict[str, AreaPresence] = {}
        # entity_id -> latest known raw state string ("on"/"off"/"open"/...)
        self._known: dict[str, str] = {}
        # entity_id -> (area_key, area_name)
        self._entity_area: dict[str, tuple[str, str]] = {}
        # area_key -> {(entity_id): float} for temperature / humidity averaging
        self._temp_readings: dict[str, dict[str, float]] = {}
        self._hum_readings: dict[str, dict[str, float]] = {}
        self._battery_readings: dict[str, dict[str, float]] = {}
        self._co2_readings: dict[str, dict[str, float]] = {}
        self._person_home: dict[str, bool] = {}
        self._last_person_sent: dict[str, datetime] = {}
        self._last_door_sent: dict[str, datetime] = {}
        self._offline_reported: set[str] = set()
        # entity_id -> last telemetry value enqueued, so an unchanged state is
        # never re-sent for the same device.
        self._last_sent_value: dict[str, str] = {}
        # area_id -> signature of the last presence summary that was sent.
        self._summary_signature: dict[str, str] = {}
        # area_id -> when the last presence summary was sent.
        self._last_summary_sent: dict[str, datetime] = {}
        # entity_id -> when its current state began (for duration checks).
        self._state_changed_at: dict[str, datetime] = {}
        # (entity_id, alert_type) pairs currently active for numeric thresholds.
        self._numeric_alert_active: set[tuple[str, str]] = set()
        self._door_alerted: set[str] = set()
        self._offline_alerted: set[str] = set()
        self._alarm_state: str | None = None
        self._last_fall: datetime | None = None
        # Seeded from already-active binary alerts at startup so we do not
        # re-send "active" for sensors that were on before we listened.
        self._binary_alert_active: set[str] = set()

    # -- lifecycle -------------------------------------------------------

    async def async_start(self) -> None:
        """Begin streaming and send one lightweight summary per area."""
        self._discover()
        # Report binary alerts already active at startup so Care is aware
        # without waiting for the next transition.
        for entity_id in list(self._binary_alert_active):
            state = self._hass.states.get(entity_id)
            if state is None:
                continue
            area = self._area(entity_id)
            alert = build_alert(
                state,
                area.area_name if area.area_id != HUB_AREA_ID else None,
            )
            if alert is not None:
                self._enqueue_alert(alert)
        self._unsub_bus = self._hass.bus.async_listen(
            EVENT_STATE_CHANGED, self._handle_state_changed
        )
        self._unsub_timer = async_track_time_interval(
            self._hass, self._async_tick, NO_MOVEMENT_CHECK_INTERVAL
        )
        self._enqueue_all_summaries(force=True)
        self._schedule_flush()
        _LOGGER.info(
            "Care API presence streaming started (%d areas, no-movement %dmin, summary every %dmin)",
            len(self._areas),
            self._no_movement_minutes,
            int(self._summary_interval.total_seconds() // 60),
        )

    async def async_stop(self) -> None:
        """Stop streaming and make a final attempt to deliver what is queued."""
        if self._unsub_bus:
            self._unsub_bus()
            self._unsub_bus = None
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None
        await self._async_flush()

    # -- discovery --------------------------------------------------------

    def _area_key_name(self, entity_id: str) -> tuple[str, str]:
        """Resolve (area_key, area_name) for an entity, falling back to the hub."""
        cached = self._entity_area.get(entity_id)
        if cached:
            return cached
        entry = er.async_get(self._hass).async_get(entity_id)
        area_id: str | None = None
        if entry is not None:
            area_id = entry.area_id
            if area_id is None and entry.device_id:
                device = dr.async_get(self._hass).async_get(entry.device_id)
                area_id = device.area_id if device else None
        if area_id:
            area = ar.async_get(self._hass).async_get_area(area_id)
            name = area.name if area else area_id
            result = (area_id, name)
        else:
            result = (HUB_AREA_ID, self._hass.config.location_name or "Home")
        self._entity_area[entity_id] = result
        return result

    def _area(self, entity_id: str) -> AreaPresence:
        key, name = self._area_key_name(entity_id)
        area = self._areas.get(key)
        if area is None:
            area = AreaPresence(area_id=key, area_name=name)
            self._areas[key] = area
        else:
            area.area_name = name
        return area

    def _is_tracked(self, entity_id: str) -> bool:
        """Skip hidden/disabled entities and our own integration entities."""
        # Care-relevant entities this integration owns must still be tracked.
        if (
            entity_id == "binary_sensor.face_recognition"
            or entity_id == "binary_sensor.someone_home_sensor"
            or entity_id.endswith("_in_bed_sensor")
        ):
            return True
        entry = er.async_get(self._hass).async_get(entity_id)
        if entry is None:
            # Group/computed entities without registry entries: only track
            # binary_sensor groups that proxy real sensors.
            return not entity_id.startswith("group.")
        if entry.disabled or entry.entity_category or entry.hidden_by:
            return False
        if entry.platform == "oasira_b2b":
            return False
        return True

    @staticmethod
    def _is_in_bed_entity(entity_id: str) -> bool:
        return entity_id.endswith("_in_bed_sensor")

    @staticmethod
    def _is_relevant(state: State) -> bool:
        """Whether a state could ever produce an event or feed a summary."""
        entity_id = state.entity_id
        domain = entity_id.split(".", 1)[0]
        if domain == "binary_sensor":
            if (
                entity_id == "binary_sensor.face_recognition"
                or entity_id == "binary_sensor.someone_home_sensor"
                or entity_id.endswith("_in_bed_sensor")
            ):
                return True
            dc = _device_class(state)
            if (
                dc in MOTION_DEVICE_CLASSES
                or dc in OCCUPANCY_DEVICE_CLASSES
                or dc in DOOR_DEVICE_CLASSES
                or dc in BINARY_ALERT_CLASSES
                or dc in INVERTED_ALERT_CLASSES
                or dc in {"lock"}
            ):
                return True
            # Name-based fall / panic (no device_class for these).
            return _heuristic_alert(state) is not None
        if domain in PERSON_DOMAINS:
            return True
        if domain == "alarm_control_panel":
            return True
        if domain == "lock":
            return True
        if domain == "event":
            return True
        if domain == "input_boolean":
            return _heuristic_alert(state) is not None
        if domain == "sensor":
            return _device_class(state) in ENV_DEVICE_CLASSES
        if domain == "light":
            # Cached for summaries only; never emits an event.
            return True
        if domain in ("input_boolean", "input_button", "button"):
            return _heuristic_alert(state) is not None
        return False

    def _discover(self) -> None:
        """Seed area state from current states so the first summary is meaningful."""
        now = dt_util.utcnow()
        for state in self._hass.states.async_all():
            if not self._is_relevant(state) or not self._is_tracked(state.entity_id):
                continue
            self._known[state.entity_id] = state.state
            self._state_changed_at[state.entity_id] = state.last_changed
            domain = state.entity_id.split(".", 1)[0]
            dc = _device_class(state)
            area = self._area(state.entity_id)

            if domain == "binary_sensor" and dc in MOTION_DEVICE_CLASSES:
                area.has_motion = True
                area.motion_entity_ids.add(state.entity_id)
                if state.state == "on":
                    area.motion_on = True
                    if area.last_movement is None or state.last_changed > area.last_movement:
                        area.last_movement = state.last_changed
                    # A motion sensor that is currently on may have been on
                    # long ago; treat its last change as the movement time.
            elif domain == "binary_sensor" and dc in OCCUPANCY_DEVICE_CLASSES:
                area.has_motion = True
                area.occupancy_entity_ids.add(state.entity_id)
                if state.state == "on":
                    area.occupancy_on = True
                    if area.last_movement is None or state.last_changed > area.last_movement:
                        area.last_movement = state.last_changed
            elif domain == "binary_sensor" and dc in DOOR_DEVICE_CLASSES:
                area.door_entity_ids.add(state.entity_id)
                if state.state == "on" and state.entity_id not in self._door_alerted:
                    # Open at startup gets a grace period (state_changed_at is
                    # now, not the real open time) so we do not alert immediately.
                    self._state_changed_at[state.entity_id] = now
            elif domain in PERSON_DOMAINS:
                self._person_home[state.entity_id] = state.state == "home"
            elif domain == "sensor":
                self._cache_environment(state)
            elif domain == "light":
                area.light_entity_ids.add(state.entity_id)
            elif domain == "alarm_control_panel":
                self._alarm_state = state.state
            elif domain == "binary_sensor" and self._is_in_bed_entity(state.entity_id):
                area.in_bed = state.state == "on"
            elif domain == "binary_sensor" and (
                dc in BINARY_ALERT_CLASSES
                or dc in INVERTED_ALERT_CLASSES
                or _heuristic_alert(state) is not None
            ):
                # Remember already-active binary alerts so we do not re-send
                # "active" for sensors that were on before we listened.
                active = state.state == "on" or (
                    dc in INVERTED_ALERT_CLASSES and state.state == "off"
                )
                if active:
                    self._binary_alert_active.add(state.entity_id)
                    if (_heuristic_alert(state) or ("", ""))[0] == "fall_detected":
                        if self._last_fall is None or state.last_changed > self._last_fall:
                            self._last_fall = state.last_changed

        # Give quiet areas a grace period so startup does not raise
        # an immediate (false) no-movement alert. Done after the loop so a
        # sensor that is currently "on" can still seed last_movement from
        # its own last_changed regardless of iteration order.
        for area in self._areas.values():
            if area.last_movement is None and area.has_motion:
                area.last_movement = now

    # -- event handling ----------------------------------------------------

    @callback
    def _handle_state_changed(self, event: Event) -> None:
        new_state: State | None = event.data.get("new_state")
        old_state: State | None = event.data.get("old_state")
        if new_state is None:
            return
        entity_id = new_state.entity_id

        # Attribute-only updates carry no new signal, but the underlying
        # reading may have changed (e.g. a battery percentage).
        if old_state is not None and old_state.state == new_state.state:
            if (
                new_state.entity_id.split(".", 1)[0] == "sensor"
                and self._is_relevant(new_state)
                and self._cache_environment(new_state)
            ):
                self._schedule_flush()
            return

        if not self._is_tracked(entity_id):
            return
        if not self._is_relevant(new_state):
            return

        # Offline / unknown transitions: report once so the device shows as
        # offline in Care, then stay quiet until it returns. Entities that do
        # not stream readings are skipped: an "unavailable" reading would
        # create a device that can never come back to active.
        if new_state.state in IGNORED_STATES:
            if (
                entity_id in self._known
                and self._known[entity_id] not in IGNORED_STATES
                and self._streams_readings(new_state)
            ):
                self._state_changed_at[entity_id] = new_state.last_changed
                area = self._area(entity_id)
                name = new_state.attributes.get("friendly_name") or entity_id
                self._enqueue_telemetry(
                    {
                        "entity_id": entity_id,
                        "sensor_type": _device_class(new_state) or entity_id.split(".", 1)[0],
                        "value": "unavailable",
                        "unit": None,
                        "name": name,
                        "location": area.area_name if area.area_id != HUB_AREA_ID else None,
                        "recorded_at": new_state.last_changed.isoformat(),
                        "metadata": {"domain": entity_id.split(".", 1)[0]},
                    },
                    dedupe=False,
                    track=True,
                )
                self._offline_reported.add(entity_id)
                self._schedule_flush()
            elif entity_id not in self._state_changed_at:
                self._state_changed_at[entity_id] = new_state.last_changed
            self._known[entity_id] = new_state.state
            return

        if entity_id in self._offline_reported:
            self._offline_reported.discard(entity_id)
            # Report the recovered state so Care flips the device back to
            # active. Entities that have their own handler below report the
            # recovery themselves, so they are skipped here to avoid sending
            # the same recovery twice.
            if not self._reports_itself(new_state):
                area = self._area(entity_id)
                name = new_state.attributes.get("friendly_name") or entity_id
                canonical = self._canonical_reading(new_state)
                sensor_type, value = (
                    canonical
                    if canonical is not None
                    else (
                        _device_class(new_state) or entity_id.split(".", 1)[0],
                        new_state.state,
                    )
                )
                self._enqueue_telemetry(
                    {
                        "entity_id": entity_id,
                        "sensor_type": sensor_type,
                        "value": value,
                        "unit": new_state.attributes.get("unit_of_measurement"),
                        "name": name,
                        "location": area.area_name if area.area_id != HUB_AREA_ID else None,
                        "recorded_at": new_state.last_changed.isoformat(),
                        "metadata": {"domain": entity_id.split(".", 1)[0], "recovered": True},
                    }
                )
        # A sensor coming back online resolves a prolonged offline alert.
        if entity_id in self._offline_alerted:
            self._offline_alerted.discard(entity_id)
            area = self._area(entity_id)
            name = new_state.attributes.get("friendly_name") or entity_id
            self._enqueue_alert(
                {
                    "external_id": entity_id,
                    "type": "device_offline",
                    "severity": "medium",
                    "location": area.area_name if area.area_id != HUB_AREA_ID else None,
                    "description": f"{name} is back online",
                    "status": "resolved",
                    "occurred_at": dt_util.utcnow().isoformat(),
                }
            )
            self._schedule_flush()

        self._known[entity_id] = new_state.state
        self._state_changed_at[entity_id] = new_state.last_changed

        domain = entity_id.split(".", 1)[0]
        dc = _device_class(new_state)
        urgent = False

        # 1) Safety + alarm alerts (immediate, idempotent).
        # Suppress duplicate "active" for sensors already active since startup.
        transition = alert_transition(old_state, new_state)
        is_alert_capable = domain == "alarm_control_panel" or (
            domain in ("binary_sensor", "input_boolean", "input_button", "button")
            and (
                dc in BINARY_ALERT_CLASSES
                or dc in INVERTED_ALERT_CLASSES
                or _heuristic_alert(new_state) is not None
            )
        )
        if transition and not is_alert_capable:
            transition = None
        if transition == "active" and entity_id in self._binary_alert_active:
            transition = None
        if transition == "active":
            self._binary_alert_active.add(entity_id)
        if transition == "resolved":
            self._binary_alert_active.discard(entity_id)
        if transition:
            area = self._area(entity_id)
            alert = build_alert(
                new_state,
                area.area_name if area.area_id != HUB_AREA_ID else None,
                resolved=transition == "resolved",
            )
            if alert:
                self._enqueue_alert(alert)
                urgent = True
                if alert["type"] == "fall_detected" and transition == "active":
                    self._last_fall = new_state.last_changed

        # 2) Motion / occupancy -> presence updates.
        if domain == "binary_sensor" and dc in MOTION_DEVICE_CLASSES:
            area = self._area(entity_id)
            area.motion_entity_ids.add(entity_id)
            area.has_motion = True
            if new_state.state == "on":
                self._on_motion(area, new_state)
            else:
                area.motion_on = self._any_on(area.motion_entity_ids)
        elif domain == "binary_sensor" and dc in OCCUPANCY_DEVICE_CLASSES:
            area = self._area(entity_id)
            area.occupancy_entity_ids.add(entity_id)
            area.has_motion = True
            if new_state.state == "on":
                area.occupancy_on = True
                area.occupancy_cleared_at = None
                self._on_motion(area, new_state)
            else:
                # Defer the "off" event: single re-triggers in quick succession
                # are common for occupancy sensors. The summary will reflect
                # the cleared state once the delay has passed.
                area.occupancy_cleared_at = new_state.last_changed
                if area.last_movement is None or new_state.last_changed > area.last_movement:
                    area.last_movement = new_state.last_changed
                area.motion_on = self._any_on(area.motion_entity_ids)
        elif domain == "binary_sensor" and entity_id == "binary_sensor.face_recognition":
            if new_state.state == "on":
                person = new_state.attributes.get("last_recognized_person", "Unknown")
                area = self._area(entity_id)
                # Person detections are never debounced by the motion window.
                area.motion_on = True
                area.last_movement = new_state.last_changed
                self._resolve_no_movement(area, new_state.last_changed)
                self._enqueue_telemetry(
                    {
                        "entity_id": entity_id,
                        "sensor_type": "person",
                        "value": "detected",
                        "unit": None,
                        "name": new_state.attributes.get("friendly_name") or entity_id,
                        "location": area.area_name if area.area_id != HUB_AREA_ID else None,
                        "recorded_at": new_state.last_changed.isoformat(),
                        "metadata": {
                            "domain": "binary_sensor",
                            "person": person,
                            "kind": "face_recognition",
                        },
                    },
                    dedupe=False,
                    track=False,
                )
                urgent = True

        # 3) Door / window open-close (immediate, flap-guarded).
        elif domain == "binary_sensor" and dc in DOOR_DEVICE_CLASSES:
            area = self._area(entity_id)
            area.door_entity_ids.add(entity_id)
            self._on_door(area, new_state, dc)
            urgent = True

        # 4) Person / device_tracker home-away (debounced against GPS jitter).
        elif domain in PERSON_DOMAINS:
            self._on_person(new_state)
            urgent = True

        # 5) Lock state (immediate).
        elif domain == "lock":
            area = self._area(entity_id)
            name = new_state.attributes.get("friendly_name") or entity_id
            self._enqueue_telemetry(
                {
                    "entity_id": entity_id,
                    "sensor_type": "lock",
                    "value": new_state.state,
                    "unit": None,
                    "name": name,
                    "location": area.area_name if area.area_id != HUB_AREA_ID else None,
                    "recorded_at": new_state.last_changed.isoformat(),
                    "metadata": {"domain": "lock"},
                }
            )
            urgent = True

        # 6) Binary lock device_class (alternative lock reporting).
        elif domain == "binary_sensor" and dc == "lock":
            area = self._area(entity_id)
            name = new_state.attributes.get("friendly_name") or entity_id
            self._enqueue_telemetry(
                {
                    "entity_id": entity_id,
                    "sensor_type": "lock",
                    "value": "locked" if new_state.state == "on" else "unlocked",
                    "unit": None,
                    "name": name,
                    "location": area.area_name if area.area_id != HUB_AREA_ID else None,
                    "recorded_at": new_state.last_changed.isoformat(),
                    "metadata": {"domain": "binary_sensor", "device_class": "lock"},
                }
            )
            urgent = True

        # 7) In-bed (this integration's bed sensor).
        elif domain == "binary_sensor" and self._is_in_bed_entity(entity_id):
            area = self._area(entity_id)
            area.in_bed = new_state.state == "on"
            name = new_state.attributes.get("friendly_name") or entity_id
            self._enqueue_telemetry(
                {
                    "entity_id": entity_id,
                    "sensor_type": "in_bed",
                    "value": "in_bed" if new_state.state == "on" else "out_of_bed",
                    "unit": None,
                    "name": name,
                    "location": area.area_name if area.area_id != HUB_AREA_ID else None,
                    "recorded_at": new_state.last_changed.isoformat(),
                    "metadata": {"domain": "binary_sensor", "kind": "in_bed"},
                }
            )
            urgent = True

        # 8) Alarm panel arm/disarm state (triggered already handled as alert).
        elif domain == "alarm_control_panel":
            if new_state.state != "triggered":
                self._alarm_state = new_state.state
                area = self._area(entity_id)
                name = new_state.attributes.get("friendly_name") or entity_id
                self._enqueue_telemetry(
                    {
                        "entity_id": entity_id,
                        "sensor_type": "security",
                        "value": new_state.state,
                        "unit": None,
                        "name": name,
                        "location": area.area_name if area.area_id != HUB_AREA_ID else None,
                        "recorded_at": new_state.last_changed.isoformat(),
                        "metadata": {"domain": "alarm_control_panel"},
                    }
                )
                urgent = True
        # 9) Event entities (e.g. fall / press triggers).
        elif domain == "event":
            area = self._area(entity_id)
            name = new_state.attributes.get("friendly_name") or entity_id
            event_type = str(new_state.state)
            if "fall" in event_type.lower():
                self._last_fall = new_state.last_changed
                self._enqueue_alert(
                    {
                        "external_id": entity_id,
                        "type": "fall_detected",
                        "severity": "critical",
                        "location": area.area_name if area.area_id != HUB_AREA_ID else None,
                        "description": f"Fall detected: {name} ({event_type})",
                        "status": "active",
                        "occurred_at": new_state.last_changed.isoformat(),
                    }
                )
            else:
                self._enqueue_telemetry(
                    {
                        "entity_id": entity_id,
                        "sensor_type": "event",
                        "value": event_type,
                        "unit": None,
                        "name": name,
                        "location": area.area_name if area.area_id != HUB_AREA_ID else None,
                        "recorded_at": new_state.last_changed.isoformat(),
                        "metadata": {"domain": "event"},
                    },
                    dedupe=False,
                    track=False,
                )
            urgent = True

        # 10) Lights: cache only for the summary (never emits traffic).
        elif domain == "light":
            area = self._area(entity_id)
            area.light_entity_ids.add(entity_id)

        # 11) Environment + battery: cache and evaluate thresholds (never
        # streams the raw reading; alerts fire once per crossing).
        elif domain == "sensor" and dc in ENV_DEVICE_CLASSES:
            if self._cache_environment(new_state):
                urgent = True

        # 12) Panic / fall via input_boolean (already alerted in step 1).
        elif domain == "input_boolean":
            pass

        if urgent:
            self._schedule_flush()
        elif domain == "binary_sensor" and (
            dc in MOTION_DEVICE_CLASSES or dc in OCCUPANCY_DEVICE_CLASSES
        ):
            # Motion is urgent-ish but coalesced with the timer flush; the
            # 5-minute debounce above already thins repeats. Flush soon so
            # Care sees movement promptly.
            self._schedule_flush()

    # -- signal handlers ---------------------------------------------------

    def _on_motion(self, area: AreaPresence, state: State) -> None:
        """Record motion and (debounced) send a motion telemetry event."""
        area.motion_on = True
        area.last_movement = state.last_changed
        self._resolve_no_movement(area, state.last_changed)

        suppressed = (
            area.last_motion_sent is not None
            and state.last_changed - area.last_motion_sent < MOTION_DEBOUNCE
        )
        if suppressed:
            return
        area.last_motion_sent = state.last_changed

        name = state.attributes.get("friendly_name") or state.entity_id
        self._enqueue_telemetry(
            {
                "entity_id": state.entity_id,
                "sensor_type": "motion",
                "value": "on",
                "unit": None,
                "name": name,
                "location": area.area_name if area.area_id != HUB_AREA_ID else None,
                "recorded_at": state.last_changed.isoformat(),
                "metadata": {
                    "domain": "binary_sensor",
                    "area_id": area.area_id,
                    "area_name": area.area_name,
                    "last_movement_at": state.last_changed.isoformat(),
                },
            },
            # Motion is an occurrence, not a state: the value is always "on",
            # so it must not be deduplicated or tracked. The per-area debounce
            # above is what keeps it from flooding.
            dedupe=False,
            track=False,
        )

    def _on_door(self, area: AreaPresence, state: State, device_class: str) -> None:
        """Send a door/window open-closed event with a short flap guard."""
        # Resolve a prolonged door_left_open alert as soon as it closes.
        if state.state != "on" and state.entity_id in self._door_alerted:
            self._door_alerted.discard(state.entity_id)
            name = state.attributes.get("friendly_name") or state.entity_id
            self._enqueue_alert(
                {
                    "external_id": state.entity_id,
                    "type": "door_left_open",
                    "severity": "medium",
                    "location": area.area_name if area.area_id != HUB_AREA_ID else None,
                    "description": f"{name} closed",
                    "status": "resolved",
                    "occurred_at": state.last_changed.isoformat(),
                }
            )
        last = self._last_door_sent.get(state.entity_id)
        if last and state.last_changed - last < DOOR_FLAP_GUARD:
            return
        self._last_door_sent[state.entity_id] = state.last_changed

        value = "open" if state.state == "on" else "closed"
        if device_class in ("door", "garage_door", "opening"):
            sensor_type = "door" if device_class == "door" else "garage_door"
            if device_class == "opening":
                sensor_type = "door"
        else:
            sensor_type = "window"
        name = state.attributes.get("friendly_name") or state.entity_id
        self._enqueue_telemetry(
            {
                "entity_id": state.entity_id,
                "sensor_type": sensor_type,
                "value": value,
                "unit": None,
                "name": name,
                "location": area.area_name if area.area_id != HUB_AREA_ID else None,
                "recorded_at": state.last_changed.isoformat(),
                "metadata": {
                    "domain": "binary_sensor",
                    "area_id": area.area_id,
                    "area_name": area.area_name,
                    "device_class": device_class,
                },
            }
        )

    def _on_person(self, state: State) -> None:
        """Send a person/ device_tracker home-away event (debounced)."""
        last = self._last_person_sent.get(state.entity_id)
        if last and state.last_changed - last < PERSON_DEBOUNCE:
            self._person_home[state.entity_id] = state.state == "home"
            return
        self._last_person_sent[state.entity_id] = state.last_changed
        self._person_home[state.entity_id] = state.state == "home"

        value = "home" if state.state == "home" else "away"
        name = state.attributes.get("friendly_name") or state.entity_id
        self._enqueue_telemetry(
            {
                "entity_id": state.entity_id,
                "sensor_type": "person",
                "value": value,
                "unit": None,
                "name": name,
                "location": None,
                "recorded_at": state.last_changed.isoformat(),
                "metadata": {
                    "domain": state.entity_id.split(".", 1)[0],
                    "kind": "presence",
                },
            }
        )

    def _cache_environment(
        self, state: State, check_thresholds: bool = True
    ) -> bool:
        """Cache env/battery readings and evaluate alert thresholds.

        Returns True if an alert was enqueued (so the caller flushes urgently).
        Raw readings are never streamed; only threshold crossings alert.
        """
        dc = _device_class(state)
        try:
            value = float(state.state)
        except (TypeError, ValueError):
            return False
        # Normalize Fahrenheit temperatures to Celsius for threshold checks.
        if dc == "temperature":
            unit = str(state.attributes.get("unit_of_measurement") or "").lower()
            if unit in ("°f", "f", "fahrenheit"):
                value = (value - 32.0) * 5.0 / 9.0
        area = self._area(state.entity_id)
        fired = False
        if dc == "temperature":
            self._temp_readings.setdefault(area.area_id, {})[state.entity_id] = value
            if check_thresholds:
                fired = self._check_numeric_alert(
                    state, area, "high_temperature", value, value >= TEMP_HIGH_C, value <= TEMP_HIGH_RECOVER_C,
                    TEMP_HIGH_C, TEMP_HIGH_RECOVER_C, "high_temperature",
                ) or fired
                fired = self._check_numeric_alert(
                    state, area, "low_temperature", value, value <= TEMP_LOW_C, value >= TEMP_LOW_RECOVER_C,
                    TEMP_LOW_C, TEMP_LOW_RECOVER_C, "low_temperature",
                ) or fired
        elif dc == "humidity":
            self._hum_readings.setdefault(area.area_id, {})[state.entity_id] = value
            if check_thresholds:
                fired = self._check_numeric_alert(
                    state, area, "high_humidity", value, value >= HUMIDITY_HIGH_PCT, value <= HUMIDITY_HIGH_RECOVER_PCT,
                    HUMIDITY_HIGH_PCT, HUMIDITY_HIGH_RECOVER_PCT, "high_humidity",
                ) or fired
        elif dc == "battery":
            self._battery_readings.setdefault(area.area_id, {})[state.entity_id] = value
            if check_thresholds:
                fired = self._check_numeric_alert(
                    state, area, "low_battery", value, value <= BATTERY_LOW_PCT, value >= BATTERY_RECOVER_PCT,
                    BATTERY_LOW_PCT, BATTERY_RECOVER_PCT, "low_battery",
                ) or fired
        elif dc == "co2":
            self._co2_readings.setdefault(area.area_id, {})[state.entity_id] = value
            if check_thresholds:
                fired = self._check_numeric_alert(
                    state, area, "high_co2", value, value >= CO2_HIGH_PPM, value <= CO2_RECOVER_PPM,
                    CO2_HIGH_PPM, CO2_RECOVER_PPM, "high_co2",
                ) or fired
        elif dc in ("pm25", "pm2.5"):
            if check_thresholds:
                fired = self._check_numeric_alert(
                    state, area, "high_pm25", value, value >= PM25_HIGH, value <= PM25_RECOVER,
                    PM25_HIGH, PM25_RECOVER, "high_pm25",
                ) or fired
        return fired

    def _check_numeric_alert(
        self,
        state: State,
        area: AreaPresence,
        alert_type: str,
        value: float,
        is_active: bool,
        is_recovered: bool,
        high: float,
        recover: float,
        severity_key: str,
    ) -> bool:
        """Hysteresis helper: active once, resolved once, then quiet."""
        key = (state.entity_id, alert_type)
        name = state.attributes.get("friendly_name") or state.entity_id
        location = area.area_name if area.area_id != HUB_AREA_ID else None
        if is_active and key not in self._numeric_alert_active:
            self._numeric_alert_active.add(key)
            _, severity = DERIVED_ALERT_TYPES.get(
                alert_type, (alert_type, "medium")
            )
            self._enqueue_alert(
                {
                    "external_id": state.entity_id,
                    "type": alert_type,
                    "severity": severity,
                    "location": location,
                    "description": f"{name} ({value:.1f}) crossed {alert_type.replace('_', ' ')} threshold",
                    "status": "active",
                    "occurred_at": state.last_changed.isoformat(),
                }
            )
            return True
        if is_recovered and key in self._numeric_alert_active:
            self._numeric_alert_active.discard(key)
            self._enqueue_alert(
                {
                    "external_id": state.entity_id,
                    "type": alert_type,
                    "severity": DERIVED_ALERT_TYPES.get(alert_type, (alert_type, "medium"))[1],
                    "location": location,
                    "description": f"{name} back within normal range ({value:.1f})",
                    "status": "resolved",
                    "occurred_at": state.last_changed.isoformat(),
                }
            )
            return True
        return False

    def _any_on(self, entity_ids: set[str]) -> bool:
        return any(self._known.get(eid) == "on" for eid in entity_ids)

    # -- canonical readings -------------------------------------------------

    def _canonical_reading(self, state: State) -> tuple[str, str] | None:
        """Return (sensor_type, value) for a state-like entity, else None.

        State-like entities report a value that only changes when the state
        changes, so they can be deduplicated. Occurrence-based entities
        (motion, face recognition, HA events) report a new occurrence each
        time and are handled separately.
        """
        entity_id = state.entity_id
        domain = entity_id.split(".", 1)[0]
        dc = _device_class(state)

        if domain == "lock":
            return ("lock", state.state)
        if domain == "alarm_control_panel":
            return ("security", state.state)
        if domain in PERSON_DOMAINS:
            return ("person", "home" if state.state == "home" else "away")
        if domain == "binary_sensor":
            if self._is_in_bed_entity(entity_id):
                return ("in_bed", "in_bed" if state.state == "on" else "out_of_bed")
            if entity_id == "binary_sensor.face_recognition":
                return ("person", "detected" if state.state == "on" else "off")
            if dc in DOOR_DEVICE_CLASSES:
                sensor_type = "door" if dc in ("door", "opening") else "garage_door"
                if dc == "window":
                    sensor_type = "window"
                return (sensor_type, "open" if state.state == "on" else "closed")
            if dc == "lock":
                return ("lock", "locked" if state.state == "on" else "unlocked")
        return None

    def _streams_readings(self, state: State) -> bool:
        """Whether this entity normally produces telemetry readings.

        Entities that only feed alerts or summaries (temperature, humidity,
        battery, lights) must not get an ``unavailable`` reading: that would
        create a device in Care that can never return to active.
        """
        entity_id = state.entity_id
        domain = entity_id.split(".", 1)[0]
        dc = _device_class(state)
        if self._canonical_reading(state) is not None:
            return True
        if domain == "binary_sensor" and (
            dc in MOTION_DEVICE_CLASSES or dc in OCCUPANCY_DEVICE_CLASSES
        ):
            return True
        if entity_id == "binary_sensor.face_recognition":
            return True
        if domain == "event":
            return True
        return False

    def _reports_itself(self, state: State) -> bool:
        """Whether this entity's own handler will emit a reading for it.

        Used to avoid sending the same recovery twice. Motion, occupancy and
        face recognition only report their "on" transition, so a recovery back
        to "off" has to be reported by the generic recovery path.
        """
        entity_id = state.entity_id
        domain = entity_id.split(".", 1)[0]
        dc = _device_class(state)
        if domain == "event":
            return True
        if domain in ("lock", "alarm_control_panel"):
            return True
        if domain in PERSON_DOMAINS:
            return True
        if entity_id == "binary_sensor.face_recognition":
            return state.state == "on"
        if domain == "binary_sensor":
            if self._is_in_bed_entity(entity_id):
                return True
            if dc in DOOR_DEVICE_CLASSES or dc == "lock":
                return True
            if dc in MOTION_DEVICE_CLASSES or dc in OCCUPANCY_DEVICE_CLASSES:
                return state.state == "on"
        return False

    # -- no-movement + summaries ------------------------------------------

    async def _async_tick(self, now: datetime) -> None:
        """Periodic tick: occupancy clearing, duration alerts, summaries."""
        # 1) Occupancy sensors that went "off" a while ago: settle the area.
        for area in self._areas.values():
            if area.occupancy_cleared_at:
                if now - area.occupancy_cleared_at >= OCCUPANCY_CLEAR_DELAY:
                    if not self._any_on(area.occupancy_entity_ids):
                        area.occupancy_on = False
                    area.occupancy_cleared_at = None

        # 2) No-movement alerts (once per quiet period, auto-resolved).
        for area in self._areas.values():
            if not area.has_motion or area.last_movement is None:
                continue
            idle = now - area.last_movement
            if idle >= timedelta(minutes=self._no_movement_minutes):
                if not area.no_movement_alert_active:
                    area.no_movement_alert_active = True
                    minutes = int(idle.total_seconds() // 60)
                    self._enqueue_alert(
                        {
                            "external_id": f"no_movement_{area.area_id}",
                            "type": "no_movement",
                            "severity": "medium",
                            "location": area.area_name if area.area_id != HUB_AREA_ID else None,
                            "description": f"No movement in {area.area_name} for {minutes} minutes",
                            "status": "active",
                            "occurred_at": now.isoformat(),
                        }
                    )
                    _LOGGER.debug("No-movement alert for %s (%dmin)", area.area_name, minutes)

        # 3) Door left open for too long (once per open period).
        for area in self._areas.values():
            for entity_id in list(area.door_entity_ids):
                if self._known.get(entity_id) != "on":
                    continue
                if entity_id in self._door_alerted:
                    continue
                since = self._state_changed_at.get(entity_id)
                if since is None or now - since < timedelta(minutes=DOOR_LEFT_OPEN_MIN):
                    continue
                self._door_alerted.add(entity_id)
                self._enqueue_alert(
                    {
                        "external_id": entity_id,
                        "type": "door_left_open",
                        "severity": "medium",
                        "location": area.area_name if area.area_id != HUB_AREA_ID else None,
                        "description": f"Door left open in {area.area_name}",
                        "status": "active",
                        "occurred_at": now.isoformat(),
                    }
                )

        # 4) Device offline for too long (promotes telemetry to an alert).
        for entity_id, value in list(self._known.items()):
            if value not in IGNORED_STATES:
                continue
            if entity_id in self._offline_alerted:
                continue
            # Only alert for sensors we actually track (not lights etc.).
            if entity_id.split(".", 1)[0] == "light":
                continue
            since = self._state_changed_at.get(entity_id)
            if since is None or now - since < timedelta(minutes=OFFLINE_ALERT_MIN):
                continue
            self._offline_alerted.add(entity_id)
            area = self._area(entity_id)
            self._enqueue_alert(
                {
                    "external_id": entity_id,
                    "type": "device_offline",
                    "severity": "medium",
                    "location": area.area_name if area.area_id != HUB_AREA_ID else None,
                    "description": f"{entity_id} has been offline for over {OFFLINE_ALERT_MIN} minutes",
                    "status": "active",
                    "occurred_at": now.isoformat(),
                }
            )

        # 5) Presence summaries: only sent when the area's presence state
        #    changed (plus an optional slow refresh of unchanged areas).
        if self._enqueue_all_summaries(now):
            self._schedule_flush()

    def _resolve_no_movement(self, area: AreaPresence, now: datetime) -> None:
        if area.no_movement_alert_active:
            area.no_movement_alert_active = False
            self._enqueue_alert(
                {
                    "external_id": f"no_movement_{area.area_id}",
                    "type": "no_movement",
                    "severity": "medium",
                    "location": area.area_name if area.area_id != HUB_AREA_ID else None,
                    "description": f"Movement resumed in {area.area_name}",
                    "status": "resolved",
                    "occurred_at": now.isoformat(),
                }
            )

    def _enqueue_all_summaries(self, now: datetime | None = None, force: bool = False) -> int:
        """Enqueue a presence summary per area, but only when it changed.

        Continuous values (temperature, humidity, minutes since movement) are
        deliberately excluded from the signature: they change on every tick and
        would defeat the point. They still ride along in the payload of the
        next summary that is sent.

        Returns the number of summaries enqueued.
        """
        now = now or dt_util.utcnow()
        sent = 0
        for area in self._areas.values():
            signature = self._presence_signature(area, now)
            previous = self._summary_signature.get(area.area_id)
            changed = previous is None or previous != signature
            last_sent = self._last_summary_sent.get(area.area_id)

            if (
                not force
                and last_sent is not None
                and now - last_sent < SUMMARY_MIN_SPACING
            ):
                # Too soon; the next tick picks it up.
                continue
            if not changed and not force and not self._heartbeat_due(now, last_sent):
                continue

            self._summary_signature[area.area_id] = signature
            self._last_summary_sent[area.area_id] = now
            self._enqueue_summary(area, now)
            sent += 1
        return sent

    def _heartbeat_due(self, now: datetime, last_sent: datetime | None) -> bool:
        """Whether an unchanged area should be refreshed anyway."""
        if self._summary_interval <= timedelta(0):
            return False
        if last_sent is None:
            return True
        return now - last_sent >= self._summary_interval

    def _occupied(self, area: AreaPresence, now: datetime) -> bool:
        """Whether an area currently counts as occupied."""
        return bool(
            area.occupancy_on
            or area.motion_on
            or (
                area.last_movement is not None
                and now - area.last_movement < timedelta(minutes=5)
            )
        )

    def _area_offline_count(self, area_id: str) -> int:
        """Number of tracked entities in an area that are unavailable."""
        count = 0
        for entity_id, value in self._known.items():
            if value not in IGNORED_STATES:
                continue
            if entity_id.split(".", 1)[0] == "light":
                continue
            if self._entity_area.get(entity_id, (HUB_AREA_ID, ""))[0] == area_id:
                count += 1
        return count

    def _presence_signature(self, area: AreaPresence, now: datetime) -> str:
        """Fingerprint of the discrete presence state of an area.

        Only state-like values are included, so the signature changes when
        something meaningful happens (someone arrives, a door opens, the alarm
        is armed) and not when a sensor merely reports a new number.
        """
        doors_open = sorted(
            eid for eid in area.door_entity_ids if self._known.get(eid) == "on"
        )
        lights_on = (
            self._any_on(area.light_entity_ids) if area.light_entity_ids else False
        )
        persons_home = sum(1 for home in self._person_home.values() if home)
        low_battery = sorted(
            eid
            for eid, val in self._battery_readings.get(area.area_id, {}).items()
            if val <= BATTERY_LOW_PCT
        )
        return "|".join(
            (
                "occupied" if self._occupied(area, now) else "empty",
                f"occupancy={area.occupancy_on}",
                f"in_bed={area.in_bed}",
                f"lights={lights_on}",
                f"alarm={self._alarm_state}",
                f"persons={persons_home}",
                f"doors={','.join(doors_open)}",
                f"no_movement={area.no_movement_alert_active}",
                f"low_battery={','.join(low_battery)}",
                f"offline={self._area_offline_count(area.area_id)}",
            )
        )

    def _enqueue_summary(self, area: AreaPresence, now: datetime) -> None:
        """One compact reading per area with everything Care needs to show."""
        area_slug = slugify(area.area_id) if area.area_id else "hub"
        minutes_since = None
        if area.last_movement is not None:
            minutes_since = int((now - area.last_movement).total_seconds() // 60)

        occupied = self._occupied(area, now)
        value = "occupied" if occupied else "empty"

        # Open doors/windows currently known to be open.
        doors_open = [
            eid for eid in area.door_entity_ids if self._known.get(eid) == "on"
        ]

        temps = list(self._temp_readings.get(area.area_id, {}).values())
        hums = list(self._hum_readings.get(area.area_id, {}).values())
        temp_avg = round(sum(temps) / len(temps), 1) if temps else None
        hum_avg = round(sum(hums) / len(hums), 1) if hums else None
        co2s = list(self._co2_readings.get(area.area_id, {}).values())
        co2_avg = round(sum(co2s) / len(co2s), 1) if co2s else None

        persons_home = sum(1 for home in self._person_home.values() if home)

        lights_on = self._any_on(area.light_entity_ids) if area.light_entity_ids else None
        low_batt = [
            eid
            for eid, val in self._battery_readings.get(area.area_id, {}).items()
            if val <= BATTERY_LOW_PCT
        ]
        offline_count = self._area_offline_count(area.area_id)

        self._enqueue_telemetry(
            {
                "entity_id": f"sensor.oasira_presence_{area_slug}",
                "sensor_type": "presence",
                "value": value,
                "unit": None,
                "name": f"{area.area_name} presence",
                "location": area.area_name if area.area_id != HUB_AREA_ID else None,
                "recorded_at": now.isoformat(),
                "metadata": {
                    "domain": "oasira",
                    "kind": "presence_summary",
                    "area_id": area.area_id,
                    "area_name": area.area_name,
                    "occupied": occupied,
                    "motion_on": area.motion_on,
                    "occupancy_on": area.occupancy_on,
                    "in_bed": area.in_bed,
                    "lights_on": lights_on,
                    "alarm_state": self._alarm_state,
                    "last_movement_at": area.last_movement.isoformat()
                    if area.last_movement
                    else None,
                    "minutes_since_movement": minutes_since,
                    "no_movement_alert_active": area.no_movement_alert_active,
                    "doors_open": doors_open,
                    "persons_home": persons_home,
                    "temperature_c": temp_avg,
                    "humidity_pct": hum_avg,
                    "co2_ppm": co2_avg,
                    "low_battery_count": len(low_batt),
                    "low_battery_entities": low_batt,
                    "offline_count": offline_count,
                    "last_fall_at": self._last_fall.isoformat() if self._last_fall else None,
                },
            },
            dedupe=False,
        )

    # -- manual events (service) -------------------------------------------

    async def async_send_event(
        self,
        event_type: str,
        *,
        location: str | None = None,
        value: str | None = None,
        description: str | None = None,
        entity_id: str | None = None,
    ) -> None:
        """Enqueue a caller-supplied event (used by the ``send_event`` service).

        Safety-like types become alerts (immediate + idempotent); everything
        else becomes a telemetry reading. Tests and automations can push
        custom signals without exposing raw sensor streaming.
        """
        now = dt_util.utcnow()
        alert_types = (
            {v[0] for v in BINARY_ALERT_CLASSES.values()}
            | {v[0] for v in INVERTED_ALERT_TYPES.values()}
            | set(DERIVED_ALERT_TYPES)
            | {"security", "no_movement"}
        )
        if event_type in alert_types:
            self._enqueue_alert(
                {
                    "external_id": entity_id or f"manual_{event_type}",
                    "type": event_type,
                    "severity": "medium",
                    "location": location,
                    "description": description or f"Manual {event_type} event",
                    "status": "active",
                    "occurred_at": now.isoformat(),
                }
            )
        else:
            self._enqueue_telemetry(
                {
                    "entity_id": entity_id or "sensor.oasira_manual_event",
                    "sensor_type": event_type,
                    "value": value or "on",
                    "unit": None,
                    "name": description or event_type,
                    "location": location,
                    "recorded_at": now.isoformat(),
                    "metadata": {"domain": "oasira", "kind": "manual_event"},
                },
                # Manual events are explicit requests: always deliver them
                # and do not let them mask a later real state change.
                dedupe=False,
                track=False,
            )
        await self._async_flush()

    # -- queueing + delivery ------------------------------------------------

    def _enqueue_telemetry(
        self, reading: dict[str, Any], dedupe: bool = True, track: bool = True
    ) -> bool:
        """Queue a telemetry reading.

        With ``dedupe`` (the default for state-like readings) a reading whose
        value is identical to the last one sent for the same entity is dropped,
        so a device is never re-reported while it stays in the same state.

        ``track`` controls whether the reading becomes the new "last sent
        value" for the entity. It is turned off for pure occurrences (motion,
        face recognition, HA events, manual events) whose value is always the
        same and would otherwise mask the next real state change.
        """
        entity_id = reading.get("entity_id")
        value = reading.get("value")
        if entity_id is not None:
            key = str(value)
            if dedupe and self._last_sent_value.get(entity_id) == key:
                return False
            if track:
                self._last_sent_value[entity_id] = key
        self._telemetry.append(reading)
        del self._telemetry[:-MAX_QUEUED_TELEMETRY]
        return True

    def _enqueue_alert(self, alert: dict[str, Any]) -> None:
        self._alerts.append(alert)
        del self._alerts[:-MAX_QUEUED_ALERTS]

    def _schedule_flush(self) -> None:
        self._hass.async_create_background_task(
            self._async_flush(), "oasira_b2b care stream flush"
        )

    async def _async_flush(self) -> None:
        if self._auth_failed:
            return
        async with self._flush_lock:
            while self._alerts:
                batch = self._alerts[:BATCH_SIZE]
                if not await self._post("alerts", {"alerts": batch}):
                    return
                del self._alerts[: len(batch)]
            while self._telemetry:
                batch = self._telemetry[:BATCH_SIZE]
                if not await self._post("telemetry", {"readings": batch}):
                    return
                del self._telemetry[: len(batch)]

    async def _post(self, path: str, payload: dict[str, Any]) -> bool:
        session = async_get_clientsession(self._hass)
        try:
            async with session.post(
                f"{self._base_url}/ingest/{path}",
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=REQUEST_TIMEOUT,
            ) as response:
                if response.status in (401, 403):
                    self._auth_failed = True
                    _LOGGER.error(
                        "Care API rejected this node's key; streaming paused until the node is re-enrolled"
                    )
                    if self._on_auth_failed is not None:
                        self._on_auth_failed()
                    return False
                if response.status >= 400:
                    # Retrying a rejected batch would block the queue forever; drop it.
                    if response.status < 500:
                        _LOGGER.error(
                            "Care API rejected %s batch (%s); dropping it", path, response.status
                        )
                        return True
                    _LOGGER.warning("Care API error %s; will retry", response.status)
                    return False
                return True
        except (ClientError, asyncio.TimeoutError) as err:
            _LOGGER.warning("Care API unreachable (%s); will retry", err)
            return False
