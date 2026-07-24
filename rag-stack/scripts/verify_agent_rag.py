#!/usr/bin/env python3
"""Run the tracked retrieval cases against the independent hybrid collection."""

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

import httpx


def evaluate_case(
    case: dict[str, Any],
    hits: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate retrieved metadata and evidence without returning document text.

    Args:
        case: One tracked retrieval acceptance case.
        hits: Qdrant hits with source and text payload fields.

    Returns:
        Document match and missing required-term group indexes.
    """
    sources = {
        str(hit.get("source", "")).casefold()
        for hit in hits
        if hit.get("source")
    }
    expected = [str(item).casefold() for item in case["expected_documents"]]
    document_match = any(
        source == document or source.endswith(f"/{document}")
        for source in sources
        for document in expected
    )
    evidence = "\n".join(str(hit.get("text", "")) for hit in hits).casefold()
    missing = [
        index
        for index, alternatives in enumerate(case["required_term_groups"])
        if not any(str(term).casefold() in evidence for term in alternatives)
    ]
    return {
        "document_match": document_match,
        "missing_term_groups": missing,
    }


async def embed(client: httpx.AsyncClient, query: str, model: str) -> list[float]:
    """Embed one query through the OpenAI-compatible local service."""
    response = await client.post("embeddings", json={"model": model, "input": [query]})
    response.raise_for_status()
    body = response.json()
    vector = body["data"][0]["embedding"]
    if not isinstance(vector, list) or len(vector) != 1024:
        raise RuntimeError("embedding response is not a 1024-dimensional vector")
    return vector


async def query_qdrant(
    client: httpx.AsyncClient,
    collection: str,
    query: str,
    vector: list[float],
    top_k: int,
) -> list[dict[str, Any]]:
    """Run the same dense/BM25/RRF query contract as the Gateway."""
    candidate_limit = top_k * 3
    response = await client.post(
        f"collections/{collection}/points/query",
        json={
            "prefetch": [
                {"query": vector, "using": "dense", "limit": candidate_limit},
                {
                    "query": {
                        "text": query,
                        "model": "qdrant/bm25",
                        "options": {
                            "tokenizer": "multilingual",
                            "language": "none",
                        },
                    },
                    "using": "bm25",
                    "limit": candidate_limit,
                },
            ],
            "query": {"fusion": "rrf"},
            "limit": top_k,
            "with_payload": True,
        },
    )
    response.raise_for_status()
    points = response.json()["result"]["points"]
    return [
        {
            "source": (point.get("payload") or {}).get("source", "unknown"),
            "text": (point.get("payload") or {}).get("text", ""),
        }
        for point in points
    ]


async def main() -> int:
    """Execute every case and print only an auditable result summary."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path(
            os.environ.get(
                "AGENT_RAG_CASES",
                "/AstrBot/rag-stack/corpus/history-cpu/retrieval_cases.json",
            )
        ),
    )
    parser.add_argument("--collection", default="agent_rag_v1")
    parser.add_argument("--top-k", type=int, default=8)
    args = parser.parse_args()
    if not 1 <= args.top_k <= 32:
        raise SystemExit("top-k must be between 1 and 32")

    cases = json.loads(args.cases.read_text(encoding="utf-8"))["cases"]
    embedding_url = os.environ.get(
        "EMBEDDING_BASE_URL", "http://embedding-server:8000/v1"
    ).rstrip("/") + "/"
    qdrant_url = os.environ.get(
        "QDRANT_HOST_URL", "http://qdrant:6333"
    ).rstrip("/") + "/"
    async with (
        httpx.AsyncClient(
            base_url=embedding_url,
            headers={"Authorization": f"Bearer {os.environ['EMBEDDING_API_KEY']}"},
            timeout=120,
        ) as embedding_client,
        httpx.AsyncClient(
            base_url=qdrant_url,
            headers={"api-key": os.environ["QDRANT_API_KEY"]},
            timeout=120,
        ) as qdrant_client,
    ):
        results = []
        for case in cases:
            vector = await embed(
                embedding_client,
                case["query"],
                os.environ.get("EMBEDDING_MODEL", "BAAI/bge-m3"),
            )
            hits = await query_qdrant(
                qdrant_client,
                args.collection,
                case["query"],
                vector,
                args.top_k,
            )
            evaluation = evaluate_case(case, hits)
            passed = evaluation["document_match"] and not evaluation[
                "missing_term_groups"
            ]
            results.append(
                {
                    "id": case["id"],
                    "passed": passed,
                    **evaluation,
                    "sources": sorted(
                        {
                            str(hit["source"])
                            for hit in hits
                            if hit.get("source")
                        }
                    ),
                }
            )
    failures = [result for result in results if not result["passed"]]
    print(
        json.dumps(
            {
                "collection": args.collection,
                "total": len(results),
                "passed": len(results) - len(failures),
                "failed": len(failures),
                "failures": failures,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
