from types import SimpleNamespace

import pytest

from astrbot.api.platform import MessageType
from astrbot_plugin_agent_gateway.main import Main


class FakeGatewayClient:
    def __init__(self) -> None:
        self.controls: list[dict] = []
        self.events: list[dict] = []

    async def control_session(self, payload: dict) -> dict:
        self.controls.append(payload)
        return {"message": "会话已创建"}

    async def handle(self, payload: dict) -> dict:
        self.events.append(payload)
        return {"action": "no_reply", "messages": []}


class FakeEvent:
    def __init__(self, text: str) -> None:
        self.message_str = text
        self.unified_msg_origin = "aiocqhttp:FriendMessage:test"
        self.sent: list[object] = []
        self.llm_enabled: list[bool] = []
        self.stopped = False

    def get_message_type(self) -> MessageType:
        return MessageType.FRIEND_MESSAGE

    def get_extra(self, _name: str, default: object) -> object:
        return default

    def is_admin(self) -> bool:
        return True

    def get_group_id(self) -> None:
        return None

    def get_sender_id(self) -> str:
        return "admin"

    def get_self_id(self) -> str:
        return "bot"

    def get_messages(self) -> list[object]:
        return []

    async def send(self, message: object) -> None:
        self.sent.append(message)

    def should_call_llm(self, enabled: bool) -> None:
        self.llm_enabled.append(enabled)

    def stop_event(self) -> None:
        self.stopped = True


def gateway_with(client: FakeGatewayClient) -> Main:
    gateway = object.__new__(Main)
    gateway.enabled = True
    gateway.client = client
    gateway.group_context = None
    return gateway


@pytest.mark.asyncio
async def test_tilde_new_uses_gateway_session_control_without_llm():
    client = FakeGatewayClient()
    event = FakeEvent("~/new")

    await gateway_with(client).route_to_gateway(event)

    assert client.controls == [
        {
            "schema_version": "1",
            "session_id": "aiocqhttp:FriendMessage:test",
            "action": "new",
            "chat_type": "private",
            "is_admin": True,
        }
    ]
    assert event.llm_enabled == [False]
    assert event.stopped


@pytest.mark.asyncio
async def test_legacy_slash_command_returns_migration_hint_without_gateway_call():
    client = FakeGatewayClient()
    event = FakeEvent("/new")

    await gateway_with(client).route_to_gateway(event)

    assert client.controls == []
    assert len(event.sent) == 1
    assert event.llm_enabled == [False]
    assert event.stopped


@pytest.mark.asyncio
async def test_tilde_research_forces_external_route_with_only_the_question():
    client = FakeGatewayClient()
    event = FakeEvent("~/research 查询 Qdrant 的混合检索")
    event.message_obj = SimpleNamespace(message_id="research-1", timestamp=1_700_000_000)

    await gateway_with(client).route_to_gateway(event)

    assert client.events[0]["text"] == "查询 Qdrant 的混合检索"
    assert client.events[0]["force_route"] == "external_fact"
    assert event.llm_enabled == [False]
    assert event.stopped
