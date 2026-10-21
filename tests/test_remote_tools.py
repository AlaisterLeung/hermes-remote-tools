"""Tests for hermes-remote-tools: config handling, guard wiring, snapshot/undo and the tool surface. Handlers run against a fake pool session instead of real SSH."""

import base64
import json
import types

import pytest
from hermes_plugins.hermes_remote_tools import (
    common,
    patch_remote_file,
    remote_config,
    remote_guards,
    remote_pool,
    remote_snapshots,
    terminal_remote,
    undo_remote_file,
    write_remote_file,
)
from hermes_plugins.hermes_remote_tools.remote_tools import TOOLS
from tools.environments.base import EnvironmentConnectionError
from tools.file_operations_common import (
    PatchResult,
    ReadResult,
    WriteResult,
)


class FakeEnv:
    """Minimal stand-in for SSHEnvironment: records commands, decodes undo writes (the real env executes `base64 -d > path` on the remote host)."""

    def __init__(self):
        self.cwd = "~"
        self.commands: list[tuple[str, str]] = []
        self.written: dict[str, bytes] = {}

    def execute(self, command, cwd="", timeout=None, stdin_data=None, **_):
        self.commands.append((command, stdin_data or ""))
        if command.startswith("base64 -d >"):
            path = command.split("> ", 1)[1].strip().strip("'")
            self.written[path] = base64.b64decode(stdin_data or "")
            return {"output": "", "returncode": 0}
        return {"output": "ok", "returncode": 0}

    def cleanup(self):
        pass


class FakeOps:
    """Stand-in for ShellFileOperations with a tiny in-memory fs."""

    def __init__(self):
        self.files: dict[str, bytes] = {}

    def read_file_bytes(self, path, max_bytes=None):
        if path not in self.files:
            return ReadResult(error=f"File not found: {path}")
        data = self.files[path]
        if max_bytes is not None and len(data) > max_bytes:
            return ReadResult(error="File is too large", file_size=len(data))
        return ReadResult(
            base64_content=base64.b64encode(data).decode(),
            file_size=len(data),
            is_binary=True,
        )

    def write_file(self, path, content, pre_content=None):
        self.files[path] = content.encode()
        return WriteResult(bytes_written=len(content), verified=True)

    def patch_replace(self, path, old_string, new_string, replace_all=False):
        text = self.files[path].decode()
        if old_string not in text:
            return PatchResult(success=False, error="old_string not found")
        self.files[path] = text.replace(old_string, new_string).encode()
        return PatchResult(success=True, files_modified=[path])


def _configure(monkeypatch, targets=None):
    monkeypatch.setattr(remote_config, "TARGETS", {} if targets is None else targets)


@pytest.fixture
def patched(monkeypatch, tmp_path):
    """Route the handlers at a fake session + tmp snapshot store."""
    env, ops = FakeEnv(), FakeOps()
    store = remote_snapshots.SnapshotStore(tmp_path / "snaps")
    _configure(monkeypatch, {"devbox": {"host": "h", "user": "u"}})
    monkeypatch.setattr(remote_pool, "get_session", lambda name, cfg: (env, ops))
    monkeypatch.setattr(remote_snapshots, "default_store", lambda: store)
    monkeypatch.setattr(remote_guards, "guard_command", lambda command, target: None)
    return env, ops, store


def test_registration_surface():
    names = [name for name, *_ in TOOLS]
    assert names == [
        "terminal_remote",
        "read_remote_file",
        "write_remote_file",
        "patch_remote_file",
        "search_remote_files",
        "undo_remote_file",
    ]
    for _name, schema, handler, check_fn, _emoji in TOOLS:
        assert schema["name"] == _name
        assert callable(handler) and callable(check_fn)


class FakeCtx:
    """Loader-context stand-in capturing registrations."""

    def __init__(self):
        self.tools = []
        self.skills = []

    def get_config(self, *args):
        return {}

    def on_unload(self, fn):
        pass

    def register_tool(self, **kwargs):
        self.tools.append(kwargs["name"])

    def register_skill(self, name, path, description="", frontmatter=None):
        self.skills.append((name, path, description))


