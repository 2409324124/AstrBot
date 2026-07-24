import asyncio
import json
import re
import time
from collections import deque
from collections.abc import AsyncGenerator

from aiocqhttp import CQHttp, Event

from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import (
    At,
    BaseMessageComponent,
    File,
    Image,
    Node,
    Nodes,
    Plain,
    Record,
    Video,
)
from astrbot.api.platform import Group, MessageMember


class OutboundMessageTracker:
    """Remember recent AstrBot sends so self-message events do not loop back."""

    def __init__(self) -> None:
        self._message_ids: dict[str, float] = {}
        self._pending_fingerprints: deque[tuple[str, float]] = deque()
        self._group_sent_at: dict[str, float] = {}
        self._group_activity_cache: dict[str, tuple[float, dict]] = {}

    def remember_pending(self, message: list[dict]) -> None:
        self._prune()
        self._pending_fingerprints.append(
            (_message_fingerprint(message), time.monotonic() + 30)
        )

    def remember_sent_message_id(self, message_id: object) -> None:
        if message_id is None:
            return
        self._prune()
        self._message_ids[str(message_id)] = time.monotonic() + 30

    def remember_group_send(self, group_id: object, *, sent_at: float) -> None:
        if group_id is None:
            return
        group_key = str(group_id)
        self._group_sent_at[group_key] = float(sent_at)
        self._group_activity_cache.pop(group_key, None)

    def get_group_send_time(self, group_id: object) -> float | None:
        if group_id is None:
            return None
        return self._group_sent_at.get(str(group_id))

    def get_group_activity(self, group_id: object) -> dict | None:
        if group_id is None:
            return None
        group_key = str(group_id)
        cached = self._group_activity_cache.get(group_key)
        if not cached:
            return None
        expires_at, activity = cached
        if expires_at <= time.monotonic():
            self._group_activity_cache.pop(group_key, None)
            return None
        return activity

    def remember_group_activity(
        self,
        group_id: object,
        activity: dict,
        *,
        ttl_seconds: float = 5.0,
    ) -> None:
        if group_id is None:
            return
        self._group_activity_cache[str(group_id)] = (
            time.monotonic() + ttl_seconds,
            activity,
        )

    def discard_pending(self, message: list[dict]) -> None:
        """Forget one pending send after the corresponding action failed.

        Args:
            message: OneBot message segments from the failed send action.
        """
        self._prune()
        fingerprint = _message_fingerprint(message)
        for index, (pending, _) in enumerate(self._pending_fingerprints):
            if pending == fingerprint:
                del self._pending_fingerprints[index]
                break

    def consume_if_bot_message(self, event: dict) -> bool:
        self._prune()
        message_id = event.get("message_id")
        matched_message_id = bool(
            message_id is not None and self._message_ids.pop(str(message_id), None)
        )

        fingerprint = _message_fingerprint(event.get("message", []))
        matched_fingerprint = False
        for index, (pending, _) in enumerate(self._pending_fingerprints):
            if pending == fingerprint:
                del self._pending_fingerprints[index]
                matched_fingerprint = True
                break
        return matched_message_id or matched_fingerprint

    def _prune(self) -> None:
        now = time.monotonic()
        self._message_ids = {
            message_id: expires_at
            for message_id, expires_at in self._message_ids.items()
            if expires_at > now
        }
        while self._pending_fingerprints and self._pending_fingerprints[0][1] <= now:
            self._pending_fingerprints.popleft()


