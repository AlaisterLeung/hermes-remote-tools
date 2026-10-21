# hermes-remote-tools

A Hermes plugin that adds terminal and file operation tools for configured remote SSH hosts. Remote tools reuse the built-in approval stack, process registry, and file-operations layer, with write verification and per-file snapshots on top.

Verified compatible Hermes Agent versions: v0.22.0 - v0.22.2

## Remote Tools

| Remote Tool           | What it does                                                                          |
| --------------------- | ------------------------------------------------------------------------------------- |
| `terminal_remote`     | Run a shell command remotely under the same approval stack as the builtin terminal    |
| `read_remote_file`    | Read a remote file with pagination and line numbers                                   |
| `write_remote_file`   | Create or overwrite a remote file with a pre-edit snapshot and read-back verification |
| `patch_remote_file`   | Fuzzy find-and-replace on a remote file with a pre-edit snapshot                      |
| `search_remote_files` | Search remote files by regex or glob                                                  |
| `undo_remote_file`    | Restore the previous content of a remote file from its snapshot                       |

## Get Started

Install from Git using CLI:

```bash
hermes plugins install AlaisterLeung/hermes-remote-tools --enable
```

Then add at least one host to config.yaml (see Configuration below), restart the gateway, and enable the `remote_tools` toolset:

- run `hermes tools` and pick it in the configurator;
- or add `remote_tools` to the `platform_toolsets` list for each platform that should get the tools.

Verify with `hermes plugins doctor hermes-remote-tools` afterwards:

```
OK: runtime discovery, manifest parsing, import, and registration passed
registrations: 6 tool(s), 0 hook(s)
```

### Configuration

```yaml
plugins:
    entries:
        hermes-remote-tools:
            settings:
                targets:
                    devbox:
                        host: 1.2.3.4
                        user: alaister
                        port: 22
                        key: ~/.ssh/path-to-devbox-key
                        cwd: "~"
                    cloud:
                        host: 5.6.7.8
                        user: leung
                        port: 22
                        key: ~/.ssh/path-to-cloud-key
                        cwd: "~"
```

#### Multiple addresses per host

A machine reachable on more than one network (say, a home LAN plus a VPN) takes a list of addresses in `host`, tried in order with a 2s timeout. Example:

```yaml
laptop:
    host:
        - 192.0.2.101
        - 198.51.100.10
        - 10.10.100.67
    user: alaister
    key: ~/.ssh/laptop
```

## Development

### Unit testing

Tests run against a fake environment, not real SSH hosts. Provide the hermes-agent source in `PYTHONPATH` since the plugin imports modules from the core.

```bash
PYTHONPATH=~/.hermes/hermes-agent ~/.hermes/hermes-agent/venv/bin/pytest
```

### Format, lint, and typecheck

```bash
export HERMES_VENV=~/.hermes/hermes-agent/venv
$HERMES_VENV/bin/ruff format .
$HERMES_VENV/bin/ruff check .
uvx pyright
```

### Technical notes

- Background execution is supported with `background=true` in which the terminal process joins the process registry for completion notifications and standard process management.
- Snapshots are stored under `$HERMES_HOME/plugin-data/hermes-remote-tools/snapshots`, capped at 2 MiB per file and 5 snapshots per path. A file too large for snapshot will not be edited at all.
- `~/.hermes` is not mirrored to a remote host as `sync_files` is always disabled.
- Remote commands run under bash regardless of the login shell. On non-bash hosts, the plugin wraps the script with base64 through the command line, so the login shell does not parse it.
- Since the core file-mutation verifier and checkpoints cover only the builtin host-local tools, remote file writes are instead covered by a before-mutate snapshot plus a read-back hash verification after the write.
- Terminal tool results carry `failed: true` only on a non-zero exit while a success omits the key. This is because `"failed": false` on a success payload would be misread as an error.
