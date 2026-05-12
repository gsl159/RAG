"""Contextual compression: LLM compresses retrieved context to fit more info."""

from app.domain.ports.llm_port import AbstractLLMService


class ContextualCompressor:
    """Compress retrieved documents to remove irrelevant parts
    while preserving key information relevant to the query.

    When the combined retrieved context exceeds ``target_tokens`` the
    compressor uses the LLM to extract and condense only query-relevant
    passages, preserving key facts, numbers, and citations.  Contexts
    already within the budget are returned verbatim (zero-overhead path).

    Usage::

        compressor = ContextualCompressor(llm_service)
        compressed = await compressor.compress(query, documents, target_tokens=2000)
    """

    def __init__(self, llm_service: AbstractLLMService) -> None:
        self._llm = llm_service

    async def compress(
        self, query: str, documents: list[str], target_tokens: int = 2000
    ) -> str:
        """Compress *documents* to *target_tokens*, keeping query-relevant info.

        Args:
            query: The original user query (used as a relevance anchor).
            documents: List of document text strings to compress.
            target_tokens: Maximum estimated token count for the output.

        Returns:
            Compressed context string, or an empty string if *documents* is empty.
        """
        if not documents:
            return ""

        combined = "\n\n---\n\n".join(documents)
        if self._estimate_tokens(combined) <= target_tokens:
            return combined

        # LLM-based compression: truncate input to a safe length first
        max_input_chars = 8000
        truncated_input = combined[:max_input_chars]

        prompt = (
            f"Given the query: '{query}'\n\n"
            f"Extract and condense only the information relevant to answering "
            f"the query from the following text.  Preserve key facts, numbers, "
            f"and citations.\n\n"
            f"{truncated_input}"
        )
        compressed = await self._llm.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=target_tokens,
        )
        return compressed

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough token estimate: ~3 chars per token as a conservative average."""
        if not text:
            return 0
        return max(1, len(text) // 3)