def _message_fingerprint(message: object) -> str:
    return json.dumps(
        message, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def get_outbound_message_tracker(bot: CQHttp) -> OutboundMessageTracker:
    tracker = getattr(bot, "_astrbot_outbound_message_tracker", None)
    if isinstance(tracker, OutboundMessageTracker):
        return tracker
    tracker = OutboundMessageTracker()
    setattr(bot, "_astrbot_outbound_message_tracker", tracker)
    return tracker


class AiocqhttpMessageEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str,
        message_obj,
        platform_meta,
        session_id,
        bot: CQHttp,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.bot = bot

    @staticmethod
    async def _from_segment_to_dict(segment: BaseMessageComponent) -> dict:
        """修复部分字段"""
        if isinstance(segment, Image | Record):
            # For Image and Record segments, we convert them to base64
            bs64 = await segment.convert_to_base64()
            return {
                "type": segment.type.lower(),
                "data": {
                    "file": f"base64://{bs64}",
                },
            }
        if isinstance(segment, File):
            # For File segments, we need to handle the file differently
            d = await segment.to_dict()
            file_val = d.get("data", {}).get("file", "")
            if file_val:
                import pathlib

                try:
                    # 使用 pathlib 处理路径，能更好地处理 Windows/Linux 差异
                    path_obj = pathlib.Path(file_val)
                    # 如果是绝对路径且不包含协议头 (://)，则转换为标准的 file: URI
                    if path_obj.is_absolute() and "://" not in file_val:
                        d["data"]["file"] = path_obj.as_uri()
                except Exception:
                    # 如果不是合法路径（例如已经是特定的特殊字符串），则跳过转换
                    pass
            return d
        if isinstance(segment, Video):
            d = await segment.to_dict()
            return d
        # For other segments, we simply convert them to a dict by calling toDict
        return segment.toDict()

    @staticmethod
    async def _parse_onebot_json(message_chain: MessageChain):
        """解析成 OneBot json 格式"""
        ret = []
        for segment in message_chain.chain:
            if isinstance(segment, At):
                # At 组件后插入一个空格，避免与后续文本粘连
                d = await AiocqhttpMessageEvent._from_segment_to_dict(segment)
                ret.append(d)
                ret.append({"type": "text", "data": {"text": " "}})
            elif isinstance(segment, Plain):
                if not segment.text.strip():
                    continue
                d = await AiocqhttpMessageEvent._from_segment_to_dict(segment)
                ret.append(d)
            else:
                d = await AiocqhttpMessageEvent._from_segment_to_dict(segment)
                ret.append(d)
        return ret

    @classmethod
    async def _dispatch_send(
        cls,
        bot: CQHttp,
        event: Event | None,
        is_group: bool,
        session_id: str | None,
        messages: list[dict],
    ) -> None:
        # session_id 必须是纯数字字符串
        session_id_int = (
            int(session_id) if session_id and session_id.isdigit() else None
        )
        routing_params = {}
        if isinstance(event, Event) and event.get("self_id"):
            routing_params["self_id"] = event["self_id"]

        tracker = get_outbound_message_tracker(bot)
        tracker.remember_pending(messages)
        try:
            if is_group and isinstance(session_id_int, int):
                result = await bot.send_group_msg(
                    group_id=session_id_int,
                    message=messages,
                    **routing_params,
                )
            elif not is_group and isinstance(session_id_int, int):
                result = await bot.send_private_msg(
                    user_id=session_id_int,
                    message=messages,
                    **routing_params,
                )
            elif isinstance(event, Event):  # 最后兜底
                result = await bot.send(event=event, message=messages)
            else:
                raise ValueError(
                    f"无法发送消息：缺少有效的数字 session_id({session_id}) 或 event({event})",
                )
        except Exception:
            tracker.discard_pending(messages)
            raise
        if isinstance(result, dict):
            tracker.remember_sent_message_id(result.get("message_id"))
        if is_group and session_id is not None:
            tracker.remember_group_send(session_id, sent_at=time.time())

    @classmethod
    async def send_message(
        cls,
        bot: CQHttp,
        message_chain: MessageChain,
        event: Event | None = None,
        is_group: bool = False,
        session_id: str | None = None,
    ) -> None:
        """发送消息至 QQ 协议端（aiocqhttp）。

        Args:
            bot (CQHttp): aiocqhttp 机器人实例
            message_chain (MessageChain): 要发送的消息链
            event (Event | None, optional): aiocqhttp 事件对象.
            is_group (bool, optional): 是否为群消息.
            session_id (str | None, optional): 会话 ID（群号或 QQ 号

        """
        # 转发消息、文件消息不能和普通消息混在一起发送
        send_one_by_one = any(
            isinstance(seg, Node | Nodes | File) for seg in message_chain.chain
        )
        if not send_one_by_one:
            ret = await cls._parse_onebot_json(message_chain)
            if not ret:
                return
            await cls._dispatch_send(bot, event, is_group, session_id, ret)
            return
        for seg in message_chain.chain:
            if isinstance(seg, Node | Nodes):
                # 合并转发消息
                if isinstance(seg, Node):
                    nodes = Nodes([seg])
                    seg = nodes

                payload = await seg.to_dict()

                if is_group:
                    payload["group_id"] = session_id
                    if isinstance(event, Event) and event.get("self_id"):
                        payload["self_id"] = event["self_id"]
                    await bot.call_action("send_group_forward_msg", **payload)
                else:
                    payload["user_id"] = session_id
                    if isinstance(event, Event) and event.get("self_id"):
                        payload["self_id"] = event["self_id"]
                    await bot.call_action("send_private_forward_msg", **payload)
            elif isinstance(seg, File):
                d = await cls._from_segment_to_dict(seg)
                await cls._dispatch_send(bot, event, is_group, session_id, [d])
            else:
                messages = await cls._parse_onebot_json(MessageChain([seg]))
                if not messages:
                    continue
                await cls._dispatch_send(bot, event, is_group, session_id, messages)
                await asyncio.sleep(0.5)

    async def send(self, message: MessageChain) -> None:
        """发送消息"""
        event = getattr(self.message_obj, "raw_message", None)

        is_group = bool(self.get_group_id())
        session_id = self.get_group_id() if is_group else self.get_sender_id()

        await self.send_message(
            bot=self.bot,
            message_chain=message,
            event=event,  # 不强制要求一定是 Event
            is_group=is_group,
            session_id=session_id,
        )
        await super().send(message)

    async def get_group_account_activity(self) -> dict[str, float | None] | None:
        """Return current-account activity metadata for this group."""
        group_id = self.get_group_id()
        self_id = self.get_self_id()
        if not group_id or not self_id:
            return None
        tracker = get_outbound_message_tracker(self.bot)
        if cached := tracker.get_group_activity(group_id):
            return cached
        params = {
            "group_id": int(group_id) if str(group_id).isdigit() else group_id,
            "user_id": int(self_id) if str(self_id).isdigit() else self_id,
            "no_cache": True,
        }
        member = await self.bot.call_action("get_group_member_info", **params)
        if not isinstance(member, dict):
            return None
        try:
            account_last_sent_at = float(member["last_sent_time"])
        except (KeyError, TypeError, ValueError):
            return None
        activity = {
            "account_last_sent_at": account_last_sent_at,
            "bot_last_sent_at": tracker.get_group_send_time(group_id),
            "observed_at": time.time(),
        }
        tracker.remember_group_activity(group_id, activity)
        return activity

    async def send_streaming(
        self,
        generator: AsyncGenerator,
        use_fallback: bool = False,
    ):
        if not use_fallback:
            buffer = None
            async for chain in generator:
                if not buffer:
                    buffer = chain
                else:
                    buffer.chain.extend(chain.chain)
            if not buffer:
                return None
            buffer.squash_plain()
            await self.send(buffer)
            return await super().send_streaming(generator, use_fallback)

        buffer = ""
        pattern = re.compile(r"[^。？！~…]+[。？！~…]+")

        async for chain in generator:
            if isinstance(chain, MessageChain):
                for comp in chain.chain:
                    if isinstance(comp, Plain):
                        buffer += comp.text
                        if any(p in buffer for p in "。？！~…"):
                            buffer = await self.process_buffer(buffer, pattern)
                    else:
                        await self.send(MessageChain(chain=[comp]))
                        await asyncio.sleep(1.5)  # 限速

        buffer = buffer.strip()
        if buffer:
            await self.send(MessageChain([Plain(buffer)]))
        return await super().send_streaming(generator, use_fallback)

    async def get_group(self, group_id=None, **kwargs):
        if isinstance(group_id, str) and group_id.isdigit():
            group_id = int(group_id)
        elif self.get_group_id():
            group_id = int(self.get_group_id())
        else:
            return None

        routing_params = {}
        if getattr(self.message_obj, "self_id", None):
            routing_params["self_id"] = self.message_obj.self_id

        info: dict = await self.bot.call_action(
            "get_group_info",
            group_id=group_id,
            **routing_params,
        )

        members: list[dict] = await self.bot.call_action(
            "get_group_member_list",
            group_id=group_id,
            **routing_params,
        )

        owner_id = None
        admin_ids = []
        for member in members:
            if member["role"] == "owner":
                owner_id = member["user_id"]
            if member["role"] == "admin":
                admin_ids.append(member["user_id"])

        group = Group(
            group_id=str(group_id),
            group_name=info.get("group_name"),
            group_avatar="",
            group_admins=admin_ids,
            group_owner=str(owner_id),
            members=[
                MessageMember(
                    user_id=member["user_id"],
                    nickname=member.get("nickname") or member.get("card"),
                )
                for member in members
            ],
        )

        return group
