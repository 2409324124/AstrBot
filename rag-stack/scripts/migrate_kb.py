#!/usr/bin/env python3
"""Re-embed existing AstrBot chunks and upsert them into Qdrant."""

import argparse
import asyncio
import json
import os
import sqlite3
import uuid
from pathlib import Path

import httpx
from qdrant_client import AsyncQdrantClient, models


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--knowledge-root",
        type=Path,
        default=Path(os.environ["ASTRBOT_KB_ROOT"]),
    )
    parser.add_argument(
        "--embedding-base-url",
        default=os.environ.get("EMBEDDING_BASE_URL", "http://127.0.0.1:8000/v1"),
    )
    parser.add_argument(
        "--embedding-model",
        default=os.environ.get("EMBEDDING_MODEL", "BAAI/bge-m3"),
    )
    parser.add_argument(
        "--dimension",
        type=int,
        default=int(os.environ.get("EMBEDDING_DIMENSION", "1024")),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.environ.get("EMBEDDING_BATCH_SIZE", "32")),
    )
    parser.add_argument("--kb-id", action="append", default=[])
    parser.add_argument("--result-file", type=Path)
    return parser.parse_args()


def read_chunks(db_path: Path) -> list[tuple[str, str, dict]]:
    """Read AstrBot chunks without modifying the source database.

    Args:
        db_path: Knowledge-base chunk database.

    Returns:
        Chunk ID, text, and metadata tuples ordered by SQLite row ID.
    """
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT doc_id, text, metadata FROM documents ORDER BY id",
        ).fetchall()
    finally:
        connection.close()
    return [
        (str(doc_id), str(text), json.loads(metadata or "{}"))
        for doc_id, text, metadata in rows
    ]


async def embed_batch(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    model: str,
    texts: list[str],
    dimension: int,
) -> list[list[float]]:
    """Request and validate one OpenAI-compatible embedding batch.

    Args:
        client: Shared HTTP client.
        base_url: OpenAI-compatible API base URL.
        api_key: Embedding service API key.
        model: Embedding model ID.
        texts: Chunk texts.
        dimension: Expected vector dimension.

    Returns:
        Vectors in input order.

    Raises:
        RuntimeError: If the service returns invalid vectors after retries.
    """
    endpoint = f"{base_url.rstrip('/')}/embeddings"
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            response = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model, "input": texts},
            )
            response.raise_for_status()
            data = sorted(response.json()["data"], key=lambda item: item["index"])
            vectors = [item["embedding"] for item in data]
            if len(vectors) != len(texts) or any(
                len(vector) != dimension for vector in vectors
            ):
                raise ValueError("embedding count or dimension mismatch")
            return vectors
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                await asyncio.sleep(2**attempt)
    raise RuntimeError(f"embedding batch failed after 3 attempts: {last_error}")


async def main() -> int:
    """Run the idempotent chunk migration.

    Returns:
        Process exit code.
    """
    args = parse_args()
    embedding_key = os.environ["EMBEDDING_API_KEY"]
    qdrant_key = os.environ["QDRANT_API_KEY"]
    qdrant_url = os.environ.get("QDRANT_HOST_URL", "http://127.0.0.1:6333")
    prefix = os.environ.get("ASTRBOT_QDRANT_COLLECTION_PREFIX", "astrbot_kb_")

    kb_dirs = sorted(
        path
        for path in args.knowledge_root.iterdir()
        if path.is_dir() and (path / "doc.db").is_file()
    )
    if args.kb_id:
        selected = set(args.kb_id)
        kb_dirs = [path for path in kb_dirs if path.name in selected]
    if not kb_dirs:
        raise SystemExit("no AstrBot knowledge-base chunk databases found")

    qdrant = AsyncQdrantClient(
        url=qdrant_url,
        api_key=qdrant_key,
        timeout=60,
    )
    results = []
    async with httpx.AsyncClient(timeout=120) as embedding_client:
        try:
            for kb_dir in kb_dirs:
                kb_id = kb_dir.name
                collection_name = f"{prefix}{kb_id}"
                chunks = read_chunks(kb_dir / "doc.db")
                if not await qdrant.collection_exists(collection_name):
                    await qdrant.create_collection(
                        collection_name=collection_name,
                        vectors_config=models.VectorParams(
                            size=args.dimension,
                            distance=models.Distance.COSINE,
                        ),
                    )
                    for field_name in (
                        "metadata.kb_id",
                        "metadata.kb_doc_id",
                        "doc_id",
                    ):
                        await qdrant.create_payload_index(
                            collection_name=collection_name,
                            field_name=field_name,
                            field_schema=models.PayloadSchemaType.KEYWORD,
                            wait=True,
                        )
                else:
                    collection = await qdrant.get_collection(collection_name)
                    vectors_config = collection.config.params.vectors
                    if isinstance(vectors_config, dict):
                        raise RuntimeError(
                            f"{collection_name} uses unsupported named vectors",
                        )
                    if vectors_config.size != args.dimension:
                        raise RuntimeError(
                            f"{collection_name} dimension is {vectors_config.size}, "
                            f"expected {args.dimension}",
                        )

                for offset in range(0, len(chunks), args.batch_size):
                    batch = chunks[offset : offset + args.batch_size]
                    vectors = await embed_batch(
                        embedding_client,
                        args.embedding_base_url,
                        embedding_key,
                        args.embedding_model,
                        [text for _, text, _ in batch],
                        args.dimension,
                    )
                    points = []
                    for (chunk_id, text, metadata), vector in zip(batch, vectors):
                        try:
                            point_id = str(uuid.UUID(chunk_id))
                        except ValueError:
                            point_id = str(
                                uuid.uuid5(
                                    uuid.NAMESPACE_URL,
                                    f"astrbot:{chunk_id}",
                                ),
                            )
                        points.append(
                            models.PointStruct(
                                id=point_id,
                                vector=vector,
                                payload={
                                    "doc_id": chunk_id,
                                    "text": text,
                                    "metadata": metadata,
                                },
                            ),
                        )
                    await qdrant.upsert(
                        collection_name=collection_name,
                        points=points,
                        wait=True,
                    )
                    print(
                        json.dumps(
                            {
                                "kb_id": kb_id,
                                "migrated": min(offset + len(batch), len(chunks)),
                                "total": len(chunks),
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )

                result = {
                    "kb_id": kb_id,
                    "collection": collection_name,
                    "chunks": len(chunks),
                }
                results.append(result)
        finally:
            await qdrant.close()

    if args.result_file:
        args.result_file.parent.mkdir(parents=True, exist_ok=True)
        args.result_file.write_text(
            "\n".join(json.dumps(item, ensure_ascii=False) for item in results) + "\n",
            encoding="utf-8",
        )
    print(json.dumps({"status": "ok", "knowledge_bases": results}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
