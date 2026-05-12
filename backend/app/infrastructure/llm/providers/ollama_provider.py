"""Ollama LLM provider implementation.

Note: Ollama does not support the ``response_format`` parameter for JSON mode.
The ``chat_json`` method falls back to appending a JSON instruction to the
system prompt instead.
"""

import asyncio
import json
from typing import AsyncGenerator

import httpx

from app.infrastructure.llm.providers.base import LLMProviderConfig
from app.shared.logging import logger

_JSON_SYSTEM_PROMPT = "Respond with valid JSON only, no markdown, no explanation."


class OllamaProvider:
    """Ollama provider for chat completions.

    Embedding is not typically supported by Ollama; the embed methods will
    raise a ``NotImplementedError`` unless the configured model implements
    an embedding endpoint.
    """

    def __init__(self, config: LLMProviderConfig) -> None:
        self.config = config
        self._client = httpx.AsyncClient(
            timeout=120,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
        }

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        max_retries: int = 2,
        **kwargs,
    ) -> httpx.Response:
        """HTTP request with exponential backoff retry (5xx / timeout / connection errors only)."""
        last_exc: Exception | None = None
        for attempt in range(max_retries):
            try:
                resp = await self._client.request(method, url, **kwargs)
                if resp.status_code < 500:
                    return resp
                last_exc = httpx.HTTPStatusError(
                    f"Server error {resp.status_code}",
                    request=resp.request,
                    response=resp,
                )
                logger.warning(
                    f"Ollama HTTP {resp.status_code} on attempt {attempt + 1}/{max_retries}"
                )
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_exc = e
                logger.warning(
                    f"Ollama {type(e).__name__} on attempt {attempt + 1}/{max_retries}"
                )
            if attempt < max_retries - 1:
                await asyncio.sleep(min(2**attempt, 2))
        raise last_exc  # type: ignore[misc]

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 1024,
        model: str = "",
    ) -> str:
        resp = await self._request_with_retry(
            "POST",
            f"{self.config.api_base}/chat/completions",
            headers=self._headers(),
            json={
                "model": model or self.config.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    async def chat_json(
        self,
        messages: list[dict[str, str]],
        model: str = "",
    ) -> dict:
        """Ollama does not support ``response_format``; inject JSON instruction instead."""
        injected = list(messages)
        if injected and injected[0].get("role") == "system":
            injected[0]["content"] = (
                injected[0]["content"] + "\n\n" + _JSON_SYSTEM_PROMPT
            )
        else:
            injected.insert(
                0, {"role": "system", "content": _JSON_SYSTEM_PROMPT}
            )

        resp = await self._request_with_retry(
            "POST",
            f"{self.config.api_base}/chat/completions",
            headers=self._headers(),
            json={
                "model": model or self.config.model,
                "messages": injected,
                "temperature": 0,
                "max_tokens": 512,
            },
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]
        return json.loads(raw)

    async def stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        model: str = "",
    ) -> AsyncGenerator[str, None]:
        async with self._client.stream(
            "POST",
            f"{self.config.api_base}/chat/completions",
            headers=self._headers(),
            json={
                "model": model or self.config.model,
                "messages": messages,
                "stream": True,
                "temperature": temperature,
                "max_tokens": 1024,
            },
        ) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except Exception:
                        pass

    async def embed_one(self, text: str, model: str = "") -> list[float]:
        results = await self.embed_batch([text], model=model)
        return results[0]

    async def embed_batch(
        self,
        texts: list[str],
        batch_size: int = 32,
        model: str = "",
    ) -> list[list[float]]:
        all_vecs: list[list[float]] = []
        effective_model = model or self.config.embed_model
        if not effective_model:
            raise NotImplementedError(
                "Ollama provider requires an embed_model to be configured for embeddings."
            )
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            logger.debug(
                f"Ollama embedding batch {i}~{i + len(batch)}/{len(texts)}"
            )
            resp = await self._request_with_retry(
                "POST",
                f"{self.config.api_base}/embeddings",
                headers=self._headers(),
                json={"model": effective_model, "input": batch},
            )
            resp.raise_for_status()
            items = sorted(resp.json()["data"], key=lambda x: x["index"])
            all_vecs.extend(item["embedding"] for item in items)
        return all_vecs

    async def close(self) -> None:
        await self._client.aclose()
