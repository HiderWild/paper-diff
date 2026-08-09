"""Synchronous file-store ports used by current services and workers."""

from __future__ import annotations

from collections.abc import Iterable
from typing import BinaryIO, Protocol, runtime_checkable

from app.storage.types import FileInfo, StorageCapabilities, StorageKey


@runtime_checkable
class FileStore(Protocol):
    capabilities: StorageCapabilities

    def ensure_prefix(self, prefix: StorageKey) -> None: ...

    def stat(self, key: StorageKey) -> FileInfo | None: ...

    def list(self, prefix: StorageKey, *, recursive: bool = True) -> Iterable[FileInfo]: ...

    def open_read(self, key: StorageKey) -> BinaryIO: ...

    def read_bytes(self, key: StorageKey) -> bytes: ...

    def write_stream(
        self,
        key: StorageKey,
        source: BinaryIO,
        *,
        expected: str | None = None,
    ) -> FileInfo: ...

    def write_bytes(
        self,
        key: StorageKey,
        data: bytes,
        *,
        expected: str | None = None,
    ) -> FileInfo: ...

    def delete(self, key: StorageKey, *, recursive: bool = False) -> None: ...

    def copy(self, source: StorageKey, target: StorageKey) -> None: ...

    def move(self, source: StorageKey, target: StorageKey) -> None: ...

    def replace_prefix(self, target: StorageKey, staged: StorageKey) -> None: ...
