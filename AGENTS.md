# hermes-remote-tools

Standalone Hermes plugin: remote execution tools for ssh hosts configured in the plugin settings. The tools load at gateway startup and stay opt-in through the `remote_tools` toolset.

## Layout

- `__init__.py` - loader entry; lazy `register(ctx)` wiring schemas + handlers (module-level relative imports here would break pytest collection, which imports this file)
- `tools.py` - the TOOLS registration table: aggregates one TOOL entry per tool module below; register() wires them into the plugin toolset
- `schemas.py` - tool schemas only (docs-layout root: the model-facing surface reviewable apart from handler code)
- `remote_tools/` - the implementation package
  - `common.py` - shared handler helpers: target resolution, session access, tilde expansion, pre-mutate snapshot guard
  - `terminal.py`, `read.py`, `write.py`, `patch.py`, `search.py`, `undo.py` - one handler + TOOL entry per tool
  - `plugin_state.py` - config getter indirection (tests patch it without executing the loader entry)
  - `remote_pool.py` - persistent SSHEnvironment pool keyed by spec fingerprint
  - `remote_guards.py` - approval guard wiring (core `tools/approval.py`)
  - `remote_snapshots.py` - bounded before-mutate snapshots + undo
- `skills/` - one skill per directory (`skills/<name>/SKILL.md`), registered by `register()` through `ctx.register_skill` under the plugin's namespace, so agents using these tools load the usage + pitfalls guidance
- `tests/` + `tests/conftest.py` (registers the plugin root as the importable package `hermes_plugins.hermes_remote_tools` in sys.modules - the exact namespace the loader derives for this manifest - so `from ..schemas import` in the subpackage resolves; pure sys.modules registration, sys.path is never touched)
- `pyrightconfig.json` - editor/LSP import resolution; the paths are relative to the repo and assume the standard install layout (plugin at `~/.hermes/plugins/hermes-remote-tools`, hermes checkout at `~/.hermes/hermes-agent`), so adjust them when the plugin lives elsewhere

## Conventions

- Python 3.13 typing: `dict`, `X | None`; no `Dict`/`Optional`.
- No `from __future__ import annotations` - 3.13+ only, unneeded; keep forward refs out instead.
- No em dashes; use hyphens.
- Lowercase `remote`/`target` in strings and comments.
- No hard-wrapped lines in comments, docstrings, or Markdown prose: write flowing lines (one sentence or paragraph per line) and let the renderer wrap; hard line breaks stay only where they are structural (code blocks, YAML, bullets).
- Short comments; no references to uncommitted files.
- Run `ruff format` + `ruff check` before done.

## Core seams this plugin leans on (coupling map)

- `tools/environments/ssh.py::SSHEnvironment` - connection + exec; the plugin always passes the file-sync switch off (`sync_files`; its True default mirrors the local ~/.hermes skills + cache onto the remote host at session creation, older cores spelled it `file_sync`), because self-managed remote hosts keep their own ~/.hermes. The guard in `remote_pool._env_kwargs` matches the parameter name from the signature, so a core that renames or drops the switch stays tolerated.
- `tools/environments/remote_common.py::run_capture` - the one-shot ssh dial helper behind the login-shell probe and the multi-host alive probe.
- `tools/file_operations.py::ShellFileOperations` - wraps ANY env exposing `execute(command, cwd)`; gives read/write/patch/search with core logic (fuzzy patch, atomic write, sha256 verification).
- `tools/approval.py::check_all_command_guards` - the exact guard entry the builtin terminal uses; approvals and guardrails behave identically.
- `tools/process_registry.py::process_registry.spawn_via_env` - background sessions so notifications, process_manage and teardown reaping apply.
- `tools/registry.py::tool_error` - the standard refusal-response helper every handler returns on error.
- `tools/terminal_tool_background.py::_stamp_routing_if_gateway` + `gateway/session_context.py::get_session_env` - best-effort gateway routing parity for background spawns; a failure there never blocks the spawn.
- `plugins/plugin_storage.plugin_data_dir` - snapshot storage root.

These are semi-private core internals. If a core refactor breaks an import, the plugin fails visibly at tool call time - fix the import, do not shim.

## Tests

```bash
HERMES_HOME=$(mktemp -d) PYTHONPATH=<hermes-agent source tree> \
  <hermes venv>/bin/pytest tests/ -o 'addopts=' -q
```

Run the venv pytest BINARY, never `python -m pytest` from the plugin root: `python -m` puts the cwd on sys.path, and the root tools.py would shadow the core hermes tools package (bare `import tools` inside the plugin must resolve to the core tree).

No test talks to a real ssh host; handlers are exercised with a fake env.
