"""In-memory FileStore for contract tests and host-integration fakes."""

from __future__ import annotations

import io
import threading
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import BinaryIO

from app.storage.errors import InvalidStorageKey, StorageConflict, StorageNotFound
from app.storage.types import (
    MISSING_VERSION,
    FileInfo,
    FileKind,
    StorageCapabilities,
    StorageKey,
)


class MemoryFileStore:
    capabilities = StorageCapabilities(materialization=False)

    def __init__(self):
        self._files: dict[str, bytes] = {}
        self._versions: dict[str, int] = {}
        self._modified: dict[str, datetime] = {}
        self._prefixes: set[str] = {""}
        self._counter = 0
        self._lock = threading.RLock()

    @staticmethod
    def _under(value: str, prefix: str) -> bool:
        return not prefix or value == prefix or value.startswith(prefix + "/")

    def _add_parents(self, key: StorageKey) -> None:
        parent = key.parent
        while True:
            self._prefixes.add(parent.value)
            if parent.is_root:
                break
            parent = parent.parent

    def ensure_prefix(self, prefix: StorageKey) -> None:
        with self._lock:
            self._add_parents(prefix.child("_placeholder"))
            self._prefixes.add(prefix.value)

    def stat(self, key: StorageKey) -> FileInfo | None:
        with self._lock:
            if key.value in self._files:
                return FileInfo(
                    key=key,
                    kind=FileKind.FILE,
                    size=len(self._files[key.value]),
                    modified_at=self._modified[key.value],
                    version=str(self._versions[key.value]),
                )
            if key.value in self._prefixes or any(
                self._under(value, key.value) for value in self._files
            ):
                return FileInfo(key=key, kind=FileKind.PREFIX)
            return None

    def list(self, prefix: StorageKey, *, recursive: bool = True) -> Iterable[FileInfo]:
        with self._lock:
            keys: set[str] = set()
            for value in self._files:
                if not self._under(value, prefix.value) or value == prefix.value:
                    continue
                rel = StorageKey(value).relative_to(prefix)
                if recursive or "/" not in rel:
                    keys.add(value)
                elif rel:
                    keys.add(prefix.child(rel.split("/", 1)[0]).value)
            for value in self._prefixes:
                if not value or not self._under(value, prefix.value) or value == prefix.value:
                    continue
                rel = StorageKey(value).relative_to(prefix)
                if recursive or "/" not in rel:
                    keys.add(value)
                elif rel:
                    keys.add(prefix.child(rel.split("/", 1)[0]).value)
            return [self.stat(StorageKey(value)) for value in sorted(keys) if self.stat(StorageKey(value))]

    def open_read(self, key: StorageKey) -> BinaryIO:
        with self._lock:
            if key.value not in self._files:
                raise StorageNotFound(f"storage object not found: {key.value}")
            return io.BytesIO(self._files[key.value])

    def read_bytes(self, key: StorageKey) -> bytes:
        with self.open_read(key) as source:
            return source.read()

    def _check_expected(self, key: StorageKey, expected: str | None) -> None:
        current = self.stat(key)
        if expected is None:
            return
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
        data = source.read()
        with self._lock:
            self._check_expected(key, expected)
            self._counter += 1
            self._files[key.value] = bytes(data)
            self._versions[key.value] = self._counter
            self._modified[key.value] = datetime.now(timezone.utc)
            self._add_parents(key)
            info = self.stat(key)
            assert info is not None
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
        with self._lock:
            if key.value in self._files:
                self._files.pop(key.value, None)
                self._versions.pop(key.value, None)
                self._modified.pop(key.value, None)
                return
            descendants = [value for value in self._files if self._under(value, key.value)]
            if descendants and not recursive:
                raise StorageConflict("prefix is not empty")
            for value in descendants:
                self._files.pop(value, None)
                self._versions.pop(value, None)
                self._modified.pop(value, None)
            self._prefixes = {
                value for value in self._prefixes if not self._under(value, key.value)
            }
            self._prefixes.add("")

    def _copy_mapping(self, source: StorageKey, target: StorageKey) -> dict[str, bytes]:
        if source.value in self._files:
            return {target.value: self._files[source.value]}
        marker = source.value + "/"
        mapping = {
            target.child(value[len(marker) :]).value: data
            for value, data in self._files.items()
            if value.startswith(marker)
        }
        if not mapping and self.stat(source) is None:
            raise StorageNotFound(f"storage object not found: {source.value}")
        return mapping

    def copy(self, source: StorageKey, target: StorageKey) -> None:
        if source.is_root or target.is_root:
            raise InvalidStorageKey("root copy is not allowed")
        with self._lock:
            mapping = self._copy_mapping(source, target)
            if self.stat(source) and self.stat(source).kind == FileKind.PREFIX:
                self.delete(target, recursive=True)
                self.ensure_prefix(target)
            for key, data in mapping.items():
                self.write_bytes(StorageKey(key), data)

    def move(self, source: StorageKey, target: StorageKey) -> None:
        with self._lock:
            self.copy(source, target)
            self.delete(source, recursive=True)

    def replace_prefix(self, target: StorageKey, staged: StorageKey) -> None:
        if target.is_root or staged.is_root or target == staged:
            raise InvalidStorageKey("invalid prefix replacement")
        with self._lock:
            if self.stat(staged) is None or self.stat(staged).kind != FileKind.PREFIX:
                raise StorageNotFound(f"staged prefix not found: {staged.value}")
            mapping = self._copy_mapping(staged, target)
            self.delete(target, recursive=True)
            self.ensure_prefix(target)
            for key, data in mapping.items():
                self.write_bytes(StorageKey(key), data)
            self.delete(staged, recursive=True)
