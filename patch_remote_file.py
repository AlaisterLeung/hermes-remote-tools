"""patch_remote_file: fuzzy find-and-replace with a pre-edit snapshot."""

from tools.registry import tool_error

from .common import _dumps, _premutate, _remote_path, _session
from .remote_pool import TargetError


def _handle_patch_remote_file(args: dict, **_) -> str:
    target = str(args.get("target", "")).strip()
    path = str(args.get("path", "")).strip()
    if not target or not path:
        return tool_error("patch_remote_file: both 'target' and 'path' are required.")

    old_string = args.get("old_string")
    new_string = args.get("new_string")
    if not isinstance(old_string, str) or not isinstance(new_string, str):
        return tool_error(
            "patch_remote_file: 'old_string' and 'new_string' must be strings."
        )

    try:
        _env, ops = _session(target)
    except TargetError as exc:
        return tool_error(f"patch_remote_file: {exc}")

    path = _remote_path(_env, path)
    blocked = _premutate(target, path, ops)
    if blocked:
        return tool_error(blocked)

    patched = ops.patch_replace(
        path, old_string, new_string, replace_all=bool(args.get("replace_all", False))
    )
    if patched.error:
        return tool_error(f"patch_remote_file: {patched.error}")

    return _dumps(
        {
            "status": "patched",
            "target": target,
            "path": path,
            "mutation_verified": bool(patched.files_modified or patched.files_created),
            **patched.to_dict(),
        }
    )
