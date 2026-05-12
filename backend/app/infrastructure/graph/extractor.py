"""
GraphExtractor -- LLM-based entity and relation extraction from text.

Uses an LLM service (compatible with ``AbstractLLMService``) to extract
structured entities and relations from document chunks.  Designed for
graceful degradation: returns empty lists on any failure.
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.shared.logging import logger

_EXTRACT_PROMPT = """You are an information extraction expert. Extract entities and \
relations from the following text.

Requirements:
1. Extract important entities (people, organizations, concepts, events, locations)
2. Extract relations between entities
3. Return JSON only, no other text

Output format:
{
  "entities": [
    {"name": "entity name", "type": "person|org|concept|event|location", "description": "short description"}
  ],
  "relations": [
    {"source": "source entity", "target": "target entity", "relation_type": "relation type", "description": "relation description", "weight": 1.0}
  ]
}

Text:
"""

_DEFAULT_TIMEOUT = 30.0
_TEXT_TRUNCATE = 1500


class GraphExtractor:
    """Extracts entities and relations from text using an LLM service.

    The extraction is timeout-protected and degrades gracefully:
    if the LLM call fails or times out, empty lists are returned.

    Usage::

        extractor = GraphExtractor()
        entities, relations = await extractor.extract_entities_relations(
            text="Some document text...",
            llm_service=llm_client,
        )
    """

    def __init__(self, timeout: float = _DEFAULT_TIMEOUT) -> None:
        self._timeout = timeout

    async def extract_entities_relations(
        self,
        text: str,
        llm_service: Any,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Extract structured entities and relations from *text*.

        Args:
            text: The raw text to analyse.
            llm_service: An object with a ``chat_json(messages)`` async
                method (e.g. the global ``llm_client``).

        Returns:
            A ``(entities, relations)`` pair.  Each entity dict has keys
            ``name``, ``type``, ``description``.  Each relation dict has
            keys ``source``, ``target``, ``relation_type``, ``description``,
            ``weight``.  Returns ``([], [])`` on any failure or if the
            input text is too short.
        """
        if not text or len(text.strip()) < 20:
            return [], []

        # Truncate input to control token usage
        truncated = text.strip()[:_TEXT_TRUNCATE]
        messages = [{"role": "user", "content": _EXTRACT_PROMPT + truncated}]

        try:
            result = await asyncio.wait_for(
                llm_service.chat_json(messages),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "GraphExtractor timeout after %.1fs (text length {})",
                self._timeout,
                len(text),
            )
            return [], []
        except Exception as exc:
            logger.warning(
                "GraphExtractor LLM call failed: {}: {}",
                type(exc).__name__,
                repr(exc),
            )
            return [], []

        return self._parse_result(result)

    @staticmethod
    def _parse_result(
        result: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Parse and validate the LLM JSON output."""
        entities: list[dict[str, Any]] = []
        relations: list[dict[str, Any]] = []

        raw_entities = result.get("entities", [])
        if not isinstance(raw_entities, list):
            raw_entities = []

        for e_data in raw_entities:
            if not isinstance(e_data, dict):
                continue
            name = (e_data.get("name") or "").strip()
            if not name or len(name) > 50:
                continue
            entities.append({
                "name": name,
                "type": e_data.get("type", "concept"),
                "description": e_data.get("description", ""),
            })

        entity_names = {e["name"] for e in entities}
        raw_relations = result.get("relations", [])
        if not isinstance(raw_relations, list):
            raw_relations = []

        for r_data in raw_relations:
            if not isinstance(r_data, dict):
                continue
            source = (r_data.get("source") or "").strip()
            target = (r_data.get("target") or "").strip()
            rel_type = (
                r_data.get("relation_type") or r_data.get("relation") or ""
            ).strip()
            if not source or not target or not rel_type:
                continue
            if source not in entity_names or target not in entity_names:
                continue
            relations.append({
                "source": source,
                "target": target,
                "relation_type": rel_type,
                "description": r_data.get("description", ""),
                "weight": min(max(float(r_data.get("weight", 1.0)), 0.0), 1.0),
            })

        return entities, relations
