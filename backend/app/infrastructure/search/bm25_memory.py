"""
Memory-based BM25 search backend implementing AbstractSearchService.

Uses rank_bm25.BM25Okapi with thread-safe access via threading.Lock.
Tokenization attempts jieba (Chinese) first, falling back to regex
whitespace/character splitting.
"""
import re
import threading
from typing import Any, Dict, List, Optional

from rank_bm25 import BM25Okapi

from app.domain.ports.search_port import AbstractSearchService
from app.shared.logging import logger


def _tokenize(text: str) -> List[str]:
    """Tokenize text: prefer jieba for Chinese, fall back to regex split."""
    try:
        import jieba

        return [w for w in jieba.cut(text) if w.strip()]
    except ImportError:
        return re.findall(r"[一-龥]+|[a-zA-Z0-9]+", text)


class MemoryBM25Search(AbstractSearchService):
    """In-memory BM25 search using BM25Okapi.

    Thread-safe: all index mutations and searches acquire a lock.
    """

    def __init__(self) -> None:
        self._corpus: List[Dict[str, Any]] = []  # list of chunk dicts
        self._tokenized: List[List[str]] = []
        self._bm25: Optional[BM25Okapi] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # AbstractSearchService interface
    # ------------------------------------------------------------------

    async def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Full-text BM25 search, returning top_k results."""
        query_tokens = _tokenize(query)
        with self._lock:
            if not self._bm25 or not self._corpus:
                return []
            scores = self._bm25.get_scores(query_tokens)
            corpus_snapshot = list(self._corpus)

        if len(scores) == 0:
            return []

        top_idx = sorted(
            range(len(scores)), key=lambda i: scores[i], reverse=True
        )[:top_k]

        results: List[Dict[str, Any]] = []
        for i in top_idx:
            if i >= len(corpus_snapshot) or scores[i] <= 0:
                continue
            doc = corpus_snapshot[i]
            results.append(
                {
                    "id": doc.get("id", f"bm25_{i}"),
                    "doc_id": doc.get("doc_id", ""),
                    "chunk_idx": doc.get("chunk_idx"),
                    "text": doc.get("text", doc.get("content", "")),
                    "score": float(scores[i]),
                    "source": "sparse",
                }
            )
        return results

    async def add_texts(self, texts: List[dict]) -> None:
        """Index new text documents.

        Each dict should contain at least 'id' and 'text' (or 'content').
        """
        if not texts:
            return
        with self._lock:
            self._corpus.extend(texts)
            new_tokenized = [
                _tokenize(t.get("text", t.get("content", ""))) for t in texts
            ]
            self._tokenized.extend(new_tokenized)
            self._bm25 = BM25Okapi(self._tokenized)
        logger.debug(f"BM25[memory] added {len(texts)} texts, total={len(self._corpus)}")

    async def remove_texts(self, chunk_ids: List[str]) -> None:
        """Remove indexed texts by their chunk IDs."""
        if not chunk_ids:
            return
        id_set = set(chunk_ids)
        removed = 0
        with self._lock:
            new_corpus: List[Dict[str, Any]] = []
            new_tokenized: List[List[str]] = []
            for doc, tokens in zip(self._corpus, self._tokenized):
                if doc.get("id") in id_set:
                    id_set.discard(doc.get("id", ""))
                    removed += 1
                else:
                    new_corpus.append(doc)
                    new_tokenized.append(tokens)
            self._corpus = new_corpus
            self._tokenized = new_tokenized
            self._bm25 = BM25Okapi(self._tokenized) if self._tokenized else None
        if removed:
            logger.debug(
                f"BM25[memory] removed {removed} texts, remaining={len(self._corpus)}"
            )

    async def clear(self) -> None:
        """Clear the entire index."""
        with self._lock:
            self._corpus.clear()
            self._tokenized.clear()
            self._bm25 = None
        logger.info("BM25[memory] index cleared.")

    async def rebuild(self, texts: List[dict]) -> None:
        """Atomically rebuild the index from a complete list of documents."""
        with self._lock:
            self._corpus = list(texts)
            self._tokenized = [
                _tokenize(t.get("text", t.get("content", ""))) for t in self._corpus
            ]
            self._bm25 = BM25Okapi(self._tokenized) if self._tokenized else None
        logger.info(f"BM25[memory] rebuilt index with {len(self._corpus)} documents.")
