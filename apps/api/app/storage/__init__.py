"""Unified file access ports and paper-diff storage facades."""

from app.storage.project_store import ProjectStorage
from app.storage.types import StorageKey, StorageScope, TreeRef

__all__ = ["ProjectStorage", "StorageKey", "StorageScope", "TreeRef"]