def test_register_registers_the_bundled_skill():
    """The skills/ tree ships with the plugin so other agents use the tools correctly: register() must hand every skills/<name>/SKILL.md to the loader."""
    from hermes_plugins.hermes_remote_tools import register

    ctx = FakeCtx()
    register(ctx)
    assert ctx.tools == [name for name, *_ in TOOLS]
    assert len(ctx.skills) == 1
    name, path, description = ctx.skills[0]
    assert name == "remote-hosts"
    assert path.name == "SKILL.md" and path.is_file()
    assert description


def test_check_remote_available_follows_config(monkeypatch):
    _configure(monkeypatch, {"devbox": {"host": "h", "user": "u"}})
    assert common._check_remote_available() is True
    _configure(monkeypatch, {})
    assert common._check_remote_available() is False


def test_terminal_remote_blocking_guard(monkeypatch, patched):
    monkeypatch.setattr(
        remote_guards,
        "guard_command",
        lambda command, target: {
            "output": "",
            "returncode": -1,
            "status": "blocked",
            "failed": True,
            "error": "denied",
        },
    )
    result = json.loads(
        terminal_remote._handle_terminal_remote(
            {"target": "devbox", "command": "rm -rf /"}
        )
    )
    assert result["status"] == "blocked" and result["failed"] is True


def test_terminal_remote_success_and_failure_flag(patched):
    env, _ops, _store = patched
    ok = json.loads(
        terminal_remote._handle_terminal_remote(
            {"target": "devbox", "command": "hostname"}
        )
    )
    # "failed" is omitted on success: the generic failure detector in core keys on the quoted key name being present in the result text, not its value
    assert ok["returncode"] == 0 and "failed" not in ok and ok["target"] == "devbox"
    env.execute = lambda command, cwd="", timeout=None, **_: {
        "output": "boom",
        "returncode": 2,
    }
    bad = json.loads(
        terminal_remote._handle_terminal_remote(
            {"target": "devbox", "command": "falsy"}
        )
    )
    assert bad["failed"] is True and bad["returncode"] == 2


def test_unknown_target_errors(patched):
    payload = terminal_remote._handle_terminal_remote(
        {"target": "nope", "command": "ls"}
    )
    assert "unknown target" in payload


def test_write_snapshot_and_undo_roundtrip(patched):
    _env, ops, store = patched
    ops.files["/etc/motd"] = b"before"
    written = json.loads(
        write_remote_file._handle_write_remote_file(
            {"target": "devbox", "path": "/etc/motd", "content": "after"}
        )
    )
    assert written["status"] == "written" and written["verified"] is True
    assert store.latest_count("devbox", "/etc/motd") == 1
    undone = json.loads(
        undo_remote_file._handle_undo_remote_file(
            {"target": "devbox", "path": "/etc/motd"}
        )
    )
    assert undone["status"] == "restored" and undone["bytes"] == 6
    assert _env.written["/etc/motd"] == b"before"


def test_write_refuses_oversize_without_snapshot(patched):
    _env, ops, _store = patched
    ops.files["/big"] = b"x" * (remote_snapshots.MAX_SNAPSHOT_BYTES + 1)
    payload = write_remote_file._handle_write_remote_file(
        {"target": "devbox", "path": "/big", "content": "n"}
    )
    assert "refusing to edit" in payload


def test_patch_reports_mutation(patched):
    _env, ops, _store = patched
    ops.files["/etc/motd"] = b"hello world"
    result = json.loads(
        patch_remote_file._handle_patch_remote_file(
            {
                "target": "devbox",
                "path": "/etc/motd",
                "old_string": "hello",
                "new_string": "goodbye",
            }
        )
    )
    assert result["success"] is True and result["mutation_verified"] is True
    assert ops.files["/etc/motd"] == b"goodbye world"


