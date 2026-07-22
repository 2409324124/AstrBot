import json

import pytest

from astrbot.core.db.vec_db.qdrant_impl.vec_db import QdrantVecDB


class FakeEmbeddingProvider:
    """Return deterministic vectors for vector database behavior tests."""

    def __init__(self) -> None:
        self.batch_calls = 0
        self.dimension = 3

    def get_dim(self) -> int:
        return self.dimension

    async def get_embedding(self, text: str) -> list[float]:
        vectors = {
            "alpha": [1.0, 0.0, 0.0],
            "beta": [0.0, 1.0, 0.0],
        }
        return vectors[text]

    async def get_embeddings_batch(
        self,
        texts: list[str],
        **_kwargs,
    ) -> list[list[float]]:
        self.batch_calls += 1
        return [await self.get_embedding(text) for text in texts]


@pytest.mark.asyncio
async def test_inserted_chunk_can_be_retrieved(tmp_path) -> None:
    """A stored chunk is returned through the public retrieval interface."""
    vec_db = QdrantVecDB(
        doc_store_path=str(tmp_path / "doc.db"),
        collection_name="test_kb",
        qdrant_url=":memory:",
        embedding_provider=FakeEmbeddingProvider(),
    )
    await vec_db.initialize()

    await vec_db.insert(
        "alpha",
        metadata={"kb_id": "kb-1", "kb_doc_id": "doc-1", "chunk_index": 0},
        id="00000000-0000-0000-0000-000000000001",
    )

    results = await vec_db.retrieve(
        "alpha",
        k=1,
        metadata_filters={"kb_id": "kb-1"},
    )

    assert len(results) == 1
    assert results[0].data["doc_id"] == "00000000-0000-0000-0000-000000000001"
    assert results[0].data["text"] == "alpha"
    assert json.loads(results[0].data["metadata"])["kb_doc_id"] == "doc-1"
    assert results[0].similarity == pytest.approx(1.0)

    await vec_db.close()


@pytest.mark.asyncio
async def test_batch_insert_uses_one_embedding_batch(tmp_path) -> None:
    """Batch ingestion uses the provider batch API and stores every chunk."""
    provider = FakeEmbeddingProvider()
    vec_db = QdrantVecDB(
        doc_store_path=str(tmp_path / "doc.db"),
        collection_name="test_kb",
        qdrant_url=":memory:",
        embedding_provider=provider,
    )
    await vec_db.initialize()

    row_ids = await vec_db.insert_batch(
        contents=["alpha", "beta"],
        metadatas=[
            {"kb_id": "kb-1", "kb_doc_id": "doc-1", "chunk_index": 0},
            {"kb_id": "kb-1", "kb_doc_id": "doc-1", "chunk_index": 1},
        ],
        ids=[
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
        ],
    )

    assert provider.batch_calls == 1
    assert len(row_ids) == 2
    assert await vec_db.count_documents({"kb_doc_id": "doc-1"}) == 2

    await vec_db.close()


@pytest.mark.asyncio
async def test_document_chunks_can_be_deleted_by_metadata(tmp_path) -> None:
    """Deleting a knowledge document removes SQLite and Qdrant chunks."""
    vec_db = QdrantVecDB(
        doc_store_path=str(tmp_path / "doc.db"),
        collection_name="test_kb",
        qdrant_url=":memory:",
        embedding_provider=FakeEmbeddingProvider(),
    )
    await vec_db.initialize()
    await vec_db.insert_batch(
        contents=["alpha", "beta"],
        metadatas=[
            {"kb_id": "kb-1", "kb_doc_id": "doc-1", "chunk_index": 0},
            {"kb_id": "kb-1", "kb_doc_id": "doc-1", "chunk_index": 1},
        ],
        ids=[
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002",
        ],
    )

    await vec_db.delete_documents({"kb_doc_id": "doc-1"})

    assert await vec_db.count_documents({"kb_doc_id": "doc-1"}) == 0
    assert await vec_db.retrieve("alpha", k=5) == []

    await vec_db.close()


@pytest.mark.asyncio
async def test_existing_collection_rejects_embedding_dimension_change(tmp_path) -> None:
    """Initialization fails before use when collection dimensions do not match."""
    provider = FakeEmbeddingProvider()
    vec_db = QdrantVecDB(
        doc_store_path=str(tmp_path / "doc.db"),
        collection_name="test_kb",
        qdrant_url=":memory:",
        embedding_provider=provider,
    )
    await vec_db.initialize()
    provider.dimension = 2

    with pytest.raises(ValueError, match="dimension"):
        await vec_db.initialize()

    await vec_db.close()
