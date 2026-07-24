"""Semantic knowledge-base selection with cached local embeddings."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from astrbot.core.provider.provider import EmbeddingProvider

_MAX_CACHE_ENTRIES = 512
_prototype_embedding_cache: dict[
    tuple[int, str, str],
    tuple[tuple[float, ...], ...],
] = {}


@dataclass(frozen=True)
class KnowledgeBaseCandidate:
    """One session-authorized knowledge base and its routing prototypes."""

    kb_id: str
    kb_name: str
    prototypes: tuple[str, ...]


@dataclass(frozen=True)
class KnowledgeBaseSelection:
    """A selected candidate with its best prototype similarity."""

    candidate: KnowledgeBaseCandidate
    similarity: float


def clear_selector_cache() -> None:
    """Clear cached prototype vectors (primarily for lifecycle and tests)."""
    _prototype_embedding_cache.clear()


def _cache_key(
    provider: EmbeddingProvider,
    candidate: KnowledgeBaseCandidate,
) -> tuple[int, str, str]:
    payload = "\0".join(candidate.prototypes).encode("utf-8")
    return id(provider), candidate.kb_id, hashlib.sha256(payload).hexdigest()


def _cosine(left: list[float], right: tuple[float, ...]) -> float:
    if not left or len(left) != len(right):
        return -1.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return -1.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (
        left_norm * right_norm
    )


async def select_knowledge_bases(
    query: str,
    candidates: list[KnowledgeBaseCandidate],
    embedding_provider: EmbeddingProvider,
    *,
    min_similarity: float = 0.52,
    max_bases: int = 2,
) -> list[KnowledgeBaseSelection]:
    """Select relevant authorized KBs without ever widening the candidate set."""
    if not query.strip() or not candidates or max_bases <= 0:
        return []

    usable = [candidate for candidate in candidates if candidate.prototypes]
    if not usable:
        return []

    missing: list[KnowledgeBaseCandidate] = []
    missing_texts: list[str] = []
    for candidate in usable:
        if _cache_key(embedding_provider, candidate) in _prototype_embedding_cache:
            continue
        missing.append(candidate)
        missing_texts.extend(candidate.prototypes)

    if missing_texts:
        vectors = await embedding_provider.get_embeddings(missing_texts)
        if len(vectors) != len(missing_texts):
            raise ValueError("Embedding provider returned an unexpected vector count")
        offset = 0
        if len(_prototype_embedding_cache) + len(missing) > _MAX_CACHE_ENTRIES:
            clear_selector_cache()
        for candidate in missing:
            count = len(candidate.prototypes)
            candidate_vectors = vectors[offset : offset + count]
            _prototype_embedding_cache[_cache_key(embedding_provider, candidate)] = (
                tuple(
                    tuple(float(value) for value in vector)
                    for vector in candidate_vectors
                )
            )
            offset += count

    query_vector = [
        float(value) for value in await embedding_provider.get_embedding(query)
    ]
    selected: list[KnowledgeBaseSelection] = []
    for candidate in usable:
        vectors = _prototype_embedding_cache[_cache_key(embedding_provider, candidate)]
        similarity = max(_cosine(query_vector, vector) for vector in vectors)
        if similarity >= min_similarity:
            selected.append(KnowledgeBaseSelection(candidate, similarity))

    selected.sort(key=lambda item: item.similarity, reverse=True)
    return selected[:max_bases]


__all__ = [
    "KnowledgeBaseCandidate",
    "KnowledgeBaseSelection",
    "clear_selector_cache",
    "select_knowledge_bases",
]
