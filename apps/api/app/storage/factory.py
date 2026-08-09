"""Project-scoped storage factories for standalone and host-provided stores."""

from __future__ import annotations

from pathlib import Path

from app.storage.adapters.local import LocalFileStore
from app.storage.ports import FileStore
from app.storage.project_store import ProjectStorage
from app.storage.types import FileKind, StorageKey, StorageScope, validate_segment


class ProjectStorageFactory:
    """Bind project ids to one provider already scoped to a host namespace."""

    def __init__(self, store: FileStore, *, namespace: str = "default"):
        self.store = store
        self.namespace = validate_segment(namespace, label="namespace")

    @classmethod
    def local(
        cls,
        root: str | Path,
        *,
        namespace: str = "default",
    ) -> ProjectStorageFactory:
        return cls(LocalFileStore(root), namespace=namespace)

    def for_project(self, project_id: str) -> ProjectStorage:
        return ProjectStorage(
            self.store,
            StorageScope(namespace=self.namespace, project_id=project_id),
        )

    def list_project_ids(self) -> list[str]:
        """Discover projects by their metadata object, independent of provider layout APIs."""
        project_ids: set[str] = set()
        prefix = (
            StorageKey.root()
            if self.namespace == "default"
            else StorageKey(self.namespace)
        )
        for info in self.store.list(prefix, recursive=True):
            if info.kind != FileKind.FILE or info.key.name != "meta.json":
                continue
            parts = info.key.relative_to(prefix).split("/")
            if len(parts) != 2:
                continue
            try:
                project_ids.add(validate_segment(parts[0], label="project id"))
            except ValueError:
                continue
        return sorted(project_ids)
