from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.api.message_components import Plain
from astrbot.builtin_stars.astrbot.main import Main


def make_main_with_conversation_manager(conv_mgr):
    main = Main.__new__(Main)
    main.context = MagicMock()
    main.context.conversation_manager = conv_mgr
    return main


def _make_extras_store():
    """Return a mutable dict and get_extra / set_extra side_effects bound to it."""
    store: dict[str, object] = {}
    get_extra = lambda key, default=None: store.get(key, default)  # noqa: E731
    set_extra = store.__setitem__  # type: ignore[assignment]
    return store, get_extra, set_extra


def make_event(
    umo: str = "aiocqhttp:GroupMessage:user_123_group_456",
    *,
    handlers_parsed_params: dict | None = None,
):
    event = MagicMock()
    event.unified_msg_origin = umo
    event.get_platform_id.return_value = "aiocqhttp"
    event.message_obj = SimpleNamespace(message=[Plain("hello")])
    event.message_str = "hello"
    event.session_id = "session-1"

    store, get_extra, set_extra = _make_extras_store()
    # Simulate WakingCheckStage output: an empty dict means no command matched.
    store["handlers_parsed_params"] = (
        {} if handlers_parsed_params is None else handlers_parsed_params
    )
    event.get_extra.side_effect = get_extra
    event.set_extra.side_effect = set_extra
    return event


@pytest.mark.asyncio
async def test_active_reply_does_not_create_conversation_when_current_missing():
    conv_mgr = SimpleNamespace(
        get_curr_conversation_id=AsyncMock(return_value=None),
        new_conversation=AsyncMock(),
        get_conversation=AsyncMock(),
    )
    main = make_main_with_conversation_manager(conv_mgr)
    main.context.get_config.return_value = {
        "provider_ltm_settings": {
            "group_icl_enable": False,
            "active_reply": {"enable": True},
        },
    }
    main.context.get_using_provider.return_value = object()
    main.group_chat_context = SimpleNamespace(
        need_active_reply=AsyncMock(return_value=True),
        handle_message=AsyncMock(),
    )
    event = make_event()

    results = [item async for item in main.on_message(event)]

    assert results == []
    conv_mgr.get_curr_conversation_id.assert_awaited_once_with(event.unified_msg_origin)
    conv_mgr.new_conversation.assert_not_called()
    conv_mgr.get_conversation.assert_not_called()
    event.request_llm.assert_not_called()


@pytest.mark.asyncio
async def test_active_reply_reuses_current_umo_conversation():
    conv = SimpleNamespace(cid="cid-1")
    conv_mgr = SimpleNamespace(
        get_curr_conversation_id=AsyncMock(return_value="cid-1"),
        new_conversation=AsyncMock(),
        get_conversation=AsyncMock(return_value=conv),
    )
    main = make_main_with_conversation_manager(conv_mgr)
    main.context.get_config.return_value = {
        "provider_ltm_settings": {
            "group_icl_enable": False,
            "active_reply": {"enable": True},
        },
    }
    main.context.get_using_provider.return_value = object()
    main.group_chat_context = SimpleNamespace(
        need_active_reply=AsyncMock(return_value=True),
        handle_message=AsyncMock(),
    )
    event = make_event("aiocqhttp:GroupMessage:user_999_group_456")
    llm_request = object()
    event.request_llm.return_value = llm_request

    results = [item async for item in main.on_message(event)]

    assert results == [llm_request]
    conv_mgr.get_curr_conversation_id.assert_awaited_once_with(event.unified_msg_origin)
    conv_mgr.new_conversation.assert_not_called()
    conv_mgr.get_conversation.assert_awaited_once_with(
        event.unified_msg_origin,
        "cid-1",
    )
    event.request_llm.assert_called_once_with(
        prompt="hello",
        session_id="session-1",
        image_urls=[],
        conversation=conv,
    )


