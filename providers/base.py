from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProviderConfig:
    provider_name: str
    model_name: str
    api_key: str
    base_url: str | None = None


class LLMProvider(Protocol):
    def generate(self, prompt: str, system_instruction: str) -> str:
        ...
