from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiocqhttp import Event

from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
    OutboundMessageTracker,
    get_outbound_message_tracker,
)
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
    AiocqhttpAdapter,
)


def test_outbound_message_tracker_filters_pending_bot_message_by_content():
    tracker = OutboundMessageTracker()
    tracker.remember_pending([{"type": "text", "data": {"text": "Bot reply"}}])

    assert tracker.consume_if_bot_message(
        {
            "message_id": 42,
            "message": [{"type": "text", "data": {"text": "Bot reply"}}],
        }
    )


def test_outbound_message_tracker_keeps_manual_self_message():
    tracker = OutboundMessageTracker()
    tracker.remember_sent_message_id(42)

    assert not tracker.consume_if_bot_message(
        {
            "message_id": 99,
            "message": [{"type": "text", "data": {"text": "我来回答"}}],
        }
    )


def make_self_group_message_event(message_id: int, text: str) -> Event:
    return Event(
        {
            "time": 1,
            "post_type": "message",
            "message_type": "group",
            "sub_type": "normal",
            "self_id": 3250641287,
            "user_id": 3250641287,
            "group_id": 123,
            "message_id": message_id,
            "message": [{"type": "text", "data": {"text": text}}],
            "raw_message": text,
            "sender": {
                "user_id": 3250641287,
                "nickname": "云洁",
                "card": "云洁",
            },
        }
    )


@pytest.mark.asyncio
async def test_untracked_normal_self_group_message_is_tagged_as_human_takeover():
    adapter = AiocqhttpAdapter.__new__(AiocqhttpAdapter)
    adapter.bot = MagicMock()

    message = await adapter.convert_message(
        make_self_group_message_event(99, "我来回答")
    )

    assert message is not None
    assert message.raw_message["_astrbot_self_message_source"] == "human"


@pytest.mark.asyncio
async def test_tracked_group_message_sent_is_not_forwarded_as_human_takeover():
    adapter = AiocqhttpAdapter.__new__(AiocqhttpAdapter)
    adapter.bot = MagicMock()
    get_outbound_message_tracker(adapter.bot).remember_sent_message_id(99)

    message = await adapter.convert_message(
        make_self_group_message_event(99, "Bot reply")
    )

    assert message is None


def test_consuming_bot_message_clears_id_and_matching_pending_fingerprint():
    tracker = OutboundMessageTracker()
    message = [{"type": "text", "data": {"text": "相同文本"}}]
    tracker.remember_pending(message)
    tracker.remember_sent_message_id(99)

    assert tracker.consume_if_bot_message({"message_id": 99, "message": message})
    assert not tracker.consume_if_bot_message({"message_id": 100, "message": message})


@pytest.mark.asyncio
async def test_failed_send_does_not_leave_pending_self_message_fingerprint():
    bot = MagicMock()
    bot.send_group_msg = AsyncMock(side_effect=RuntimeError("send failed"))
    message = [{"type": "text", "data": {"text": "发送失败"}}]

    with pytest.raises(RuntimeError, match="send failed"):
        await AiocqhttpMessageEvent._dispatch_send(
            bot=bot,
            event=None,
            is_group=True,
            session_id="123",
            messages=message,
        )

    assert not get_outbound_message_tracker(bot).consume_if_bot_message(
        {"message_id": 100, "message": message}
    )


@pytest.mark.asyncio
async def test_group_account_activity_includes_last_successful_bot_send():
    bot = MagicMock()
    bot.send_group_msg = AsyncMock(return_value={"message_id": 99})
    bot.call_action = AsyncMock(return_value={"last_sent_time": 120})
    event = AiocqhttpMessageEvent.__new__(AiocqhttpMessageEvent)
    event.bot = bot
    event.get_group_id = MagicMock(return_value="123")
    event.get_self_id = MagicMock(return_value="3250641287")

    with patch(
        "astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event.time.time",
        side_effect=[100.0, 130.0],
    ):
        await AiocqhttpMessageEvent._dispatch_send(
            bot=bot,
            event=None,
            is_group=True,
            session_id="123",
            messages=[{"type": "text", "data": {"text": "Bot reply"}}],
        )
        activity = await event.get_group_account_activity()

    assert activity == {
        "account_last_sent_at": 120.0,
        "bot_last_sent_at": 100.0,
        "observed_at": 130.0,
    }


@pytest.mark.asyncio
async def test_group_account_activity_is_rate_limited_per_group():
    bot = MagicMock()
    bot.call_action = AsyncMock(return_value={"last_sent_time": 120})
    event = AiocqhttpMessageEvent.__new__(AiocqhttpMessageEvent)
    event.bot = bot
    event.get_group_id = MagicMock(return_value="123")
    event.get_self_id = MagicMock(return_value="3250641287")

    first = await event.get_group_account_activity()
    second = await event.get_group_account_activity()

    assert first == second
    bot.call_action.assert_awaited_once()


@pytest.mark.asyncio
async def test_successful_group_send_invalidates_cached_account_activity():
    bot = MagicMock()
    bot.call_action = AsyncMock(
        side_effect=[{"last_sent_time": 120}, {"last_sent_time": 140}]
    )
    bot.send_group_msg = AsyncMock(return_value={"message_id": 99})
    event = AiocqhttpMessageEvent.__new__(AiocqhttpMessageEvent)
    event.bot = bot
    event.get_group_id = MagicMock(return_value="123")
    event.get_self_id = MagicMock(return_value="3250641287")

    first = await event.get_group_account_activity()
    await AiocqhttpMessageEvent._dispatch_send(
        bot=bot,
        event=None,
        is_group=True,
        session_id="123",
        messages=[{"type": "text", "data": {"text": "Bot reply"}}],
    )
    second = await event.get_group_account_activity()

    assert first["account_last_sent_at"] == 120.0
    assert second["account_last_sent_at"] == 140.0
    assert second["bot_last_sent_at"] is not None
    assert bot.call_action.await_count == 2
