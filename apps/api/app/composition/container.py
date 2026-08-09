"""Explicit service and storage composition for standalone or host embedding."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from app.core.config import Settings
from app.integrations.ports import CompileExecutor, GitBackend
from app.services.agent_service import AgentService
from app.services.compare_service import CompareService
from app.services.compile_service import CompileService
from app.services.git_service import GitService
from app.services.project_service import ProjectService
from app.services.zone_service import ZoneService
from app.storage.factory import ProjectStorageFactory


@dataclass
class AppContainer:
    settings: Settings
    storage: ProjectStorageFactory
    git_backend: GitBackend | None = None
    compile_executor: CompileExecutor | None = None
    projects: ProjectService = field(init=False)
    compiler: CompileService = field(init=False)
    comparer: CompareService = field(init=False)
    git: GitService = field(init=False)
    zones: ZoneService = field(init=False)
    agent: AgentService = field(init=False)

    def __post_init__(self) -> None:
        self.git = GitService(self.settings, self.storage, backend=self.git_backend)
        self.projects = ProjectService(
            self.settings,
            self.storage,
            git_service=self.git,
        )
        self.compiler = CompileService(
            self.settings,
            self.storage,
            executor=self.compile_executor,
        )
        self.comparer = CompareService(self.settings, self.storage)
        self.zones = ZoneService(self.settings, self.storage)
        self.agent = AgentService(self.settings, self.storage)

    @classmethod
    def local(cls, settings: Settings) -> AppContainer:
        return cls(
            settings=settings,
            storage=ProjectStorageFactory.local(settings.workspace_root),
        )


_containers: dict[tuple[str, str], AppContainer] = {}
_containers_guard = threading.Lock()


def default_container(settings: Settings) -> AppContainer:
    """Reuse a local container while preserving tests that vary env per request."""
    key = (str(settings.workspace_root.expanduser().absolute()), settings.model_dump_json())
    with _containers_guard:
        if key not in _containers:
            _containers[key] = AppContainer.local(settings)
        return _containers[key]
