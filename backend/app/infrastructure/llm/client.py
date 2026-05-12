"""LLMClient — multi-provider failover chat client.

Implements ``AbstractLLMService`` from ``domain/ports/llm_port.py``.
"""

import json
from typing import AsyncGenerator

from app.config.settings import settings
from app.infrastructure.llm.providers.base import LLMProviderConfig
from app.infrastructure.llm.providers.ollama_provider import OllamaProvider
from app.infrastructure.llm.providers.openai_provider import OpenAIProvider
from app.infrastructure.llm.providers.siliconflow import SiliconFlowProvider
from app.shared.logging import logger

_ollama_names = {"ollama", "ollama_provider"}


class LLMClient:
    """LLM text generation client with automatic provider failover.

    Builds a provider chain sorted by ``priority`` and tries each in order
    until one succeeds.
    """

    def __init__(self, providers: list[LLMProviderConfig] | None = None) -> None:
        self._providers = _build_provider_chain() if providers is None else providers
        self._providers.sort(key=lambda p: p.priority)

        self._instances: list = []
        for cfg in self._providers:
            self._instances.append(_instantiate(cfg))

        if len(self._instances) > 1:
            logger.info(
                "LLM failover chain: "
                + " -> ".join(
                    f"{p.name}:{p.model}" for p in self._providers
                )
            )

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 1024,
        model: str = "",
    ) -> str:
        last_exc: Exception | None = None
        for provider, cfg in zip(self._instances, self._providers):
            try:
                return await provider.chat(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    model=model or "",
                )
            except Exception as e:
                last_exc = e
                logger.warning(
                    f"LLM provider [{cfg.name}] failed: {e}, trying next..."
                )
        raise last_exc or RuntimeError("No LLM providers available")

    async def chat_json(
        self,
        messages: list[dict[str, str]],
        model: str = "",
    ) -> dict:
        last_exc: Exception | None = None
        for provider, cfg in zip(self._instances, self._providers):
            try:
                return await provider.chat_json(
                    messages=messages,
                    model=model or "",
                )
            except json.JSONDecodeError as e:
                last_exc = e
                logger.warning(
                    f"LLM JSON decode error from [{cfg.name}]: {e}, trying next..."
                )
            except Exception as e:
                last_exc = e
                logger.warning(
                    f"LLM JSON provider [{cfg.name}] failed: {e}, trying next..."
                )
        raise last_exc or RuntimeError("No LLM providers available")

    async def stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        model: str = "",
    ) -> AsyncGenerator[str, None]:
        last_exc: Exception | None = None
        for provider, cfg in zip(self._instances, self._providers):
            try:
                async for token in provider.stream(
                    messages=messages,
                    temperature=temperature,
                    model=model or "",
                ):
                    yield token
                return
            except Exception as e:
                last_exc = e
                logger.warning(
                    f"LLM stream provider [{cfg.name}] failed: {e}, trying next..."
                )
        if last_exc:
            raise last_exc

    async def close(self) -> None:
        for provider in self._instances:
            try:
                await provider.close()
            except Exception as e:
                logger.warning(f"Error closing LLM provider: {e}")

    def get_model_for_intent(self, complexity: str) -> str:
        """Map C0/C1/C2 complexity tier to a specific model.

        Falls back to ``LLM_MODEL`` when the tier-specific setting is empty.
        """
        mapping = {
            "C0": settings.LLM_MODEL_C0,
            "C1": settings.LLM_MODEL_C1,
            "C2": settings.LLM_MODEL_C2,
        }
        return mapping.get(complexity, "") or settings.LLM_MODEL


def _build_provider_chain() -> list[LLMProviderConfig]:
    """Build ordered list of LLM providers: primary + fallbacks."""
    chain: list[LLMProviderConfig] = [
        LLMProviderConfig(
            name="siliconflow",
            api_base=settings.SILICONFLOW_BASE_URL,
            api_key=settings.SILICONFLOW_API_KEY,
            model=settings.LLM_MODEL,
            embed_model=settings.EMBED_MODEL,
            priority=0,
        )
    ]

    if settings.OPENAI_API_KEY:
        chain.append(
            LLMProviderConfig(
                name="openai",
                api_base=settings.OPENAI_BASE_URL,
                api_key=settings.OPENAI_API_KEY,
                model=settings.OPENAI_MODEL,
                priority=1,
            )
        )

    if settings.OLLAMA_BASE_URL and settings.OLLAMA_MODEL:
        chain.append(
            LLMProviderConfig(
                name="ollama",
                api_base=settings.OLLAMA_BASE_URL,
                api_key="ollama",
                model=settings.OLLAMA_MODEL,
                priority=2,
            )
        )

    if settings.LLM_FALLBACK_PROVIDERS:
        try:
            providers_extra = json.loads(settings.LLM_FALLBACK_PROVIDERS)
            for i, p in enumerate(providers_extra):
                chain.append(
                    LLMProviderConfig(
                        name=p.get("provider", "custom"),
                        api_base=p["base_url"],
                        api_key=p.get("api_key", ""),
                        model=p["model"],
                        embed_model=p.get("embed_model", ""),
                        priority=3 + i,
                    )
                )
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"LLM_FALLBACK_PROVIDERS parsing failed: {e}")

    return chain


def _instantiate(cfg: LLMProviderConfig):
    """Create a provider instance based on its name."""
    name = cfg.name.lower()
    if "siliconflow" in name:
        return SiliconFlowProvider(cfg)
    if name in _ollama_names:
        return OllamaProvider(cfg)
    return OpenAIProvider(cfg)
