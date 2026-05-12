"""Factory function for creating search service instances."""

from app.domain.ports.search_port import AbstractSearchService
from app.infrastructure.search.bm25_elasticsearch import ElasticsearchBM25Search
from app.infrastructure.search.bm25_memory import MemoryBM25Search
from app.shared.logging import logger


def create_search_service(backend: str, **kwargs) -> AbstractSearchService:
    """Create a search service backend based on the named strategy.

    Args:
        backend: One of 'elasticsearch' or 'memory'.
        **kwargs: Backend-specific keyword arguments (e.g. es_url,
            index_name for Elasticsearch).

    Returns:
        An instance implementing AbstractSearchService.
    """
    if backend == "elasticsearch":
        logger.info("Creating ElasticsearchBM25Search backend.")
        return ElasticsearchBM25Search(**kwargs)
    logger.info("Creating MemoryBM25Search backend (default).")
    return MemoryBM25Search()
