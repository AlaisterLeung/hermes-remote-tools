"""write_remote_file: snapshotted, read-back-verified overwrite."""

from tools.registry import tool_error

from ..schemas import WRITE
from .common import _check_remote_available, _dumps, _premutate, _remote_path, _session
from .remote_pool import TargetError


def _handle_write_remote_file(args: dict, **_) -> str:
    target = str(args.get("target", "")).strip()
    path = str(args.get("path", "")).strip()
    content = args.get("content")
    if not target or not path:
        return tool_error("write_remote_file: both 'target' and 'path' are required.")
    if not isinstance(content, str):
        return tool_error("write_remote_file: 'content' must be a string.")
    try:
        _env, ops = _session(target)
    except TargetError as exc:
        return tool_error(f"write_remote_file: {exc}")
    path = _remote_path(_env, path)
    blocked = _premutate(target, path, ops)
    if blocked:
        return tool_error(blocked)
    written = ops.write_file(path, content)
    if written.error:
        return tool_error(f"write_remote_file: {written.error}")
    return _dumps(
        {"status": "written", "target": target, "path": path, **written.to_dict()}
    )


TOOL = (
    "write_remote_file",
    WRITE,
    _handle_write_remote_file,
    _check_remote_available,
    "✍️",
)
