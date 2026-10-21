"""terminal_remote: remote exec with the core approval guard and background spawn registration."""

from tools.registry import tool_error

from . import remote_guards
from .common import (
    DEFAULT_TIMEOUT,
    _dumps,
    _remote_path,
    _session,
)
from .remote_pool import TargetError


def _handle_terminal_remote(args: dict, task_id: str = "", **_) -> str:
    target = str(args.get("target", "")).strip()
    command = str(args.get("command", "")).strip()
    if not target or not command:
        return tool_error("terminal_remote: both 'target' and 'command' are required.")

    try:
        env, _ops = _session(target)
    except TargetError as exc:
        return tool_error(f"terminal_remote: {exc}")

    blocked = remote_guards.guard_command(command, target)
    if blocked is not None:
        return _dumps(blocked)

    timeout = int(args.get("timeout") or DEFAULT_TIMEOUT)
    workdir = _remote_path(env, str(args.get("workdir", "") or ""))
    if args.get("background"):
        return _dumps(
            _spawn_background(env, target, command, workdir, task_id, timeout)
        )

    result = env.execute(command, cwd=workdir, timeout=timeout)
    return_code = int(result.get("returncode", -1))
    payload: dict = {
        "output": result.get("output", ""),
        "returncode": return_code,
        "target": target,
        "cwd": getattr(env, "cwd", workdir or "~"),
    }
    if return_code != 0:
        payload["failed"] = True

    return _dumps(payload)


def _spawn_background(
    env, target: str, command: str, workdir: str, task_id: str, timeout: int
) -> dict:
    """Register the remote process in the core process registry so completion notifications, process_manage, stop fan-out and teardown reaping see it."""

    from tools.process_registry import process_registry

    session = process_registry.spawn_via_env(
        env=env,
        command=command,
        cwd=workdir,
        task_id=task_id or "default",
        timeout=timeout,
    )
    session.notify_on_complete = True
    _route_session(process_registry, session)
    return {
        "status": "running",
        "background": True,
        "session_id": session.id,
        "target": target,
        "backend": "ssh",
        "notify": True,
        "hint": "poll or stop it through the standard process management tool "
        f"with session_id {session.id}.",
    }


def _route_session(process_registry, session) -> None:
    """Best-effort gateway routing parity with the builtin background spawn."""

    try:
        from gateway.session_context import get_session_env
        from tools.terminal_tool_background import _stamp_routing_if_gateway

        _stamp_routing_if_gateway(
            process_registry, session, get_session_env("HERMES_SESSION_KEY", "")
        )
    except Exception:
        # Routing is an enhancement, not a spawn blocker
        pass
