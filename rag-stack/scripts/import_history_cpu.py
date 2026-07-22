#!/usr/bin/env python3
"""Safely import the tracked historical CPU corpus into an isolated AstrBot KB."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

STACK_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = STACK_ROOT / "corpus" / "history-cpu"
DEFAULT_STATE = STACK_ROOT / "runtime" / "history-cpu-import.json"


def require_ok(response: httpx.Response) -> dict[str, Any]:
    """Return data from a successful AstrBot dashboard response."""
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") not in {"ok", None}:
        raise RuntimeError(str(payload.get("message", payload)))
    return payload


def validate_backup_dir(path: Path) -> dict[str, Any]:
    """Validate the completed pre-import backup required by an apply run."""
    manifest_path = path / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"backup manifest is missing: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"backup manifest is invalid: {manifest_path}") from exc
    if not manifest.get("created_at") or not manifest.get("files"):
        raise RuntimeError(f"backup manifest is incomplete: {manifest_path}")
    if not manifest.get("qdrant_snapshots"):
        raise RuntimeError(f"backup manifest has no Qdrant snapshots: {manifest_path}")
    return manifest


def build_local_state(corpus_dir: Path) -> dict[str, Any]:
    """Hash every declared Markdown document and the operational settings."""
    manifest = json.loads((corpus_dir / "manifest.json").read_text(encoding="utf-8"))
    documents: dict[str, str] = {}
    for entry in manifest["documents"]:
        path = corpus_dir / entry["path"]
        documents[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    fingerprint_input = {
        "knowledge_base_name": manifest["knowledge_base_name"],
        "embedding_provider_id": manifest["embedding_provider_id"],
        "chunk_size": manifest["chunk_size"],
        "chunk_overlap": manifest["chunk_overlap"],
        "documents": documents,
    }
    corpus_sha256 = hashlib.sha256(
        json.dumps(
            fingerprint_input,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode(),
    ).hexdigest()
    return {**fingerprint_input, "corpus_sha256": corpus_sha256}


def plan_import(
    existing_kbs: list[dict[str, Any]],
    remote_doc_names: list[str],
    state: dict[str, Any] | None,
    local: dict[str, Any],
) -> dict[str, Any]:
    """Plan an additive create/resume/no-op operation without deleting anything."""
    matching = [
        kb for kb in existing_kbs if kb.get("kb_name") == local["knowledge_base_name"]
    ]
    if len(matching) > 1:
        raise RuntimeError("multiple knowledge bases have the requested name")
    if not matching:
        if state:
            raise RuntimeError("import state exists but its knowledge base is missing")
        return {
            "create": True,
            "kb_id": None,
            "upload": sorted(local["documents"]),
        }

    kb_id = str(matching[0]["kb_id"])
    if len(remote_doc_names) != len(set(remote_doc_names)):
        raise RuntimeError(
            "the target knowledge base contains duplicate document names"
        )
    remote = set(remote_doc_names)
    declared = set(local["documents"])
    unexpected = sorted(remote - declared)
    if unexpected:
        raise RuntimeError(f"unmanaged documents found: {unexpected}")

    if remote:
        if not state:
            raise RuntimeError(
                "target contains documents but has no local import state"
            )
        if state.get("kb_id") != kb_id:
            raise RuntimeError("import state points at a different knowledge base")
        state_documents = state.get("documents")
        if not isinstance(state_documents, dict):
            raise RuntimeError("import state has no document hashes")
        state_matches_current = (
            state.get("corpus_sha256") == local["corpus_sha256"]
            and state_documents == local["documents"]
        )
        if not state_matches_current:
            if state.get("status") != "completed" or remote != set(state_documents):
                raise RuntimeError(
                    "target documents do not match the current corpus state"
                )
            changed = sorted(
                name
                for name, digest in state_documents.items()
                if local["documents"].get(name) != digest
            )
            if changed:
                raise RuntimeError(f"previously imported document changed: {changed}")
    elif state and state.get("kb_id") not in {None, kb_id}:
        raise RuntimeError("import state points at a different knowledge base")

    return {
        "create": False,
        "kb_id": kb_id,
        "upload": sorted(declared - remote),
    }


def write_state(path: Path, state: dict[str, Any]) -> None:
    """Atomically persist resumable import state without storing credentials."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def login(client: httpx.Client, base_url: str) -> None:
    """Authenticate with dashboard credentials from the untracked environment."""
    result = require_ok(
        client.post(
            f"{base_url}/auth/login",
            json={
                "username": os.environ["ASTRBOT_DASHBOARD_USERNAME"],
                "password": os.environ["ASTRBOT_DASHBOARD_PASSWORD"],
            },
        ),
    )
    token = result.get("data", {}).get("token")
    if not token:
        raise RuntimeError("AstrBot login did not return a token")
    client.headers["Authorization"] = f"Bearer {token}"


