"""EmbeddingClient — multi-provider failover embedding service.

Implements ``AbstractEmbeddingService`` from ``domain/ports/llm_port.py``.
"""

from app.config.settings import settings
from app.infrastructure.llm.providers.base import LLMProviderConfig
from app.infrastructure.llm.providers.ollama_provider import OllamaProvider
from app.infrastructure.llm.providers.openai_provider import OpenAIProvider
from app.infrastructure.llm.providers.siliconflow import SiliconFlowProvider
from app.shared.logging import logger

_ollama_names = {"ollama", "ollama_provider"}


class EmbeddingClient:
    """Embedding client with automatic provider failover.

    Wraps provider embed methods. Only providers that have an ``embed_model``
    configured are included in the fallback chain.
    """

    def __init__(self, providers: list[LLMProviderConfig] | None = None) -> None:
        raw = _build_embed_chain() if providers is None else providers
        self._providers: list[LLMProviderConfig] = [
            p for p in raw if p.embed_model
        ]
        # Fallback: if no provider has embed_model, promote the primary
        if not self._providers and raw:
            raw[0].embed_model = settings.EMBED_MODEL
            self._providers = [raw[0]]

        self._instances = [_instantiate(cfg) for cfg in self._providers]

        if len(self._instances) > 1:
            logger.info(
                "Embed failover chain: "
                + " -> ".join(
                    f"{p.name}:{p.embed_model}" for p in self._providers
                )
            )

    async def embed_one(self, text: str) -> list[float]:
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(
        self,
        texts: list[str],
        batch_size: int = 32,
    ) -> list[list[float]]:
        last_exc: Exception | None = None
        for provider, cfg in zip(self._instances, self._providers):
            try:
                return await provider.embed_batch(
                    texts=texts,
                    batch_size=batch_size or settings.EMBED_BATCH_SIZE,
                )
            except Exception as e:
                last_exc = e
                logger.warning(
                    f"Embed provider [{cfg.name}] failed: {e}, trying next..."
                )
        raise last_exc or RuntimeError("No Embed providers available")

    async def close(self) -> None:
        for provider in self._instances:
            try:
                await provider.close()
            except Exception as e:
                logger.warning(f"Error closing embed provider: {e}")


def _build_embed_chain() -> list[LLMProviderConfig]:
    """Build provider chain for embeddings (mirrors LLM chain)."""
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

    return chain


def _instantiate(cfg: LLMProviderConfig):
    """Create a provider instance based on its name."""
    name = cfg.name.lower()
    if "siliconflow" in name:
        return SiliconFlowProvider(cfg)
    if name in _ollama_names:
        return OllamaProvider(cfg)
    return OpenAIProvider(cfg)
