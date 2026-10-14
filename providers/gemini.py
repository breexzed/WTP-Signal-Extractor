from __future__ import annotations

from typing import Any

from google import genai
from google.genai import types

from providers.base import ProviderConfig


class GeminiProvider:
    def __init__(self, config: ProviderConfig):
        self._config = config
        self._client = genai.Client(api_key=config.api_key)
        self.structured_mode = "json_schema"  # Gemini always enforces the schema

    def generate(self, prompt: str, system_instruction: str, schema: dict[str, Any]) -> str:
        response = self._client.models.generate_content(
            model=self._config.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_json_schema=schema,
            ),
        )
        return response.text or ""
