"""Oasira Care backup agent: stores Home Assistant backups in the Oasira Care API."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import AsyncIterator, Callable, Coroutine
import json
import logging
from typing import Any

from aiohttp import ClientError, ClientTimeout
from homeassistant.components.backup import (
    AgentBackup,
    BackupAgent,
    BackupAgentError,
    BackupNotFound,
    OnProgressCallback,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DATA_CREDENTIALS = "care_backup_credentials"
DATA_LISTENERS = "care_backup_listeners"
API_TIMEOUT = ClientTimeout(total=30)
TRANSFER_TIMEOUT = ClientTimeout(total=3600, sock_read=120)
CHUNK_SIZE = 1024 * 1024


class BackupAgentUnreachableError(BackupAgentError):
    """The Oasira Care API could not be reached."""

    error_code = "backup_agent_unreachable"
    _message = "The Oasira Care API is unreachable."


async def async_get_backup_agents(hass: HomeAssistant, **kwargs: Any) -> list[BackupAgent]:
    """Return the Care API agent once the node has API credentials."""
    credentials = hass.data.get(DOMAIN, {}).get(DATA_CREDENTIALS)
    if credentials is None:
        return []
    return [CareBackupAgent(hass, *credentials)]


@callback
def async_register_backup_agents_listener(
    hass: HomeAssistant, *, listener: Callable[[], None], **kwargs: Any
) -> Callable[[], None]:
    """Register a listener to be called when the agent appears or disappears."""
    listeners: list[Callable[[], None]] = hass.data.setdefault(DOMAIN, {}).setdefault(
        DATA_LISTENERS, []
    )
    listeners.append(listener)

    @callback
    def remove_listener() -> None:
        listeners.remove(listener)

    return remove_listener


@callback
def async_notify_backup_listeners(hass: HomeAssistant) -> None:
    """Tell the backup integration to re-read the agent list."""
    for listener in list(hass.data.get(DOMAIN, {}).get(DATA_LISTENERS, [])):
        listener()


class CareBackupAgent(BackupAgent):
    """Backup agent backed by /ingest/backups on the Oasira Care API."""

    domain = DOMAIN
    name = "Oasira Care"

    def __init__(self, hass: HomeAssistant, base_url: str, api_key: str) -> None:
        self._hass = hass
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self.unique_id = "care_api"

    def _check(self, status: int, backup_id: str | None = None) -> None:
        if status == 404 and backup_id is not None:
            raise BackupNotFound(f"Backup {backup_id} not found")
        if status in (401, 403):
            raise BackupAgentError("Oasira Care API rejected this node's key")
        if status == 413:
            raise BackupAgentError("Backup exceeds the Oasira Care API upload limit")
        if status >= 400:
            raise BackupAgentError(f"Oasira Care API returned HTTP {status}")

    async def async_download_backup(
        self, backup_id: str, **kwargs: Any
    ) -> AsyncIterator[bytes]:
        session = async_get_clientsession(self._hass)
        try:
            response = await session.get(
                f"{self._base_url}/ingest/backups/{backup_id}/download",
                headers=self._headers,
                timeout=TRANSFER_TIMEOUT,
            )
        except (ClientError, asyncio.TimeoutError) as err:
            raise BackupAgentUnreachableError from err
        try:
            self._check(response.status, backup_id)
        except BackupAgentError:
            response.release()
            raise

        async def stream() -> AsyncIterator[bytes]:
            try:
                async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                    yield chunk
            except (ClientError, asyncio.TimeoutError) as err:
                raise BackupAgentUnreachableError from err
            finally:
                response.release()

        return stream()

    async def async_upload_backup(
        self,
        *,
        open_stream: Callable[[], Coroutine[Any, Any, AsyncIterator[bytes]]],
        backup: AgentBackup,
        on_progress: OnProgressCallback | None = None,
        **kwargs: Any,
    ) -> None:
        stream = await open_stream()

        async def counted() -> AsyncIterator[bytes]:
            sent = 0
            async for chunk in stream:
                sent += len(chunk)
                if on_progress is not None:
                    on_progress(bytes_uploaded=sent)
                yield chunk

        metadata = base64.b64encode(json.dumps(backup.as_dict()).encode()).decode()
        headers = {
            **self._headers,
            "Content-Type": "application/x-tar",
            "Content-Length": str(backup.size),
            "X-Backup-Id": backup.backup_id,
            "X-Backup-Metadata": metadata,
            "X-HA-Version": backup.homeassistant_version or "",
        }
        session = async_get_clientsession(self._hass)
        try:
            async with session.post(
                f"{self._base_url}/ingest/backups",
                data=counted(),
                headers=headers,
                timeout=TRANSFER_TIMEOUT,
            ) as response:
                self._check(response.status)
        except (ClientError, asyncio.TimeoutError) as err:
            raise BackupAgentUnreachableError from err

    async def async_delete_backup(self, backup_id: str, **kwargs: Any) -> None:
        session = async_get_clientsession(self._hass)
        try:
            async with session.delete(
                f"{self._base_url}/ingest/backups/{backup_id}",
                headers=self._headers,
                timeout=API_TIMEOUT,
            ) as response:
                self._check(response.status, backup_id)
        except (ClientError, asyncio.TimeoutError) as err:
            raise BackupAgentUnreachableError from err

    async def async_list_backups(self, **kwargs: Any) -> list[AgentBackup]:
        session = async_get_clientsession(self._hass)
        try:
            async with session.get(
                f"{self._base_url}/ingest/backups",
                headers=self._headers,
                timeout=API_TIMEOUT,
            ) as response:
                self._check(response.status)
                payload = await response.json()
        except (ClientError, asyncio.TimeoutError) as err:
            raise BackupAgentUnreachableError from err
        backups: list[AgentBackup] = []
        for item in payload.get("backups", []):
            try:
                backups.append(AgentBackup.from_dict(item["metadata"]))
            except (KeyError, TypeError, ValueError):
                _LOGGER.warning("Skipping unreadable backup entry %s", item.get("backup_id"))
        return backups

    async def async_get_backup(self, backup_id: str, **kwargs: Any) -> AgentBackup:
        session = async_get_clientsession(self._hass)
        try:
            async with session.get(
                f"{self._base_url}/ingest/backups/{backup_id}",
                headers=self._headers,
                timeout=API_TIMEOUT,
            ) as response:
                self._check(response.status, backup_id)
                payload = await response.json()
        except (ClientError, asyncio.TimeoutError) as err:
            raise BackupAgentUnreachableError from err
        try:
            return AgentBackup.from_dict(payload["metadata"])
        except (KeyError, TypeError, ValueError) as err:
            raise BackupAgentError("Stored backup metadata is unreadable") from err
