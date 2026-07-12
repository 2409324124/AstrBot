from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from astrbot.api.message_components import Plain
from astrbot.api.platform import MessageType
from astrbot.builtin_stars.astrbot.group_chat_context import GroupChatContext
from astrbot.core.config.default import CONFIG_METADATA_2, DEFAULT_CONFIG


def make_context(*, trigger_keywords: list[str] | None = None) -> GroupChatContext:
    plugin_context = MagicMock()
    plugin_context.get_config.return_value = {
        "provider_settings": {"image_caption_prompt": "describe"},
        "provider_ltm_settings": {
            "group_message_max_cnt": 30,
            "image_caption": False,
            "image_caption_provider_id": "",
            "active_reply": {
                "enable": True,
                "method": "relevance_reply",
                "possibility_reply": 0.0,
                "whitelist": [],
                "relevance_threshold": 0.55,
                "cooldown_seconds": 120,
                "context_messages": 12,
                "trigger_keywords": trigger_keywords or [],
            },
        },
    }
    return GroupChatContext(MagicMock(), plugin_context)


def make_event(text: str):
    event = MagicMock()
    event.unified_msg_origin = "qq_napcat:GroupMessage:123"
    event.get_message_type.return_value = MessageType.GROUP_MESSAGE
    event.get_group_id.return_value = "123"
    event.is_at_or_wake_command = False
    event.message_str = text
    event.message_obj = SimpleNamespace(
        sender=SimpleNamespace(nickname="群友"),
        message=[Plain(text)],
    )
    event.get_messages.return_value = [Plain(text)]
    event.get_extra.return_value = None
    return event


@pytest.mark.asyncio
async def test_relevance_reply_joins_a_question_continuing_the_recent_topic():
    context = make_context()
    await context.handle_message(make_event("我们准备在服务器部署这个模型"))

    should_reply = await context.need_active_reply(
        make_event("这个模型具体要怎么部署？")
    )

    assert should_reply is True


@pytest.mark.asyncio
async def test_relevance_reply_ignores_unrelated_short_chatter():
    context = make_context()
    await context.handle_message(make_event("我们准备在服务器部署这个模型"))

    should_reply = await context.need_active_reply(make_event("哈哈"))

    assert should_reply is False


@pytest.mark.asyncio
async def test_relevance_reply_respects_cooldown_after_replying():
    context = make_context(trigger_keywords=["小董"])

    first = await context.need_active_reply(make_event("小董你觉得呢"))
    second = await context.need_active_reply(make_event("小董还在吗"))

    assert first is True
    assert second is False


def test_relevance_reply_is_exposed_in_core_config_schema():
    active_reply = DEFAULT_CONFIG["provider_ltm_settings"]["active_reply"]
    active_reply_schema = CONFIG_METADATA_2["provider_group"]["metadata"][
        "provider_ltm_settings"
    ]["items"]["active_reply"]["items"]

    assert active_reply["relevance_threshold"] == 0.55
    assert active_reply["cooldown_seconds"] == 120
    assert active_reply["context_messages"] == 12
    assert active_reply["trigger_keywords"] == []
    assert "relevance_reply" in active_reply_schema["method"]["options"]
