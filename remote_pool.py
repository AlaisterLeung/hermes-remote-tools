"""Pool of persistent SSH environments, keyed by a target spec fingerprint.

Each target gets one SSHEnvironment (constructed with `sync_files=False` so ~/.hermes is not mirrored) and one ShellFileOperations wrapper. The fingerprint hashes every connection-relevant field, so a config edit rotates the session instead of reusing old credentials. The pool caps at _POOL_CAP live sessions with LRU eviction, and the evicted session is closed rather than leaked.

A target's 'host' may be a single address or an ordered list of fallbacks: the first address that connects wins, and a pooled session is probed before reuse.
"""

import base64
import hashlib
import json
import logging
import subprocess
import threading
import uuid
from collections import OrderedDict

from tools.environments.remote_common import run_capture
from tools.environments.ssh import SSHEnvironment
from tools.file_operations import ShellFileOperations

logger = logging.getLogger(__name__)

_POOL_CAP = 4

# Multi-host targets dial every candidate and probe the pooled session with a short ConnectTimeout.
# Single-host targets are constructed without the override and keep the core default.
_MULTI_HOST_CONNECT_TIMEOUT = 2

# Login shells that cannot parse POSIX-quoted scripts:
_NON_POSIX_LOGIN_SHELLS = ("fish", "csh", "tcsh")


class _LoginShellSafeSSHEnvironment(SSHEnvironment):
    """SSHEnvironment variant that survives a fish, csh or tcsh login shell.

    sshd runs the remote command through the account's login shell, and the core's multi-line POSIX-quoted bash wrappers do not parse there. The login shell is probed once per session under the class-level _probe_lock; a failed probe keeps the plain core transport, and a shell in _NON_POSIX_LOGIN_SHELLS switches the call to the base64 path.

    On that path the script is encoded onto the command line, decoded into a /tmp file and run with bash, then removes it, so the outer line carries no quoting the login shell could mangle, bash still executes the real script, and stdin stays clear for stdin_data payloads.
    """

    _probe_lock = threading.Lock()

    def __init__(self, *args, connect_timeout: int | None = None, **kwargs):
        self._connect_timeout = connect_timeout
        super().__init__(*args, **kwargs)

    def _run_bash(
        self,
        cmd_string: str,
        *,
        login: bool = False,
        timeout: int = 120,
        stdin_data: str | None = None,
    ):
        if self._needs_base64_transport():
            # Decode the script into a temp file rather than piping it into bash, so bash does not own stdin.
            # The payload stdin_data uses it for file writes.
            script = f"/tmp/.hermes-b64-{uuid.uuid4().hex}.sh"
            payload = base64.b64encode(cmd_string.encode()).decode()
            cmd_string = (
                f"echo {payload} | base64 -d > {script}; "
                f"bash {script}; rc=$?; rm -f {script}; exit $rc"
            )

        return super()._run_bash(
            cmd_string, login=login, timeout=timeout, stdin_data=stdin_data
        )

    def _run_ssh(self, remote_cmd: str, timeout: float) -> subprocess.CompletedProcess:
        """Shorten the connect timeout on the establishment/probe path for multi-host targets.

        Since SSH takes the first obtained value per option, the injected flag precedes the core's hardcoded ConnectTimeout=10.
        Command execution uses _run_bash and keeps the core default.
        """

        cmd = self._build_ssh_command()
        if self._connect_timeout:
            cmd[1:1] = ["-o", f"ConnectTimeout={self._connect_timeout}"]
        return run_capture(cmd + [remote_cmd], timeout=timeout)

    def _needs_base64_transport(self) -> bool:
        if getattr(self, "_b64_probe_done", False):
            return self._b64_needed

        with self._probe_lock:
            if getattr(self, "_b64_probe_done", False):
                return self._b64_needed

            shell = ""
            try:
                proc = self._run_ssh("echo $SHELL", timeout=15)
                if proc.returncode == 0:
                    shell = proc.stdout.strip().rsplit("/", 1)[-1]
            except Exception as exc:
                # Keep the plain path for probe failures
                logger.debug("login-shell probe failed: %s", exc)

            self._b64_needed = shell in _NON_POSIX_LOGIN_SHELLS
            self._b64_probe_done = True
            if self._b64_needed:
                logger.info("ssh target login shell %r: using base64 transport", shell)

            return self._b64_needed


_lock = threading.Lock()
_pool: OrderedDict[str, tuple[SSHEnvironment, ShellFileOperations]] = OrderedDict()


class TargetError(ValueError):
    """Raised when a target name is unknown or its config is malformed."""


def _hosts(cfg: dict) -> list[str]:
    """Ordered candidate hosts for a target: 'host' may be one address or a list tried in order.

    The list form is what makes a machine that lives on multiple networks reachable under one target name: the first address that connects wins.
    """

    raw = cfg.get("host", "")
    if isinstance(raw, (list, tuple)):
        hosts = [str(h).strip() for h in raw]
    else:
        hosts = [str(raw).strip()]

    hosts = [h for h in hosts if h]
    if not hosts:
        raise TargetError("needs at least one non-empty 'host'")

    return hosts


