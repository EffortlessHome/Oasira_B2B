"""Stream alerts and telemetry from Home Assistant entities to the Oasira Care API."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from collections.abc import Callable
from typing import Any

from aiohttp import ClientError, ClientTimeout
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval

_LOGGER = logging.getLogger(__name__)

CONF_CARE_API_URL = "care_api_url"
CONF_CARE_API_KEY = "care_api_key"

TELEMETRY_DOMAINS = {"sensor", "binary_sensor", "climate", "lock", "cover"}
# Numeric sensors change constantly; send at most one reading per entity per interval.
SENSOR_MIN_INTERVAL = timedelta(seconds=60)
FLUSH_INTERVAL = timedelta(seconds=10)
BATCH_SIZE = 200
MAX_QUEUED_TELEMETRY = 2000
MAX_QUEUED_ALERTS = 500
REQUEST_TIMEOUT = ClientTimeout(total=15)

IGNORED_STATES = {"unknown", ""}

# binary_sensor device_class -> (alert type, severity) raised while the sensor is "on"
BINARY_ALERT_CLASSES: dict[str, tuple[str, str]] = {
    "smoke": ("smoke", "critical"),
    "carbon_monoxide": ("carbon_monoxide", "critical"),
    "gas": ("gas_leak", "critical"),
    "heat": ("high_temperature", "high"),
    "moisture": ("water_leak", "high"),
    "safety": ("safety", "high"),
    "tamper": ("tamper", "high"),
    "problem": ("device_problem", "medium"),
}


def parse_value(state: str) -> float | str:
    """Return numeric readings as numbers so the backend can chart them."""
    try:
        return float(state)
    except ValueError:
        return state


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
    elif domain == "binary_sensor":
        mapping = BINARY_ALERT_CLASSES.get(state.attributes.get("device_class", ""))
        if mapping is None or (state.state != "on" and not resolved):
            return None
        alert_type, severity = mapping
        description = f"{name} detected {alert_type.replace('_', ' ')}"
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
    active_value = "triggered" if domain == "alarm_control_panel" else "on"
    was_active = old_state is not None and old_state.state == active_value
    is_active = new_state.state == active_value
    if is_active and not was_active:
        return "active"
    if was_active and not is_active:
        return "resolved"
    return None


class CareStreamer:
    """Queue state changes from Home Assistant and push them to the Care API."""

    def __init__(
        self,
        hass: HomeAssistant,
        base_url: str,
        api_key: str,
        on_auth_failed: Callable[[], None] | None = None,
    ) -> None:
        self._hass = hass
        self._on_auth_failed = on_auth_failed
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._telemetry: list[dict[str, Any]] = []
        self._alerts: list[dict[str, Any]] = []
        self._last_sensor_sent: dict[str, datetime] = {}
        self._flush_lock = asyncio.Lock()
        self._unsub_bus = None
        self._unsub_timer = None
        self._auth_failed = False

    async def async_start(self) -> None:
        """Begin streaming, starting with a snapshot of current entity states."""
        self._unsub_bus = self._hass.bus.async_listen(
            EVENT_STATE_CHANGED, self._handle_state_changed
        )
        self._unsub_timer = async_track_time_interval(
            self._hass, self._async_timer_flush, FLUSH_INTERVAL
        )
        for state in self._hass.states.async_all():
            self._queue_telemetry(state, force=True)
            if alert := build_alert(state, self._location(state.entity_id)):
                self._enqueue_alert(alert)
        self._schedule_flush()
        _LOGGER.info("Streaming alerts and telemetry to %s", self._base_url)

    async def async_stop(self) -> None:
        """Stop streaming and make a final attempt to deliver what is queued."""
        if self._unsub_bus:
            self._unsub_bus()
            self._unsub_bus = None
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None
        await self._async_flush()

    @callback
    def _handle_state_changed(self, event: Event) -> None:
        new_state: State | None = event.data.get("new_state")
        old_state: State | None = event.data.get("old_state")
        if new_state is None:
            return

        urgent = False
        transition = alert_transition(old_state, new_state)
        if transition:
            alert = build_alert(
                new_state,
                self._location(new_state.entity_id),
                resolved=transition == "resolved",
            )
            if alert:
                self._enqueue_alert(alert)
                urgent = True

        # Attribute-only updates are not new readings.
        if old_state is None or old_state.state != new_state.state:
            self._queue_telemetry(new_state)

        if urgent:
            self._schedule_flush()

    def _queue_telemetry(self, state: State, force: bool = False) -> None:
        entity_id = state.entity_id
        domain = entity_id.split(".", 1)[0]
        if domain not in TELEMETRY_DOMAINS or state.state in IGNORED_STATES:
            return

        registry_entry = er.async_get(self._hass).async_get(entity_id)
        if registry_entry and (registry_entry.entity_category or registry_entry.hidden_by):
            return

        if domain == "sensor" and not force:
            last = self._last_sensor_sent.get(entity_id)
            if last and state.last_changed - last < SENSOR_MIN_INTERVAL:
                return
        self._last_sensor_sent[entity_id] = state.last_changed

        self._telemetry.append(
            {
                "entity_id": entity_id,
                "sensor_type": state.attributes.get("device_class") or domain,
                "value": parse_value(state.state),
                "unit": state.attributes.get("unit_of_measurement"),
                "name": state.attributes.get("friendly_name"),
                "location": self._location(entity_id),
                "recorded_at": state.last_changed.isoformat(),
                "metadata": {"domain": domain},
            }
        )
        del self._telemetry[:-MAX_QUEUED_TELEMETRY]

    def _enqueue_alert(self, alert: dict[str, Any]) -> None:
        self._alerts.append(alert)
        del self._alerts[:-MAX_QUEUED_ALERTS]

    def _location(self, entity_id: str) -> str | None:
        entry = er.async_get(self._hass).async_get(entity_id)
        if entry is None:
            return None
        area_id = entry.area_id
        if area_id is None and entry.device_id:
            device = dr.async_get(self._hass).async_get(entry.device_id)
            area_id = device.area_id if device else None
        area = ar.async_get(self._hass).async_get_area(area_id) if area_id else None
        return area.name if area else None

    def _schedule_flush(self) -> None:
        self._hass.async_create_background_task(
            self._async_flush(), "oasira_b2b care stream flush"
        )

    async def _async_timer_flush(self, _now: datetime) -> None:
        await self._async_flush()

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
