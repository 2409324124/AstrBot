from astrbot_plugin_agent_gateway.command_parser import (
    is_gateway_command_prefix,
    legacy_migration_hint,
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


def test_legacy_gateway_slash_commands_receive_only_a_migration_hint():
    assert legacy_migration_hint("/reset") == "命令已迁移：请使用 ~/reset"
    assert legacy_migration_hint("/research 检索 RTX 5090") == (
        "命令已迁移：请使用 ~/research <问题>"
    )
    assert legacy_migration_hint("/sid") is None
    assert legacy_migration_hint("/unrelated") is None
