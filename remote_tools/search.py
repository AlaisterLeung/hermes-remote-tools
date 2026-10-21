"""search_remote_files: regex/glob search via core ShellFileOperations."""

from tools.registry import tool_error

from ..schemas import SEARCH
from .common import _check_remote_available, _dumps, _remote_path, _session
from .remote_pool import TargetError


def _handle_search_remote_files(args: dict, **_) -> str:
    target = str(args.get("target", "")).strip()
    pattern = str(args.get("pattern", "")).strip()
    if not target or not pattern:
        return tool_error(
            "search_remote_files: both 'target' and 'pattern' are required."
        )
    try:
        _env, ops = _session(target)
    except TargetError as exc:
        return tool_error(f"search_remote_files: {exc}")
    found = ops.search(
        pattern,
        path=_remote_path(_env, str(args.get("path", ".") or ".")),
        target=str(args.get("mode", "content") or "content"),
        file_glob=args.get("file_glob") or None,
        limit=int(args.get("limit") or 50),
    )
    if found.error:
        return tool_error(f"search_remote_files: {found.error}")
    matches = [
        {"path": m.path, "line": m.line_number, "text": m.content}
        for m in found.matches
    ]
    return _dumps(
        {
            "matches": matches,
            "files": found.files,
            "total_count": found.total_count,
            "truncated": found.truncated,
        }
    )


TOOL = (
    "search_remote_files",
    SEARCH,
    _handle_search_remote_files,
    _check_remote_available,
    "🔎",
)
