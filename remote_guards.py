"""Approval integration: runs the same guard entry as the builtin terminal tool, so smart mode, permanent and session grants, gateway /approve cards and the consecutive-denial breaker all behave identically for remote commands."""

import logging
from typing import Any

from tools.approval import check_all_command_guards

logger = logging.getLogger(__name__)


def guard_command(command: str, target: str) -> dict[str, Any] | None:
    """Screen a remote command through the same approval stack the builtin terminal uses. Return None for approved commands; otherwise return a tool error response."""

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
