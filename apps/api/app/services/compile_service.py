"""Compile capability facade; process and local-path access live in integrations."""

from __future__ import annotations

from app.core.config import Settings
from app.core.errors import AppError
from app.integrations.compile_executor import (
    LocalCompileExecutor,
    subscribe_events,
    unsubscribe_events,
)
from app.integrations.ports import CompileExecutor
from app.storage.factory import ProjectStorageFactory

__all__ = ["CompileService", "subscribe_events", "unsubscribe_events"]


class CompileService:
    def __init__(
        self,
        settings: Settings,
        storage: ProjectStorageFactory,
        executor: CompileExecutor | None = None,
    ):
        self.settings = settings
        self.storage = storage
        self._requires_local_materialization = executor is None
        self.executor = executor or LocalCompileExecutor(settings, self.storage)

    def __getattr__(self, name: str):
        target = getattr(self.executor, name)
        if not callable(target):
            return target

        def invoke(*args, **kwargs):
            if (
                self._requires_local_materialization
                and not self.storage.store.capabilities.materialization
            ):
                raise AppError(
                    "STORAGE_CAPABILITY_UNAVAILABLE",
                    "Compile requires a storage provider with local materialization support",
                    status_code=501,
                )
            return target(*args, **kwargs)

        return invoke