def list_knowledge_bases(client: httpx.Client, base_url: str) -> list[dict[str, Any]]:
    """List all knowledge bases required for name collision checks."""
    data = require_ok(
        client.get(
            f"{base_url}/knowledge-bases",
            params={"page": 1, "page_size": 1000},
        ),
    )["data"]
    return data["items"]


def list_document_names(
    client: httpx.Client,
    base_url: str,
    kb_id: str,
) -> list[str]:
    """List every remote document name in the isolated knowledge base."""
    data = require_ok(
        client.get(
            f"{base_url}/knowledge-bases/{kb_id}/documents",
            params={"page": 1, "page_size": 1000},
        ),
    )["data"]
    return [str(item["doc_name"]) for item in data["items"]]


def wait_for_task(
    client: httpx.Client,
    base_url: str,
    task_id: str,
    timeout: float,
) -> dict[str, Any]:
    """Wait for one background upload and fail on partial document errors."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = require_ok(
            client.get(f"{base_url}/knowledge-bases/tasks/{task_id}"),
        )["data"]
        status = data.get("status")
        if status == "completed":
            result = data.get("result") or {}
            if result.get("failed_count") or result.get("failed"):
                raise RuntimeError(f"document upload partially failed: {result}")
            return result
        if status == "failed":
            raise RuntimeError(f"document upload failed: {data.get('error')}")
        time.sleep(2)
    raise TimeoutError(f"document upload timed out after {timeout:.0f}s")


def build_upload_batches(
    names: list[str],
    batch_size: int = 10,
) -> list[list[str]]:
    """Split an ordered upload plan into AstrBot API-sized batches."""
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    return [
        names[offset : offset + batch_size]
        for offset in range(0, len(names), batch_size)
    ]


def upload_documents(
    client: httpx.Client,
    base_url: str,
    kb_id: str,
    corpus_dir: Path,
    names: list[str],
    local: dict[str, Any],
    timeout: float,
) -> dict[str, Any] | None:
    """Upload at most ten missing documents through AstrBot's normal parser."""
    if not names:
        return None
    if len(names) > 10:
        raise RuntimeError("this importer supports at most 10 documents per batch")
    files = [
        ("files[]", (name, (corpus_dir / name).read_bytes(), "text/markdown"))
        for name in names
    ]
    response = require_ok(
        client.post(
            f"{base_url}/knowledge-bases/{kb_id}/documents",
            data={
                "chunk_size": str(local["chunk_size"]),
                "chunk_overlap": str(local["chunk_overlap"]),
                "batch_size": os.environ.get("EMBEDDING_BATCH_SIZE", "32"),
                "tasks_limit": "3",
                "max_retries": "3",
            },
            files=files,
        ),
    )["data"]
    return wait_for_task(client, base_url, str(response["task_id"]), timeout)


def verify_retrieval(
    client: httpx.Client,
    base_url: str,
    kb_id: str,
    kb_name: str,
    cases_path: Path,
) -> list[dict[str, Any]]:
    """Run deterministic model/platform/generation retrieval smoke tests."""
    retrieval_config = json.loads(cases_path.read_text(encoding="utf-8"))
    top_k_by_layer = retrieval_config.get(
        "retrieval_top_k_by_layer",
        {"overview": 5, "example": 8, "detail": 15},
    )
    cases = retrieval_config["cases"]
    summaries = []
    for case in cases:
        retrieval_top_k = case.get(
            "retrieval_top_k",
            top_k_by_layer[case["layer"]],
        )
        data = require_ok(
            client.post(
                f"{base_url}/knowledge-bases/{kb_id}/retrieve",
                json={
                    "query": case["query"],
                    "kb_names": [kb_name],
                    "top_k": retrieval_top_k,
                },
            ),
        )["data"]
        results = data.get("results", [])
        expected_documents = set(case.get("expected_documents", []))
        matched_documents = sorted(
            {
                str(result.get("doc_name", ""))
                for result in results
                if result.get("doc_name") in expected_documents
            },
        )
        if expected_documents and not matched_documents:
            raise RuntimeError(
                f"retrieval case {case['id']} missed expected document: "
                f"{sorted(expected_documents)}",
            )
        expected_results = [
            result
            for result in results
            if not expected_documents or result.get("doc_name") in expected_documents
        ]
        searchable = json.dumps(expected_results, ensure_ascii=False)
        missing = [
            group
            for group in case["required_term_groups"]
            if not any(term in searchable for term in group)
        ]
        if missing:
            raise RuntimeError(
                f"retrieval case {case['id']} missed required groups: {missing}",
            )
        summaries.append(
            {
                "id": case["id"],
                "query": case["query"],
                "layer": case.get("layer"),
                "retrieval_top_k": retrieval_top_k,
                "result_count": len(results),
                "matched_documents": matched_documents,
            },
        )
    return summaries


