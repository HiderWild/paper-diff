"""Administrative storage operations kept out of application startup code."""

from __future__ import annotations

from app.storage.adapters.local import LocalFileStore
from app.storage.errors import StorageCapabilityUnavailable
from app.storage.factory import ProjectStorageFactory
from app.storage.types import FileKind, StorageKey


class StorageAdmin:
    def __init__(self, factory: ProjectStorageFactory):
        self.factory = factory

    def _namespace_prefix(self) -> StorageKey:
        if self.factory.namespace == "default":
            return StorageKey.root()
        return StorageKey(self.factory.namespace)

    def _assert_safe_local_root(self) -> None:
        store = self.factory.store
        if not isinstance(store, LocalFileStore):
            return
        root = store.root
        name = root.name.lower()
        recognized = name in ("projects", "workspace", "workspaces", "data")
        recognizable_path = "paper-diff" in str(root).lower() or "paper_diff" in str(root).lower()
        if self.factory.namespace == "default" and not recognized and not recognizable_path:
            raise StorageCapabilityUnavailable(
                f"refusing to clear unrecognized local workspace root: {root}"
            )

    def clear_namespace(self) -> int:
        """Clear only the factory namespace, never the provider root implicitly."""
        self._assert_safe_local_root()
        prefix = self._namespace_prefix()
        if not prefix.is_root:
            existed = self.factory.store.stat(prefix) is not None
            self.factory.store.delete(prefix, recursive=True)
            self.factory.store.ensure_prefix(prefix)
            return 1 if existed else 0

        entries = list(self.factory.store.list(prefix, recursive=False))
        for info in entries:
            self.factory.store.delete(
                info.key,
                recursive=info.kind == FileKind.PREFIX,
            )
        return len(entries)
