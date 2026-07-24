from __future__ import annotations

from typing import Any

import httpx


class GatewayClient:
    """Call the external Agent Gateway with a scoped event token."""

    def __init__(self, base_url: str, token: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=httpx.Timeout(95),
        )

    async def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Submit one normalized QQ event.

        Args:
            payload: Versioned event payload without platform credentials.

        Returns:
            Validated Gateway decision.

        Raises:
            RuntimeError: If the Gateway response is invalid.
            httpx.HTTPError: If the request fails.
        """
        response = await self._client.post("/v1/events", json=payload)
        response.raise_for_status()
        decision = response.json()
        if decision.get("action") not in {"reply", "no_reply"} or not isinstance(
            decision.get("messages"), list
        ):
            raise RuntimeError("invalid gateway decision")
        return decision

    async def close(self) -> None:
        """Close the shared HTTP connection pool."""
        await self._client.aclose()
