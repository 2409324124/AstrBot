from pathlib import Path


def test_astrbot_exposes_onebot_listener_to_host_network_napcat():
    compose = Path("compose.yml").read_text(encoding="utf-8")

    assert '"127.0.0.1:6199:6199"' in compose
