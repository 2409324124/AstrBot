_TILDE_COMMANDS = {"help", "new", "reset", "stop", "stats", "research"}


def is_gateway_command_prefix(text: str) -> bool:
    """Return whether text begins with the Gateway-only command root."""
    return text.strip().startswith("~/")


def parse_gateway_command(text: str) -> tuple[str, str] | None:
    """Parse a complete Gateway command rooted at ``~/``."""
    normalized = text.strip()
    if not is_gateway_command_prefix(normalized):
        return None
    parts = normalized[2:].split(maxsplit=1)
    if not parts:
        return None
    command = parts[0].lower()
    if command not in _TILDE_COMMANDS:
        return None
    return command, parts[1] if len(parts) == 2 else ""


def is_retired_gateway_slash_command(text: str) -> bool:
    """Return whether text uses a retired Gateway slash command."""
    normalized = text.strip()
    if not normalized.startswith("/"):
        return False
    command, _, _argument = normalized[1:].partition(" ")
    command = command.lower()
    aliases = {"研究": "research", "检索": "research"}
    command = aliases.get(command, command)
    return command in _TILDE_COMMANDS
