from __future__ import annotations

import os
import time
from sys import maxsize
from typing import Any

from astrbot import logger
from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.message_components import At, Reply
from astrbot.api.platform import MessageType
from astrbot.builtin_stars.astrbot.group_chat_context import GroupChatContext

from .client import GatewayClient


class Main(star.Star):
    """Keep AstrBot as QQ transport while an external service owns the Agent."""

    def __init__(self, context: star.Context) -> None:
        self.context = context
        self.enabled = os.environ.get("AGENT_GATEWAY_ENABLED", "false").lower() in {
            "1",
            "true",
            "yes",
        }
        self.client = GatewayClient(
            os.environ.get("AGENT_GATEWAY_URL", "http://agent-gateway:8090"),
            os.environ.get("AGENT_GATEWAY_TOKEN", "disabled"),
        )
        try:
            self.group_context = GroupChatContext(
                self.context.astrbot_config_mgr,
                self.context,
            )
        except Exception:
            self.group_context = None

    @filter.event_message_type(filter.EventMessageType.ALL, priority=maxsize - 2)
    async def route_to_gateway(self, event: AstrMessageEvent) -> None:
        """Route eligible events and always stop the old LLM after cutover.

        Args:
            event: Incoming AstrBot platform event.
        """
        if not self.enabled:
            return
        normalized = event.message_str.strip()
        if normalized.lstrip("/").startswith(("astrbot切换", "bot切换")):
            return

        message_type = event.get_message_type()
        if message_type == MessageType.FRIEND_MESSAGE and not event.is_admin():
            event.should_call_llm(False)
            event.stop_event()
            return
        if message_type not in {MessageType.FRIEND_MESSAGE, MessageType.GROUP_MESSAGE}:
            return

        owner_takeover_active = False
        if message_type == MessageType.GROUP_MESSAGE and self.group_context:
            handoff = self.group_context.consume_human_handoff(event)
            if handoff:
                normalized = handoff
            else:
                owner_takeover_active = (
                    await self.group_context.should_suppress_group_bot_reply(event)
                )
                if owner_takeover_active:
                    event.should_call_llm(False)
                    event.stop_event()
                    return
                if not event.is_at_or_wake_command and not await self.group_context.need_active_reply(
                    event
                ):
                    event.should_call_llm(False)
                    event.stop_event()
                    return

        mentions = [
            str(component.qq)
            for component in event.get_messages()
            if isinstance(component, At)
        ]
        reply_sender = next(
            (
                str(component.sender_id)
                for component in event.get_messages()
                if isinstance(component, Reply)
            ),
            None,
        )
        message_obj = getattr(event, "message_obj", None)
        timestamp = getattr(message_obj, "timestamp", None)
        payload: dict[str, Any] = {
            "schema_version": "1",
            "message_id": str(
                getattr(message_obj, "message_id", None)
                or f"fallback-{event.unified_msg_origin}-{time.time_ns()}"
            ),
            "umo": event.unified_msg_origin,
            "chat_type": (
                "group" if message_type == MessageType.GROUP_MESSAGE else "private"
            ),
            "sender_id": str(event.get_sender_id()),
            "self_id": str(event.get_self_id()),
            "text": normalized,
            "mentions": mentions,
            "timestamp": int(float(timestamp) * 1000) if timestamp else int(time.time() * 1000),
            "is_admin": bool(event.is_admin()),
            "owner_takeover_active": owner_takeover_active,
        }
        if event.get_group_id():
            payload["group_id"] = str(event.get_group_id())
        if reply_sender:
            payload["reply_to_sender_id"] = reply_sender

        try:
            decision = await self.client.handle(payload)
        except Exception as exc:
            logger.warning(
                "Agent gateway failed: error_type=%s",
                type(exc).__name__,
            )
            event.should_call_llm(False)
            event.stop_event()
            return

        if decision["action"] == "reply":
            texts = [
                item.get("text", "")
                for item in decision["messages"]
                if item.get("type") == "text" and item.get("text")
            ]
            if texts:
                await event.send(MessageChain().message("\n".join(texts)))
        event.should_call_llm(False)
        event.stop_event()

    async def terminate(self) -> None:
        """Release the Gateway HTTP pool when the plugin unloads."""
        await self.client.close()
