"""Optional Docker compile smoke test — skipped when image missing."""

from __future__ import annotations

import io
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[3]
FIXTURE_BASE = REPO / "fixtures" / "sample" / "base"
IMAGE = "paper-diff-texlive:latest"


def _docker_image_ok() -> bool:
    if shutil.which("docker") is None:
        return False
    r = subprocess.run(
        ["docker", "image", "inspect", IMAGE],
        capture_output=True,
    )
    return r.returncode == 0


def _zip_dir(root: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for p in root.rglob("*"):
            if p.is_file():
                zf.write(p, p.relative_to(root).as_posix())
    return buf.getvalue()


@pytest.mark.skipif(not _docker_image_ok(), reason="paper-diff-texlive image not built")
def test_compile_fixture_via_api(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_DIFF_WORKSPACE_ROOT", str(tmp_path / "ws"))
    monkeypatch.setenv("PAPER_DIFF_TEX_IMAGE", IMAGE)
    monkeypatch.setenv("PAPER_DIFF_DOCKER_ENABLED", "true")
    from app.main import app

    client = TestClient(app)
    pid = client.post("/api/v1/projects").json()["id"]
    z = _zip_dir(FIXTURE_BASE)
    # use same tree as both versions so merge is clean
    r = client.post(
        f"/api/v1/projects/{pid}/versions/upload",
        files={
            "base": ("b.zip", z, "application/zip"),
            "revised": ("r.zip", z, "application/zip"),
        },
    )
    assert r.status_code == 200, r.text
    comp = client.post(f"/api/v1/projects/{pid}/compile", json={"side": "merged"})
    assert comp.status_code == 200, comp.text
    body = comp.json()
    job_id = body["job_id"]
    job = client.get(f"/api/v1/projects/{pid}/compile/{job_id}").json()
    if job["status"] != "succeeded":
        log = client.get(f"/api/v1/projects/{pid}/compile/{job_id}/log")
        pytest.fail(f"compile {job['status']}: {job.get('message')}\n{log.text[:2000]}")
    pdf = client.get(f"/api/v1/projects/{pid}/artifacts/pdf", params={"job_id": job_id})
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"
