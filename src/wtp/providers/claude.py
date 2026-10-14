"""Claude through the official Anthropic SDK, with structured outputs.

The schema goes in `output_config.format`, so Claude's reply is JSON that
matches it. The request streams because transcripts are long, and refusals
are routed server-side to a fallback model where the model supports it.
"""
from __future__ import annotations

from typing import Any

import anthropic

from wtp.providers.base import ProviderConfig

DEFAULT_MODEL = "claude-opus-5-5"
# Server-side refusal fallback ("default" routing) is accepted on these models.
FALLBACK_MODELS = {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeRefusal(RuntimeError):
    """Claude declined the request (stop_reason "refusal"). Not retried."""


class ClaudeTruncated(RuntimeError):
    """The reply hit max_tokens, so the JSON is incomplete. Not retried."""


class ClaudeProvider:
    def __init__(self, config: ProviderConfig):
        self._config = config
        # wtp.retry owns retries (and records attempts), so the SDK must not add its own.
        # No key passes nothing: the SDK then reads ANTHROPIC_API_KEY or an `ant auth login` profile.
        kwargs: dict[str, Any] = {"max_retries": 0}
        if config.api_key:
            kwargs["api_key"] = config.api_key
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self._client = anthropic.Anthropic(**kwargs)
        self.structured_mode = "json_schema"  # output_config.format always enforces it

    def generate(self, prompt: str, system_instruction: str, schema: dict[str, Any]) -> str:
        model = self._config.model_name
        request: dict[str, Any] = {
            "model": model,
            "max_tokens": 64000,
            "system": system_instruction,
            "messages": [{"role": "user", "content": prompt}],
            # Effort is set explicitly: Opus 5.5 defaults to "medium", other models to "high".
            "output_config": {"effort": "medium", "format": {"type": "json_schema", "schema": schema}},
        }
        if model in FALLBACK_MODELS:
            request["betas"] = [FALLBACK_BETA]
            request["fallbacks"] = "default"

        with self._client.beta.messages.stream(**request) as stream:
            message = stream.get_final_message()

        if message.stop_reason == "refusal":
            details = getattr(message, "stop_details", None)
            raise ClaudeRefusal(f"Claude declined ({getattr(details, 'category', None) or 'no category'}): "
                                f"{getattr(details, 'explanation', '') or ''}".strip())
        if message.stop_reason == "max_tokens":
            raise ClaudeTruncated("Claude's reply hit max_tokens; the JSON is incomplete.")
        return next((block.text for block in message.content if block.type == "text"), "")
