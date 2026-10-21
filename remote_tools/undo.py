"""undo_remote_file: restore a remote path from the latest snapshot; the content being replaced is itself snapshotted so undo steps walk back one at a time."""

import base64
import hashlib
import shlex

from tools.registry import tool_error

from ..schemas import UNDO
from . import remote_snapshots
from .common import (
    DEFAULT_TIMEOUT,
    _check_remote_available,
    _dumps,
    _remote_path,
    _session,
)
from .remote_pool import TargetError


def _undo_env_write(env, path: str, data: bytes) -> dict:
    """Binary-safe restore: base64 through stdin, never through argv."""
    encoded = base64.b64encode(data).decode()
    return env.execute(
        f"base64 -d > {shlex.quote(path)}", stdin_data=encoded, timeout=DEFAULT_TIMEOUT
    )


def _handle_undo_remote_file(args: dict, **_) -> str:
    target = str(args.get("target", "")).strip()
    path = str(args.get("path", "")).strip()
    if not target or not path:
        return tool_error("undo_remote_file: both 'target' and 'path' are required.")
    try:
        env, ops = _session(target)
    except TargetError as exc:
        return tool_error(f"undo_remote_file: {exc}")
    path = _remote_path(env, path)
    store = remote_snapshots.default_store()
    data = store.pop_latest(target, path)
    if data is None:
        return tool_error(f"undo_remote_file: no snapshot for {target}:{path}.")
    # keep the pre-restore content so an undo is itself undoable
    store.save(ops, target, path)
    result = _undo_env_write(env, path, data)
    if int(result.get("returncode", -1)) != 0:
        return tool_error(
            f"undo_remote_file: restore failed: {result.get('output', '')!r}"
        )
    return _dumps(
        {
            "status": "restored",
            "target": target,
            "path": path,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    )


TOOL = (
    "undo_remote_file",
    UNDO,
    _handle_undo_remote_file,
    _check_remote_available,
    "⏪",
)
