from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.components import conversation
from homeassistant.components.conversation import (
    AbstractConversationAgent,
    ConversationInput,
    ConversationResult,
)

from homeassistant.const import CONF_PROMPT

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

from google import genai
from google.genai import types as genai_types

from .const import DOMAIN, DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:

    return True


class ConversationAgent(AbstractConversationAgent):
    """conversation agent (Gemini backend)."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    @property
    def supported_languages(self) -> list[str]:
        return ["en"]

    async def async_process(
        self, user_input: ConversationInput
    ) -> ConversationResult:
        """Process a conversation request."""
        ai_key=self.hass.data.get(DOMAIN, {}).get("ai_key")
        ai_model=self.hass.data.get(DOMAIN, {}).get("ai_model")

        text = user_input.text

        client = genai.Client(api_key=ai_key)
        response = client.models.generate_content(
            model=ai_model,
            contents=text
        )
        responsetext = response.text

        return ConversationResult(
            response=responsetext,
            conversation_id=user_input.conversation_id,
        )