def test_snapshot_store_trims_per_path(tmp_path):
    store = remote_snapshots.SnapshotStore(tmp_path / "snaps")

    class StubOps:
        def __init__(self, blob):
            self.blob = blob

        def read_file_bytes(self, path, max_bytes=None):
            data = base64.b64encode(self.blob).decode()
            return ReadResult(base64_content=data, file_size=len(self.blob))

    for round_no in range(8):
        store.save(StubOps(f"content-{round_no}".encode()), "t", "/p")
    assert store.latest_count("t", "/p") == remote_snapshots._KEEP_PER_PATH


def test_pool_parse_and_fingerprint():
    targets = remote_pool.parse_targets({"devbox": {"host": "h", "user": "u"}})
    assert "devbox" in targets
    with pytest.raises(remote_pool.TargetError):
        remote_pool.parse_targets({"bad": {"user": "x"}})
    with pytest.raises(remote_pool.TargetError):
        remote_pool.parse_targets("nope")
    cfg = {"host": "h", "user": "u", "port": 22}
    assert remote_pool.fingerprint("devbox", cfg) == remote_pool.fingerprint(
        "devbox", dict(cfg)
    )
    assert remote_pool.fingerprint("devbox", cfg) != remote_pool.fingerprint(
        "other", cfg
    )


def test_parse_targets_accepts_host_fallback_list():
    cfg = {"dual": {"host": ["10.0.0.1", "10.0.0.2"], "user": "u"}}
    assert remote_pool.parse_targets(cfg) is cfg
    with pytest.raises(remote_pool.TargetError):
        remote_pool.parse_targets({"dual": {"host": [], "user": "u"}})
    with pytest.raises(remote_pool.TargetError):
        remote_pool.parse_targets({"dual": {"host": ["10.0.0.1", ""], "user": "u"}})
    with pytest.raises(remote_pool.TargetError):
        remote_pool.parse_targets({"dual": {"host": [10, 20], "user": "u"}})
    assert remote_pool._hosts({"host": ["a", " b "]}) == ["a", "b"]
    assert remote_pool._hosts({"host": "a"}) == ["a"]
    with pytest.raises(remote_pool.TargetError):
        remote_pool.resolve_target({"dual": {"host": [], "user": "u"}}, "dual")


def test_fingerprint_covers_the_whole_host_list():
    cfg = {"host": ["10.0.0.1", "10.0.0.2"], "user": "u", "port": 22}
    assert remote_pool.fingerprint("devbox", cfg) == remote_pool.fingerprint(
        "devbox", dict(cfg)
    )
    assert remote_pool.fingerprint("devbox", cfg) != remote_pool.fingerprint(
        "devbox", {"host": "10.0.0.1", "user": "u", "port": 22}
    )


class FakeSSH:
    """SSHEnvironment stand-in whose reachability is per-host and per-instance."""

    dead_hosts: set[str] = set()

    def __init__(
        self,
        host="",
        user="",
        cwd="~",
        timeout=60,
        port=22,
        key_path="",
        probe_only=False,
        sync_files=True,
        connect_timeout=None,
        **_,
    ):
        if host in FakeSSH.dead_hosts:
            raise EnvironmentConnectionError(f"cannot reach {host}")
        self.host = host
        self.alive = True
        self.probes = 0
        self.connect_timeout = connect_timeout

    def _run_ssh(self, remote_cmd, timeout=None):
        self.probes += 1
        return types.SimpleNamespace(returncode=0 if self.alive else 255)

    def cleanup(self):
        pass


@pytest.fixture
def fake_pool(monkeypatch):
    """Route session creation at FakeSSH and keep the real pool empty per test."""
    remote_pool._pool.clear()
    FakeSSH.dead_hosts = set()
    monkeypatch.setattr(remote_pool, "_LoginShellSafeSSHEnvironment", FakeSSH)
    monkeypatch.setattr(
        remote_pool, "ShellFileOperations", lambda env: ("ops", env.host)
    )
    yield
    remote_pool._pool.clear()


def test_get_session_falls_back_to_next_host(monkeypatch, fake_pool):
    FakeSSH.dead_hosts = {"10.0.0.1"}
    env, _ops = remote_pool.get_session(
        "dual", {"host": ["10.0.0.1", "10.0.0.2"], "user": "u"}
    )
    assert env.host == "10.0.0.2"


