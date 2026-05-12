"""
KnowledgeGraph -- lightweight in-memory knowledge graph with Redis persistence.

Uses an adjacency-list structure for entity-relation storage.
Thread-safe via ``threading.Lock``.  Supports BFS multi-hop traversal,
fuzzy entity search, and serialisation for Redis persistence (7-day TTL).
"""
from __future__ import annotations

import json
import re
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from app.shared.logging import logger


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class Entity:
    """A node in the knowledge graph."""

    name: str
    entity_type: str = "concept"
    description: str = ""
    doc_ids: list[str] = field(default_factory=list)
    chunk_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.entity_type,
            "description": self.description,
            "doc_ids": list(self.doc_ids),
            "chunk_ids": list(self.chunk_ids),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Entity:
        return cls(
            name=data["name"],
            entity_type=data.get("type", "concept"),
            description=data.get("description", ""),
            doc_ids=data.get("doc_ids", []),
            chunk_ids=data.get("chunk_ids", []),
        )


@dataclass
class Relation:
    """A directed, weighted edge in the knowledge graph."""

    source: str
    target: str
    relation_type: str
    description: str = ""
    weight: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "relation_type": self.relation_type,
            "description": self.description,
            "weight": self.weight,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Relation:
        return cls(
            source=data["source"],
            target=data["target"],
            relation_type=data.get("relation_type", data.get("relation", "")),
            description=data.get("description", ""),
            weight=float(data.get("weight", 1.0)),
        )


# ---------------------------------------------------------------------------
# Graph store
# ---------------------------------------------------------------------------


