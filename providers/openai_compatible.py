from __future__ import annotations

from typing import Any

from providers.base import ProviderConfig

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - exercised only when dependency is missing at runtime
    OpenAI = None


class OpenAICompatibleProvider:
    def __init__(self, config: ProviderConfig):
        if OpenAI is None:
            raise RuntimeError(
                "The `openai` package is required for LLM_PROVIDER=openai_compatible."
            )
        if not config.base_url:
            raise RuntimeError(
                "Missing OpenAI-compatible base URL. Set LLM_BASE_URL or OPENAI_COMPATIBLE_BASE_URL."
            )

        self._config = config
        self._client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
        )

    def generate(self, prompt: str, system_instruction: str, schema: dict[str, Any]) -> str:
        response = self._client.responses.create(
            model=self._config.model_name,
            input=prompt,
            instructions=system_instruction,
            text={"format": {"type": "json_schema", "name": "wtp_analysis",
                             "schema": schema, "strict": True}},
        )
        return getattr(response, "output_text", "") or ""
