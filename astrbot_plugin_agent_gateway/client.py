from __future__ import annotations

from typing import Any

import httpx


class GatewayClient:
    """Call the external Agent Gateway with a scoped event token."""

    def __init__(self, base_url: str, token: str, admin_token: str = "") -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=httpx.Timeout(95),
        )
        self._admin_token = admin_token

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

    async def control_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Apply one authenticated control action to a Gateway session.

        Args:
            payload: Session identity, permission context, and control action.

        Returns:
            Validated deterministic control response.

        Raises:
            RuntimeError: If the Gateway response is invalid.
            httpx.HTTPError: If the request fails.
        """
        response = await self._client.post("/v1/sessions/control", json=payload)
        response.raise_for_status()
        result = response.json()
        if result.get("status") not in {
            "new",
            "reset",
            "stop",
            "stats",
        } or not isinstance(result.get("message"), str):
            raise RuntimeError("invalid gateway session control response")
        return result

    async def get_admin_config(self) -> dict[str, Any]:
        """Read the active model and group whitelist from the Gateway."""
        response = await self._client.get(
            "/v1/admin/config",
            headers={"Authorization": f"Bearer {self._admin_token}"},
        )
        response.raise_for_status()
        config = response.json()
        if not isinstance(config.get("model"), str) or not isinstance(
            config.get("group_whitelist"), list
        ):
            raise RuntimeError("invalid gateway admin config")
        return config

    async def update_admin_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Atomically update the Gateway model and group whitelist."""
        response = await self._client.patch(
            "/v1/admin/config",
            headers={"Authorization": f"Bearer {self._admin_token}"},
            json=config,
        )
        response.raise_for_status()
        updated = response.json()
        if not isinstance(updated.get("model"), str) or not isinstance(
            updated.get("group_whitelist"), list
        ):
            raise RuntimeError("invalid gateway admin config")
        return updated

    async def close(self) -> None:
        """Close the shared HTTP connection pool."""
        await self._client.aclose()
