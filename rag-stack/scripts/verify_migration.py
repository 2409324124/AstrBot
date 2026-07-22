#!/usr/bin/env python3
"""Verify that Qdrant contains every AstrBot chunk ID exactly once."""

import argparse
import asyncio
import json
import os
from pathlib import Path

from migrate_kb import read_chunks
from qdrant_client import AsyncQdrantClient


async def main() -> int:
    """Compare SQLite chunk IDs and Qdrant payload IDs.

    Returns:
        Zero when every collection matches, otherwise one.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--knowledge-root",
        type=Path,
        default=Path(os.environ["ASTRBOT_KB_ROOT"]),
    )
    args = parser.parse_args()
    prefix = os.environ.get("ASTRBOT_QDRANT_COLLECTION_PREFIX", "astrbot_kb_")
    client = AsyncQdrantClient(
        url=os.environ.get("QDRANT_HOST_URL", "http://127.0.0.1:6333"),
        api_key=os.environ["QDRANT_API_KEY"],
        timeout=60,
    )
    failures = []
    summaries = []
    try:
        for kb_dir in sorted(args.knowledge_root.iterdir()):
            db_path = kb_dir / "doc.db"
            if not db_path.is_file():
                continue
            collection_name = f"{prefix}{kb_dir.name}"
            local_ids = {chunk_id for chunk_id, _, _ in read_chunks(db_path)}
            remote_ids = set()
            offset = None
            while True:
                records, offset = await client.scroll(
                    collection_name=collection_name,
                    limit=256,
                    offset=offset,
                    with_payload=["doc_id"],
                    with_vectors=False,
                )
                remote_ids.update(
                    str(record.payload.get("doc_id"))
                    for record in records
                    if record.payload and record.payload.get("doc_id")
                )
                if offset is None:
                    break
            missing = local_ids - remote_ids
            extra = remote_ids - local_ids
            summary = {
                "kb_id": kb_dir.name,
                "local": len(local_ids),
                "qdrant": len(remote_ids),
                "missing": len(missing),
                "extra": len(extra),
            }
            summaries.append(summary)
            if missing or extra:
                failures.append(summary)
    finally:
        await client.close()

    print(json.dumps({"knowledge_bases": summaries}, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
