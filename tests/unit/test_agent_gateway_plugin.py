from types import SimpleNamespace

import pytest

from astrbot_plugin_agent_gateway.main import Main


class FakeEvent:
    def __init__(self) -> None:
        self.unified_msg_origin = "aiocqhttp:FriendMessage:1907483592"
        self.message_str = "你是谁"
        self.sent = []
        self.stopped = False

    def get_sender_id(self):
        return "1907483592"

    def get_self_id(self):
        return "bot-account"

    def get_group_id(self):
        return None

    def get_messages(self):
        return []

    def get_message_type(self):
        from astrbot.api.platform import MessageType

        return MessageType.FRIEND_MESSAGE

    def is_admin(self):
        return True

    async def send(self, chain):
        self.sent.append("".join(item.text for item in chain.chain))

    def should_call_llm(self, enabled):
        assert enabled is False

    def stop_event(self):
        self.stopped = True


@pytest.mark.asyncio
async def test_admin_private_message_is_replied_by_gateway_and_stops_old_agent(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AGENT_GATEWAY_ENABLED", "true")
    monkeypatch.setenv("AGENT_GATEWAY_URL", "http://agent-gateway:8090")
    monkeypatch.setenv("AGENT_GATEWAY_TOKEN", "event-secret")
    plugin = Main(SimpleNamespace(astrbot_config_mgr=object()))

    async def handle(_payload):
        return {
            "action": "reply",
            "messages": [{"type": "text", "text": "我是东云bot（ai生成内容）"}],
        }

    plugin.client = SimpleNamespace(handle=handle, close=lambda: None)
    event = FakeEvent()

    await plugin.route_to_gateway(event)

    assert event.sent == ["我是东云bot（ai生成内容）"]
    assert event.stopped is True
