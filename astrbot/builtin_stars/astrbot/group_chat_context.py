import asyncio
import datetime
import hashlib
import random
import re
import time
import uuid
from collections import defaultdict, deque

from astrbot import logger
from astrbot.api import star
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import (
    At,
    AtAll,
    Face,
    File,
    Forward,
    Image,
    Plain,
    Record,
    Reply,
    Video,
)
from astrbot.api.platform import MessageType
from astrbot.api.provider import Provider, ProviderRequest
from astrbot.core.agent.message import TextPart
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager

"""
Group chat context awareness.
"""

GROUP_HISTORY_HEADER = (
    "<system_reminder>"
    "You are in a group chat. "
    "Belows are group chat context after your last reply:\n"
    "--- BEGIN CONTEXT---\n"
)
GROUP_HISTORY_FOOTER = "\n--- END CONTEXT ---\n</system_reminder>"
DEFAULT_GROUP_MESSAGE_MAX_CNT = 300


class GroupChatContext:
    def __init__(self, acm: AstrBotConfigManager, context: star.Context) -> None:
        self.acm = acm
        self.context = context
        self._locks: dict[str, asyncio.Lock] = {}
        self.raw_records: dict[str, deque[str]] = defaultdict(deque)
        self._record_ids: dict[str, deque[str]] = defaultdict(deque)
        self._last_active_reply_at: dict[str, float] = {}
        self._human_takeover_until: dict[str, float] = {}
        self._member_mute_until: dict[str, float] = {}

    def _get_lock(self, umo: str) -> asyncio.Lock:
        lock = self._locks.get(umo)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[umo] = lock
        return lock

    def cfg(self, event: AstrMessageEvent):
        cfg = self.context.get_config(umo=event.unified_msg_origin)
        group_context_cfg = cfg["provider_ltm_settings"]
        image_caption_prompt = cfg["provider_settings"]["image_caption_prompt"]
        image_caption_provider_id = group_context_cfg.get("image_caption_provider_id")
        image_caption = group_context_cfg["image_caption"] and bool(
            image_caption_provider_id
        )
        active_reply = group_context_cfg["active_reply"]
        enable_active_reply = active_reply.get("enable", False)
        ar_method = active_reply["method"]
        ar_possibility = active_reply["possibility_reply"]
        ar_prompt = active_reply.get("prompt", "")
        ar_whitelist = active_reply.get("whitelist", [])
        return {
            "group_message_max_cnt": _positive_int(
                group_context_cfg.get(
                    "group_message_max_cnt",
                    DEFAULT_GROUP_MESSAGE_MAX_CNT,
                ),
                DEFAULT_GROUP_MESSAGE_MAX_CNT,
            ),
            "image_caption": image_caption,
            "image_caption_prompt": image_caption_prompt,
            "image_caption_provider_id": image_caption_provider_id,
            "enable_active_reply": enable_active_reply,
            "ar_method": ar_method,
            "ar_possibility": ar_possibility,
            "ar_prompt": ar_prompt,
            "ar_whitelist": ar_whitelist,
            "ar_relevance_threshold": active_reply.get(
                "relevance_threshold",
                0.55,
            ),
            "ar_context_messages": _positive_int(
                active_reply.get("context_messages", 12),
                12,
            ),
            "ar_trigger_keywords": active_reply.get("trigger_keywords", []),
            "ar_cooldown_seconds": _non_negative_float(
                active_reply.get("cooldown_seconds", 120),
                120,
            ),
            "ar_human_takeover_seconds": _non_negative_float(
                active_reply.get("human_takeover_seconds", 900),
                900,
            ),
            "ar_member_mute_seconds": _non_negative_float(
                active_reply.get("member_mute_seconds", 1800),
                1800,
            ),
        }

    async def get_image_caption(
        self,
        image_url: str,
        image_caption_provider_id: str,
        image_caption_prompt: str,
    ) -> str:
        if not image_caption_provider_id:
            provider = self.context.get_using_provider()
        else:
            provider = self.context.get_provider_by_id(image_caption_provider_id)
            if not provider:
                raise Exception(f"没有找到 ID 为 {image_caption_provider_id} 的提供商")
        if not isinstance(provider, Provider):
            raise Exception(f"提供商类型错误({type(provider)})，无法获取图片描述")
        response = await provider.text_chat(
            prompt=image_caption_prompt,
            session_id=uuid.uuid4().hex,
            image_urls=[image_url],
            persist=False,
        )
        return response.completion_text

    async def need_active_reply(self, event: AstrMessageEvent) -> bool:
        cfg = self.cfg(event)
        now = time.monotonic()
        if _is_human_self_message(event):
            self._human_takeover_until[event.unified_msg_origin] = (
                now + cfg["ar_human_takeover_seconds"]
            )
            logger.info(
                "human_takeover | event=started "
                f"| scope_ref={_scope_ref(event.unified_msg_origin)} "
                f"| seconds={cfg['ar_human_takeover_seconds']}"
            )
            return False
        if not cfg["enable_active_reply"]:
            return False
        if event.get_message_type() != MessageType.GROUP_MESSAGE:
            return False
        if event.is_at_or_wake_command:
            return False
        if _mentions_another_person(event):
            return False
        if now < self._human_takeover_until.get(event.unified_msg_origin, 0.0):
            return False
        if now < self._member_mute_until.get(event.unified_msg_origin, 0.0):
            return False
        if cfg["ar_whitelist"] and (
            event.unified_msg_origin not in cfg["ar_whitelist"]
            and (
                event.get_group_id() and event.get_group_id() not in cfg["ar_whitelist"]
            )
        ):
            return False
        match cfg["ar_method"]:
            case "possibility_reply":
                return random.random() < cfg["ar_possibility"]
            case "relevance_reply":
                last_reply_at = self._last_active_reply_at.get(
                    event.unified_msg_origin,
                    0.0,
                )
                if now - last_reply_at < cfg["ar_cooldown_seconds"]:
                    return False
                should_reply = self._is_relevant_message(event, cfg)
                if should_reply:
                    self._last_active_reply_at[event.unified_msg_origin] = now
                return should_reply
        return False

    def should_suppress_group_bot_reply(self, event: AstrMessageEvent) -> bool:
        """Suppress replies during human takeover or a member-requested hush.

        Both timers are deliberately in-memory and scoped to one UMO. Explicit
        parsed commands remain available during a takeover. Group admins bypass
        a member-requested hush, but not an active shared-account takeover.

        Args:
            event: Incoming AstrBot message event.

        Returns:
            Whether all normal bot reply paths should stop for this event.
        """
        if event.get_message_type() != MessageType.GROUP_MESSAGE:
            return False
        if _is_human_self_message(event):
            return False

        cfg = self.cfg(event)
        now = time.monotonic()
        umo = event.unified_msg_origin
        if event.get_extra("handlers_parsed_params", {}):
            return False
        if now < self._human_takeover_until.get(umo, 0.0):
            logger.info(
                f"human_takeover | event=reply_suppressed | scope_ref={_scope_ref(umo)}"
            )
            return True
        if _is_group_admin(event):
            return False
        if _MEMBER_HUSH_RE.search(event.message_str):
            mute_seconds = cfg["ar_member_mute_seconds"]
            if mute_seconds > 0:
                self._member_mute_until[umo] = now + mute_seconds

        return now < self._member_mute_until.get(umo, 0.0)

    def _is_relevant_message(self, event: AstrMessageEvent, cfg: dict) -> bool:
        text = event.message_str.strip()
        if not text:
            return False

        keywords = {
            str(keyword).strip().lower()
            for keyword in cfg["ar_trigger_keywords"]
            if str(keyword).strip()
        }
        if any(keyword in text.lower() for keyword in keywords):
            return True

        score = 0.0
        if len(text) >= 4:
            score += 0.1
        if text.endswith(("?", "？")):
            score += 0.35

        records = list(self.raw_records.get(event.unified_msg_origin, deque()))
        recent_records = records[-cfg["ar_context_messages"] :]
        common_terms = _topic_terms(text).intersection(
            _topic_terms("\n".join(recent_records))
        )
        if len(common_terms) >= 2:
            score += 0.35
        elif len(common_terms) == 1:
            score += 0.2

        return score >= float(cfg["ar_relevance_threshold"])

    def consume_human_handoff(self, event: AstrMessageEvent) -> str | None:
        """Release takeover when the owner quotes a message and hands it off.

        Args:
            event: Incoming AstrBot message event.

        Returns:
            An LLM instruction for a valid handoff, otherwise ``None``.
        """
        if not _is_human_self_message(event):
            return None
        if not any(isinstance(component, Reply) for component in event.get_messages()):
            return None
        if not _HUMAN_HANDOFF_RE.fullmatch(event.message_str):
            return None

        self._human_takeover_until.pop(event.unified_msg_origin, None)
        logger.info(
            "human_takeover | event=handoff_accepted "
            f"| scope_ref={_scope_ref(event.unified_msg_origin)}"
        )
        return "请接管并回答被引用的消息；需要外部事实时先检索。"

    async def remove_session(self, event: AstrMessageEvent) -> int:
        umo = event.unified_msg_origin
        lock = self._get_lock(umo)
        async with lock:
            cnt = len(self.raw_records.get(umo, deque()))
            self.raw_records.pop(umo, None)
            self._record_ids.pop(umo, None)
        self._locks.pop(umo, None)
        self._last_active_reply_at.pop(umo, None)
        self._human_takeover_until.pop(umo, None)
        self._member_mute_until.pop(umo, None)
        return cnt

    async def handle_message(self, event: AstrMessageEvent) -> None:
        if event.get_message_type() != MessageType.GROUP_MESSAGE:
            return

        umo = event.unified_msg_origin
        cfg = self.cfg(event)
        final_message = await self._format_message(event, cfg)

        async with self._get_lock(umo):
            records = self.raw_records[umo]
            record_ids = self._record_ids[umo]
            record_id = uuid.uuid4().hex
            records.append(final_message)
            record_ids.append(record_id)
            _trim_left(records, cfg["group_message_max_cnt"], record_ids)
            event.set_extra("_group_context_record_id", record_id)
            event.set_extra("_group_context_raw_idx", len(records) - 1)

        logger.debug(
            "group_chat_context | event=recorded "
            f"| scope_ref={_scope_ref(umo)} | chars={len(final_message)}"
        )

    async def on_req_llm(self, event: AstrMessageEvent, req: ProviderRequest) -> None:
        umo = event.unified_msg_origin
        record_id = event.get_extra("_group_context_record_id", None)
        prompt_idx = event.get_extra("_group_context_raw_idx", -1)
        if not isinstance(record_id, str) and (
            not isinstance(prompt_idx, int) or prompt_idx < 0
        ):
            return

        async with self._get_lock(umo):
            records = self.raw_records.get(umo)
            if not records:
                return

            raw_list = list(records)
            id_list = list(self._record_ids.get(umo, deque()))
            if isinstance(record_id, str) and record_id in id_list:
                prompt_idx = id_list.index(record_id)

            if prompt_idx >= len(raw_list):
                return

            records_to_inject = raw_list[:prompt_idx]
            remaining = raw_list[prompt_idx + 1 :]
            remaining_ids = id_list[prompt_idx + 1 :] if id_list else []
            records.clear()
            records.extend(remaining)
            if id_list:
                record_ids = self._record_ids[umo]
                record_ids.clear()
                record_ids.extend(remaining_ids)

        if records_to_inject:
            req.extra_user_content_parts.append(
                TextPart(text=_format_group_history_block(records_to_inject))
            )

    async def _format_message(self, event: AstrMessageEvent, cfg: dict) -> str:
        datetime_str = datetime.datetime.now().strftime("%H:%M:%S")
        parts = [f"[{event.message_obj.sender.nickname}/{datetime_str}]: "]

        for comp in event.get_messages():
            if isinstance(comp, Plain):
                parts.append(f" {comp.text}")
            elif isinstance(comp, Image):
                if cfg["image_caption"]:
                    try:
                        url = comp.url if comp.url else comp.file
                        if not url:
                            raise Exception("图片 URL 为空")
                        caption = await self.get_image_caption(
                            url,
                            cfg["image_caption_provider_id"],
                            cfg["image_caption_prompt"],
                        )
                        parts.append(f" [Image: {caption}]")
                    except Exception as e:
                        logger.error(f"获取图片描述失败: {e}")
                else:
                    parts.append(" [Image]")
            elif isinstance(comp, At):
                is_at_self = str(comp.qq) in (
                    event.get_self_id(),
                    "all",
                )
                if is_at_self:
                    parts.insert(1, "⚠️[DIRECTED AT YOU] ")
                parts.append(f" [At: {comp.name}]")
            elif isinstance(comp, Reply):
                if comp.message_str:
                    parts.append(
                        f" [Quote({comp.sender_nickname}: {_truncate_reply_text(comp.message_str)})]"
                    )
                elif comp.chain:
                    chain_desc = _describe_chain(comp.chain)
                    parts.append(f" [Quote({comp.sender_nickname}: {chain_desc})]")
                else:
                    parts.append(" [Quote]")

        return "".join(parts)


