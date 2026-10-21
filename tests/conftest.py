"""Test bootstrap, mirroring the official plugins' conftest: register the plugin root as the importable package hermes_plugins.hermes_remote_tools, the exact namespace the plugin loader derives for this manifest (hermes_cli/plugins_loader.py `_directory_module_name`), so the modules' relative imports resolve.

Also scrubs the plugin root from sys.path (removal-only, so `python -m pytest` from the plugin root cannot put common.py/schemas.py over core packages) and gives every test a throwaway HERMES_HOME, so the snapshot store roots at the plugin's data dir under the temp profile instead of the live one."""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_NAMESPACE = "hermes_plugins"
_PACKAGE = f"{_NAMESPACE}.hermes_remote_tools"

# `python -m pytest` from the plugin root puts the root on sys.path, where this plugin's
# module names (common.py, schemas.py) could shadow core packages when core is imported.
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != _ROOT]

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


@pytest.fixture(autouse=True)
def _hermes_home(tmp_path, monkeypatch):
    """Every test gets its own profile home: plugin data (snapshots) land there, never in the live one."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    (tmp_path / "hermes").mkdir()


class _RepoRootIsNotATestPackage:
    """The plugin root is a package (it has an __init__.py with relative imports), so pytest would collect it as a test Package and import that __init__.py standalone during setup, where the relative imports cannot resolve. Collect the root as a plain directory instead.

    Registered as a global plugin (not a conftest hook) because the root directory's collector is created through its parent's hook proxy, which never sees a conftest inside the root."""

    @pytest.hookimpl(tryfirst=True)
    def pytest_collect_directory(self, path, parent):
        if Path(path).resolve() == _ROOT:
            return pytest.Dir.from_parent(parent, path=path)
        return None


def pytest_configure(config):
    if not config.pluginmanager.has_plugin("hermes-remote-tools-repo-root"):
        config.pluginmanager.register(
            _RepoRootIsNotATestPackage(), "hermes-remote-tools-repo-root"
        )
