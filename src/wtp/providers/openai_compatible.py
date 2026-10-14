"""Any server that speaks the OpenAI Chat Completions API: Ollama, llama.cpp,
vLLM, LM Studio, Groq, OpenRouter, OpenAI, and others.

Chat Completions, not the newer Responses API: most compatible servers only
implement the former (Ollama returns 404 for /v1/responses, checked 2026-10-14).
"""
from __future__ import annotations

import json
from typing import Any

from wtp.providers.base import ProviderConfig

try:
    from openai import BadRequestError, OpenAI
except ImportError:  # pragma: no cover - exercised only when dependency is missing at runtime
    OpenAI = None
    BadRequestError = Exception


class OpenAICompatibleProvider:
    def __init__(self, config: ProviderConfig):
        if OpenAI is None:
            raise RuntimeError("The `openai` package is required for OpenAI-compatible providers.")
        if not config.base_url:
            raise RuntimeError("Missing base URL. Set LLM_BASE_URL.")

        self._config = config
        self._client = OpenAI(api_key=config.api_key or "not-needed", base_url=config.base_url)
        # How the last reply was constrained: "json_schema" (server enforced the
        # schema) or "json_object" (server only promised JSON; schema in prompt).
        self.structured_mode: str | None = None

    def _create(self, messages: list[dict[str, str]], response_format: dict[str, Any]) -> str:
        response = self._client.chat.completions.create(
            model=self._config.model_name,
            messages=messages,
            response_format=response_format,
        )
        return response.choices[0].message.content or ""

    def generate(self, prompt: str, system_instruction: str, schema: dict[str, Any]) -> str:
        messages = [{"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt}]
        try:
            text = self._create(messages, {"type": "json_schema", "json_schema": {
                "name": "wtp_analysis", "schema": schema, "strict": True}})
            self.structured_mode = "json_schema"
            return text
        except BadRequestError:
            # Server can't enforce a schema. Ask for plain JSON and put the schema
            # in the instructions; model_output validates the reply either way.
            messages[0] = {"role": "system", "content": system_instruction
                           + "\n\nReply with one JSON object that matches this JSON Schema exactly:\n"
                           + json.dumps(schema)}
            text = self._create(messages, {"type": "json_object"})
            self.structured_mode = "json_object"
            return text
