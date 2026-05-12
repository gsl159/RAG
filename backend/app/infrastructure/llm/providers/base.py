"""Base types for LLM providers."""

from dataclasses import dataclass
from typing import AsyncGenerator, Protocol


@dataclass
class LLMProviderConfig:
    """Configuration for a single LLM provider."""

    name: str
    api_base: str
    api_key: str
    model: str
    embed_model: str = ""
    priority: int = 0  # lower = higher priority


class AbstractLLMProvider(Protocol):
    """Protocol for individual LLM provider implementations."""

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 1024,
        model: str = "",
    ) -> str: ...

    async def chat_json(
        self,
        messages: list[dict[str, str]],
        model: str = "",
    ) -> dict: ...

    async def stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        model: str = "",
    ) -> AsyncGenerator[str, None]: ...

    async def embed_one(self, text: str, model: str = "") -> list[float]: ...

    async def embed_batch(
        self,
        texts: list[str],
        batch_size: int = 32,
        model: str = "",
    ) -> list[list[float]]: ...

    async def close(self) -> None: ...
