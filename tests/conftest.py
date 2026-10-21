"""Register the plugin root as the importable package hermes_plugins.hermes_remote_tools, the exact namespace the plugin loader derives for this manifest (hermes_cli/plugins_loader.py `_directory_module_name`), so the subpackage's relative imports (from ..schemas import ...) resolve under pytest. Pure sys.modules registration: sys.path is never touched, so the core hermes tools package keeps winning bare `import tools`."""

import importlib.util
import sys
import types
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_NAMESPACE = "hermes_plugins"
_PACKAGE = f"{_NAMESPACE}.hermes_remote_tools"

if _PACKAGE not in sys.modules:
    if _NAMESPACE not in sys.modules:
        _ns = types.ModuleType(_NAMESPACE)
        _ns.__path__ = []
        _ns.__package__ = _NAMESPACE
        sys.modules[_NAMESPACE] = _ns
    _spec = importlib.util.spec_from_file_location(
        _PACKAGE,
        _ROOT / "__init__.py",
        submodule_search_locations=[str(_ROOT)],
    )
    if _spec is None or _spec.loader is None:
        raise ImportError(f"Cannot create module spec for {_ROOT / '__init__.py'}")
    _pkg = importlib.util.module_from_spec(_spec)
    sys.modules[_PACKAGE] = _pkg
    _spec.loader.exec_module(_pkg)
