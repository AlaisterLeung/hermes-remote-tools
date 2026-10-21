"""Bounded before-mutate snapshots for remote files, stored in plugin data.

The core file-mutation verifier and checkpoints cover only the builtin host-local tools, so remote writes sit outside both. This module is the remote equivalent: before any write or patch the current file bytes are stashed under plugin-data, an undo restores them, and every entry is capped and trimmed per path.
"""

import base64
import hashlib
import json
import time
from pathlib import Path

MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024
_KEEP_PER_PATH = 5


class SnapshotStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def _index_path(self, target: str, path: str) -> Path:
        key = hashlib.sha256(f"{target}\0{path}".encode()).hexdigest()[:24]
        return self.root / f"{key}.json"

    def save(self, ops, target: str, path: str) -> str | None:
        """Stash the current remote content of path. Returns the snapshot id, or None when the file does not exist or exceeds the size cap."""
        read = ops.read_file_bytes(path, max_bytes=MAX_SNAPSHOT_BYTES)
        if read.error:
            # missing file is a normal pre-create case; oversize means no undo
            return None
        data = base64.b64decode(read.base64_content or "")
        digest = hashlib.sha256(data).hexdigest()[:16]
        stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
        snap_id = f"{stamp}-{digest}"
        blob_dir = self.root / "blobs"
        blob_dir.mkdir(parents=True, exist_ok=True)
        blob = blob_dir / f"{snap_id}.bin"
        blob.write_bytes(data)
        index_path = self._index_path(target, path)
        entries = self._load(index_path)
        entries.append(
            {
                "id": snap_id,
                "ts": int(time.time()),
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "blob": blob.name,
            }
        )
        entries = entries[-_KEEP_PER_PATH:]
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(
            json.dumps({"target": target, "path": path, "entries": entries})
        )
        return snap_id

    def pop_latest(self, target: str, path: str) -> bytes | None:
        """Return (and remove) the newest snapshot content for one path."""
        index_path = self._index_path(target, path)
        entries = self._load(index_path)
        if not entries:
            return None
        entry = entries.pop()
        blob = self.root / "blobs" / entry["blob"]
        try:
            data = blob.read_bytes()
        except OSError:
            self._write(index_path, target, path, entries)
            return None
        blob.unlink(missing_ok=True)
        self._write(index_path, target, path, entries)
        return data

    def latest_count(self, target: str, path: str) -> int:
        return len(self._load(self._index_path(target, path)))

    def _load(self, index_path: Path) -> list[dict]:
        try:
            payload = json.loads(index_path.read_text())
        except (OSError, ValueError):
            return []
        entries = payload.get("entries", [])
        return entries if isinstance(entries, list) else []

    def _write(
        self, index_path: Path, target: str, path: str, entries: list[dict]
    ) -> None:
        if entries:
            index_path.write_text(
                json.dumps({"target": target, "path": path, "entries": entries})
            )
        else:
            index_path.unlink(missing_ok=True)


_default_store: SnapshotStore | None = None


def default_store() -> SnapshotStore:
    """Store rooted at the plugin's own data dir (never the install dir)."""
    global _default_store
    if _default_store is None:
        from plugins.plugin_storage import plugin_data_dir

        _default_store = SnapshotStore(
            plugin_data_dir("hermes-remote-tools") / "snapshots"
        )
    return _default_store
