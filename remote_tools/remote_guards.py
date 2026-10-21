"""Approval integration: the plugin runs the SAME guard entry as the builtin terminal tool, so smart mode, permanent and session grants, gateway /approve cards and the consecutive-denial breaker all behave identically for remote commands. has_host_access is always False - a remote shell has no host access."""

import logging
from typing import Any

from tools.approval import check_all_command_guards

logger = logging.getLogger(__name__)


def guard_command(command: str, target: str) -> dict[str, Any] | None:
    """Run the consolidated approval guard. Returns None when approved, else a blocked result dict (ready to serialize as the tool response)."""
    verdict = check_all_command_guards(
        command,
        "ssh",
        has_host_access=False,
    )
    if verdict.get("approved"):
        return None
    detail = {k: v for k, v in verdict.items() if k != "approved"}
    logger.info("remote command blocked by approval guard on target %s", target)
    return {
        "output": "",
        "returncode": -1,
        "status": verdict.get("status", "blocked"),
        "failed": True,
        "error": verdict.get("message") or "command blocked by the approval guard",
        "approval": detail,
    }
