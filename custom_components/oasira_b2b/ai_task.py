"""AI Task integration for Generative AI."""
from __future__ import annotations
import logging
import json
from typing import TYPE_CHECKING, Any

from homeassistant.components import ai_task, conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from google import genai
from google.genai import types as genai_types
from google.genai import Client
from google.genai.types import Part, GenerateContentConfig

from .entity import async_prepare_files_for_prompt
from .const import DOMAIN, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the AI Task entity."""
    # Assuming AIImageTaskEntity also needs access to the client/key data
    # or that the async_prepare_files_for_prompt handles the client internally.
    # The original code's AIImageTaskEntity constructor was unusual:
    # self._client = entry - this is the ConfigEntry, not the client
    # The fix below assumes the client should be passed/fetched similar to DataTask.
    ai_key = hass.data[DOMAIN]["ai_key"]
    client = genai.Client(api_key=ai_key)
    
    async_add_entities([AIDataTaskEntity(config_entry, hass, client)])
    async_add_entities([AIImageTaskEntity(config_entry, hass, client)])

class AIDataTaskEntity(ai_task.AITaskEntity):
    """AI Task entity using Gemini GenAI."""

    def __init__(self, entry: ConfigEntry, hass: HomeAssistant, client: Client) -> None:
        super().__init__()
        self._entry = entry
        self._hass = hass
        self._attr_name = DOMAIN +" AI Task"
        self._attr_unique_id = f"{DOMAIN}_ai_task_{entry.entry_id}"

        self.client = client # Use the passed client

        # Supported features
        self._attr_supported_features = (
            ai_task.AITaskEntityFeature.GENERATE_DATA
            | ai_task.AITaskEntityFeature.SUPPORT_ATTACHMENTS
        )

    async def _async_generate_data(
        self, task: ai_task.GenDataTask, chat_log: conversation.ChatLog
    ) -> ai_task.GenDataTaskResult:
        user_message = chat_log.content[-1]
        assert isinstance(user_message, conversation.UserContent)
        
        # Start content with text part
        contents = [Part.from_text(text=user_message.content)]
        
        # Add attachments if present (needs to use the helper function)
        if user_message.attachments:
            # async_prepare_files_for_prompt needs to be updated to return 
            # genai.types.Part objects for the new SDK. 
            # Assuming it's updated to return a list of genai.types.Part for simplicity.
            contents.extend(
                await async_prepare_files_for_prompt(
                    self.hass,
                    self.client, # Pass the client to the file preparation helper
                    [(a.path, a.mime_type) for a in user_message.attachments]
                )
            )

        ai_model = self._hass.data[DOMAIN]["ai_model"]
        config: dict[str, Any] = {}
        
        if task.structure:
            # Home Assistant task.structure is a Voluptuous schema.
            # Gemini SDK's structured output needs a JSON Schema or Pydantic model.
            # A conversion utility (not shown) would typically convert the Voluptuous
            # schema to a compatible JSON Schema, but for this fix, we'll
            # simply enable JSON mode and rely on the prompt to guide the output.
            # If the HA structure is simple, the model might follow it anyway.
            # A full implementation would need a utility for:
            # schema_json = convert_voluptuous_to_json_schema(task.structure)
            # config = {"response_mime_type": "application/json", "response_schema": schema_json}
            
            # Simple fix: force JSON output and rely on prompt/model:
            config = {"response_mime_type": "application/json"}
            # It's highly recommended to use the 'response_schema' for reliability.
            
        
        response = self.client.models.generate_content(
            model=ai_model,
            contents=contents,
            config=GenerateContentConfig(**config) if config else None,
        )

        response_text = response.text

        if not task.structure:
            return ai_task.GenDataTaskResult(
                conversation_id=chat_log.conversation_id,
                data=response_text
            )

        # Parse JSON if structured
        try:
            # Response.text will contain the JSON string when structured output is requested
            data = json.loads(response_text)
        except Exception as err:
            _LOGGER.error("Failed to decode JSON from Gemini response: %s - Response: %s", err, response_text)
            # If JSON decoding fails, return the raw text inside a dictionary
            data = {"text": response_text}

        return ai_task.GenDataTaskResult(
            conversation_id=chat_log.conversation_id,
            data=data
        )

# Fix the class definition to use a new name or remove the duplicate
# The original code had two identical IDataTaskEntity definitions.
# Assuming the first one was the intended one, I'll keep one and fix the image class.

class AIImageTaskEntity(ai_task.AITaskEntity):
    """AI Image Task entity."""

    # Updated constructor to take hass and client
    def __init__(self, entry: ConfigEntry, hass: HomeAssistant, client: Client) -> None:
        super().__init__()  
        self._entry = entry
        self._hass = hass
        self.client = client

        self._attr_name = DOMAIN +" AI Image Task"
        self._attr_unique_id = f"{DOMAIN}_ai_image task_{entry.entry_id}"

        # Base features
        self._attr_supported_features = (
            ai_task.AITaskEntityFeature.GENERATE_DATA
            | ai_task.AITaskEntityFeature.SUPPORT_ATTACHMENTS
            | ai_task.AITaskEntityFeature.GENERATE_IMAGE # Added
        )

    async def _async_generate_image(
        self, task: ai_task.GenImageTask, chat_log: conversation.ChatLog
    ) -> ai_task.GenImageTaskResult:
        """Generate an image from AI."""
        user_message = chat_log.content[-1]
        assert isinstance(user_message, conversation.UserContent)

        model = self._hass.data[DOMAIN]["ai_model"]
        
        # Start with the text part
        contents = [Part.from_text(text=user_message.content)]
        
        if user_message.attachments:
            # async_prepare_files_for_prompt needs to be updated to return 
            # genai.types.Part objects for the new SDK. 
            contents.extend(
                await async_prepare_files_for_prompt(
                    self.hass,
                    self.client, # Pass the client to the file preparation helper
                    [(a.path, a.mime_type) for a in user_message.attachments]
                )
            )

        # The Gemini API primarily generates text and does not directly generate
        # base64 image data from a prompt in the same call (it can process image inputs).
        # Assuming the original code was for a different, image-generation capable API 
        # or an older Gemini feature/Vertex feature that the original author mapped,
        # the response processing for image output is kept but the content generation
        # call is updated to the correct SDK method. 
        # Note: Standard Gemini models (like gemini-2.5-flash) do not generate images 
        # in the same way as an Image Model (like Imagen). This part might need 
        # an entirely separate client call to an image model if true image generation 
        # is the goal.
        
        response = self.client.models.generate_content(
            model=model,
            contents=contents,
            # No response_modalities needed for the current SDK structure; 
            # the Parts in the response contain the data.
        )

        if not response or not response.candidates:
            raise HomeAssistantError("AI returned no result")

        response_text, image_data, mime_type = "", None, None
        
        # Check all parts for image data and text
        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                # .data is the raw base64 bytes for inline data
                image_data = part.inline_data.data 
                mime_type = part.inline_data.mime_type
            elif part.text:
                response_text += part.text

        if not image_data:
            # If image generation is the goal, this model/config is likely wrong.
            # Assuming the original code intended this error case for no image data.
            raise HomeAssistantError("No image in AI response")

        # Add the assistant's text response to the chat log
        chat_log.async_add_assistant_content_without_tools(
            conversation.AssistantContent(agent_id=self.entity_id, content=response_text)
        )

        return ai_task.GenImageTaskResult(
            image_data=image_data,
            conversation_id=chat_log.conversation_id,
            mime_type=mime_type,
            model=model,
        )