def test_get_session_probes_and_fails_over_after_a_move(monkeypatch, fake_pool):
    cfg = {"host": ["10.0.0.1", "10.0.0.2"], "user": "u"}
    env1, _ops = remote_pool.get_session("dual", cfg)
    assert env1.host == "10.0.0.1" and env1.probes == 0
    env1.alive = False  # the machine moved to the other network
    FakeSSH.dead_hosts = {"10.0.0.1"}  # the LAN address no longer answers
    env2, _ops = remote_pool.get_session("dual", cfg)
    assert env2 is not env1 and env2.host == "10.0.0.2"


def test_get_session_single_host_skips_the_probe(monkeypatch, fake_pool):
    cfg = {"host": "10.0.0.1", "user": "u"}
    env1, _ops = remote_pool.get_session("solo", cfg)
    env1.alive = False
    env2, _ops = remote_pool.get_session("solo", cfg)
    assert env2 is env1 and env2.probes == 0


def test_get_session_reports_every_dead_host(monkeypatch, fake_pool):
    FakeSSH.dead_hosts = {"10.0.0.1", "10.0.0.2"}
    with pytest.raises(remote_pool.TargetError) as exc:
        remote_pool.get_session("dual", {"host": ["10.0.0.1", "10.0.0.2"], "user": "u"})
    assert "10.0.0.1" in str(exc.value) and "10.0.0.2" in str(exc.value)


def test_multi_host_targets_dial_with_the_short_connect_timeout(monkeypatch, fake_pool):
    env, _ops = remote_pool.get_session(
        "dual", {"host": ["10.0.0.1", "10.18.0.2"], "user": "u"}
    )
    assert env.connect_timeout == 2


def test_single_host_targets_keep_the_core_connect_timeout(monkeypatch, fake_pool):
    env, _ops = remote_pool.get_session("solo", {"host": "10.0.0.1", "user": "u"})
    assert env.connect_timeout is None


def _capture_run_ssh(monkeypatch, connect_timeout):
    """Drive _run_ssh with a stubbed argv builder and capture what reaches run_capture."""
    env = object.__new__(remote_pool._LoginShellSafeSSHEnvironment)
    env._connect_timeout = connect_timeout
    monkeypatch.setattr(
        remote_pool._LoginShellSafeSSHEnvironment,
        "_build_ssh_command",
        lambda self: [
            "ssh",
            "-o",
            "ControlMaster=auto",
            "-o",
            "ConnectTimeout=10",
            "u@h",
        ],
    )
    seen: list[tuple[list[str], float]] = []
    monkeypatch.setattr(
        remote_pool,
        "run_capture",
        lambda cmd, timeout: seen.append((cmd, timeout)) or None,
    )
    env._run_ssh("true", 10)
    return seen[0]


def test_run_ssh_injects_short_connect_timeout_before_the_core_default(monkeypatch):
    """SSH takes the first obtained value per option, so the injected ConnectTimeout must precede the core's hardcoded ConnectTimeout=10 in the argv or it is ignored."""
    cmd, timeout = _capture_run_ssh(monkeypatch, 2)
    assert cmd[1:3] == ["-o", "ConnectTimeout=2"]
    assert cmd.index("ConnectTimeout=2") < cmd.index("ConnectTimeout=10")
    assert cmd[-1] == "true" and timeout == 10


def test_run_ssh_keeps_the_core_timeout_without_an_override(monkeypatch):
    cmd, _timeout = _capture_run_ssh(monkeypatch, None)
    assert cmd == [
        "ssh",
        "-o",
        "ControlMaster=auto",
        "-o",
        "ConnectTimeout=10",
        "u@h",
        "true",
    ]


def test_env_kwargs_disables_sync_files_on_real_core():
    """SSHEnvironment.__init__ exposes sync_files with a True default, which mirrors the local ~/.hermes (skills + cache) onto the remote host at session creation. _env_kwargs passes sync_files=False to disable this behavior."""
    kwargs = remote_pool._env_kwargs({"host": "h", "user": "u"}, "h")
    assert kwargs.get("sync_files") is False
