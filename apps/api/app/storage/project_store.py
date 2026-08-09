"""Paper-diff-specific storage facade built on the generic FileStore port."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

from app.domain.text_file import decode_text_bytes, slice_text_lines, text_line_count, text_sha256
from app.storage.errors import StorageConflict, StorageNotFound
from app.storage.layout import ProjectLayout
from app.storage.ports import FileStore
from app.storage.types import MISSING_VERSION, FileInfo, FileKind, StorageScope, TreeRef


def default_project_meta(project_id: str) -> dict:
    return {
        "id": project_id,
        "status": "empty",
        "root_file": None,
        "revisions": {},
        "accept_log": [],
        "model": "v2",
        "active_zone_id": None,
    }


class ProjectStorage:
    """All persistent project access through logical tree/resource references."""

    def __init__(self, store: FileStore, scope: StorageScope):
        self.store = store
        self.scope = scope
        self.layout = ProjectLayout(scope)

    def exists(self) -> bool:
        return self.store.stat(self.layout.meta) is not None

    def ensure_layout(self) -> None:
        for prefix in (
            self.layout.project,
            self.layout.tree(TreeRef.work()),
            self.layout.zones,
            self.layout.tree(TreeRef.base()),
            self.layout.tree(TreeRef.revised()),
            self.layout.snapshots,
        ):
            self.store.ensure_prefix(prefix)

    def ensure_zone(self, zone_id: str) -> None:
        self.store.ensure_prefix(self.layout.zone_root(zone_id))
        self.store.ensure_prefix(self.layout.tree(TreeRef.zone(zone_id)))

    def list_zone_ids(self) -> list[str]:
        ids: set[str] = set()
        for info in self.store.list(self.layout.zones, recursive=True):
            if info.kind != FileKind.FILE:
                continue
            rel = info.key.relative_to(self.layout.zones)
            parts = rel.split("/")
            if len(parts) == 2 and parts[1] == "meta.json":
                ids.add(parts[0])
        return sorted(ids)

    def list_files(self, tree: TreeRef) -> list[str]:
        prefix = self.layout.tree(tree)
        files = [
            info.key.relative_to(prefix)
            for info in self.store.list(prefix, recursive=True)
            if info.kind == FileKind.FILE
        ]
        return sorted(path for path in files if path)

    def stat_file(self, tree: TreeRef, rel_path: str) -> FileInfo | None:
        return self.store.stat(self.layout.file(tree, rel_path))

    def read_bytes(self, tree: TreeRef, rel_path: str) -> bytes:
        return self.store.read_bytes(self.layout.file(tree, rel_path))

    def write_bytes(self, tree: TreeRef, rel_path: str, data: bytes) -> FileInfo:
        return self.store.write_bytes(self.layout.file(tree, rel_path), data)

    def read_text(self, tree: TreeRef, rel_path: str) -> str:
        return decode_text_bytes(self.read_bytes(tree, rel_path))[0]

    def write_text(self, tree: TreeRef, rel_path: str, content: str) -> FileInfo:
        return self.write_bytes(tree, rel_path, content.encode("utf-8"))

    def delete_file(self, tree: TreeRef, rel_path: str) -> None:
        self.store.delete(self.layout.file(tree, rel_path))

    def file_meta(self, tree: TreeRef, rel_path: str) -> dict:
        raw = self.read_bytes(tree, rel_path)
        content, encoding = decode_text_bytes(raw)
        return {
            "path": rel_path,
            "byte_size": len(raw),
            "line_count": text_line_count(content),
            "encoding": encoding,
            "sha256": text_sha256(content),
        }

    def file_slice(
        self,
        tree: TreeRef,
        rel_path: str,
        start_line: int,
        end_line: int,
        max_lines: int,
    ) -> dict:
        content = self.read_text(tree, rel_path)
        sliced = slice_text_lines(content, start_line, end_line, max_lines)
        return {"path": rel_path, **sliced}

    def write_snapshot(self, name: str, data: bytes) -> FileInfo:
        """Persist an opaque undo snapshot under the project snapshot namespace."""
        return self.store.write_bytes(self.layout.snapshot(name), data)

    def read_snapshot(self, name: str) -> bytes:
        return self.store.read_bytes(self.layout.snapshot(name))

    def snapshot_exists(self, name: str) -> bool:
        info = self.store.stat(self.layout.snapshot(name))
        return bool(info and info.kind == FileKind.FILE)

    def write_job_json(self, job_id: str, document: dict) -> FileInfo:
        return self.store.write_bytes(
            self.layout.job(job_id, "json"),
            json.dumps(document, indent=2).encode("utf-8"),
        )

    def read_job_json(self, job_id: str) -> dict:
        return json.loads(self.store.read_bytes(self.layout.job(job_id, "json")).decode("utf-8"))

    def write_job_log(self, job_id: str, content: str) -> FileInfo:
        return self.store.write_bytes(
            self.layout.job(job_id, "log"),
            content.encode("utf-8", errors="replace"),
        )

    def read_job_log(self, job_id: str) -> str:
        return self.store.read_bytes(self.layout.job(job_id, "log")).decode(
            "utf-8", errors="replace"
        )

    def write_artifact(self, name: str, data: bytes) -> FileInfo:
        return self.store.write_bytes(self.layout.artifact(name), data)

    def read_artifact(self, name: str) -> bytes:
        return self.store.read_bytes(self.layout.artifact(name))

    def artifact_exists(self, name: str) -> bool:
        info = self.store.stat(self.layout.artifact(name))
        return bool(info and info.kind == FileKind.FILE)

    def copy_tree(self, source: TreeRef, target: TreeRef) -> None:
        self.store.copy(self.layout.tree(source), self.layout.tree(target))

    def replace_tree(self, tree: TreeRef, entries: Iterable[tuple[str, bytes]]) -> list[str]:
        target = self.layout.tree(tree)
        staged = self.layout.project.child(".staging", uuid.uuid4().hex)
        written: list[str] = []
        self.store.ensure_prefix(staged)
        try:
            for rel_path, data in entries:
                key = staged.child(rel_path)
                if key == staged:
                    continue
                self.store.write_bytes(key, data)
                written.append(key.relative_to(staged))
            self.store.replace_prefix(target, staged)
        except Exception:
            self.store.delete(staged, recursive=True)
            raise
        return sorted(written)

    def load_project_meta(self) -> dict:
        info = self.store.stat(self.layout.meta)
        if info is None:
            return default_project_meta(self.scope.project_id)
        raw = self.store.read_bytes(self.layout.meta)
        if not raw.strip():
            return default_project_meta(self.scope.project_id)
        return json.loads(raw.decode("utf-8"))

    def save_project_meta(self, meta: dict) -> None:
        meta = {**meta, "updated_at": datetime.now(timezone.utc).isoformat()}
        data = json.dumps(meta, indent=2).encode("utf-8")
        self.store.write_bytes(self.layout.meta, data)

    def mutate_project_meta(
        self,
        mutator: Callable[[dict], dict | None],
        *,
        retries: int = 64,
    ) -> dict:
        for attempt in range(retries):
            info = self.store.stat(self.layout.meta)
            if info is None:
                meta = default_project_meta(self.scope.project_id)
                expected = MISSING_VERSION
            else:
                meta = self.load_project_meta()
                expected = info.version
            result = mutator(meta)
            if isinstance(result, dict):
                meta = result
            meta["updated_at"] = datetime.now(timezone.utc).isoformat()
            data = json.dumps(meta, indent=2).encode("utf-8")
            try:
                self.store.write_bytes(self.layout.meta, data, expected=expected)
                return meta
            except StorageConflict:
                if attempt + 1 >= retries:
                    raise
                time.sleep(min(0.0005 * (attempt + 1), 0.01))
        raise StorageConflict("metadata update retries exhausted")  # pragma: no cover

    def load_zone_meta(self, zone_id: str) -> dict:
        key = self.layout.zone_meta(zone_id)
        if self.store.stat(key) is None:
            raise StorageNotFound(f"zone not found: {zone_id}")
        return json.loads(self.store.read_bytes(key).decode("utf-8"))

    def save_zone_meta(self, zone_id: str, meta: dict) -> None:
        self.ensure_zone(zone_id)
        self.store.write_bytes(
            self.layout.zone_meta(zone_id),
            json.dumps(meta, indent=2, ensure_ascii=False).encode("utf-8"),
        )

    def file_sha256(self, content: str) -> str:
        return text_sha256(content)

    def local_path(self, key) -> Path:
        method = getattr(self.store, "local_path", None)
        if method is None:
            raise TypeError("configured storage provider has no local path capability")
        return method(key)
