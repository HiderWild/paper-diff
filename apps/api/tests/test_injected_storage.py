"""Host embedding can run core project APIs without a local filesystem."""

from __future__ import annotations

import io
import zipfile

from fastapi.testclient import TestClient

from app.composition.container import AppContainer
from app.core.config import Settings
from app.main import create_app
from app.storage.adapters.memory import MemoryFileStore
from app.storage.factory import ProjectStorageFactory


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for path, data in files.items():
            archive.writestr(path, data)
    return output.getvalue()


def test_injected_memory_store_runs_project_and_zone_main_path(tmp_path):
    settings = Settings(workspace_root=tmp_path / "unused", agent_provider="stub")
    factory = ProjectStorageFactory(MemoryFileStore(), namespace="host-tenant")
    client = TestClient(create_app(AppContainer(settings=settings, storage=factory)))

    created = client.post("/api/v1/projects")
    assert created.status_code == 200
    project_id = created.json()["id"]

    imported = client.post(
        f"/api/v1/projects/{project_id}/work/import/zip",
        files={
            "work": (
                "paper.zip",
                _zip_bytes({"main.tex": b"\\documentclass{article}\nhello\n"}),
                "application/zip",
            )
        },
    )
    assert imported.status_code == 200
    assert client.get(f"/api/v1/projects/{project_id}/work/tree").json()["files"] == [
        "main.tex"
    ]

    saved = client.put(
        f"/api/v1/projects/{project_id}/work/file",
        params={"path": "main.tex"},
        json={"content": "updated\n"},
    )
    assert saved.status_code == 200
    assert saved.json()["revision"] == 1

    zone = client.post(
        f"/api/v1/projects/{project_id}/zones",
        json={"name": "host proposal", "source": "host"},
    ).json()
    zone_id = zone["id"]
    zone_import = client.post(
        f"/api/v1/projects/{project_id}/zones/{zone_id}/import/zip",
        files={
            "file": (
                "proposal.zip",
                _zip_bytes({"main.tex": b"proposed\n"}),
                "application/zip",
            )
        },
    )
    assert zone_import.status_code == 200
    assert client.get(
        f"/api/v1/projects/{project_id}/zones/{zone_id}/file",
        params={"path": "main.tex"},
    ).json()["content"] == "proposed\n"

    restored = client.get("/api/v1/projects").json()["projects"]
    assert [item["id"] for item in restored] == [project_id]
    assert all(
        info.key.value.startswith(f"host-tenant/{project_id}/")
        for info in factory.store.list(factory.for_project(project_id).layout.project)
        if info.kind.value == "file"
    )
    unavailable_git = client.get(f"/api/v1/projects/{project_id}/git/status")
    assert unavailable_git.status_code == 501
    assert unavailable_git.json()["error"]["code"] == "STORAGE_CAPABILITY_UNAVAILABLE"
    unavailable_compile = client.post(f"/api/v1/projects/{project_id}/compile", json={})
    assert unavailable_compile.status_code == 501


def test_host_can_inject_git_and_compile_capabilities(tmp_path):
    class HostGit:
        def ensure_repo(self, project_id):
            return project_id

        def commit(self, project_id, message, **kwargs):
            return {"committed": True, "project_id": project_id, "message": message}

        def status(self, project_id):
            return {"mode": "host", "project_id": project_id, "dirty": False}

    class HostCompile:
        def start_compile(self, project_id, **kwargs):
            return {"job_id": "host-job", "status": "queued", "project_id": project_id}

    settings = Settings(workspace_root=tmp_path / "unused")
    factory = ProjectStorageFactory(MemoryFileStore(), namespace="host")
    container = AppContainer(
        settings=settings,
        storage=factory,
        git_backend=HostGit(),
        compile_executor=HostCompile(),
    )
    client = TestClient(create_app(container))
    project_id = client.post("/api/v1/projects").json()["id"]

    assert client.get(f"/api/v1/projects/{project_id}/git/status").json()["mode"] == "host"
    compile_response = client.post(f"/api/v1/projects/{project_id}/compile", json={})
    assert compile_response.status_code == 200
    assert compile_response.json()["job_id"] == "host-job"


def test_request_scoped_container_resolver_isolates_tenants(tmp_path):
    settings = Settings(workspace_root=tmp_path / "unused")
    store = MemoryFileStore()
    containers: dict[str, AppContainer] = {}

    def resolve(request):
        tenant = request.headers.get("x-tenant", "anonymous")
        if tenant not in containers:
            containers[tenant] = AppContainer(
                settings=settings,
                storage=ProjectStorageFactory(store, namespace=tenant),
            )
        return containers[tenant]

    client = TestClient(create_app(container_resolver=resolve))
    created = client.post("/api/v1/projects", headers={"x-tenant": "tenant-a"})
    assert created.status_code == 200

    tenant_a = client.get("/api/v1/projects", headers={"x-tenant": "tenant-a"}).json()
    tenant_b = client.get("/api/v1/projects", headers={"x-tenant": "tenant-b"}).json()
    assert len(tenant_a["projects"]) == 1
    assert tenant_b["projects"] == []
