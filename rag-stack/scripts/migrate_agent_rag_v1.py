#!/usr/bin/env python3
"""Copy healthy AstrBot vectors into the independent hybrid RAG collection."""

import argparse
import asyncio
import json
import os
import uuid
from typing import Any

from qdrant_client import AsyncQdrantClient, models


def canonical_payload(kb_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Flatten query-critical fields while retaining original metadata.

    Args:
        kb_id: Source AstrBot knowledge-base identifier.
        payload: Existing Qdrant point payload.

    Returns:
        Canonical payload for ``agent_rag_v1``.
    """
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    chunk_id = str(payload.get("doc_id") or metadata.get("chunk_id") or "")
    doc_id = str(metadata.get("kb_doc_id") or metadata.get("doc_id") or chunk_id)
    source = str(
        metadata.get("file_name")
        or metadata.get("source")
        or metadata.get("doc_name")
        or "unknown"
    )
    result = {
        "kb_id": kb_id,
        "doc_id": doc_id,
        "chunk_id": chunk_id,
        "text": str(payload.get("text") or ""),
        "source": source,
        "metadata": metadata,
    }
    if "chunk_index" in metadata:
        result["chunk_index"] = metadata["chunk_index"]
    return result


async def main() -> int:
    """Create and populate the new collection without changing old collections."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default="agent_rag_v1")
    parser.add_argument("--source-prefix", default="astrbot_kb_")
    parser.add_argument("--dimension", type=int, default=1024)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 256:
        raise SystemExit("batch size must be between 1 and 256")

    client = AsyncQdrantClient(
        url=os.environ.get("QDRANT_HOST_URL", "http://127.0.0.1:6333"),
        api_key=os.environ["QDRANT_API_KEY"],
        timeout=120,
    )
    migrated = 0
    try:
        collections = await client.get_collections()
        sources = sorted(
            collection.name
            for collection in collections.collections
            if collection.name.startswith(args.source_prefix)
        )
        if not sources:
            raise RuntimeError("no source AstrBot Qdrant collections found")
        if args.dry_run:
            print(json.dumps({"target": args.target, "sources": sources}))
            return 0
        if not await client.collection_exists(args.target):
            await client.create_collection(
                collection_name=args.target,
                vectors_config={
                    "dense": models.VectorParams(
                        size=args.dimension,
                        distance=models.Distance.COSINE,
                    )
                },
                sparse_vectors_config={
                    "bm25": models.SparseVectorParams(
                        modifier=models.Modifier.IDF,
                    )
                },
            )
            for field in ("kb_id", "doc_id", "chunk_id", "source"):
                await client.create_payload_index(
                    collection_name=args.target,
                    field_name=field,
                    field_schema=models.PayloadSchemaType.KEYWORD,
                    wait=True,
                )

        for source in sources:
            kb_id = source.removeprefix(args.source_prefix)
            offset = None
            while True:
                records, offset = await client.scroll(
                    collection_name=source,
                    limit=args.batch_size,
                    offset=offset,
                    with_payload=True,
                    with_vectors=True,
                )
                points = []
                for record in records:
                    payload = canonical_payload(kb_id, record.payload or {})
                    dense = record.vector
                    if isinstance(dense, dict):
                        dense = dense.get("dense")
                    if not isinstance(dense, list) or len(dense) != args.dimension:
                        raise RuntimeError(f"invalid dense vector in {source}")
                    point_id = str(
                        uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"agent-rag-v1:{kb_id}:{record.id}",
                        )
                    )
                    points.append(
                        models.PointStruct(
                            id=point_id,
                            vector={
                                "dense": dense,
                                "bm25": models.Document(
                                    text=payload["text"],
                                    model="qdrant/bm25",
                                    options={
                                        "tokenizer": "multilingual",
                                        "language": "none",
                                    },
                                ),
                            },
                            payload=payload,
                        )
                    )
                if points:
                    await client.upsert(
                        collection_name=args.target,
                        points=points,
                        wait=True,
                    )
                    migrated += len(points)
                    print(
                        json.dumps(
                            {"source": source, "migrated_total": migrated},
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
                if offset is None:
                    break
    finally:
        await client.close()
    print(json.dumps({"status": "ok", "target": args.target, "points": migrated}))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
