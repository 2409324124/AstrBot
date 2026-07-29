#!/usr/bin/env python3
"""Replay the secret-free AstrBot recovery workflow for external verification."""

import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    """Run all public scenarios and emit a stable aggregate result.

    Returns:
        Process exit code.
    """
    root = Path(__file__).parent
    operations = root.parents[1] / "scripts" / "astrbot_ops.py"

    def execute(arguments: list[str], expected_code: int) -> dict:
        result = subprocess.run(
            [sys.executable, str(operations), *arguments, "--json"],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != expected_code:
            raise RuntimeError("scenario returned an unexpected exit code")
        return json.loads(result.stdout)

    healthy = execute(
        ["verify", "--fixture", str(root / "healthy.json")],
        0,
    )
    ghost = execute(
        ["verify", "--fixture", str(root / "ghost-online.json")],
        20,
    )
    recovered = execute(
        [
            "recover-qq",
            "--fixture",
            str(root / "recovery-success.json"),
            "--confirm",
        ],
        0,
    )
    qr_required = execute(
        [
            "recover-qq",
            "--fixture",
            str(root / "qr-required.json"),
            "--confirm",
        ],
        20,
    )
    if healthy.get("status") != "ok":
        raise RuntimeError("healthy deployment did not pass")
    if ghost.get("recovery_action") != "recover_qq":
        raise RuntimeError("ghost-online state was not detected")
    if recovered.get("changed_services") != ["napcat"]:
        raise RuntimeError("recovery changed more than NapCat")
    if qr_required.get("recovery_action") != "recover_qq":
        raise RuntimeError("QR fallback did not stop safely")

    print(
        json.dumps(
            {
                "status": "ok",
                "scenarios": {
                    "healthy_deployment": "passed",
                    "ghost_online_recovery": "passed",
                    "qr_required_safe_halt": "passed",
                },
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
