from __future__ import annotations

import os
import time
from sys import maxsize
from typing import Any

from astrbot import logger
from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.message_components import At, Node, Nodes, Plain, Reply
from astrbot.api.platform import MessageType
from astrbot.builtin_stars.astrbot.group_chat_context import GroupChatContext

from .client import GatewayClient
from .command_parser import (
    is_gateway_command_prefix,
    is_retired_gateway_slash_command,
    parse_gateway_command,
)


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
            os.environ.get("AGENT_GATEWAY_ADMIN_TOKEN", "disabled"),
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

        message_type = event.get_message_type()
        if message_type == MessageType.FRIEND_MESSAGE and not normalized:
            event.should_call_llm(False)
            event.stop_event()
            return
        activated_handlers = event.get_extra("activated_handlers", [])
        builtin_commands = {
            handler.handler_name
            for handler in activated_handlers
            if handler.handler_module_path
            == "astrbot.builtin_stars.builtin_commands.main"
        }
        force_external_research = any(
            handler.handler_module_path == "astrbot.builtin_stars.astrbot.main"
            and handler.handler_name == "research"
            for handler in activated_handlers
        )
        control_actions = {
            "new_conv": "new",
            "reset": "reset",
            "stop": "stop",
            "stats": "stats",
        }
        if is_retired_gateway_slash_command(normalized):
            event.should_call_llm(False)
            event.stop_event()
            return

        gateway_command = parse_gateway_command(normalized)
        explicit_gateway_command = gateway_command is not None
        if is_gateway_command_prefix(normalized) and not gateway_command:
            await event.send(MessageChain().message("未知命令；使用 ~/help 查看可用命令"))
            event.should_call_llm(False)
            event.stop_event()
            return
        if gateway_command:
            command, argument = gateway_command
            if command == "help":
                await event.send(MessageChain().message(self._command_help_text()))
                event.should_call_llm(False)
                event.stop_event()
                return
            if command in {"new", "reset", "stop", "stats"}:
                if argument:
                    await event.send(
                        MessageChain().message(f"用法：~/{command}")
                    )
                else:
                    await self._send_session_control(event, command)
                event.should_call_llm(False)
                event.stop_event()
                return
            if not argument:
                await event.send(MessageChain().message("用法：~/research <问题>"))
                event.should_call_llm(False)
                event.stop_event()
                return
            normalized = argument
            force_external_research = True
        control_handler = next(
            (name for name in control_actions if name in builtin_commands),
            None,
        )
        if control_handler:
            await self._send_session_control(event, control_actions[control_handler])
            event.should_call_llm(False)
            event.stop_event()
            return
        if "help" in builtin_commands:
            await event.send(MessageChain().message(self._command_help_text()))
            event.should_call_llm(False)
            event.stop_event()
            return
        if builtin_commands & {"sid", "name"}:
            return
        if "provider" in builtin_commands:
            await event.send(
                MessageChain().message("模型切换请使用：-astrbot切换 模型 <ID>")
            )
            event.should_call_llm(False)
            event.stop_event()
            return
        if builtin_commands & {
            "update_dashboard",
            "set_variable",
            "unset_variable",
        }:
            await event.send(MessageChain().message("此命令已停用"))
            event.should_call_llm(False)
            event.stop_event()
            return
        if self._is_admin_command(normalized):
            if message_type != MessageType.FRIEND_MESSAGE or not event.is_admin():
                event.should_call_llm(False)
                event.stop_event()
                return
            try:
                response = await self._handle_admin_command(normalized)
            except Exception as exc:
                logger.warning(
                    "Agent gateway admin command failed: error_type=%s",
                    type(exc).__name__,
                )
                response = "切换失败，请检查命令和 Gateway 状态"
            await event.send(MessageChain().message(f"{response}（ai生成内容）"))
            event.should_call_llm(False)
            event.stop_event()
            return
        raw_slash_command = any(
            isinstance(component, Plain) and component.text.lstrip().startswith("/")
            for component in event.get_messages()
        )
        if raw_slash_command and not force_external_research:
            event.should_call_llm(False)
            event.stop_event()
            return
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
                if not explicit_gateway_command:
                    owner_takeover_active = (
                        await self.group_context.should_suppress_group_bot_reply(event)
                    )
                    if owner_takeover_active:
                        event.should_call_llm(False)
                        event.stop_event()
                        return
                    if (
                        not event.is_at_or_wake_command
                        and not await self.group_context.need_active_reply(event)
                    ):
                        event.should_call_llm(False)
                        event.stop_event()
                        return

        mentions = [
            str(component.qq)
            for component in event.get_messages()
            if isinstance(component, At)
        ]
        reply_component = next(
            (
                component
                for component in event.get_messages()
                if isinstance(component, Reply)
            ),
            None,
        )
        reply_sender = (
            str(reply_component.sender_id) if reply_component is not None else None
        )
        reply_text = (
            str(reply_component.message_str or "").strip()
            if reply_component is not None
            else ""
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
            "timestamp": int(float(timestamp) * 1000)
            if timestamp
            else int(time.time() * 1000),
            "is_admin": bool(event.is_admin()),
            "owner_takeover_active": owner_takeover_active,
        }
        if force_external_research:
            payload["force_route"] = "external_fact"
        if event.get_group_id():
            payload["group_id"] = str(event.get_group_id())
        if reply_sender:
            payload["reply_to_sender_id"] = reply_sender
        if reply_component is not None and reply_text:
            payload["reply_context"] = {
                "sender_id": reply_sender or "",
                "text": reply_text[:2000],
            }

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
                reply_text = "\n".join(texts)
                forward_threshold = 500
                try:
                    configured_threshold = self.context.get_config(
                        event.unified_msg_origin
                    )["platform_settings"]["forward_threshold"]
                    if int(configured_threshold) > 0:
                        forward_threshold = int(configured_threshold)
                except (AttributeError, KeyError, TypeError, ValueError):
                    pass
                use_forward = (
                    message_type == MessageType.GROUP_MESSAGE
                    and getattr(event, "get_platform_name", lambda: "")() == "aiocqhttp"
                    and len(reply_text) >= forward_threshold
                )
                if use_forward:
                    nodes = [
                        Node(
                            uin=event.get_self_id(),
                            name="东云bot",
                            content=[Plain(part)],
                        )
                        for part in self._split_forward_text(reply_text)
                    ]
                    try:
                        await event.send(MessageChain(chain=[Nodes(nodes)]))
                    except Exception as exc:
                        logger.warning(
                            "Agent gateway merged forward failed: error_type=%s",
                            type(exc).__name__,
                        )
                        await event.send(MessageChain().message(reply_text))
                else:
                    await event.send(MessageChain().message(reply_text))
        event.should_call_llm(False)
        event.stop_event()

    @staticmethod
    def _command_help_text() -> str:
        return (
            "命令：~/new ~/reset ~/stop ~/stats ~/research <问题>；"
            "/sid；管理员可用 /name 和 -astrbot切换"
        )

    async def _send_session_control(
        self, event: AstrMessageEvent, action: str
    ) -> None:
        payload: dict[str, Any] = {
            "schema_version": "1",
            "session_id": event.unified_msg_origin,
            "action": action,
            "chat_type": (
                "group" if event.get_message_type() == MessageType.GROUP_MESSAGE else "private"
            ),
            "is_admin": bool(event.is_admin()),
        }
        if event.get_group_id():
            payload["group_id"] = str(event.get_group_id())
        try:
            response = await self.client.control_session(payload)
            text = response["message"]
        except Exception as exc:
            logger.warning(
                "Agent gateway session control failed: action=%s error_type=%s",
                action,
                type(exc).__name__,
            )
            text = "会话操作失败，请稍后重试"
        await event.send(MessageChain().message(text))

    @staticmethod
    def _split_forward_text(text: str) -> list[str]:
        """Pack paragraphs into at most twelve merged-forward nodes.

        Fenced code blocks stay intact, while oversized ordinary paragraphs may be
        split. The returned parts always reproduce the original text exactly.

        Args:
            text: Complete reply text.

        Returns:
            Ordered node text parts without truncation.
        """
        blocks: list[tuple[str, bool]] = []
        current: list[str] = []
        in_fence = False
        fence_marker = ""
        block_has_fence = False
        for line in text.splitlines(keepends=True):
            stripped = line.lstrip()
            marker = stripped[:3]
            if marker in {"```", "~~~"}:
                if not in_fence:
                    in_fence = True
                    fence_marker = marker
                    block_has_fence = True
                elif marker == fence_marker:
                    in_fence = False
            current.append(line)
            if not in_fence and not line.strip():
                blocks.append(("".join(current), block_has_fence))
                current = []
                block_has_fence = False
        if current:
            blocks.append(("".join(current), block_has_fence))
        if not blocks:
            return [text]

        target = max(1000, (len(text) + 11) // 12)
        while True:
            chunks: list[str] = []
            pending = ""
            for block, has_fence in blocks:
                pieces = (
                    [
                        block[index : index + target]
                        for index in range(0, len(block), target)
                    ]
                    if len(block) > target and not has_fence
                    else [block]
                )
                for piece in pieces:
                    if pending and len(pending) + len(piece) > target:
                        chunks.append(pending)
                        pending = ""
                    pending += piece
            if pending:
                chunks.append(pending)
            if len(chunks) <= 12:
                return chunks
            target = min(len(text), max(target + 1, target * 5 // 4))

    @staticmethod
    def _is_admin_command(text: str) -> bool:
        """Recognize the scoped private admin command prefix."""
        normalized = text.lstrip("-/ ")
        return normalized.startswith(("astrbot切换", "bot切换"))

    async def _handle_admin_command(self, text: str) -> str:
        """Apply one model or group whitelist change through the Gateway API."""
        normalized = text.lstrip("-/ ")
        for prefix in ("astrbot切换", "bot切换"):
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix) :].strip(" -/")
                break
        config = await self.client.get_admin_config()
        parts = normalized.split()
        if not parts or parts[0] in {"状态", "查看"}:
            groups = "、".join(config["group_whitelist"]) or "无"
            return f"模型：{config['model']}\n群白名单：{groups}"
        if len(parts) == 2 and parts[0] in {"模型", "切换模型"}:
            model = parts[1]
            if len(model) > 128:
                raise ValueError("model name is too long")
            config["model"] = model
            await self.client.update_admin_config(config)
            return f"已切换模型：{model}"
        if parts and parts[0] in {"白名单", "切换白名单"}:
            if len(parts) == 2 and parts[1] in {"列表", "查看"}:
                groups = "、".join(config["group_whitelist"]) or "无"
                return f"群白名单：{groups}"
            if len(parts) == 3 and parts[1] in {"添加", "删除"} and parts[2].isdigit():
                action, group_id = parts[1], parts[2]
                groups = list(dict.fromkeys(config["group_whitelist"]))
                if action == "添加" and group_id not in groups:
                    groups.append(group_id)
                if action == "删除":
                    groups = [group for group in groups if group != group_id]
                config["group_whitelist"] = groups
                await self.client.update_admin_config(config)
                return f"已{action}群：{group_id}"
        return "用法：-astrbot切换 状态 | 模型 <ID> | 白名单 添加/删除 <群号>"

    async def terminate(self) -> None:
        """Release the Gateway HTTP pool when the plugin unloads."""
        await self.client.close()