_MAX_REPLY_TEXT_LENGTH = 200
_TOPIC_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]+")
_HUMAN_HANDOFF_RE = re.compile(
    r"\s*让\s*(?:bot|机器人)\s*回答(?:这个问题)?\s*[。！？!?]?\s*",
    re.IGNORECASE,
)
_MEMBER_HUSH_RE = re.compile(
    r"(?:这(?:个)?群.{0,8}(?:别|不要|不准|关闭|关掉).{0,5}(?:bot|机器人)|(?:别|不要|不准|关闭|关掉).{0,5}(?:bot|机器人))",
    re.IGNORECASE,
)
_COMMON_TOPIC_TERMS = {
    "一个",
    "不是",
    "什么",
    "可以",
    "就是",
    "怎么",
    "这个",
    "那个",
}


def _is_human_self_message(event: AstrMessageEvent) -> bool:
    raw_message = getattr(event.message_obj, "raw_message", None)
    return isinstance(raw_message, dict) and (
        raw_message.get("_astrbot_self_message_source") == "human"
    )


def _scope_ref(umo: str) -> str:
    """Create a non-reversible short reference for audit logs.

    Args:
        umo: Unified message origin containing the platform and session scope.

    Returns:
        A truncated SHA-256 digest suitable for correlating audit events.
    """
    return hashlib.sha256(umo.encode()).hexdigest()[:12]


