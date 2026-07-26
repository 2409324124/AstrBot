from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from astrbot.api.message_components import Plain, Reply
from astrbot_plugin_agent_gateway.main import Main


def test_plugin_metadata_author_is_a_nonempty_string() -> None:
    metadata_path = (
        Path(__file__).parents[2] / "astrbot_plugin_agent_gateway" / "metadata.yaml"
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
        self.extras = {}

    def get_sender_id(self):
        return "1907483592"

    def get_self_id(self):
        return "bot-account"

    def get_group_id(self):
        return None

    def get_messages(self):
        return self.messages

    def get_extra(self, key=None, default=None):
        if key is None:
            return self.extras
        return self.extras.get(key, default)

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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler_name", "action", "message"),
    [
        ("new_conv", "new", "已开始新会话"),
        ("reset", "reset", "会话记忆已清空"),
        ("stop", "stop", "当前没有运行中的任务"),
        ("stats", "stats", "当前会话暂无用量记录"),
    ],
)
async def test_session_commands_use_gateway_control_without_calling_agent(
    monkeypatch,
    handler_name,
    action,
    message,
) -> None:
    monkeypatch.setenv("AGENT_GATEWAY_ENABLED", "true")
    plugin = Main(SimpleNamespace(astrbot_config_mgr=object()))
    controls = []
    agent_calls = 0

    async def control_session(payload):
        controls.append(payload)
        return {"status": action, "message": message}

    async def handle(_payload):
        nonlocal agent_calls
        agent_calls += 1
        return {"action": "reply", "messages": []}

    plugin.client = SimpleNamespace(
        control_session=control_session,
        handle=handle,
        close=lambda: None,
    )
    event = FakeEvent()
    event.message_str = action
    event.messages = [Plain(f"/{action}")]
    event.extras["activated_handlers"] = [
        SimpleNamespace(
            handler_module_path="astrbot.builtin_stars.builtin_commands.main",
            handler_name=handler_name,
        )
    ]
    event.extras["handlers_parsed_params"] = {f"builtin.{handler_name}": {}}

    await plugin.route_to_gateway(event)

    assert controls == [
        {
            "schema_version": "1",
            "session_id": "aiocqhttp:FriendMessage:1907483592",
            "action": action,
            "chat_type": "private",
            "is_admin": True,
        }
    ]
    assert agent_calls == 0
    assert event.sent == [message]
    assert event.stopped is True


@pytest.mark.asyncio
async def test_help_command_is_answered_before_gateway_agent(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_GATEWAY_ENABLED", "true")
    plugin = Main(SimpleNamespace(astrbot_config_mgr=object()))
    agent_calls = 0

    async def handle(_payload):
        nonlocal agent_calls
        agent_calls += 1
        return {"action": "reply", "messages": []}

    plugin.client = SimpleNamespace(handle=handle, close=lambda: None)
    event = FakeEvent()
    event.message_str = "help"
    event.messages = [Plain("/help")]
    event.extras["activated_handlers"] = [
        SimpleNamespace(
            handler_module_path="astrbot.builtin_stars.builtin_commands.main",
            handler_name="help",
        )
    ]

    await plugin.route_to_gateway(event)

    assert agent_calls == 0
    assert event.sent == [
        "命令：/new /reset /stop /stats /research；/sid；管理员可用 /name 和 -astrbot切换"
    ]
    assert event.stopped is True


@pytest.mark.asyncio
@pytest.mark.parametrize("handler_name", ["sid", "name"])
async def test_transport_builtin_commands_pass_through_to_astrbot(
    monkeypatch,
    handler_name,
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
    event.message_str = handler_name
    event.messages = [Plain(f"/{handler_name}")]
    event.extras["activated_handlers"] = [
        SimpleNamespace(
            handler_module_path="astrbot.builtin_stars.builtin_commands.main",
            handler_name=handler_name,
        )
    ]

    await plugin.route_to_gateway(event)

    assert calls == 0
    assert event.sent == []
    assert event.stopped is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler_name", "expected"),
    [
        ("provider", "模型切换请使用：-astrbot切换 模型 <ID>"),
        ("update_dashboard", "此命令已停用"),
        ("set_variable", "此命令已停用"),
        ("unset_variable", "此命令已停用"),
    ],
)
async def test_unsafe_builtin_commands_are_deterministically_intercepted(
    monkeypatch,
    handler_name,
    expected,
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
    event.extras["activated_handlers"] = [
        SimpleNamespace(
            handler_module_path="astrbot.builtin_stars.builtin_commands.main",
            handler_name=handler_name,
        )
    ]

    await plugin.route_to_gateway(event)

    assert calls == 0
    assert event.sent == [expected]
    assert event.stopped is True


@pytest.mark.asyncio
async def test_unknown_slash_command_never_reaches_gateway_agent(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_GATEWAY_ENABLED", "true")
    plugin = Main(SimpleNamespace(astrbot_config_mgr=object()))
    calls = 0

    async def handle(_payload):
        nonlocal calls
        calls += 1
        return {"action": "reply", "messages": []}

    plugin.client = SimpleNamespace(handle=handle, close=lambda: None)
    event = FakeEvent()
    event.message_str = "dangerous unknown"
    event.messages = [Plain("/dangerous unknown")]

    await plugin.route_to_gateway(event)

    assert calls == 0
    assert event.sent == ["未知或未启用的命令；使用 /help 查看可用命令"]
    assert event.stopped is True


@pytest.mark.asyncio
async def test_research_command_forces_external_route_without_builtin_llm(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AGENT_GATEWAY_ENABLED", "true")
    plugin = Main(SimpleNamespace(astrbot_config_mgr=object()))
    payloads = []

    async def handle(payload):
        payloads.append(payload)
        return {
            "action": "reply",
            "messages": [{"type": "text", "text": "检索结果（ai生成内容）"}],
        }

    plugin.client = SimpleNamespace(handle=handle, close=lambda: None)
    event = FakeEvent()
    event.message_str = "上海限行新规"
    event.messages = [Plain("/research 上海限行新规")]
    event.extras["activated_handlers"] = [
        SimpleNamespace(
            handler_module_path="astrbot.builtin_stars.astrbot.main",
            handler_name="research",
        )
    ]

    await plugin.route_to_gateway(event)

    assert payloads[0]["text"] == "上海限行新规"
    assert payloads[0]["force_route"] == "external_fact"
    assert event.sent == ["检索结果（ai生成内容）"]
    assert event.stopped is True