def main() -> int:
    """Plan or apply an audited additive import into a separate knowledge base."""
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    parser.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=900)
    args = parser.parse_args()

    local = build_local_state(args.corpus_dir)
    state = None
    if args.state_file.is_file():
        state = json.loads(args.state_file.read_text(encoding="utf-8"))
    backup_manifest = None
    if args.apply:
        if args.backup_dir is None:
            raise RuntimeError("--apply requires --backup-dir")
        backup_manifest = validate_backup_dir(args.backup_dir)

    base_url = os.environ.get(
        "ASTRBOT_DASHBOARD_URL",
        "http://127.0.0.1:6185/api/v1",
    ).rstrip("/")
    with httpx.Client(timeout=120) as client:
        login(client, base_url)
        kbs = list_knowledge_bases(client, base_url)
        matching = [
            kb for kb in kbs if kb.get("kb_name") == local["knowledge_base_name"]
        ]
        remote_docs = []
        if len(matching) == 1:
            remote_docs = list_document_names(
                client,
                base_url,
                str(matching[0]["kb_id"]),
            )
        plan = plan_import(kbs, remote_docs, state, local)
        if not args.apply:
            print(json.dumps({"mode": "dry-run", "plan": plan}, ensure_ascii=False))
            return 0

        kb_id = plan["kb_id"]
        if plan["create"]:
            manifest = json.loads(
                (args.corpus_dir / "manifest.json").read_text(encoding="utf-8"),
            )
            created = require_ok(
                client.post(
                    f"{base_url}/knowledge-bases",
                    json={
                        "kb_name": local["knowledge_base_name"],
                        "description": "Intel/AMD 历史 CPU 型号、平台与兼容性资料；官方来源优先。",
                        "emoji": "🧮",
                        "embedding_provider_id": manifest["embedding_provider_id"],
                        "chunk_size": manifest["chunk_size"],
                        "chunk_overlap": manifest["chunk_overlap"],
                        "top_k_dense": 30,
                        "top_k_sparse": 30,
                        "top_m_final": 5,
                    },
                ),
            )["data"]
            kb_id = str(created["kb_id"])

        assert kb_id is not None
        in_progress_state = {
            **local,
            "kb_id": kb_id,
            "status": "uploading",
            "backup_created_at": backup_manifest["created_at"],
        }
        write_state(args.state_file, in_progress_state)
        upload_results = [
            upload_documents(
                client,
                base_url,
                kb_id,
                args.corpus_dir,
                batch,
                local,
                args.timeout,
            )
            for batch in build_upload_batches(plan["upload"])
        ]
        remote_after = list_document_names(client, base_url, kb_id)
        if set(remote_after) != set(local["documents"]):
            raise RuntimeError(
                f"post-import document mismatch: {sorted(remote_after)}",
            )
        stats = require_ok(
            client.get(f"{base_url}/knowledge-bases/{kb_id}/stats"),
        )["data"]
        if stats.get("doc_count") != len(local["documents"]):
            raise RuntimeError(f"post-import document count mismatch: {stats}")
        if int(stats.get("chunk_count", 0)) <= 0:
            raise RuntimeError(f"post-import knowledge base has no chunks: {stats}")
        retrieval = verify_retrieval(
            client,
            base_url,
            kb_id,
            local["knowledge_base_name"],
            args.corpus_dir / "retrieval_cases.json",
        )
        completed = {
            **in_progress_state,
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "stats": stats,
            "retrieval": retrieval,
        }
        write_state(args.state_file, completed)
        print(
            json.dumps(
                {
                    "status": "ok",
                    "kb_id": kb_id,
                    "uploaded": plan["upload"],
                    "upload_results": upload_results,
                    "stats": stats,
                    "retrieval": retrieval,
                },
                ensure_ascii=False,
            ),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
