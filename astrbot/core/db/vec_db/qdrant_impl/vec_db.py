import json
import uuid

from qdrant_client import AsyncQdrantClient, models

from astrbot.core.exceptions import KnowledgeBaseUploadError
from astrbot.core.provider.provider import EmbeddingProvider, RerankProvider

from ..base import BaseVecDB, Result
from ..faiss_impl.document_storage import DocumentStorage


class QdrantVecDB(BaseVecDB):
    """Store dense vectors in Qdrant while retaining AstrBot document storage."""

    def __init__(
        self,
        doc_store_path: str,
        collection_name: str,
        qdrant_url: str,
        embedding_provider: EmbeddingProvider,
        rerank_provider: RerankProvider | None = None,
        api_key: str | None = None,
        timeout: int = 10,
    ) -> None:
        """Initialize a Qdrant-backed vector database.

        Args:
            doc_store_path: Path to AstrBot's SQLite chunk database.
            collection_name: Qdrant collection used by this knowledge base.
            qdrant_url: Qdrant HTTP URL or ``:memory:`` for tests.
            embedding_provider: Provider used to create dense vectors.
            rerank_provider: Optional provider used to rerank dense results.
            api_key: Optional Qdrant API key.
            timeout: Qdrant request timeout in seconds.
        """
        self.collection_name = collection_name
        self.embedding_provider = embedding_provider
        self.rerank_provider = rerank_provider
        self.document_storage = DocumentStorage(doc_store_path)
        if qdrant_url == ":memory:":
            self.client = AsyncQdrantClient(location=":memory:")
        else:
            self.client = AsyncQdrantClient(
                url=qdrant_url,
                api_key=api_key,
                timeout=timeout,
            )

    async def initialize(self) -> None:
        """Initialize local document storage and the Qdrant collection."""
        await self.document_storage.initialize()
        if not await self.client.collection_exists(self.collection_name):
            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=self.embedding_provider.get_dim(),
                    distance=models.Distance.COSINE,
                ),
            )
        else:
            collection = await self.client.get_collection(self.collection_name)
            vectors_config = collection.config.params.vectors
            if isinstance(vectors_config, dict):
                raise ValueError(
                    "Qdrant collection uses named vectors, but AstrBot requires "
                    "one unnamed dense vector.",
                )
            actual_dimension = vectors_config.size
            expected_dimension = self.embedding_provider.get_dim()
            if actual_dimension != expected_dimension:
                raise ValueError(
                    "Qdrant collection dimension mismatch: "
                    f"expected {expected_dimension}, got {actual_dimension}.",
                )

    async def insert(
        self,
        content: str,
        metadata: dict | None = None,
        id: str | None = None,
    ) -> int:
        """Insert one chunk into SQLite and Qdrant.

        Args:
            content: Chunk text.
            metadata: AstrBot chunk metadata.
            id: Stable AstrBot chunk ID.

        Returns:
            SQLite integer row ID.
        """
        metadata = metadata or {}
        chunk_id = id or str(uuid.uuid4())
        try:
            point_id = str(uuid.UUID(chunk_id))
        except ValueError:
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"astrbot:{chunk_id}"))

        vector = await self.embedding_provider.get_embedding(content)
        int_id = await self.document_storage.insert_document(
            chunk_id,
            content,
            metadata,
        )
        try:
            await self.client.upsert(
                collection_name=self.collection_name,
                points=[
                    models.PointStruct(
                        id=point_id,
                        vector=vector,
                        payload={
                            "doc_id": chunk_id,
                            "text": content,
                            "metadata": metadata,
                        },
                    ),
                ],
                wait=True,
            )
        except Exception:
            await self.document_storage.delete_document_by_doc_id(chunk_id)
            raise
        return int_id

    async def insert_batch(
        self,
        contents: list[str],
        metadatas: list[dict] | None = None,
        ids: list[str] | None = None,
        batch_size: int = 32,
        tasks_limit: int = 3,
        max_retries: int = 3,
        progress_callback=None,
    ) -> list[int]:
        """Insert chunks with one batched embedding request.

        Args:
            contents: Chunk texts.
            metadatas: Metadata for each chunk.
            ids: Stable chunk IDs.
            batch_size: Embedding batch size.
            tasks_limit: Maximum concurrent embedding tasks.
            max_retries: Embedding retry count.
            progress_callback: Optional embedding progress callback.

        Returns:
            SQLite integer row IDs.
        """
        if not contents:
            return []
        metadatas = metadatas or [{} for _ in contents]
        ids = ids or [str(uuid.uuid4()) for _ in contents]
        if len(metadatas) != len(contents) or len(ids) != len(contents):
            raise KnowledgeBaseUploadError(
                stage="storage",
                user_message="存储失败：文本、元数据和分块 ID 数量不一致。",
                details={
                    "contents": len(contents),
                    "metadatas": len(metadatas),
                    "ids": len(ids),
                },
            )

        vectors = await self.embedding_provider.get_embeddings_batch(
            contents,
            batch_size=batch_size,
            tasks_limit=tasks_limit,
            max_retries=max_retries,
            progress_callback=progress_callback,
        )
        dimension = self.embedding_provider.get_dim()
        if len(vectors) != len(contents) or any(
            len(vector) != dimension for vector in vectors
        ):
            raise KnowledgeBaseUploadError(
                stage="embedding",
                user_message="向量化失败：返回向量的数量或维度不正确。",
                details={
                    "expected_count": len(contents),
                    "actual_count": len(vectors),
                    "expected_dimension": dimension,
                },
            )

        points = []
        for chunk_id, content, metadata, vector in zip(
            ids,
            contents,
            metadatas,
            vectors,
        ):
            try:
                point_id = str(uuid.UUID(chunk_id))
            except ValueError:
                point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"astrbot:{chunk_id}"))
            points.append(
                models.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "doc_id": chunk_id,
                        "text": content,
                        "metadata": metadata,
                    },
                ),
            )

        int_ids = await self.document_storage.insert_documents_batch(
            ids,
            contents,
            metadatas,
        )
        try:
            await self.client.upsert(
                collection_name=self.collection_name,
                points=points,
                wait=True,
            )
        except Exception:
            for chunk_id in ids:
                await self.document_storage.delete_document_by_doc_id(chunk_id)
            raise
        return int_ids

    async def retrieve(
        self,
        query: str,
        k: int = 5,
        fetch_k: int = 20,
        rerank: bool = False,
        metadata_filters: dict | None = None,
    ) -> list[Result]:
        """Retrieve chunks by dense similarity.

        Args:
            query: Query text.
            k: Maximum number of results.
            fetch_k: Candidate count reserved for compatible call sites.
            rerank: Whether to rerank returned chunks.
            metadata_filters: Exact-match filters for chunk metadata.

        Returns:
            Ranked vector database results.
        """
        del fetch_k
        conditions = [
            models.FieldCondition(
                key=f"metadata.{key}",
                match=models.MatchValue(value=value),
            )
            for key, value in (metadata_filters or {}).items()
        ]
        response = await self.client.query_points(
            collection_name=self.collection_name,
            query=await self.embedding_provider.get_embedding(query),
            query_filter=models.Filter(must=conditions) if conditions else None,
            limit=k,
            with_payload=True,
        )
        results = []
        for point in response.points:
            payload = point.payload or {}
            results.append(
                Result(
                    similarity=float(point.score),
                    data={
                        "doc_id": str(payload.get("doc_id", point.id)),
                        "text": str(payload.get("text", "")),
                        "metadata": json.dumps(payload.get("metadata", {})),
                    },
                ),
            )

        if rerank and self.rerank_provider and results:
            reranked = await self.rerank_provider.rerank(
                query,
                [result.data["text"] for result in results],
            )
            return [results[item.index] for item in reranked]
        return results

    async def delete(self, doc_id: str) -> None:
        """Delete one chunk from Qdrant and SQLite.

        Args:
            doc_id: Stable AstrBot chunk ID.
        """
        try:
            point_id = str(uuid.UUID(doc_id))
        except ValueError:
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"astrbot:{doc_id}"))
        await self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.PointIdsList(points=[point_id]),
            wait=True,
        )
        await self.document_storage.delete_document_by_doc_id(doc_id)

    async def count_documents(self, metadata_filter: dict | None = None) -> int:
        """Count chunks in AstrBot's local document store.

        Args:
            metadata_filter: Optional exact-match metadata filters.

        Returns:
            Number of matching chunks.
        """
        return await self.document_storage.count_documents(
            metadata_filters=metadata_filter or {},
        )

    async def delete_documents(self, metadata_filters: dict) -> None:
        """Delete chunks matching metadata from Qdrant and SQLite.

        Args:
            metadata_filters: Exact-match metadata filters.
        """
        conditions = [
            models.FieldCondition(
                key=f"metadata.{key}",
                match=models.MatchValue(value=value),
            )
            for key, value in metadata_filters.items()
        ]
        await self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(must=conditions),
            ),
            wait=True,
        )
        await self.document_storage.delete_documents(
            metadata_filters=metadata_filters,
        )

    async def close(self) -> None:
        """Close Qdrant and SQLite clients."""
        await self.client.close()
        await self.document_storage.close()
