"""Abstract interfaces for LLM and embedding providers with failover support."""

from typing import AsyncGenerator, Protocol


class AbstractLLMService(Protocol):
    """Abstract interface for LLM providers with failover support."""

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 1024,
        model: str = "",
    ) -> str:
        """Send a chat completion request and return the response text.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            temperature: Sampling temperature (0.0-1.0).
            max_tokens: Maximum tokens in the response.
            model: Optional model name override.

        Returns:
            The generated response text.
        """
        ...

    async def chat_json(
        self,
        messages: list[dict[str, str]],
        model: str = "",
    ) -> dict:
        """Send a chat request and parse the response as JSON.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            model: Optional model name override.

        Returns:
            Parsed JSON response as a dictionary.
        """
        ...

    async def stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        model: str = "",
    ) -> AsyncGenerator[str, None]:
        """Stream a chat completion response token by token.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            temperature: Sampling temperature (0.0-1.0).
            model: Optional model name override.

        Yields:
            Response text tokens as they are generated.
        """
        ...

    async def close(self) -> None:
        """Release any resources held by the LLM service (e.g. HTTP sessions)."""
        ...


class AbstractEmbeddingService(Protocol):
    """Abstract interface for embedding providers."""

    async def embed_one(self, text: str) -> list[float]:
        """Generate an embedding vector for a single text string.

        Args:
            text: The input text to embed.

        Returns:
            A float vector representing the text embedding.
        """
        ...

    async def embed_batch(
        self,
        texts: list[str],
        batch_size: int = 32,
    ) -> list[list[float]]:
        """Generate embedding vectors for a batch of texts.

        Args:
            texts: List of input texts to embed.
            batch_size: Maximum number of texts per API call.

        Returns:
            A list of float vectors, one per input text.
        """
        ...

    async def close(self) -> None:
        """Release any resources held by the embedding service."""
        ...
