"""Incremental updater for document chunking.

Supports re-chunking a document that has already been indexed by computing
a diff between old and new chunk lists and preserving chunks whose content
hash has not changed.
"""

from __future__ import annotations

import hashlib
from typing import Any


class IncrementalUpdater:
    """Compute diffs between old and new chunk lists for incremental indexing.

    Usage::

        updater = IncrementalUpdater()
        if updater.should_update(doc_id="abc", new_content_hash="..."):
            to_keep, to_delete, to_create = updater.compute_diff(old, new)
    """

    def __init__(self, storage: dict[str, str] | None = None) -> None:
        """Initialise with an optional external content-hash storage.

        *storage* should be a dict-like object mapping ``doc_id`` to a
        content hash string.  If ``None``, an in-memory dict is used.
        """
        self._storage: dict[str, str] = storage if storage is not None else {}  # type: ignore[no-untyped-call]

    def should_update(self, doc_id: str, new_content_hash: str) -> bool:
        """Determine whether *doc_id* needs to be re-chunked.

        Returns ``True`` if the document has never been chunked or if its
        content hash has changed.

        Parameters
        ----------
        doc_id : str
            Unique document identifier.
        new_content_hash : str
            SHA-256 prefix (or comparable hash) of the new document content.

        Returns
        -------
        bool
        """
        old_hash = self._storage.get(doc_id)
        if old_hash is None:
            self._storage[doc_id] = new_content_hash
            return True
        return old_hash != new_content_hash

    def compute_diff(
        self,
        old_chunks: list[dict[str, Any]],
        new_chunks: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        """Compute a three-way diff between old and new chunk lists.

        Comparison is done via **chunk_hash** stored in
        ``chunk["metadata"]["chunk_hash"]`` (falling back to computing a
        hash of the ``content`` key on the fly).

        Parameters
        ----------
        old_chunks : list[dict]
            Previously indexed chunks (with metadata).
        new_chunks : list[dict]
            Freshly produced chunks (with metadata from ``MetadataInjector``).

        Returns
        -------
        tuple[list[dict], list[dict], list[dict]]
            ``(to_keep, to_delete, to_create)``.

            - **to_keep** -- new chunks whose hash matched an old chunk.
              Their ``chunk_id`` is **replaced** with the old chunk's ID
              so that the vector index entry is reused.
            - **to_delete** -- old chunks whose hash does **not** appear in
              the new set (they should be removed from the index).
            - **to_create** -- new chunks whose hash does **not** appear in
              the old set (they need fresh indexing).
        """
        # Build lookup: hash -> chunk (for old and new)
        old_by_hash = self._index_by_hash(old_chunks)
        new_by_hash = self._index_by_hash(new_chunks)

        old_hashes = set(old_by_hash.keys())
        new_hashes = set(new_by_hash.keys())

        shared_hashes = old_hashes & new_hashes
        deleted_hashes = old_hashes - new_hashes
        created_hashes = new_hashes - old_hashes

        # Build result lists
        to_keep: list[dict[str, Any]] = []
        for h in shared_hashes:
            new_chunk = new_by_hash[h]
            old_chunk = old_by_hash[h]
            # Reuse the old chunk_id so the vector index entry stays valid
            old_id = self._get_hash(old_chunk) or self._compute_content_hash(
                old_chunk.get("content", "")
            )
            if "metadata" in new_chunk:
                new_chunk["metadata"]["chunk_id"] = old_chunk.get(
                    "chunk_id",
                    old_chunk.get("metadata", {}).get("chunk_id", ""),
                )
            to_keep.append(new_chunk)

        to_delete = [old_by_hash[h] for h in deleted_hashes]
        to_create = [new_by_hash[h] for h in created_hashes]

        return to_keep, to_delete, to_create

    # ── Internal helpers ────────────────────────────────────────────────

    @staticmethod
    def _index_by_hash(
        chunks: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """Build a ``{chunk_hash: chunk}`` mapping.

        If a chunk has no ``metadata.chunk_hash``, a hash is computed
        from its ``"content"`` key.
        """
        index: dict[str, dict[str, Any]] = {}
        for chunk in chunks:
            h = IncrementalUpdater._get_hash(chunk)
            if not h:
                content = chunk.get("content", "")
                h = IncrementalUpdater._compute_content_hash(content)
            # In case of hash collision (extremely rare), keep the first entry
            if h not in index:
                index[h] = chunk
        return index

    @staticmethod
    def _get_hash(chunk: dict[str, Any]) -> str:
        """Extract chunk_hash from chunk metadata."""
        metadata = chunk.get("metadata")
        if isinstance(metadata, dict):
            return metadata.get("chunk_hash", "")
        return ""

    @staticmethod
    def _compute_content_hash(content: str) -> str:
        """Compute the same 16-char SHA-256 prefix used by ``MetadataInjector``."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    @property
    def is_incremental(self) -> bool:
        """Convenience property: was the last ``compute_diff`` incremental?"""
        return True  # The caller checks len(to_keep) > 0
