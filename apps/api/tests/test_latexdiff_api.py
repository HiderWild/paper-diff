"""latexdiff endpoint queues a job (docker may be disabled in unit test)."""

from __future__ import annotations

import io
import time
import zipfile

import pytest
from fastapi.testclient import TestClient


def _zip_bytes(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_DIFF_WORKSPACE_ROOT", str(tmp_path / "ws"))
    monkeypatch.setenv("PAPER_DIFF_DOCKER_ENABLED", "false")
    from app.main import app

    return TestClient(app)


def test_latexdiff_endpoint_queues(client: TestClient):
    pid = client.post("/api/v1/projects").json()["id"]
    z = _zip_bytes(
        {"main.tex": "\\documentclass{article}\\begin{document}Hi\\end{document}\n"}
    )
    client.post(
        f"/api/v1/projects/{pid}/versions/upload",
        files={
            "base": ("b.zip", z, "application/zip"),
            "revised": ("r.zip", z, "application/zip"),
        },
    )
    client.post(f"/api/v1/projects/{pid}/root", json={"root_file": "main.tex"})
    r = client.post(f"/api/v1/projects/{pid}/compile/latexdiff", json={})
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    deadline = time.time() + 5
    status = "queued"
    while time.time() < deadline:
        status = client.get(f"/api/v1/projects/{pid}/compile/{job_id}").json()["status"]
        if status in ("succeeded", "failed"):
            break
        time.sleep(0.05)
    assert status == "failed"  # docker disabled
