"""Provider-neutral Git facade; local process/path access lives in GitCliBackend."""

from __future__ import annotations

from app.core.config import Settings
from app.core.errors import AppError
from app.integrations.git_cli import GitCliBackend
from app.integrations.ports import GitBackend
from app.storage.adapters.local import LocalFileStore
from app.storage.factory import ProjectStorageFactory


class GitService:
    def __init__(
        self,
        settings: Settings,
        storage: ProjectStorageFactory,
        backend: GitBackend | None = None,
    ):
        self.settings = settings
        self.storage = storage
        self._requires_local_materialization = backend is None
        self._default_backend_available = isinstance(storage.store, LocalFileStore)
        self.backend = backend or GitCliBackend(settings, self.storage)

    def __getattr__(self, name: str):
        target = getattr(self.backend, name)
        if not callable(target):
            return target

        def invoke(*args, **kwargs):
            if (
                self._requires_local_materialization
                and not self._default_backend_available
            ):
                raise AppError(
                    "STORAGE_CAPABILITY_UNAVAILABLE",
                    "Git requires a storage provider with local materialization support",
                    status_code=501,
                )
            return target(*args, **kwargs)

        return invoke
