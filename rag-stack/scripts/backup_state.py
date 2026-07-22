#!/usr/bin/env python3
"""Create consistent SQLite copies and portable Qdrant snapshots."""

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def sqlite_backup(source: Path, destination: Path) -> None:
    """Use SQLite's online backup API for a consistent copy.

    Args:
        source: Live SQLite database.
        destination: Backup database path.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
    finally:
        destination_connection.close()
        source_connection.close()


async def main() -> int:
    """Back up AstrBot knowledge files and Qdrant collections.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-qdrant", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    data_root = Path(os.environ["RAG_DATA_ROOT"])
    output = args.output or data_root / "snapshots" / f"astrbot-rag-{timestamp}"
    output.mkdir(parents=True, mode=0o700)
    knowledge_root = Path(os.environ["ASTRBOT_KB_ROOT"])
    knowledge_backup = output / "knowledge_base"

    for source in knowledge_root.rglob("*"):
        if not source.is_file():
            continue
        relative = source.relative_to(knowledge_root)
        destination = knowledge_backup / relative
        if source.suffix == ".db":
            sqlite_backup(source, destination)
        elif source.name == "index.faiss":
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

    astrbot_data = knowledge_root.parent
    for name in ("cmd_config.json", "data_v4.db"):
        source = astrbot_data / name
        if source.is_file():
            destination = output / "astrbot_data" / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.suffix == ".db":
                sqlite_backup(source, destination)
            else:
                shutil.copy2(source, destination)

    compose_value = os.environ.get("ASTRBOT_COMPOSE_FILE")
    if compose_value:
        compose_file = Path(compose_value)
        if compose_file.is_file():
            shutil.copy2(compose_file, output / "compose.yml")

    snapshots = []
    if not args.skip_qdrant:
        import httpx
        from qdrant_client import AsyncQdrantClient

        qdrant_url = os.environ.get("QDRANT_HOST_URL", "http://127.0.0.1:6333")
        api_key = os.environ["QDRANT_API_KEY"]
        client = AsyncQdrantClient(url=qdrant_url, api_key=api_key, timeout=120)
        async with httpx.AsyncClient(timeout=300) as http:
            try:
                collections = (await client.get_collections()).collections
                for collection in collections:
                    snapshot = await client.create_snapshot(
                        collection_name=collection.name,
                        wait=True,
                    )
                    destination = output / "qdrant" / collection.name / snapshot.name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    response = await http.get(
                        f"{qdrant_url}/collections/{collection.name}/snapshots/{snapshot.name}",
                        headers={"api-key": api_key},
                    )
                    response.raise_for_status()
                    destination.write_bytes(response.content)
                    snapshots.append(
                        {
                            "collection": collection.name,
                            "file": str(destination.relative_to(output)),
                        },
                    )
            finally:
                await client.close()

    files = []
    for path in sorted(output.rglob("*")):
        if path.is_file():
            files.append(
                {
                    "path": str(path.relative_to(output)),
                    "size": path.stat().st_size,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                },
            )
    manifest = {
        "created_at": timestamp,
        "qdrant_snapshots": snapshots,
        "files": files,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
