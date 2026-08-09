"""Local filesystem implementation of the provider-neutral FileStore port."""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import tempfile
import threading
import uuid
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

from app.storage.errors import (
    InvalidStorageKey,
    StorageConflict,
    StorageNotFound,
)
from app.storage.types import (
    MISSING_VERSION,
    FileInfo,
    FileKind,
    StorageCapabilities,
    StorageKey,
)

_locks_guard = threading.Lock()
_key_locks: dict[str, threading.RLock] = {}


def _lock_for(root: Path, key: StorageKey) -> threading.RLock:
    lock_key = f"{root}:{key.value}"
    with _locks_guard:
        return _key_locks.setdefault(lock_key, threading.RLock())


class LocalFileStore:
    """FileStore rooted at one resolved local directory.

    All physical path construction lives here. Logical callers never need to
    join or resolve a path themselves.
    """

    capabilities = StorageCapabilities(materialization=True)

    def __init__(self, root: str | Path, *, create: bool = True):
        raw_root = Path(root).expanduser()
        if create:
            raw_root.mkdir(parents=True, exist_ok=True)
        self.root = raw_root.resolve()
        if not self.root.is_dir():
            raise StorageNotFound("local storage root does not exist")

    def _candidate(self, key: StorageKey) -> Path:
        if key.is_root:
            return self.root
        return self.root.joinpath(*key.value.split("/"))

    def _assert_no_symlink(self, key: StorageKey) -> None:
        current = self.root
        for part in key.value.split("/") if key.value else ():
            current = current / part
            if current.is_symlink():
                raise InvalidStorageKey("symbolic links are not allowed in storage keys")
            if not current.exists():
                break

    def local_path(self, key: StorageKey) -> Path:
        self._assert_no_symlink(key)
        candidate = self._candidate(key)
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise InvalidStorageKey("storage key escapes local root") from exc
        return resolved

    def key_from_path(self, path: str | Path) -> StorageKey:
        candidate = Path(os.path.abspath(path))
        try:
            rel = candidate.relative_to(self.root)
        except ValueError as exc:
            raise InvalidStorageKey("local path is outside storage root") from exc
        key = StorageKey(rel.as_posix() if rel.as_posix() != "." else "")
        self._assert_no_symlink(key)
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise InvalidStorageKey("local path escapes storage root") from exc
        return key

    @staticmethod
    def _version(path: Path) -> str:
        stat = path.stat()
        return f"{stat.st_ino}:{stat.st_size}:{stat.st_mtime_ns}"

    def ensure_prefix(self, prefix: StorageKey) -> None:
        self.local_path(prefix).mkdir(parents=True, exist_ok=True)

    def stat(self, key: StorageKey) -> FileInfo | None:
        path = self.local_path(key)
        if not path.exists():
            return None
        stat = path.stat()
        return FileInfo(
            key=key,
            kind=FileKind.PREFIX if path.is_dir() else FileKind.FILE,
            size=None if path.is_dir() else stat.st_size,
            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            version=None if path.is_dir() else self._version(path),
        )

    def list(self, prefix: StorageKey, *, recursive: bool = True) -> Iterable[FileInfo]:
        base = self.local_path(prefix)
        if not base.exists():
            return []
        if base.is_file():
            info = self.stat(prefix)
            return [info] if info is not None else []
        iterator = base.rglob("*") if recursive else base.iterdir()
        infos: list[FileInfo] = []
        for path in iterator:
            key = self.key_from_path(path)
            info = self.stat(key)
            if info is not None:
                infos.append(info)
        return sorted(infos, key=lambda item: item.key.value)

    def open_read(self, key: StorageKey) -> BinaryIO:
        path = self.local_path(key)
        if not path.is_file():
            raise StorageNotFound(f"storage object not found: {key.value}")
        return path.open("rb")

    def read_bytes(self, key: StorageKey) -> bytes:
        with self.open_read(key) as source:
            return source.read()

    def _check_expected(self, key: StorageKey, expected: str | None) -> None:
        if expected is None:
            return
        current = self.stat(key)
        if expected == MISSING_VERSION:
            if current is not None:
                raise StorageConflict(f"storage object already exists: {key.value}")
            return
        if current is None or current.version != expected:
            raise StorageConflict(f"storage object version changed: {key.value}")

    def write_stream(
        self,
        key: StorageKey,
        source: BinaryIO,
        *,
        expected: str | None = None,
    ) -> FileInfo:
        if key.is_root:
            raise InvalidStorageKey("cannot write the provider root")
        target = self.local_path(key)
        lock = _lock_for(self.root, key)
        with lock:
            self._check_expected(key, expected)
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(
                prefix=f".{target.name}.",
                suffix=".tmp",
                dir=str(target.parent),
            )
            try:
                with os.fdopen(fd, "wb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(tmp_name, target)
            except Exception:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
                raise
        info = self.stat(key)
        if info is None:  # pragma: no cover - defensive after successful replace
            raise StorageNotFound(f"storage write disappeared: {key.value}")
        return info

    def write_bytes(
        self,
        key: StorageKey,
        data: bytes,
        *,
        expected: str | None = None,
    ) -> FileInfo:
        return self.write_stream(key, io.BytesIO(data), expected=expected)

    def delete(self, key: StorageKey, *, recursive: bool = False) -> None:
        if key.is_root:
            raise InvalidStorageKey("cannot delete the provider root")
        path = self.local_path(key)
        if not path.exists():
            return
        if path.is_dir():
            if not recursive:
                try:
                    path.rmdir()
                except OSError as exc:
                    raise StorageConflict("prefix is not empty") from exc
            else:
                shutil.rmtree(path)
        else:
            path.unlink()

    def copy(self, source: StorageKey, target: StorageKey) -> None:
        if source.is_root or target.is_root:
            raise InvalidStorageKey("root copy is not allowed")
        source_path = self.local_path(source)
        if not source_path.exists():
            raise StorageNotFound(f"storage object not found: {source.value}")
        if source_path.is_file():
            with source_path.open("rb") as stream:
                self.write_stream(target, stream)
            return

        stage = target.parent.child(f".{target.name}.copy-{uuid.uuid4().hex}")
        stage_path = self.local_path(stage)
        stage_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            # Enumerating first rejects symbolic links anywhere in the source.
            list(self.list(source, recursive=True))
            shutil.copytree(source_path, stage_path)
            self.replace_prefix(target, stage)
        except Exception:
            if stage_path.exists():
                shutil.rmtree(stage_path)
            raise

    def move(self, source: StorageKey, target: StorageKey) -> None:
        if source.is_root or target.is_root:
            raise InvalidStorageKey("root move is not allowed")
        source_path = self.local_path(source)
        if not source_path.exists():
            raise StorageNotFound(f"storage object not found: {source.value}")
        if source_path.is_dir():
            self.replace_prefix(target, source)
            return
        target_path = self.local_path(target)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source_path, target_path)

    def replace_prefix(self, target: StorageKey, staged: StorageKey) -> None:
        if target.is_root or staged.is_root or target == staged:
            raise InvalidStorageKey("invalid prefix replacement")
        target_path = self.local_path(target)
        staged_path = self.local_path(staged)
        if not staged_path.is_dir():
            raise StorageNotFound(f"staged prefix not found: {staged.value}")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(target.value.encode("utf-8")).hexdigest()[:12]
        backup = target_path.parent / f".{target_path.name}.backup-{digest}-{uuid.uuid4().hex}"
        had_target = target_path.exists()
        try:
            if had_target:
                os.replace(target_path, backup)
            os.replace(staged_path, target_path)
        except Exception:
            if had_target and backup.exists() and not target_path.exists():
                os.replace(backup, target_path)
            raise
        else:
            if backup.exists():
                if backup.is_dir():
                    shutil.rmtree(backup)
                else:
                    backup.unlink()
