from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.api.message_components import Plain
from astrbot.api.platform import MessageType
from astrbot.core.pipeline.waking_check import stage as waking_module
from astrbot.core.pipeline.waking_check.stage import WakingCheckStage


def make_self_event(*, source: str = ""):
    event = MagicMock()
    event.get_self_id.return_value = "3250641287"
    event.get_sender_id.return_value = "3250641287"
    event.message_obj = SimpleNamespace(
        raw_message={"_astrbot_self_message_source": source},
        type=MessageType.GROUP_MESSAGE,
    )
    event.message_str = "  hello  "
    event.get_messages.return_value = [Plain("hello")]
    event.is_private_chat.return_value = False
    event._extras = {}
    return event


def make_stage(*, enabled: bool) -> WakingCheckStage:
    stage = WakingCheckStage()
    stage.ignore_bot_self_message = enabled
    stage.unique_session = False
    stage.no_permission_reply = True
    stage.friend_message_needs_wake_prefix = False
    stage.ignore_at_all = False
    stage.disable_builtin_commands = False
    stage.ctx = SimpleNamespace(
        astrbot_config={"admins_id": [], "wake_prefix": [], "plugin_set": []}
    )
    return stage


@pytest.fixture(autouse=True)
def no_registered_handlers(monkeypatch):
    monkeypatch.setattr(
        waking_module.star_handlers_registry,
        "get_handlers_by_event_type",
        MagicMock(return_value=[]),
    )
    monkeypatch.setattr(
        waking_module.SessionPluginManager,
        "filter_handlers_by_session",
        AsyncMock(return_value=[]),
    )


@pytest.mark.asyncio
async def test_ignore_self_message_setting_keeps_a_manual_owner_message():
    event = make_self_event(source="human")

    await make_stage(enabled=True).process(event)

    assert event.message_str == "hello"


@pytest.mark.asyncio
async def test_ignore_self_message_setting_still_filters_unmarked_self_messages():
    event = make_self_event()

    await make_stage(enabled=True).process(event)

    assert event.message_str == "  hello  "
    event.stop_event.assert_called_once_with()


@pytest.mark.asyncio
async def test_disabled_ignore_self_message_setting_keeps_self_messages():
    event = make_self_event()

    await make_stage(enabled=False).process(event)

    assert event.message_str == "hello"
