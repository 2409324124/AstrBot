from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from astrbot.api.message_components import At, Plain, Reply
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
                "human_takeover_seconds": 900,
                "member_mute_seconds": 1800,
            },
        },
    }
    return GroupChatContext(MagicMock(), plugin_context)


def make_event(
    text: str,
    *,
    umo: str = "qq_napcat:GroupMessage:123",
    manual_self_message: bool = False,
    components: list | None = None,
    sender_role: str = "member",
    handlers_parsed_params: dict | None = None,
):
    event = MagicMock()
    event.unified_msg_origin = umo
    event.get_message_type.return_value = MessageType.GROUP_MESSAGE
    event.get_group_id.return_value = "123"
    event.is_at_or_wake_command = False
    event.message_str = text
    message_components = components or [Plain(text)]
    event.message_obj = SimpleNamespace(
        sender=SimpleNamespace(nickname="群友"),
        message=message_components,
        raw_message={
            "_astrbot_self_message_source": "human" if manual_self_message else "",
            "sender": {"role": sender_role},
        },
    )
    event.get_messages.return_value = message_components
    event.get_self_id.return_value = "3250641287"
    extras = {"handlers_parsed_params": handlers_parsed_params or {}}
    event.get_extra.side_effect = lambda key, default=None: extras.get(key, default)
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


@pytest.mark.asyncio
async def test_human_self_message_silences_only_its_group_for_takeover_window():
    context = make_context(trigger_keywords=["小董"])

    await context.need_active_reply(make_event("我来回答", manual_self_message=True))

    assert (await context.need_active_reply(make_event("小董你觉得呢"))) is False
    assert (
        await context.need_active_reply(
            make_event("小董你觉得呢", umo="qq_napcat:GroupMessage:456")
        )
    ) is True


@pytest.mark.asyncio
async def test_handoff_phrase_releases_human_takeover_and_requests_a_quoted_answer():
    context = make_context(trigger_keywords=["小董"])
    await context.need_active_reply(make_event("我来回答", manual_self_message=True))

    instruction = context.consume_human_handoff(
        make_event(
            "让bot回答这个问题",
            manual_self_message=True,
            components=[Reply(id="42"), Plain("让bot回答这个问题")],
        )
    )

    assert instruction == "请接管并回答被引用的消息；需要外部事实时先检索。"
    assert (await context.need_active_reply(make_event("小董你觉得呢"))) is True


@pytest.mark.asyncio
async def test_handoff_requires_a_quoted_message():
    context = make_context(trigger_keywords=["小董"])
    await context.need_active_reply(make_event("我来回答", manual_self_message=True))

    instruction = context.consume_human_handoff(
        make_event("让机器人回答", manual_self_message=True)
    )

    assert instruction is None
    assert context.should_suppress_group_bot_reply(make_event("小董你觉得呢")) is True


@pytest.mark.asyncio
async def test_handoff_can_only_be_sent_by_the_shared_account_owner():
    context = make_context(trigger_keywords=["小董"])
    await context.need_active_reply(make_event("我来回答", manual_self_message=True))

    instruction = context.consume_human_handoff(
        make_event(
            "让bot回答",
            components=[Reply(id="42"), Plain("让bot回答")],
        )
    )

    assert instruction is None
    assert context.should_suppress_group_bot_reply(make_event("小董你觉得呢")) is True


@pytest.mark.asyncio
async def test_human_takeover_suppresses_same_group_mentions_and_admin_messages():
    context = make_context(trigger_keywords=["小董"])
    await context.need_active_reply(make_event("我来回答", manual_self_message=True))

    mention = make_event(
        "你回答一下",
        components=[At(qq="3250641287", name="Bot"), Plain("你回答一下")],
    )
    admin_message = make_event("小董你觉得呢", sender_role="admin")

    assert context.should_suppress_group_bot_reply(mention) is True
    assert context.should_suppress_group_bot_reply(admin_message) is True


@pytest.mark.asyncio
async def test_human_takeover_is_scoped_to_one_group_and_allows_explicit_commands():
    context = make_context(trigger_keywords=["小董"])
    await context.need_active_reply(make_event("我来回答", manual_self_message=True))

    explicit_command = make_event(
        "/help",
        handlers_parsed_params={"builtin.help": {}},
    )
    other_group = make_event(
        "小董你觉得呢",
        umo="qq_napcat:GroupMessage:456",
    )

    assert context.should_suppress_group_bot_reply(explicit_command) is False
    assert context.should_suppress_group_bot_reply(other_group) is False


@pytest.mark.asyncio
async def test_member_hush_phrase_mutes_only_its_group_for_thirty_minutes():
    context = make_context(trigger_keywords=["小董"])
    hush_event = make_event("这群别开bot")

    assert context.should_suppress_group_bot_reply(hush_event) is True
    assert await context.need_active_reply(make_event("小董你觉得呢")) is False
    assert (
        await context.need_active_reply(
            make_event("小董你觉得呢", umo="qq_napcat:GroupMessage:456")
        )
    ) is True


def test_group_admin_hush_phrase_does_not_silence_the_bot():
    context = make_context()

    assert (
        context.should_suppress_group_bot_reply(
            make_event("这群别开bot", sender_role="admin")
        )
        is False
    )


@pytest.mark.asyncio
async def test_active_reply_ignores_messages_mentioning_a_different_person():
    context = make_context(trigger_keywords=["小董"])

    should_reply = await context.need_active_reply(
        make_event(
            "小董你觉得呢？",
            components=[At(qq="1907483592", name="云洁"), Plain("小董你觉得呢？")],
        )
    )

    assert should_reply is False


def test_relevance_reply_is_exposed_in_core_config_schema():
    active_reply = DEFAULT_CONFIG["provider_ltm_settings"]["active_reply"]
    active_reply_schema = CONFIG_METADATA_2["provider_group"]["metadata"][
        "provider_ltm_settings"
    ]["items"]["active_reply"]["items"]

    assert active_reply["relevance_threshold"] == 0.55
    assert active_reply["cooldown_seconds"] == 120
    assert active_reply["context_messages"] == 12
    assert active_reply["trigger_keywords"] == []
    assert active_reply["human_takeover_seconds"] == 900
    assert active_reply["member_mute_seconds"] == 1800
    assert "relevance_reply" in active_reply_schema["method"]["options"]
    assert "human_takeover_seconds" in active_reply_schema
    assert "member_mute_seconds" in active_reply_schema
