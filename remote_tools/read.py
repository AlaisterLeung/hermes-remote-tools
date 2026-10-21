"""read_remote_file: paginated text read via core ShellFileOperations."""

from tools.registry import tool_error

from ..schemas import READ
from .common import _check_remote_available, _remote_path, _session
from .remote_pool import TargetError


def _handle_read_remote_file(args: dict, **_) -> str:
    target = str(args.get("target", "")).strip()
    path = str(args.get("path", "")).strip()
    if not target or not path:
        return tool_error("read_remote_file: both 'target' and 'path' are required.")
    try:
        _env, ops = _session(target)
    except TargetError as exc:
        return tool_error(f"read_remote_file: {exc}")
    read = ops.read_file(
        _remote_path(_env, path),
        offset=int(args.get("offset") or 1),
        limit=int(args.get("limit") or 2000),
    )
    if read.error:
        return tool_error(f"read_remote_file: {read.error}")
    return read.content


TOOL = (
    "read_remote_file",
    READ,
    _handle_read_remote_file,
    _check_remote_available,
    "📖",
)
