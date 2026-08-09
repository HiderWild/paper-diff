"""Provider-neutral storage value objects."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from app.storage.errors import InvalidStorageKey

_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
MISSING_VERSION = "__paper_diff_missing__"


def validate_segment(value: str, *, label: str = "segment") -> str:
    """Validate a single logical path segment such as a project or zone id."""
    text = str(value or "")
    if (
        not text
        or text in (".", "..")
        or "/" in text
        or "\\" in text
        or "\x00" in text
        or any(ord(ch) < 32 for ch in text)
    ):
        raise InvalidStorageKey(f"invalid {label}")
    return text


@dataclass(frozen=True, order=True)
class StorageKey:
    """Normalized POSIX-relative provider key.

    The empty value is reserved for the provider root prefix. File operations
    must use a non-root key; list/stat may use ``StorageKey.root()``.
    """

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", self._normalize(self.value))

    @staticmethod
    def _normalize(value: str) -> str:
        raw = str(value or "")
        if "\x00" in raw or any(ord(ch) < 32 for ch in raw):
            raise InvalidStorageKey("storage key contains control characters")
        raw = raw.replace("\\", "/")
        if raw.startswith("/") or _WINDOWS_DRIVE.match(raw):
            raise InvalidStorageKey("absolute storage key is not allowed")
        parts: list[str] = []
        for part in raw.split("/"):
            if not part or part == ".":
                continue
            if part == "..":
                raise InvalidStorageKey("storage key traversal is not allowed")
            parts.append(part)
        return "/".join(parts)

    @classmethod
    def root(cls) -> StorageKey:
        return cls("")

    @property
    def is_root(self) -> bool:
        return not self.value

    @property
    def name(self) -> str:
        return self.value.rsplit("/", 1)[-1] if self.value else ""

    @property
    def parent(self) -> StorageKey:
        if not self.value or "/" not in self.value:
            return StorageKey.root()
        return StorageKey(self.value.rsplit("/", 1)[0])

    def child(self, *parts: str) -> StorageKey:
        suffix = "/".join(str(part) for part in parts if str(part))
        if not suffix:
            return self
        return StorageKey(f"{self.value}/{suffix}" if self.value else suffix)

    def relative_to(self, prefix: StorageKey) -> str:
        if prefix.is_root:
            return self.value
        if self.value == prefix.value:
            return ""
        marker = prefix.value + "/"
        if not self.value.startswith(marker):
            raise InvalidStorageKey("key is outside prefix")
        return self.value[len(marker) :]


@dataclass(frozen=True)
class StorageScope:
    namespace: str
    project_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "namespace",
            validate_segment(self.namespace, label="namespace"),
        )
        object.__setattr__(
            self,
            "project_id",
            validate_segment(self.project_id, label="project id"),
        )


class FileKind(str, Enum):
    FILE = "file"
    PREFIX = "prefix"


@dataclass(frozen=True)
class FileInfo:
    key: StorageKey
    kind: FileKind
    size: int | None = None
    modified_at: datetime | None = None
    version: str | None = None


@dataclass(frozen=True)
class StorageCapabilities:
    conditional_write: bool = True
    atomic_write: bool = True
    native_copy: bool = True
    native_move: bool = True
    atomic_replace_prefix: bool = True
    materialization: bool = False


class TreeKind(str, Enum):
    WORK = "work"
    BASE = "base"
    REVISED = "revised"
    ZONE = "zone"


@dataclass(frozen=True)
class TreeRef:
    kind: TreeKind
    zone_id: str | None = None

    def __post_init__(self) -> None:
        if self.kind == TreeKind.ZONE:
            if self.zone_id is None:
                raise InvalidStorageKey("zone tree requires a zone id")
            validate_segment(self.zone_id, label="zone id")
        elif self.zone_id is not None:
            raise InvalidStorageKey("zone id is only valid for a zone tree")

    @classmethod
    def work(cls) -> TreeRef:
        return cls(TreeKind.WORK)

    @classmethod
    def base(cls) -> TreeRef:
        return cls(TreeKind.BASE)

    @classmethod
    def revised(cls) -> TreeRef:
        return cls(TreeKind.REVISED)

    @classmethod
    def zone(cls, zone_id: str) -> TreeRef:
        return cls(TreeKind.ZONE, zone_id)