def _is_group_admin(event: AstrMessageEvent) -> bool:
    raw_message = getattr(event.message_obj, "raw_message", None)
    if not isinstance(raw_message, dict):
        return False
    sender = raw_message.get("sender")
    if not isinstance(sender, dict):
        return False
    return str(sender.get("role", "")).lower() in {"admin", "owner"}


def _mentions_another_person(event: AstrMessageEvent) -> bool:
    self_id = str(event.get_self_id())
    for component in event.get_messages():
        if isinstance(component, At) and str(component.qq) not in {self_id, "all"}:
            return True
    return False


def _topic_terms(text: str) -> set[str]:
    terms: set[str] = set()
    for token in _TOPIC_TOKEN_RE.findall(text.lower()):
        if token.isascii():
            if len(token) >= 3:
                terms.add(token)
            continue
        if len(token) == 1:
            continue
        terms.update(token[index : index + 2] for index in range(len(token) - 1))
    return terms.difference(_COMMON_TOPIC_TERMS)


def _describe_chain(chain: list) -> str:
    """Summarize message chain content for quoted reply display."""
    desc = []
    for c in chain:
        if isinstance(c, Plain) and getattr(c, "text", None):
            desc.append(c.text)
        elif isinstance(c, Image):
            desc.append("[Image]")
        elif isinstance(c, At):
            name = getattr(c, "name", "") or getattr(c, "qq", "")
            desc.append(f"[At: {name}]")
        elif isinstance(c, Record):
            desc.append("[Voice]")
        elif isinstance(c, Video):
            desc.append("[Video]")
        elif isinstance(c, File):
            desc.append(f"[File: {getattr(c, 'name', '') or ''}]")
        elif isinstance(c, Forward):
            desc.append("[Forward]")
        elif isinstance(c, AtAll):
            desc.append("[At: All]")
        elif isinstance(c, Face):
            desc.append(f"[Sticker: {getattr(c, 'id', '')}]")
        elif isinstance(c, Reply):
            desc.append("[Quote]")
        else:
            desc.append(f"[{c.__class__.__name__}]")
    return "".join(desc) or "[Unknown]"


def _truncate_reply_text(text: str) -> str:
    """Truncate overly long quoted reply text."""
    if len(text) <= _MAX_REPLY_TEXT_LENGTH:
        return text
    return text[:_MAX_REPLY_TEXT_LENGTH] + "..."


def _positive_int(value, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def _non_negative_float(value, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed >= 0 else fallback


def _trim_left(
    records: deque[str],
    max_records: int,
    record_ids: deque[str] | None = None,
) -> None:
    while len(records) > max_records:
        records.popleft()
        if record_ids:
            record_ids.popleft()


def _format_group_history_block(records: list[str]) -> str:
    return GROUP_HISTORY_HEADER + "\n".join(records) + GROUP_HISTORY_FOOTER
