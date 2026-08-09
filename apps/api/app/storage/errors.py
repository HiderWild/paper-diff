"""Storage-layer errors independent from HTTP and provider SDKs."""

from __future__ import annotations


class StorageError(Exception):
    """Base class for normalized storage failures."""


class InvalidStorageKey(StorageError, ValueError):
    """A logical key is malformed or escapes its storage namespace."""


class StorageNotFound(StorageError, FileNotFoundError):
    """The requested logical object does not exist."""


class StorageConflict(StorageError):
    """A conditional write observed a different object version."""


class StorageUnavailable(StorageError):
    """The configured provider cannot currently serve the operation."""


class StorageCapabilityUnavailable(StorageError):
    """The configured provider does not implement a requested capability."""


class StorageQuotaExceeded(StorageError):
    """A provider or project storage quota was exceeded."""


class InvalidArchive(StorageError):
    """An uploaded archive is malformed or contains unsafe entries."""
