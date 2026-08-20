from astrbot_plugin_agent_gateway.command_parser import (
    is_gateway_command_prefix,
    parse_gateway_command,
)


def test_gateway_tilde_commands_are_parsed_without_astrbot_slash_handlers():
    assert parse_gateway_command("~/new") == ("new", "")
    assert parse_gateway_command("  ~/research  查询 Qdrant 的 RRF ") == (
        "research",
        "查询 Qdrant 的 RRF",
    )
    assert parse_gateway_command("~/research\t查询 BM25") == ("research", "查询 BM25")
    assert parse_gateway_command("/new") is None
    assert parse_gateway_command("东云bot ~/new") is None
    assert is_gateway_command_prefix("~/unknown")
    assert not is_gateway_command_prefix("普通聊天 ~/unknown")
