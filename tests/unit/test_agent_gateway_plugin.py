from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from astrbot.api.message_components import Reply
from astrbot_plugin_agent_gateway.main import Main


def test_plugin_metadata_author_is_a_nonempty_string() -> None:
    metadata_path = (
        Path(__file__).parents[2]
        / "astrbot_plugin_agent_gateway"
        / "metadata.yaml"
    )
    metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))

    assert isinstance(metadata["author"], str)
    assert metadata["author"].strip()


class FakeEvent:
    def __init__(self) -> None:
        self.unified_msg_origin = "aiocqhttp:FriendMessage:1907483592"
        self.message_str = "你是谁"
        self.sent = []
        self.stopped = False
        self.messages = []

    def get_sender_id(self):
        return "1907483592"

    def get_self_id(self):
        return "bot-account"

    def get_group_id(self):
        return None

    def get_messages(self):
        return self.messages

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


@pytest.mark.asyncio
async def test_blank_admin_private_message_is_stopped_before_gateway(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AGENT_GATEWAY_ENABLED", "true")
    plugin = Main(SimpleNamespace(astrbot_config_mgr=object()))
    calls = 0

    async def handle(_payload):
        nonlocal calls
        calls += 1
        return {"action": "reply", "messages": []}

    plugin.client = SimpleNamespace(handle=handle, close=lambda: None)
    event = FakeEvent()
    event.message_str = "   "

    await plugin.route_to_gateway(event)

    assert calls == 0
    assert event.sent == []
    assert event.stopped is True


@pytest.mark.asyncio
async def test_quoted_message_context_is_forwarded_to_gateway(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_GATEWAY_ENABLED", "true")
    plugin = Main(SimpleNamespace(astrbot_config_mgr=object()))
    payloads = []

    async def handle(payload):
        payloads.append(payload)
        return {"action": "no_reply", "messages": []}

    plugin.client = SimpleNamespace(handle=handle, close=lambda: None)
    event = FakeEvent()
    event.message_str = "会好用吗"
    event.messages = [
        Reply(
            id="quoted-1",
            sender_id="owner",
            message_str="直接接 Pi 这个轮子",
        )
    ]

    await plugin.route_to_gateway(event)

    assert payloads[0]["reply_context"] == {
        "sender_id": "owner",
        "text": "直接接 Pi 这个轮子",
    }


@pytest.mark.asyncio
async def test_admin_private_command_switches_gateway_model(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_GATEWAY_ENABLED", "true")
    monkeypatch.setenv("AGENT_GATEWAY_TOKEN", "event-secret")
    monkeypatch.setenv("AGENT_GATEWAY_ADMIN_TOKEN", "admin-secret")
    plugin = Main(SimpleNamespace(astrbot_config_mgr=object()))
    updates = []

    async def get_admin_config():
        return {
            "model": "deepseek-v4-pro",
            "group_whitelist": ["709694410"],
        }

    async def update_admin_config(config):
        updates.append(config)
        return config

    plugin.client = SimpleNamespace(
        get_admin_config=get_admin_config,
        update_admin_config=update_admin_config,
        close=lambda: None,
    )
    event = FakeEvent()
    event.message_str = "-astrbot切换 模型 qwen3.5-27b-local"

    await plugin.route_to_gateway(event)

    assert updates == [
        {
            "model": "qwen3.5-27b-local",
            "group_whitelist": ["709694410"],
        }
    ]
    assert event.sent == ["已切换模型：qwen3.5-27b-local（ai生成内容）"]
    assert event.stopped is True


@pytest.mark.asyncio
async def test_admin_private_command_updates_gateway_group_whitelist(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AGENT_GATEWAY_ENABLED", "true")
    monkeypatch.setenv("AGENT_GATEWAY_TOKEN", "event-secret")
    monkeypatch.setenv("AGENT_GATEWAY_ADMIN_TOKEN", "admin-secret")
    plugin = Main(SimpleNamespace(astrbot_config_mgr=object()))
    updates = []

    async def get_admin_config():
        return {
            "model": "deepseek-v4-pro",
            "group_whitelist": ["709694410"],
        }

    async def update_admin_config(config):
        updates.append(config)
        return config

    plugin.client = SimpleNamespace(
        get_admin_config=get_admin_config,
        update_admin_config=update_admin_config,
        close=lambda: None,
    )
    event = FakeEvent()
    event.message_str = "-astrbot切换 白名单 添加 89589336"

    await plugin.route_to_gateway(event)

    assert updates[0]["group_whitelist"] == ["709694410", "89589336"]
    assert event.sent == ["已添加群：89589336（ai生成内容）"]
    assert event.stopped is True