class KnowledgeGraph:
    """In-memory adjacency-list knowledge graph with thread safety.

    Entities and relations can be added incrementally.  Supports BFS
    multi-hop traversal, fuzzy name search, and JSON serialisation for
    external persistence (e.g. Redis with a 7-day TTL).
    """

    REDIS_KEY = "graph:knowledge"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entities: dict[str, Entity] = {}
        # adjacency: entity_name -> list of (relation_type, target_name)
        self._adjacency: dict[str, list[tuple[str, str]]] = defaultdict(list)
        self._relations: list[Relation] = []

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def entity_count(self) -> int:
        with self._lock:
            return len(self._entities)

    @property
    def relation_count(self) -> int:
        with self._lock:
            return len(self._relations)

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add_entity(self, entity: Entity) -> None:
        """Add or merge an entity into the graph."""
        with self._lock:
            existing = self._entities.get(entity.name)
            if existing is not None:
                for did in entity.doc_ids:
                    if did not in existing.doc_ids:
                        existing.doc_ids.append(did)
                for cid in entity.chunk_ids:
                    if cid not in existing.chunk_ids:
                        existing.chunk_ids.append(cid)
                if entity.description and not existing.description:
                    existing.description = entity.description
            else:
                self._entities[entity.name] = entity

    def add_relation(self, relation: Relation) -> None:
        """Add a relation edge (bidirectional indexing for traversal)."""
        with self._lock:
            self._relations.append(relation)
            self._adjacency[relation.source].append(
                (relation.relation_type, relation.target),
            )
            self._adjacency[relation.target].append(
                (relation.relation_type, relation.source),
            )

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query_entities(self, query: str) -> list[Entity]:
        """Query entities by exact name match or fuzzy description match.

        Performs a case-insensitive substring search over entity names
        and descriptions.
        """
        query_lower = query.lower()
        results: list[Entity] = []
        with self._lock:
            for ent in self._entities.values():
                if (
                    query_lower in ent.name.lower()
                    or query_lower in ent.description.lower()
                ):
                    results.append(ent)
        return results

    def multi_hop_query(
        self,
        entity_name: str,
        max_depth: int = 3,
        max_nodes: int = 50,
    ) -> list[Entity]:
        """BFS traversal from *entity_name* up to *max_depth* hops.

        Args:
            entity_name: Starting entity name.
            max_depth: Maximum traversal depth.
            max_nodes: Maximum number of entities to collect.

        Returns:
            List of reachable entities (including the start node).
        """
        with self._lock:
            if entity_name not in self._entities:
                return []

            visited: set[str] = {entity_name}
            queue: list[tuple[str, int]] = [(entity_name, 0)]
            result: list[Entity] = [self._entities[entity_name]]

            while queue and len(result) < max_nodes:
                current, depth = queue.pop(0)
                if depth >= max_depth:
                    continue
                for _rel_type, neighbor in self._adjacency.get(current, []):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        ent = self._entities.get(neighbor)
                        if ent is not None:
                            result.append(ent)
                            if len(result) >= max_nodes:
                                break
                        queue.append((neighbor, depth + 1))

            return result

    def build_subgraph_context(
        self,
        entity_names: list[str],
        max_depth: int = 2,
    ) -> str:
        """Build a human-readable subgraph context string for LLM prompts.

        Collects relations from the neighbourhood of each entity and
        formats them as ``A --[relation]--> B`` lines.
        """
        seen: set[str] = set()
        facts: list[str] = []

        with self._lock:
            for name in entity_names:
                if name not in self._entities:
                    continue
                for rel_type, neighbor in self._adjacency.get(name, []):
                    fact = f"{name} --[{rel_type}]--> {neighbor}"
                    if fact not in seen:
                        seen.add(fact)
                        facts.append(fact)

        if not facts:
            return ""

        return "【Knowledge Graph Relations】\n" + "\n".join(facts[:30])

    # ------------------------------------------------------------------
    # Entity name extraction from query
    # ------------------------------------------------------------------

    @staticmethod
    def extract_query_entities(query: str) -> list[str]:
        """Fast entity name extraction from a user query using jieba.

        Returns a list of candidate token strings extracted via
        Chinese / alphanumeric tokenisation.  The caller should match
        candidates against stored entities for final resolution.
        """
        try:
            import jieba

            words = [w.strip() for w in jieba.cut(query) if len(w.strip()) > 1]
        except ImportError:
            words = re.findall(r"[一-鿿]{2,}|[a-zA-Z0-9]{2,}", query)

        return words

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize the graph to a dictionary."""
        with self._lock:
            return {
                "entities": {
                    name: ent.to_dict() for name, ent in self._entities.items()
                },
                "relations": [r.to_dict() for r in self._relations],
            }

    def from_dict(self, data: dict[str, Any]) -> None:
        """Restore the graph from a dictionary (clears current state)."""
        with self._lock:
            self._entities.clear()
            self._adjacency.clear()
            self._relations.clear()

            for name, e_data in data.get("entities", {}).items():
                self._entities[name] = Entity.from_dict(e_data)

            for r_data in data.get("relations", []):
                rel = Relation.from_dict(r_data)
                self._relations.append(rel)
                self._adjacency[rel.source].append(
                    (rel.relation_type, rel.target),
                )
                self._adjacency[rel.target].append(
                    (rel.relation_type, rel.source),
                )

    def to_json(self) -> str:
        """Serialize the graph to a JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)

    def from_json(self, json_str: str) -> None:
        """Restore the graph from a JSON string."""
        try:
            data = json.loads(json_str)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning(f"KnowledgeGraph from_json failed: {exc}")
            return
        self.from_dict(data)

    # ------------------------------------------------------------------
    # Redis persistence helpers
    # ------------------------------------------------------------------

    async def save_to_redis(self, redis_client: Any) -> bool:
        """Persist the knowledge graph to Redis with 7-day TTL."""
        if redis_client is None:
            return False
        try:
            await redis_client.set(
                self.REDIS_KEY,
                self.to_json(),
                ex=86400 * 7,
            )
            logger.info(
                "KnowledgeGraph saved: {} entities, {} relations",
                self.entity_count,
                self.relation_count,
            )
            return True
        except Exception as exc:
            logger.warning(f"KnowledgeGraph save_to_redis failed: {exc}")
            return False

    async def load_from_redis(self, redis_client: Any) -> bool:
        """Restore the knowledge graph from Redis."""
        if redis_client is None:
            return False
        try:
            raw = await redis_client.get(self.REDIS_KEY)
            if raw:
                self.from_json(raw)
                logger.info(
                    "KnowledgeGraph restored: {} entities, {} relations",
                    self.entity_count,
                    self.relation_count,
                )
                return True
        except Exception as exc:
            logger.warning(f"KnowledgeGraph load_from_redis failed: {exc}")
        return False

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Return summary statistics."""
        with self._lock:
            type_counts: dict[str, int] = defaultdict(int)
            for ent in self._entities.values():
                type_counts[ent.entity_type or "unknown"] += 1
            return {
                "entity_count": self.entity_count,
                "relation_count": self.relation_count,
                "entity_types": dict(type_counts),
            }
