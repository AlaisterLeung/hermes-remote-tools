# hermes-remote-tools

A Hermes plugin that adds terminal and file operation tools for configured remote SSH hosts. Remote tools reuse the built-in approval stack, process registry, and file-operations layer, with write verification and per-file snapshots on top.

Verified compatible Hermes Agent stable versions: v0.22.0 - v0.22.2

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

Then add at least one host to config.yaml (see below), restart the gateway, and enable the `remote_tools` toolset:

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

A machine reachable on more than one network (say, a home LAN plus a VPN) takes a list of addresses in `host`, tried in order with a 2s timeout:

```yaml
laptop:
    host:
        - 192.0.2.101 # home LAN
        - 198.51.100.10 # VPN
    user: alaister
    key: ~/.ssh/laptop
```

## Development

Run the tests against a throwaway `HERMES_HOME` with the hermes-agent source tree on `PYTHONPATH`:

```bash
HERMES_HOME=$(mktemp -d) PYTHONPATH=<hermes_source> \
  <hermes venv>/bin/pytest tests/ -o 'addopts=' -q
```

Run the venv pytest binary. Tests run against a fake environment, not real ssh hosts. Beware that you shouldn't run `python -m pytest` from the plugin root since `python -m` puts the cwd on `sys.path` such that the root `tools.py` would shadow the core hermes `tools` package the plugin imports.

Format, lint, and typecheck before committing:

```bash
<hermes_venv>/bin/ruff format .
<hermes_venv>/bin/ruff check .
uvx pyright
```

### Technical Notes

- With `background=true` the terminal process joins the core process registry for completion notifications and standard process management.
- Snapshots are stored under `<HERMES_HOME>/plugin-data/hermes-remote-tools/snapshots`, capped at 2 MiB per file and 5 kept per path. A file too large to snapshot is not edited at all, rather than mutated without an undo point.
- `~/.hermes` is never mirrored to a remote host as `sync_files` is always disabled.
- Remote commands run under bash even when the remote login shell is fish, csh or tcsh. On those hosts the plugin base64-wraps the script through the command line, so the login shell never parses it.
- Upstream file-mutation verifier and checkpoints cover only the builtin host-local tools, so remote writes are instead covered by a before-mutate snapshot plus a read-back hash verification after the write.
- Terminal results carry `failed: true` only on a nonzero exit while a success omits the key. Since the failure detector from upstream scans the result text for the key name, not its value, so `"failed": false` on a success payload would be misread as an error.
