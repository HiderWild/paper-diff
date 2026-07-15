"""SSE events stream heartbeats and compile status when job finishes."""

from __future__ import annotations

import io
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


def test_events_stream_has_event_lines(client: TestClient):
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
    job_id = client.post(f"/api/v1/projects/{pid}/compile", json={}).json()["job_id"]
    with client.stream(
        "GET", f"/api/v1/projects/{pid}/events", params={"job_id": job_id}
    ) as resp:
        assert resp.status_code == 200
        # read a chunk
        chunks = []
        for line in resp.iter_lines():
            chunks.append(line)
            if len(chunks) > 20:
                break
    text = "\n".join(chunks)
    assert "event:" in text or "data:" in text