def parse_targets(raw: object) -> dict[str, dict]:
    """Validate the targets mapping from settings. Returns the mapping unchanged when every entry parses. Raises TargetError on invalid configuration."""

    if raw is None or raw == {}:
        return {}

    if not isinstance(raw, dict):
        raise TargetError("'targets' must be a mapping of name -> {host, user, ...}")

    for name, cfg in raw.items():
        if not isinstance(cfg, dict):
            raise TargetError(f"target {name!r} must be a mapping")

        if isinstance(cfg.get("host"), (list, tuple)):
            for entry in cfg["host"]:
                if not isinstance(entry, str) or not entry.strip():
                    raise TargetError(
                        f"target {name!r}: every 'host' list entry must be a non-empty string"
                    )

        for field in ("host", "user"):
            value = cfg.get(field, "")
            if isinstance(value, (list, tuple)):
                if not value:
                    raise TargetError(
                        f"target {name!r} is missing required field {field!r}"
                    )
            elif not str(value).strip():
                raise TargetError(
                    f"target {name!r} is missing required field {field!r}"
                )

    return raw


def resolve_target(targets: dict, name: str) -> dict:
    """Return the validated config for one target name."""

    if not targets:
        raise TargetError(
            "no remote targets configured: add them under plugins.entries.hermes-remote-tools.settings.targets in config.yaml"
        )

    if name not in targets:
        raise TargetError(f"unknown target {name!r}")

    cfg = targets[name]
    if not isinstance(cfg, dict) or not str(cfg.get("user", "")).strip():
        raise TargetError(f"target {name!r} needs at least 'host' and 'user'")

    _hosts(cfg)  # raises TargetError on an empty/blank host list
    return cfg


def fingerprint(name: str, cfg: dict) -> str:
    """Stable short id for the connection-relevant spec of one target."""

    payload = json.dumps(
        [
            name,
            _hosts(cfg),
            cfg.get("user"),
            cfg.get("port"),
            cfg.get("key", ""),
            cfg.get("cwd", "~"),
        ],
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _env_kwargs(cfg: dict, host: str) -> dict:
    """Build SSHEnvironment kwargs with sync_files disabled, so ~/.hermes is not mirrored onto the remote host at session creation."""

    kwargs = {
        "host": host,
        "user": str(cfg["user"]).strip(),
        "port": int(cfg.get("port") or 22),
        "key_path": str(cfg.get("key", "") or ""),
        "cwd": str(cfg.get("cwd", "~") or "~"),
    }
    kwargs["sync_files"] = False
    return kwargs


def _session_alive(env) -> bool:
    """One SSH round trip over the session's own mux socket. A single-host target skips the probe."""

    try:
        proc = env._run_ssh("true", timeout=10)
        return proc.returncode == 0
    except Exception:
        return False


def _drop(key: str, expected: tuple) -> None:
    """Remove one pooled session and close its mux sockets, unless a newer session already took the slot."""

    with _lock:
        if _pool.get(key) is not expected:
            return
        env, _ops = _pool.pop(key)

    try:
        env.cleanup()
    except Exception as exc:
        logger.warning("cleanup of dropped ssh session failed: %s", exc)


def get_session(name: str, cfg: dict) -> tuple[SSHEnvironment, ShellFileOperations]:
    """Return the (env, file ops) session tuple for one target, creating it on first use.

    Candidate hosts are tried in configured order and the first reachable address wins. For multi-host targets, a pooled session is probed before reuse. When the probe fails, it is dropped and the address list is walked again.
    """

    hosts = _hosts(cfg)
    key = fingerprint(name, cfg)
    with _lock:
        hit = _pool.get(key)
        if hit is not None:
            _pool.move_to_end(key)

    if hit is not None:
        if len(hosts) == 1 or _session_alive(hit[0]):
            return hit

        _drop(key, hit)

    failures: list[str] = []
    connect_timeout = _MULTI_HOST_CONNECT_TIMEOUT if len(hosts) > 1 else None
    for host in hosts:
        try:
            env = _LoginShellSafeSSHEnvironment(
                **_env_kwargs(cfg, host), connect_timeout=connect_timeout
            )
        except Exception as exc:
            logger.info(
                "remote target %r: host %s failed to connect (%s)", name, host, exc
            )
            failures.append(f"{host}: {exc}")
            continue

        ops = ShellFileOperations(env)
        with _lock:
            _pool[key] = (env, ops)
            _pool.move_to_end(key)
            while len(_pool) > _POOL_CAP:
                _, (old_env, _) = _pool.popitem(last=False)
                try:
                    old_env.cleanup()
                except Exception as exc:
                    logger.warning("cleanup of evicted ssh session failed: %s", exc)

        return env, ops

    raise TargetError(
        f"target {name!r} is unreachable on every configured host: "
        + "; ".join(failures)
    )


def shutdown() -> None:
    """Clean up all pooled sessions."""

    with _lock:
        sessions = list(_pool.values())
        _pool.clear()

    for env, _ops in sessions:
        try:
            env.cleanup()
        except Exception as exc:
            logger.warning("ssh session cleanup failed: %s", exc)
