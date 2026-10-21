"""Remote tools registration table. ``register()`` wires them into the plugin toolset."""

from collections.abc import Callable

from .common import _check_remote_available
from .patch_remote_file import _handle_patch_remote_file
from .read_remote_file import _handle_read_remote_file
from .schemas import PATCH, READ, SEARCH, TERMINAL, UNDO, WRITE
from .search_remote_files import _handle_search_remote_files
from .terminal_remote import _handle_terminal_remote
from .undo_remote_file import _handle_undo_remote_file
from .write_remote_file import _handle_write_remote_file

TOOLS: list[tuple[str, dict, Callable, Callable, str]] = [
    (
        "terminal_remote",
        TERMINAL,
        _handle_terminal_remote,
        _check_remote_available,
        "🖥️",
    ),
    ("read_remote_file", READ, _handle_read_remote_file, _check_remote_available, "📖"),
    (
        "write_remote_file",
        WRITE,
        _handle_write_remote_file,
        _check_remote_available,
        "✍️",
    ),
    (
        "patch_remote_file",
        PATCH,
        _handle_patch_remote_file,
        _check_remote_available,
        "🔧",
    ),
    (
        "search_remote_files",
        SEARCH,
        _handle_search_remote_files,
        _check_remote_available,
        "🔎",
    ),
    ("undo_remote_file", UNDO, _handle_undo_remote_file, _check_remote_available, "⏪"),
]
