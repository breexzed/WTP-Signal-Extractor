from __future__ import annotations

from google import genai
from google.genai import types

from providers.base import ProviderConfig


class GeminiProvider:
    def __init__(self, config: ProviderConfig):
        self._config = config
        self._client = genai.Client(api_key=config.api_key)

    def generate(self, prompt: str, system_instruction: str) -> str:
        response = self._client.models.generate_content(
            model=self._config.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system_instruction),
        )
        return response.text or ""
