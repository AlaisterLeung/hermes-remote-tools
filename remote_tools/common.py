"""Shared handler helpers: payload encoding, target resolution, session access, tilde expansion and the pre-mutate snapshot guard."""

import json
from typing import Any

from . import plugin_state, remote_pool, remote_snapshots
from .remote_pool import TargetError

DEFAULT_TIMEOUT = 180


def _dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def parse_targets() -> dict:
    try:
        return remote_pool.parse_targets(plugin_state.get_config())
    except TargetError as exc:
        raise TargetError(str(exc)) from None


def _target_cfg(name: str) -> dict:
    return remote_pool.resolve_target(parse_targets(), name)


def _session(name: str) -> tuple[Any, Any]:
    return remote_pool.get_session(name, _target_cfg(name))


def _check_remote_available() -> bool:
    try:
        return bool(parse_targets())
    except TargetError:
        return False


def _remote_path(env, path: str) -> str:
    """Expand a leading tilde against the detected remote home.

    Core shell-escapes paths, so a quoted ~ no longer expands remotely; the tools accept ~-relative paths, so expand them at the handler boundary.
    """
    home = getattr(env, "_remote_home", "") or ""
    if not home:
        return path
    if path == "~":
        return home
    if path.startswith("~/"):
        return f"{home}/{path[2:]}"
    return path


def _premutate(target: str, path: str, ops) -> str | None:
    """Snapshot before mutating; returns error text when the file is too large to snapshot (refuse rather than make an unundoable edit)."""
    store = remote_snapshots.default_store()
    snap_id = store.save(ops, target, path)
    if snap_id is None:
        probe = ops.read_file_bytes(path, max_bytes=remote_snapshots.MAX_SNAPSHOT_BYTES)
        # the too-large error path is the only one that still reports file_size
        if (
            probe.error
            and probe.file_size
            and probe.file_size > remote_snapshots.MAX_SNAPSHOT_BYTES
        ):
            return (
                f"{target}:{path} is larger than the snapshot cap "
                f"({remote_snapshots.MAX_SNAPSHOT_BYTES} bytes); refusing to "
                "edit without an undo point."
            )
    return None