@pytest.mark.asyncio
async def test_on_message_does_not_clear_group_context_on_first_enabled_message():
    main = Main.__new__(Main)
    main.context = MagicMock()
    main.context.get_config.return_value = {
        "provider_ltm_settings": {
            "group_icl_enable": True,
            "active_reply": {"enable": False},
        },
    }
    main.group_chat_context = SimpleNamespace(
        need_active_reply=AsyncMock(return_value=False),
        handle_message=AsyncMock(),
        remove_session=AsyncMock(),
    )
    event = make_event()

    async for _ in main.on_message(event):
        pass

    main.group_chat_context.need_active_reply.assert_awaited_once_with(event)
    main.group_chat_context.handle_message.assert_awaited_once_with(event)
    main.group_chat_context.remove_session.assert_not_called()


@pytest.mark.asyncio
async def test_on_message_skips_recording_when_command_handler_matched():
    """A slash-command message (handlers_parsed_params non-empty) must not be
    recorded into the group context buffer."""
    main = Main.__new__(Main)
    main.context = MagicMock()
    main.context.get_config.return_value = {
        "provider_ltm_settings": {
            "group_icl_enable": True,
            "active_reply": {"enable": False},
        },
    }
    main.group_chat_context = SimpleNamespace(
        need_active_reply=AsyncMock(return_value=False),
        handle_message=AsyncMock(),
    )
    event = make_event(
        handlers_parsed_params={
            "astrbot.builtin_stars.builtin_commands.main_reset": {}
        },
    )

    async for _ in main.on_message(event):
        pass

    main.group_chat_context.need_active_reply.assert_awaited_once_with(event)
    main.group_chat_context.handle_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_human_handoff_turns_shared_account_message_into_llm_request():
    main = Main.__new__(Main)
    main.context = MagicMock()
    main.context.get_config.return_value = {
        "provider_ltm_settings": {
            "group_icl_enable": True,
            "active_reply": {"enable": True},
        },
    }
    handoff_instruction = "请接管并回答被引用的消息；需要外部事实时先检索。"
    main.group_chat_context = SimpleNamespace(
        need_active_reply=AsyncMock(return_value=False),
        handle_message=AsyncMock(),
        consume_human_handoff=MagicMock(return_value=handoff_instruction),
    )
    event = make_event()
    event.is_at_or_wake_command = False
    event.is_wake = False

    async for _ in main.on_message(event):
        pass

    main.group_chat_context.consume_human_handoff.assert_called_once_with(event)
    assert event.message_str == handoff_instruction
    assert event.is_at_or_wake_command is True
    assert event.is_wake is True


@pytest.mark.asyncio
async def test_member_group_mute_stops_the_event_before_any_bot_reply():
    main = Main.__new__(Main)
    main.context = MagicMock()
    main.context.get_config.return_value = {
        "provider_ltm_settings": {
            "group_icl_enable": True,
            "active_reply": {"enable": True},
        },
    }
    main.group_chat_context = SimpleNamespace(
        should_suppress_group_bot_reply=MagicMock(return_value=True),
        need_active_reply=AsyncMock(),
        handle_message=AsyncMock(),
    )
    event = make_event()

    results = [item async for item in main.on_message(event)]

    assert results == []
    event.stop_event.assert_called_once_with()
    main.group_chat_context.need_active_reply.assert_not_awaited()


@pytest.mark.asyncio
async def test_research_command_requests_llm_with_external_research_flag():
    main = Main.__new__(Main)
    event = make_event()
    event.request_llm.return_value = "research-request"

    results = [item async for item in main.research(event, "贪心算法的反例")]

    assert results == ["research-request"]
    assert event.get_extra("_force_external_research") is True
    event.request_llm.assert_called_once_with(
        prompt="贪心算法的反例",
        session_id="session-1",
    )


@pytest.mark.asyncio
async def test_research_command_requires_a_question():
    main = Main.__new__(Main)
    event = make_event()
    event.plain_result.return_value = "usage"

    results = [item async for item in main.research(event, "")]

    assert results == ["usage"]
    event.request_llm.assert_not_called()
