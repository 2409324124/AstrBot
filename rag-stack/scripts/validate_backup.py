#!/usr/bin/env python3
"""Validate a backup manifest before any restore-side mutation."""

import argparse
import hashlib
import json
from pathlib import Path


def validate_backup(backup_dir: Path) -> int:
    """Verify exact file membership, size, and SHA-256 checksums.

    Args:
        backup_dir: Backup directory containing ``manifest.json``.

    Returns:
        Number of verified files.

    Raises:
        RuntimeError: The manifest is invalid or does not match disk state.
    """
    root = backup_dir.resolve(strict=True)
    manifest_path = root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries = manifest["files"]
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("backup manifest is invalid") from exc
    if not isinstance(entries, list):
        raise RuntimeError("backup manifest is invalid")

    expected = {}
    for entry in entries:
        try:
            relative = Path(entry["path"])
            size = int(entry["size"])
            digest = str(entry["sha256"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("backup manifest is invalid") from exc
        if relative.is_absolute() or ".." in relative.parts or relative == Path("."):
            raise RuntimeError("backup manifest is invalid")
        key = relative.as_posix()
        if key in expected or len(digest) != 64 or size < 0:
            raise RuntimeError("backup manifest is invalid")
        expected[key] = (size, digest)

    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path != manifest_path
    }
    if actual != set(expected):
        raise RuntimeError("backup manifest does not match files")

    for relative, (expected_size, expected_digest) in expected.items():
        path = root / relative
        if path.is_symlink() or path.stat().st_size != expected_size:
            raise RuntimeError("backup manifest does not match files")
        hasher = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                hasher.update(chunk)
        if hasher.hexdigest() != expected_digest:
            raise RuntimeError("backup manifest does not match files")
    return len(expected)


def main() -> int:
    """Run manifest validation and print only a redacted result.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("backup_directory", type=Path)
    args = parser.parse_args()
    try:
        count = validate_backup(args.backup_directory)
    except (OSError, RuntimeError):
        print(
            json.dumps(
                {
                    "status": "failed",
                    "reason_code": "manifest_mismatch",
                },
                separators=(",", ":"),
            )
        )
        return 1
    print(json.dumps({"status": "ok", "files": count}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
