from collections.abc import Callable

from .remote_tools.patch import TOOL as PATCH
from .remote_tools.read import TOOL as READ
from .remote_tools.search import TOOL as SEARCH
from .remote_tools.terminal import TOOL as TERMINAL
from .remote_tools.undo import TOOL as UNDO
from .remote_tools.write import TOOL as WRITE

TOOLS: list[tuple[str, dict, Callable, Callable, str]] = [
    TERMINAL,
    READ,
    WRITE,
    PATCH,
    SEARCH,
    UNDO,
]
