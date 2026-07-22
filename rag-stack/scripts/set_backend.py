#!/usr/bin/env python3
"""Atomically update the untracked RAG environment backend switch."""

import argparse
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    """Update ASTRBOT_VECTOR_DB while preserving a timestamped backup.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("env_file", type=Path)
    parser.add_argument("backend", choices=("faiss", "qdrant"))
    args = parser.parse_args()
    content = args.env_file.read_text(encoding="utf-8").splitlines()
    updated = []
    replaced = False
    for line in content:
        if line.startswith("ASTRBOT_VECTOR_DB="):
            updated.append(f"ASTRBOT_VECTOR_DB={args.backend}")
            replaced = True
        else:
            updated.append(line)
    if not replaced:
        updated.append(f"ASTRBOT_VECTOR_DB={args.backend}")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = args.env_file.with_name(f"{args.env_file.name}.bak.{timestamp}")
    shutil.copy2(args.env_file, backup)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=args.env_file.parent,
        delete=False,
    ) as handle:
        handle.write("\n".join(updated) + "\n")
        temporary = Path(handle.name)
    os.chmod(temporary, args.env_file.stat().st_mode)
    temporary.replace(args.env_file)
    print(f"ASTRBOT_VECTOR_DB={args.backend}; backup={backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
