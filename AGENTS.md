# hermes-remote-tools

Standalone Hermes plugin: remote execution tools for ssh hosts configured in the plugin settings. The tools load at gateway startup and stay opt-in through the `remote_tools` toolset.

## Layout

- `__init__.py` - loader entry; module-level wiring imports per the official plugins' style (the loader and tests/conftest.py both import this file as a proper package); `register(ctx)` sets the config getter, unload hook, then registers tools + skills
- `remote_tools.py` - the TOOLS registration table: one entry per tool module; register() wires them into the plugin toolset
- `schemas.py` - tool schemas only (docs-layout root: the model-facing surface reviewable apart from handler code)
- one handler-only module per tool, named for the tool: `terminal_remote.py`, `read_remote_file.py`, `write_remote_file.py`, `patch_remote_file.py`, `search_remote_files.py`, `undo_remote_file.py`
- `common.py` - shared handler helpers: target resolution, session access, tilde expansion, pre-mutate snapshot guard
- `remote_config.py` - the targets mapping, captured once at register(); config edits take effect on restart, and tests patch the module's TARGETS
- `remote_pool.py` - persistent SSHEnvironment pool keyed by spec fingerprint
- `remote_guards.py` - approval guard wiring (core `tools/approval.py`)
- `remote_snapshots.py` - bounded before-mutate snapshots + undo
- `skills/` - one skill per directory (`skills/<name>/SKILL.md`), registered by `register()` through `ctx.register_skill` under the plugin's namespace; `_SKILLS` in `__init__.py` supplies the registered name and index description, so agents using these tools load the usage + pitfalls guidance
- `tests/` + `tests/conftest.py` (registers the plugin root as the importable package `hermes_plugins.hermes_remote_tools` in sys.modules - the exact namespace the loader derives for this manifest - so relative imports across the flat modules resolve; also scrubs the plugin root from sys.path, removal-only, and gives every test a throwaway `HERMES_HOME`)
- `pyrightconfig.json` - editor/LSP import resolution; the paths are relative to the repo and assume the standard install layout (plugin at `~/.hermes/plugins/hermes-remote-tools`, hermes checkout at `~/.hermes/hermes-agent`), so adjust them when the plugin lives elsewhere

## Conventions

- Python 3.13 typing: `dict`, `X | None`; no `Dict`/`Optional`.
- No `from __future__ import annotations` - 3.13+ only, unneeded; keep forward refs out instead.
- No em dashes; use hyphens.
- Lowercase `remote`/`target` in strings and comments.
- No hard-wrapped lines in comments, docstrings, or Markdown prose: write flowing lines (one sentence or paragraph per line) and let the renderer wrap; hard line breaks stay only where they are structural (code blocks, YAML, bullets).
- Short comments; no references to uncommitted files.
- Run `ruff format` + `ruff check` before done.

## Versioning

Two version numbers on two axes, never re-aligned: `plugin.yaml` `version` is the release (what `plugins list`, `plugins doctor` and the catalog pin report), while `skills/<name>/SKILL.md` frontmatter `version` is that document's own history, bumped only when its instructions change. A skill at 1.1.1 inside a plugin at 1.0.1 is correct; never lower a skill version to match the plugin.

The skill index is not read from SKILL.md: `_SKILLS` in `__init__.py` supplies the name and description for `<available_skills>` and `skills_list`, so a description edit needs the `_SKILLS` update plus a gateway restart, while `version` never reaches the index at all. No test pins the `_SKILLS` set to the disk any more, so keep it in lockstep by hand: add, rename or drop an entry in step with `skills/<name>/`, and keep the entry's name and description matching the SKILL.md frontmatter.

## Core seams this plugin leans on (coupling map)

- `tools/environments/ssh.py::SSHEnvironment` - connection + exec; the plugin always constructs it with `sync_files=False` (its True default mirrors the local ~/.hermes skills + cache onto the remote host at session creation), because self-managed remote hosts keep their own ~/.hermes. The plugin pins hermes-agent >= 0.22.0, which always exposes the switch, so it passes it unconditionally.
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
PYTHONPATH=~/.hermes/hermes-agent ~/.hermes/hermes-agent/venv/bin/pytest
<hermes venv>/bin/ruff format . && <hermes venv>/bin/ruff check .
uvx pyright
hermes plugins doctor hermes-remote-tools
```

The `PYTHONPATH` is mandatory: conftest imports the plugin package at collection time and its modules import core (`tools.environments.ssh` and friends), so collection fails at import without the tree on sys.path. `HERMES_HOME` needs no shell setup: the conftest autouse fixture gives every test a throwaway profile home. Run `hermes plugins validate <abs path>` with an absolute path; validating from inside the plugin root also works (the flat layout no longer ships a root `tools.py` to shadow the core `tools` package), but the absolute-path form stays the habit so root-level module names like `common.py` can never shadow core.

The conftest scrubs the plugin root from sys.path (removal-only), so even `python -m pytest` cannot leak root-level `common.py`/`schemas.py` into core imports. Outside pytest, avoid running python with the plugin root as cwd for the same reason.

No test talks to a real ssh host; handlers are exercised with a fake env.
