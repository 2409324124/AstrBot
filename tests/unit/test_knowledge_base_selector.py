from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.knowledge_base.selector import (
    KnowledgeBaseCandidate,
    clear_selector_cache,
    select_knowledge_bases,
)


def candidate(kb_id: str, *prototypes: str) -> KnowledgeBaseCandidate:
    return KnowledgeBaseCandidate(
        kb_id=kb_id,
        kb_name=kb_id,
        prototypes=prototypes,
    )


@pytest.mark.asyncio
async def test_selector_returns_only_top_authorized_matches_above_threshold():
    provider = MagicMock()
    provider.get_embedding = AsyncMock(return_value=[1.0, 0.0])
    provider.get_embeddings = AsyncMock(
        return_value=[
            [0.60, 0.80],
            [0.90, 0.10],
            [0.80, 0.20],
            [0.80, 0.20],
        ]
    )

    selected = await select_knowledge_bases(
        "query",
        [
            candidate("weak", "weak title"),
            candidate("best", "best description", "best title"),
            candidate("second", "second title"),
        ],
        provider,
        min_similarity=0.52,
        max_bases=2,
    )

    assert [item.candidate.kb_id for item in selected] == ["best", "second"]
    assert selected[0].similarity > selected[1].similarity >= 0.52


@pytest.mark.asyncio
async def test_selector_returns_no_database_when_every_score_is_below_threshold():
    provider = MagicMock()
    provider.get_embedding = AsyncMock(return_value=[1.0, 0.0])
    provider.get_embeddings = AsyncMock(return_value=[[0.10, 0.99]])

    selected = await select_knowledge_bases(
        "unrelated",
        [candidate("docs", "unrelated title")],
        provider,
        min_similarity=0.52,
    )

    assert selected == []


@pytest.mark.asyncio
async def test_selector_caches_prototype_embeddings_but_not_query_embeddings():
    clear_selector_cache()
    provider = MagicMock()
    provider.get_embedding = AsyncMock(return_value=[1.0, 0.0])
    provider.get_embeddings = AsyncMock(return_value=[[0.90, 0.10]])
    candidates = [candidate("docs", "document title")]

    await select_knowledge_bases("first", candidates, provider)
    await select_knowledge_bases("second", candidates, provider)

    assert provider.get_embedding.await_count == 2
    provider.get_embeddings.assert_awaited_once_with(["document title"])
